"""
Central configuration.

All runtime knobs are read from environment variables (loaded from `.env` in
development via python-dotenv). Keeping them in one place means every module —
auth, persistence, the agent, the sandbox — shares a single source of truth and
tests can override values by setting env vars before import.
"""
from __future__ import annotations

import os
import secrets
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """Process-wide settings resolved from the environment.

    Attributes are read once at construction. Use :func:`get_settings` so the
    instance is cached; tests that need to change env vars can call
    ``get_settings.cache_clear()``.
    """

    def __init__(self) -> None:
        # --- Identity / legacy shared secret (kept for back-compat) --------
        self.email: str | None = os.getenv("EMAIL")
        self.secret: str | None = os.getenv("SECRET")
        # When true, /solve still accepts the legacy shared SECRET in addition
        # to JWT / API-key auth. Handy so existing HF deployments keep working.
        self.allow_legacy_secret: bool = _get_bool("ALLOW_LEGACY_SECRET", True)

        # --- JWT / auth ----------------------------------------------------
        # In production JWT_SECRET MUST be set. If it is absent we generate an
        # ephemeral one so the app still boots locally, but tokens then become
        # invalid on restart (and we warn via `jwt_secret_is_ephemeral`).
        env_jwt = os.getenv("JWT_SECRET")
        self.jwt_secret_is_ephemeral: bool = env_jwt is None
        self.jwt_secret: str = env_jwt or secrets.token_urlsafe(48)
        self.jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
        self.jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))

        # --- Persistence ---------------------------------------------------
        # Default to a local SQLite file so the app is runnable with zero
        # external services. Point DATABASE_URL at Supabase/Postgres in prod,
        # e.g. postgresql+psycopg2://user:pass@host:5432/dbname
        self.database_url: str = os.getenv(
            "DATABASE_URL", "sqlite:///./data/runs.db"
        )

        # --- LLM -----------------------------------------------------------
        self.gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3-pro")
        self.google_api_key: str | None = os.getenv("GOOGLE_API_KEY")

        # --- Agent limits --------------------------------------------------
        self.recursion_limit: int = int(os.getenv("RECURSION_LIMIT", "5000"))
        self.max_tokens: int = int(os.getenv("MAX_TOKENS", "60000"))

        # --- CORS ----------------------------------------------------------
        raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
        self.allowed_origins: list[str] = [
            o.strip() for o in raw_origins.split(",") if o.strip()
        ] or ["*"]

        # --- Sandbox (E5) --------------------------------------------------
        self.run_code_timeout: int = int(os.getenv("RUN_CODE_TIMEOUT", "120"))
        self.run_code_mem_mb: int = int(os.getenv("RUN_CODE_MEM_MB", "2048"))
        self.run_code_cpu_seconds: int = int(os.getenv("RUN_CODE_CPU_SECONDS", "60"))
        self.run_code_allow_network: bool = _get_bool("RUN_CODE_ALLOW_NETWORK", True)
        # RLIMIT_AS caps *virtual* address space, which numpy/pandas/BLAS often
        # over-reserve — so memory enforcement is opt-in to avoid breaking real
        # data tasks. CPU + wall-clock + fd limits are always on (POSIX).
        self.run_code_enforce_mem: bool = _get_bool("RUN_CODE_ENFORCE_MEM", False)

        # --- Observability -------------------------------------------------
        self.langsmith_enabled: bool = _get_bool("LANGCHAIN_TRACING_V2", False)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
