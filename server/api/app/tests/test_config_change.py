from unittest.mock import AsyncMock, Mock

import pytest

from pub.services import create_config_tasks


@pytest.mark.asyncio
async def test_create_config_tasks_creates_pending_task_when_no_open_task_exists():
    result = Mock()
    result.scalar_one_or_none.return_value = None
    session = Mock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    await create_config_tasks(session, ["STL26SH0001"])

    session.add_all.assert_called_once()
    tasks = session.add_all.call_args.args[0]
    assert len(tasks) == 1
    assert tasks[0].sn == "STL26SH0001"
    assert tasks[0].action == 1
    assert tasks[0].val == 1
    assert tasks[0].status == 0
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_config_tasks_does_not_duplicate_dispatched_task():
    existing = Mock(id="existing-task")
    result = Mock()
    result.scalar_one_or_none.return_value = existing
    session = Mock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    await create_config_tasks(session, ["STL26SH0001"])

    statement = session.execute.await_args.args[0]
    assert "sensor_task.status IN" in str(statement)
    assert set(statement.compile().params["status_1"]) == {0, 2}
    session.add_all.assert_not_called()
    session.commit.assert_not_awaited()
