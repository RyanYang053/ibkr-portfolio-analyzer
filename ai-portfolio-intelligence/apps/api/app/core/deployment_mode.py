"""Deployment modes for the local-first desktop product."""

from __future__ import annotations

from enum import StrEnum


class DeploymentMode(StrEnum):
    DESKTOP_LOCAL = "desktop_local"
    DEVELOPMENT = "development"


# Postponed / out of scope for the personal product:
# multi_user_hosted, public production, public registration, cloud portfolio storage.
