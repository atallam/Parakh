"""Secrets: .env locally, AWS SSM Parameter Store in production (C6.4).

Parameters are SecureStrings named /parakh/<NAME>, read with the role GitHub Actions
assumes through OIDC, so no long-lived AWS keys exist anywhere.
"""

from __future__ import annotations

import os
from functools import lru_cache

from parakh.config import get_settings


@lru_cache(maxsize=64)
def get_secret(name: str) -> str | None:
    value = os.environ.get(name)
    if value or get_settings().app_env != "prod":
        return value
    import boto3

    ssm = boto3.client("ssm", region_name=get_settings().aws_region)
    response = ssm.get_parameter(Name=f"/parakh/{name}", WithDecryption=True)
    return response["Parameter"]["Value"]
