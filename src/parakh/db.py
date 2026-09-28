"""Supabase client, created lazily so tests and `--help` never need credentials."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from parakh.config import get_settings


@lru_cache(maxsize=1)
def get_supabase() -> Any:
    s = get_settings()
    if not (s.supabase_url and s.supabase_service_key):
        raise RuntimeError("Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env first")
    from supabase import create_client

    return create_client(s.supabase_url, s.supabase_service_key.get_secret_value())
