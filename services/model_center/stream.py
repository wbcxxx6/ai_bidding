import json
import logging

import requests

from core.llm_providers import PROVIDERS
from services.model_router import ModelRouterError, _safe_error, model_router


LOGGER = logging.getLogger(__name__)


def _extract_full_content(data):
    if "output" in data:
        choices = data.get("output", {}).get("choices") or []
        if choices:
            return choices[0].get("message", {}).get("content", "")
    choices = data.get("choices") or []
    if choices:
        return choices[0].get("message", {}).get("content", "")
    return ""


def _iter_openai_sse(response):
    for raw_line in response.iter_lines(decode_unicode=False):
        if not raw_line:
            continue
        if isinstance(raw_line, bytes):
            raw_line = raw_line.decode("utf-8", errors="replace")
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            continue
        for choice in payload.get("choices") or []:
            delta = choice.get("delta") or {}
            content = delta.get("content")
            if content:
                yield content


def stream_chat_completion(messages, *, task_type="generate_chapter", project_id=None, timeout=None):
    route = model_router.route_for_task(task_type, timeout=timeout)
    provider = PROVIDERS[route.provider_code]
    if not route.api_key:
        raise ModelRouterError(f"{provider['name']} API key is not set")

    payload = {"model": route.model, "messages": messages, "stream": True}
    url = f"{route.base_url}{provider.get('chat_path', '/chat/completions')}"
    headers = {"Authorization": f"Bearer {route.api_key}", "Content-Type": "application/json"}
    try:
        with requests.post(url, headers=headers, json=payload, timeout=route.timeout, stream=True) as response:
            if response.status_code != 200:
                raise ModelRouterError(f"{provider['name']} stream API Error: status={response.status_code}")
            yielded = False
            for content in _iter_openai_sse(response):
                yielded = True
                yield content
            if yielded:
                return
    except Exception as exc:
        LOGGER.warning("stream route failed; falling back to non-stream chat: %s", _safe_error(exc))

    data = model_router.chat(
        messages,
        task_type=task_type,
        project_id=project_id,
        timeout=timeout,
    )
    content = _extract_full_content(data)
    if content:
        yield content
