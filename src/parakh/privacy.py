"""PII controls before text reaches a cloud model (C6.3).

Patterns cover e-mail, Indian mobile numbers, PAN, Aadhaar, card numbers and the demat
identifiers a CAS carries (NSDL DP ID + client ID, CDSL 16-digit BO ID; plan 13 P6). Order
matters: the demat patterns run before the generic card pattern so they keep their label.
ISINs (INE…) are not PII and are never matched. Extend PII_PATTERNS for your domain and add a
test for each new pattern.
"""

from __future__ import annotations

import re

PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "demat_nsdl": re.compile(r"\bIN\d{6}(?:[\s-]?\d{8})?\b"),  # DP ID, optionally + client ID
    "demat_cdsl": re.compile(r"\b\d{16}\b"),  # CDSL beneficiary-owner ID
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "pan": re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
    "aadhaar": re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),
    "card": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    "phone": re.compile(r"(?<!\d)(?:\+91[\s-]?|0)?[6-9]\d{9}(?!\d)"),
}


def redact_pii(text: str) -> str:
    for label, pattern in PII_PATTERNS.items():
        text = pattern.sub(f"[{label.upper()}]", text)
    return text


def contains_pii(text: str) -> bool:
    return any(pattern.search(text) for pattern in PII_PATTERNS.values())


ACCOUNT_KEY_ENV = "PARAKH_ACCOUNT_KEY"


class AccountKeyMissing(RuntimeError):
    pass


def account_key(require_stable: bool = False) -> bytes:
    """The key behind `account_ref` hashes (plan 13 P6).

    Read from PARAKH_ACCOUNT_KEY (hex, in your .env). Without it, a throwaway key is created in
    state/secrets/account_key for local checks only; storing lots needs the stable .env key
    (`require_stable=True`), because a new key gives every account a new reference and would
    orphan the stored lots. The key never exposes an account ID either way.
    """
    import os
    import secrets

    from parakh.config import get_settings, state_dir

    configured = get_settings().parakh_account_key
    value = configured.get_secret_value() if configured else os.environ.get(ACCOUNT_KEY_ENV)
    if value:
        return bytes.fromhex(value)
    if require_stable:
        raise AccountKeyMissing(
            "PARAKH_ACCOUNT_KEY is not set in .env; run `parakh holdings keygen` first"
        )
    path = state_dir() / "secrets" / "account_key"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(secrets.token_bytes(32))
        path.chmod(0o600)
    return path.read_bytes()
