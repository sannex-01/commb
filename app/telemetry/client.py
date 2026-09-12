"""Optional, pluggable telemetry backend.

A self-hosted CommB instance must never phone home, so telemetry is OFF by
default and the SDK that implements it is an optional dependency
(`pip install commb[telemetry]`). Every method here is a no-op unless BOTH
`ENABLE_TELEMETRY` is true AND a `COMMB_TELEMETRY_KEY` is configured AND the
SDK is importable — so the app runs identically with the package absent.
"""

from typing import Optional, Dict, Any, List

from app.core.config import settings
from app.core.logger import logger

# The telemetry SDK is optional. Import failure is normal and must never be
# fatal — it just means this instance has no telemetry backend available.
try:  # pragma: no cover - depends on optional extra being installed
    from commb_agent import CommBClient as _TelemetryClient
except ImportError:  # pragma: no cover
    _TelemetryClient = None


class TelemetryWrapper:
    """No-op by default; forwards to the SDK only when fully configured."""

    def __init__(self):
        self.api_key = settings.COMMB_TELEMETRY_KEY
        self.host = settings.COMMB_TELEMETRY_HOST
        self._client = None

        if not (settings.ENABLE_TELEMETRY and self.api_key):
            return

        if _TelemetryClient is None:
            logger.warning(
                "Telemetry is enabled and a key is set, but the optional SDK is not "
                "installed. Run `pip install commb[telemetry]` or unset "
                "COMMB_TELEMETRY_KEY. Continuing with telemetry disabled."
            )
            return

        try:
            kwargs: Dict[str, Any] = {"api_key": self.api_key}
            if self.host:
                kwargs["host"] = self.host
            self._client = _TelemetryClient(**kwargs)
        except Exception as e:
            logger.warning(f"Could not initialise telemetry client, continuing without it: {e}")

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
        """Enqueues an analytics event. No-op when telemetry is unavailable."""
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
        """Pushes a batched conversation transcript to the collector."""
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


telemetry_client = TelemetryWrapper()
