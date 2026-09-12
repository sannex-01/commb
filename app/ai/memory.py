import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.logger import logger
from app.models.session import ConversationSession, MessageLog
from app.models.config_override import ConfigOverride
from app.cloud_sync.client import cloud_client


class MemoryManager:
    """Manages sliding window conversation context and TTL session expiry."""

    @staticmethod
    async def get_or_create_session(
        db: AsyncSession,
        channel: str,
        customer_identifier: str,
        agent_id: Optional[int] = None,
    ) -> ConversationSession:
        session_key = f"{channel}:{customer_identifier}"
        now = datetime.now(timezone.utc)

        stmt = select(ConversationSession).where(ConversationSession.session_key == session_key)
        result = await db.execute(stmt)
        session = result.scalars().first()

        if not session:
            session = ConversationSession(
                session_key=session_key,
                channel=channel,
                customer_identifier=customer_identifier,
                agent_id=agent_id,
                bot_mode=settings.BOT_MODE,
                memory_json="[]",
                state_data="{}",
                last_active_at=now,
                expires_at=now + timedelta(hours=settings.SESSION_EXPIRY_HOURS),
            )
            db.add(session)
            await db.commit()
            await db.refresh(session)
            return session

        # Update agent_id if newly provided
        if agent_id and session.agent_id != agent_id:
            session.agent_id = agent_id

        # Check if session has expired
        if session.expires_at:
            # Ensure expires_at is timezone-aware
            expires_at_aware = session.expires_at
            if expires_at_aware.tzinfo is None:
                expires_at_aware = expires_at_aware.replace(tzinfo=timezone.utc)
            
            if expires_at_aware < now:
                logger.info(f"Session {session_key} expired at {session.expires_at}. Resetting active context.")
                session.memory_json = "[]"
                session.active_flow = None
                session.current_step = None
                session.state_data = "{}"
                # Marks the new conversation's start so history-replaying
                # channels (widget /history) know to stop replaying
                # anything logged before this point — see the column's
                # docstring in app/models/session.py.
                session.session_started_at = now

        # Refresh expiry and active time
        session.last_active_at = now
        session.expires_at = now + timedelta(hours=settings.SESSION_EXPIRY_HOURS)
        await db.commit()
        await db.refresh(session)
        return session

    @staticmethod
    def get_history(session: ConversationSession) -> List[Dict[str, Any]]:
        """Returns the list of serialized conversation turns."""
        try:
            return json.loads(session.memory_json or "[]")
        except Exception:
            return []

    @staticmethod
    async def add_message(
        db: AsyncSession,
        session: ConversationSession,
        role: str,
        content: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Appends a message to message logs and updates sliding memory buffer."""
        # 1. Add permanent message log
        log_entry = MessageLog(
            session_id=session.id,
            role=role,
            content=content,
            tool_calls_json=json.dumps(tool_calls) if tool_calls else None,
            metadata_json=json.dumps(metadata or {}),
        )
        db.add(log_entry)

        # Track chat_transcript telemetry event
        cloud_client.track(
            channel=session.channel,
            customer_id=session.customer_identifier,
            event="chat_transcript",
            metadata={
                "messages": [{
                    "role": role,
                    "content": content,
                    "created_at": datetime.now(timezone.utc).isoformat()
                }]
            }
        )

        # 2. Update sliding memory
        history = MemoryManager.get_history(session)
        msg_payload = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if tool_calls:
            msg_payload["tool_calls"] = tool_calls

        history.append(msg_payload)

        # Trim to sliding window size
        stmt = select(ConfigOverride).where(ConfigOverride.key == "memory_window_size")
        result = await db.execute(stmt)
        override = result.scalars().first()
        window_size = int(override.value) if override and override.value.isdigit() else settings.MEMORY_WINDOW_SIZE

        if len(history) > window_size * 2:
            history = history[-(window_size * 2):]

        session.memory_json = json.dumps(history)
        session.last_active_at = datetime.now(timezone.utc)
        session.expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.SESSION_EXPIRY_HOURS)
        await db.commit()

    @staticmethod
    async def update_flow_state(
        db: AsyncSession,
        session: ConversationSession,
        active_flow: Optional[str],
        current_step: Optional[str],
        state_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Updates interactive button flow progress."""
        session.active_flow = active_flow
        session.current_step = current_step
        if state_data is not None:
            session.state_data = json.dumps(state_data)
        session.last_active_at = datetime.now(timezone.utc)
        session.expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.SESSION_EXPIRY_HOURS)
        await db.commit()

    @staticmethod
    def get_flow_state_data(session: ConversationSession) -> Dict[str, Any]:
        """Returns the current state dictionary for the active flow."""
        try:
            return json.loads(session.state_data or "{}")
        except Exception:
            return {}

    @staticmethod
    async def reset_session(db: AsyncSession, session: ConversationSession) -> None:
        """Clears memory and active flow state manually."""
        session.memory_json = "[]"
        session.active_flow = None
        session.current_step = None
        session.state_data = "{}"
        await db.commit()
