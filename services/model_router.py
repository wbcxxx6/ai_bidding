import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime

import requests

from core.db import get_db
from core.llm_providers import PROVIDERS, get_model_setting


LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = int(os.getenv("MODEL_ROUTER_TIMEOUT", "120"))
DEFAULT_RETRIES = int(os.getenv("MODEL_ROUTER_RETRIES", "1"))
TASK_TIMEOUTS = {
    "pre_analysis": 120,
    "chapter_design": 120,
    "generate_chapter": 180,
    "review": 120,
    "embedding": 60,
}


@dataclass
class ModelRoute:
    provider_code: str
    model: str
    base_url: str
    api_key: str
    timeout: int


class ModelRouterError(Exception):
    pass


def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _resolve_api_key(setting, provider):
    configured_key = (setting.get("api_key") or "").strip()
    if configured_key:
        return configured_key
    env_name = provider.get("api_key_env")
    return (os.getenv(env_name) or "").strip()


def _normalize_openai_response(data, *, route_meta=None):
    if "output" in data:
        normalized = data
    else:
        choices = []
        for item in data.get("choices", []):
            message = item.get("message") or {}
            choices.append(
                {
                    "message": {
                        "role": message.get("role", "assistant"),
                        "content": message.get("content", ""),
                    }
                }
            )
        normalized = {"output": {"choices": choices}, "raw": data}
    if route_meta:
        normalized["route"] = route_meta
    return normalized


def _safe_error(exc):
    message = str(exc)
    for secret in [
        os.getenv("DASHSCOPE_API_KEY"),
        os.getenv("ARK_API_KEY"),
        os.getenv("MOONSHOT_API_KEY"),
        os.getenv("OPENAI_API_KEY"),
        os.getenv("MIMO_API_KEY"),
        os.getenv("EMBEDDING_API_KEY"),
    ]:
        if secret:
            message = message.replace(secret, "[redacted]")
    return message[:1000]


def _first_present(*values):
    for value in values:
        if value:
            return value
    return None


