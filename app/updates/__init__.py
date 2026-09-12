"""Public update check: release notes and sponsor banner.

Deliberately separate from `app.cloud_sync`. This package talks to a public,
unauthenticated endpoint, needs no API key and no account, and sends no
personal data -- only the running version, so the server can say which releases
are newer. That keeps security notices reaching every install, including
self-hosted ones that will never have a CommB Cloud key.
"""

from app.updates.client import fetch_public_updates, get_support_config

__all__ = ["fetch_public_updates", "get_support_config"]
