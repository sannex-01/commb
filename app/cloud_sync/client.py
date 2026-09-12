"""Optional CommB Cloud sync. NOT anonymous telemetry.

When enabled, this exports PERSONAL DATA to the configured CommB Cloud
workspace: customer profiles (name, email, phone), delivery addresses, order
and payment records, and full conversation transcripts, which CommB Cloud
renders in its Conversations CRM. Enabling it makes that workspace a data
processor for your end users (NDPR / GDPR).

It is therefore OFF by default -- a self-hosted CommB never phones home -- and
the SDK that implements it is an optional dependency (`pip install
commb[cloud]`). Every method here is a no-op unless BOTH cloud sync is enabled
AND a key is configured AND the SDK is importable, so the app runs identically
with the package absent.

Release notes and the sponsor banner deliberately do NOT live here: they are a
keyless public fetch in `app.updates`, so that update and security notices
reach every install without opting into any of the above.
"""

from typing import Optional, Dict, Any, List

from app.core.config import settings
from app.core.logger import logger

# The cloud SDK is optional. Import failure is normal and must never be fatal --
# it just means this instance has no cloud backend available.
try:  # pragma: no cover - depends on optional extra being installed
    from commb_agent import CommBClient as _CloudClient
except ImportError:  # pragma: no cover
    _CloudClient = None


class CloudSyncClient:
    """No-op by default; forwards to the SDK only when fully configured."""

    def __init__(self):
        self.api_key = settings.cloud_key
        self.host = settings.cloud_host
        self._client = None

        if not (settings.cloud_sync_enabled and self.api_key):
            return

        if _CloudClient is None:
            logger.warning(
                "CommB Cloud sync is enabled and a key is set, but the optional SDK "
                "is not installed. Run `pip install commb[cloud]` or unset "
                "COMMB_CLOUD_KEY. Continuing with cloud sync disabled."
            )
            return

        logger.warning(
            "CommB Cloud sync is ENABLED: customer profiles, addresses, orders and "
            "conversation transcripts from this instance will be sent to %s. "
            "Unset COMMB_CLOUD_KEY to disable.",
            self.host or "https://commb.app",
        )

        try:
            kwargs: Dict[str, Any] = {"api_key": self.api_key}
            if self.host:
                kwargs["host"] = self.host
            self._client = _CloudClient(**kwargs)
        except Exception as e:
            logger.warning(f"Could not initialise cloud sync client, continuing without it: {e}")

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def track(
        self,
        channel: str,
        customer_id: str,
        event: str,
        status: str = "success",
        amount: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
    ) -> None:
        """Enqueues an event for CommB Cloud. No-op when cloud sync is unavailable.

        `customer_id` is the real end-user identifier and `metadata` may carry
        personal data (names, emails, phone numbers, delivery addresses), so
        this only ever runs on an instance explicitly connected to a workspace.
        """
        if not self._client:
            return
        try:
            self._client.track(
                channel=channel,
                customer_id=customer_id,
                event=event,
                status=status,
                amount=amount,
                metadata=metadata,
                agent_id=agent_id,
            )
        except Exception as e:
            # Telemetry must never break a customer-facing request path.
            logger.warning(f"Telemetry track failed: {e}")

    def sync_conversation(
        self,
        channel: str,
        customer_id: str,
        messages: List[Dict[str, Any]],
        agent_id: Optional[str] = None,
    ) -> None:
        """Pushes a verbatim conversation transcript to CommB Cloud.

        Sends the actual message text on both sides, for the Conversations CRM.
        This is the most sensitive thing this instance transmits.
        """
        if not self._client:
            return
        if not hasattr(self._client, "sync_conversation"):
            logger.warning("Telemetry SDK is outdated, missing sync_conversation.")
            return
        try:
            self._client.sync_conversation(
                channel=channel,
                customer_id=customer_id,
                messages=messages,
                agent_id=agent_id,
            )
        except Exception as e:
            logger.warning(f"Telemetry sync_conversation failed: {e}")

    def close(self) -> None:
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass


cloud_client = CloudSyncClient()
