from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM Provider selection: "auto" (default, prefers Google if key set), "google", or "tencent"
    LLM_PROVIDER: str = "auto"

    # 1. Google Gemini LLM Configuration (Light / Fast Model)
    GOOGLE_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash-lite"        # Primary fast, lightweight model
    GEMINI_FAST_MODEL: str = "gemini-2.0-flash-lite"   # Validator & extractor model

    # 2. Tencent Cloud TokenHub / WorkBuddy LLM Configuration
    TENCENT_LLM_BASE_URL: str = "https://api.tokenhub.tencentcloud.com/v1"
    TENCENT_LLM_API_KEY: str = "your-tencent-workbuddy-tokenhub-key"
    PLANNER_MODEL: str = "deepseek-v3"                 # Stronger model for Planner & Drafter (TRD Section 8)
    FAST_MODEL: str = "hunyuan-turbo"                  # Smaller/faster model for Extractor, Validator, PIC Parser
    USE_MOCK_LLM_FALLBACK: bool = True                 # Uses deterministic structured fallback when API key is placeholder

    AUDIT_HMAC_SECRET: str = "sekre-v3-immutable-secret-2026"
    DATABASE_URL: str = f"sqlite:///{(BASE_DIR / 'sekre_v3.db').as_posix()}"
    SQLITE_DB_PATH: str = str(BASE_DIR / "sekre_v3.db")
    CONFIG_DIR: str = str(BASE_DIR / "config")
    FIXTURES_DIR: str = str(BASE_DIR / "config" / "fixtures")
    OUTBOX_DELAY_SECONDS: int = 60

    # Authentication & Owner Identity Verification (TRD Sec 5, Item 5)
    SEKRE_API_KEY: str = "sekre-dev-key-2026"
    API_KEY_REGISTRY: dict[str, str] = {
        "sekre-key-andi-2026": "owner_andi",
        "sekre-key-exec-2026": "default_owner",
        "sekre-dev-key-2026": "owner_andi",
    }

    # Real email delivery is OFF unless SMTP_HOST is set
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_FROM_EMAIL: str = ""

    @property
    def sender_email(self) -> str:
        return self.SMTP_FROM or self.SMTP_FROM_EMAIL or self.SMTP_USER or "sekre@localhost"


settings = Settings()


def get_owner_for_api_key(api_key: str | None) -> str | None:
    if not api_key:
        return None
    cleaned = api_key.strip()
    if cleaned in settings.API_KEY_REGISTRY:
        return settings.API_KEY_REGISTRY[cleaned]
    if cleaned == settings.SEKRE_API_KEY:
        return "owner_andi"
    return None


def is_google_provider() -> bool:
    provider = (settings.LLM_PROVIDER or "auto").strip().lower()
    if provider == "google":
        return True
    if provider == "tencent":
        return False
    # Auto-detection: if GOOGLE_API_KEY is present and not placeholder, use Google
    gkey = (settings.GOOGLE_API_KEY or "").strip()
    return bool(gkey) and not gkey.startswith("your-")


def has_live_llm_credentials() -> bool:
    if is_google_provider():
        gkey = (settings.GOOGLE_API_KEY or "").strip()
        return bool(gkey) and not gkey.startswith("your-")
    key = (settings.TENCENT_LLM_API_KEY or "").strip()
    return bool(key) and key != "your-tencent-workbuddy-tokenhub-key" and not key.startswith("your-")


def get_engine_name(role: str = "planner") -> str:
    if not has_live_llm_credentials():
        return "deterministic_rules"
    if is_google_provider():
        mod = settings.GEMINI_FAST_MODEL if role == "validator" else settings.GEMINI_MODEL
        return f"llm_{mod.replace('-', '_').replace('.', '_')}"
    mod = settings.FAST_MODEL if role == "validator" else settings.PLANNER_MODEL
    return f"llm_{mod.replace('-', '_').replace('.', '_')}"


def get_planner_llm() -> BaseChatModel:
    if is_google_provider():
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.0,
        )
    return ChatOpenAI(
        model=settings.PLANNER_MODEL,
        base_url=settings.TENCENT_LLM_BASE_URL,
        api_key=settings.TENCENT_LLM_API_KEY,
        temperature=0.0,
    )


def get_fast_llm() -> BaseChatModel:
    if is_google_provider():
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=settings.GEMINI_FAST_MODEL,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.0,
        )
    return ChatOpenAI(
        model=settings.FAST_MODEL,
        base_url=settings.TENCENT_LLM_BASE_URL,
        api_key=settings.TENCENT_LLM_API_KEY,
        temperature=0.0,
    )