class ModelRouter:
    def route_for_task(self, task_type=None, *, model=None, timeout=None):
        setting = get_model_setting()
        route_config = self._route_config(task_type)
        provider_code = _first_present(route_config.get("primary_provider"), setting.get("active_provider"), "xiaomi_mimo")
        provider = PROVIDERS.get(provider_code)
        if not provider:
            raise ModelRouterError(f"Unsupported model provider: {provider_code}")
        resolved_model = _first_present(model, route_config.get("model"), setting.get("model"), provider.get("default_model"))
        if not resolved_model:
            raise ModelRouterError(f"Model is required for provider: {provider_code}")
        api_key = _resolve_api_key(setting, provider)
        return ModelRoute(
            provider_code=provider_code,
            model=resolved_model,
            base_url=(route_config.get("base_url") or setting.get("base_url") or provider["base_url"]).rstrip("/"),
            api_key=api_key,
            timeout=int(timeout or route_config.get("timeout") or TASK_TIMEOUTS.get(task_type or "", DEFAULT_TIMEOUT)),
        )

    def fallback_routes(self, task_type=None, *, primary_provider=None, timeout=None):
        route_config = self._route_config(task_type)
        configured = route_config.get("fallback_providers") or os.getenv("MODEL_ROUTER_FALLBACK_PROVIDERS", "")
        provider_codes = [item.strip() for item in configured.split(",") if item.strip()] if isinstance(configured, str) else configured
        routes = []
        for provider_code in provider_codes or []:
            if provider_code == primary_provider or provider_code not in PROVIDERS:
                continue
            provider = PROVIDERS[provider_code]
            api_key = _resolve_api_key({}, provider)
            if not api_key:
                continue
            routes.append(
                ModelRoute(
                    provider_code=provider_code,
                    model=route_config.get("fallback_model") or provider["default_model"],
                    base_url=(route_config.get("fallback_base_url") or provider["base_url"]).rstrip("/"),
                    api_key=api_key,
                    timeout=int(timeout or route_config.get("timeout") or DEFAULT_TIMEOUT),
                )
            )
        return routes

    def chat(
        self,
        messages,
        *,
        task_type=None,
        model=None,
        response_format=None,
        timeout=None,
        generation_task_id=None,
        project_id=None,
        retries=None,
    ):
        primary = self.route_for_task(task_type, model=model, timeout=timeout)
        routes = [primary] + self.fallback_routes(task_type, primary_provider=primary.provider_code, timeout=timeout)
        retry_count = int(retries if retries is not None else os.getenv("MODEL_ROUTER_RETRIES", DEFAULT_RETRIES))
        errors = []
        for route_index, route in enumerate(routes):
            for attempt in range(retry_count + 1):
                started = time.time()
                fallback_used = route_index > 0
                try:
                    data = self._call_route(route, messages, response_format=response_format)
                    latency_ms = int((time.time() - started) * 1000)
                    self._log_call(
                        route=route,
                        task_type=task_type,
                        project_id=project_id,
                        generation_task_id=generation_task_id,
                        latency_ms=latency_ms,
                        status="succeeded",
                        fallback_used=fallback_used,
                    )
                    return _normalize_openai_response(
                        data,
                        route_meta={
                            "task_type": task_type,
                            "provider": route.provider_code,
                            "model": route.model,
                            "fallback_used": fallback_used,
                            "attempt": attempt + 1,
                        },
                    )
                except Exception as exc:
                    latency_ms = int((time.time() - started) * 1000)
                    reason = _safe_error(exc)
                    errors.append(reason)
                    self._log_call(
                        route=route,
                        task_type=task_type,
                        project_id=project_id,
                        generation_task_id=generation_task_id,
                        latency_ms=latency_ms,
                        status="failed",
                        error_message=reason,
                        fallback_used=fallback_used,
                    )
                    LOGGER.warning(
                        "model route failed task_type=%s provider=%s model=%s attempt=%s fallback=%s reason=%s",
                        task_type,
                        route.provider_code,
                        route.model,
                        attempt + 1,
                        fallback_used,
                        reason,
                    )
        self._mark_generation_task_failed(generation_task_id, "; ".join(errors[-3:]))
        raise ModelRouterError(f"All model routes failed. degraded_reason={'; '.join(errors[-3:])}")

    def _call_route(self, route, messages, *, response_format=None):
        provider = PROVIDERS[route.provider_code]
        if not route.api_key:
            raise ModelRouterError(f"{provider['name']} API key is not set")
        payload = {"model": route.model, "messages": messages}
        if response_format:
            payload["response_format"] = response_format
        response = requests.post(
            f"{route.base_url}{provider.get('chat_path', '/chat/completions')}",
            headers={"Authorization": f"Bearer {route.api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=route.timeout,
        )
        if response.status_code != 200:
            raise ModelRouterError(f"{provider['name']} API Error: status={response.status_code}")
        return response.json()

    def _route_config(self, task_type=None):
        raw = os.getenv("MODEL_ROUTES_JSON", "")
        if not raw:
            return {}
        try:
            config = json.loads(raw)
        except json.JSONDecodeError:
            LOGGER.warning("MODEL_ROUTES_JSON is invalid; default model_settings route will be used")
            return {}
        return config.get(task_type or "default") or config.get("default") or {}

    def _log_call(
        self,
        *,
        route,
        task_type=None,
        project_id=None,
        generation_task_id=None,
        latency_ms=None,
        status,
        error_message=None,
        fallback_used=False,
    ):
        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO model_call_logs
                (tenant_id, project_id, generation_task_id, provider_code, model_name,
                 latency_ms, status, error_message, created_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    generation_task_id,
                    route.provider_code,
                    route.model,
                    latency_ms,
                    status,
                    f"task_type={task_type}; fallback_used={fallback_used}; {error_message or ''}"[:1000],
                    now(),
                ),
            )
            conn.commit()
        except Exception:
            LOGGER.exception("failed to write model_call_logs")
        finally:
            conn.close()

    def _mark_generation_task_failed(self, generation_task_id, reason):
        if not generation_task_id:
            return
        conn = get_db()
        try:
            conn.execute(
                """
                UPDATE generation_tasks
                SET error_message=?, updated_at=?
                WHERE id=? AND status='running'
                """,
                (f"ModelRouter failed: {reason}"[:1000], now(), generation_task_id),
            )
            conn.commit()
        finally:
            conn.close()


model_router = ModelRouter()
