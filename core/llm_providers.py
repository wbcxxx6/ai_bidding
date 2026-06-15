from datetime import datetime

from core.db import get_db


PROVIDERS = {
    "deepseek": {
        "id": "deepseek",
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "chat_path": "/chat/completions",
        "default_model": "deepseek-chat",
        "api_key_env": "DEEPSEEK_API_KEY",
        "model_hint": "\u5982 deepseek-chat\u3001deepseek-reasoner",
        "official_docs": "https://platform.deepseek.com/api-docs",
    },
    "dashscope": {
        "id": "dashscope",
        "name": "\u901a\u4e49\u5343\u95ee (Qwen)",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "chat_path": "/chat/completions",
        "default_model": "qwen-plus",
        "api_key_env": "DASHSCOPE_API_KEY",
        "model_hint": "\u5982 qwen-plus\u3001qwen-turbo\u3001qwen-max\u3001qwen-long",
        "official_docs": "https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope",
    },
    "volcengine": {
        "id": "volcengine",
        "name": "\u8c46\u5305 (\u706b\u5c71\u65b9\u821f)",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "chat_path": "/chat/completions",
        "default_model": "",
        "api_key_env": "ARK_API_KEY",
        "model_hint": "\u586b\u5199\u706b\u5c71\u65b9\u821f\u63a8\u7406\u63a5\u5165\u70b9 ID\uff08ep- \u5f00\u5934\uff09\uff0c\u5982 ep-xxxxx",
        "official_docs": "https://www.volcengine.com/docs/82379/1330626",
    },
    "xiaomi_mimo": {
        "id": "xiaomi_mimo",
        "name": "\u5c0f\u7c73 MiMo",
        "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
        "chat_path": "/chat/completions",
        "default_model": "mimo-v2.5",
        "api_key_env": "MIMO_API_KEY",
        "model_hint": "\u5982 mimo-v2.5\u3001mimo-v2.5-pro\u3001mimo-v2-pro",
        "official_docs": "https://platform.xiaomimimo.com/docs/api/chat/openai-api",
    },
    "openai": {
        "id": "openai",
        "name": "OpenAI (GPT)",
        "base_url": "https://api.openai.com/v1",
        "chat_path": "/chat/completions",
        "default_model": "gpt-4o-mini",
        "api_key_env": "OPENAI_API_KEY",
        "model_hint": "\u5982 gpt-4o\u3001gpt-4o-mini\u3001gpt-4-turbo\u3001o1-mini",
        "official_docs": "https://platform.openai.com/docs/api-reference/chat/create",
    },
    "moonshot": {
        "id": "moonshot",
        "name": "Moonshot / Kimi",
        "base_url": "https://api.moonshot.cn/v1",
        "chat_path": "/chat/completions",
        "default_model": "moonshot-v1-32k",
        "api_key_env": "MOONSHOT_API_KEY",
        "model_hint": "\u5982 moonshot-v1-8k\u3001moonshot-v1-32k\u3001moonshot-v1-128k",
        "official_docs": "https://platform.moonshot.cn/docs/api/chat",
    },
}


def _now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def ensure_model_settings_table(db_path=None):
    conn = get_db()
    try:
        cursor = conn.cursor()
        default_provider = PROVIDERS["xiaomi_mimo"]
        cursor.execute("SELECT id FROM model_settings WHERE id = 1")
        if not cursor.fetchone():
            cursor.execute(
                """
                INSERT INTO model_settings (id, active_provider, model, api_key, base_url, created_at, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?)
                """,
                (
                    default_provider["id"],
                    default_provider["default_model"],
                    "",
                    default_provider["base_url"],
                    _now(),
                    _now(),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def get_model_setting(db_path=None):
    ensure_model_settings_table(db_path)
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM model_settings WHERE id = 1").fetchone()
        if not row:
            provider = PROVIDERS["xiaomi_mimo"]
            return {
                "active_provider": provider["id"],
                "model": provider["default_model"],
                "api_key": "",
                "base_url": provider["base_url"],
            }
        return dict(row)
    finally:
        conn.close()


def save_model_setting(active_provider, model, api_key, base_url=None, db_path=None):
    ensure_model_settings_table(db_path)
    if active_provider not in PROVIDERS:
        raise ValueError("Unsupported model provider")

    provider = PROVIDERS[active_provider]
    resolved_base_url = (base_url or provider["base_url"]).rstrip("/")
    resolved_model = (model or provider["default_model"]).strip()
    if not resolved_model:
        raise ValueError("Model is required for the selected provider")

    conn = get_db()
    try:
        conn.execute(
            """
            UPDATE model_settings
            SET active_provider = ?, model = ?, api_key = ?, base_url = ?, updated_at = ?
            WHERE id = 1
            """,
            (
                active_provider,
                resolved_model,
                api_key or "",
                resolved_base_url,
                _now(),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "active_provider": active_provider,
        "model": resolved_model,
        "api_key_set": bool(api_key),
        "base_url": resolved_base_url,
    }


def public_provider_list():
    return list(PROVIDERS.values())


def mask_api_key(api_key):
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}{'*' * 8}{api_key[-4:]}"
