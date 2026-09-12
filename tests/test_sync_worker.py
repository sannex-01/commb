import pytest
from unittest.mock import patch, MagicMock
from app.core.config import settings
from app.telemetry.sync_worker import scheduler, start_sync_scheduler, shutdown_sync_scheduler


def test_sync_interval_configuration():
    assert settings.SYNC_INTERVAL_MINUTES == 30


def test_start_sync_scheduler():
    with patch("app.telemetry.sync_worker.scheduler.add_job") as mock_add_job, \
         patch("app.telemetry.sync_worker.scheduler.start") as mock_start, \
         patch("app.telemetry.sync_worker._scheduled_sync_job", return_value=None), \
         patch("asyncio.create_task") as mock_create_task:
        
        start_sync_scheduler()
        
        mock_add_job.assert_called_once()
        args, kwargs = mock_add_job.call_args
        assert kwargs.get("minutes") == 30
        assert kwargs.get("id") == "remote_sync_job"
        assert kwargs.get("replace_existing") is True
