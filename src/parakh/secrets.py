"""Secrets: .env locally, AWS SSM Parameter Store on scheduled runs (C6.4, ADR-009).

Parameters are SecureStrings named <path>/<NAME>, for example /parakh/prod/TELEGRAM_BOT_TOKEN.
The role GitHub Actions assumes through OIDC reads them, so no long-lived AWS keys exist anywhere.
The job sets PARAKH_SSM_PATH; without it nothing here calls AWS.
"""

from __future__ import annotations

import os
import re
from typing import Any

import structlog

SSM_PATH_VAR = "PARAKH_SSM_PATH"
DEFAULT_REGION = "ap-south-1"
_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")

log = structlog.get_logger(__name__)
_loaded_paths: set[str] = set()


def ssm_path() -> str | None:
    """The Parameter Store path for this run (for example /parakh/prod), if one is set."""
    path = os.environ.get(SSM_PATH_VAR, "").strip().rstrip("/")
    return path or None


def _client() -> Any:
    import boto3

    return boto3.client("ssm", region_name=os.environ.get("AWS_REGION") or DEFAULT_REGION)


def load_ssm_environment(client: Any | None = None) -> list[str]:
    """Copy every parameter under PARAKH_SSM_PATH into the environment; returns the names set.

    A variable that is already set and non-empty wins, so a workflow can override one value. Values are never
    logged. Runs once per path per process.
    """
    path = ssm_path()
    if path is None or path in _loaded_paths:
        return []
    ssm = client if client is not None else _client()
    names: list[str] = []
    token: str | None = None
    while True:
        kwargs: dict[str, Any] = {"Path": path, "WithDecryption": True, "Recursive": False}
        if token:
            kwargs["NextToken"] = token
        page = ssm.get_parameters_by_path(**kwargs)
        for parameter in page.get("Parameters", []):
            name = str(parameter["Name"]).rsplit("/", 1)[-1]
            if not _NAME.match(name):
                log.warning("secrets.ssm.name_skipped", path=path)
                continue
            if not os.environ.get(name):  # unset or empty (an unset GitHub secret arrives empty)
                os.environ[name] = str(parameter["Value"])
                names.append(name)
        token = page.get("NextToken")
        if not token:
            break
    _loaded_paths.add(path)
    log.info("secrets.ssm.loaded", path=path, count=len(names))
    return names


def get_secret(name: str) -> str | None:
    """A secret by its variable name: the environment, after SSM has been loaded into it."""
    load_ssm_environment()
    return os.environ.get(name) or None
