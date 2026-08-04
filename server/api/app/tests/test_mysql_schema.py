from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from pub.manager.mysql_manager import (
    ensure_device_inst_optional_fields,
    ensure_process_code_tenant_unique,
)


@pytest.mark.asyncio
async def test_process_code_index_migration_replaces_global_unique_index():
    legacy_result = Mock()
    legacy_result.scalar_one.return_value = 1
    scoped_result = Mock()
    scoped_result.scalar_one.return_value = 0
    conn = SimpleNamespace(
        dialect=SimpleNamespace(name="mysql"),
        execute=AsyncMock(side_effect=[legacy_result, scoped_result, Mock()]),
    )

    await ensure_process_code_tenant_unique(conn)

    migration_sql = str(conn.execute.await_args_list[2].args[0])
    lookup_sql = str(conn.execute.await_args_list[0].args[0])
    assert "table_name = 'dg_template'" in lookup_sql
    assert "ALTER TABLE `dg_template`" in migration_sql
    assert "DROP INDEX `ix_process_code`" in migration_sql
    assert "UNIQUE (`tenant_id`, `code`)" in migration_sql


@pytest.mark.asyncio
async def test_process_code_index_migration_skips_non_mysql_database():
    conn = SimpleNamespace(
        dialect=SimpleNamespace(name="sqlite"),
        execute=AsyncMock(),
    )

    await ensure_process_code_tenant_unique(conn)

    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_device_inst_optional_field_migration_makes_both_columns_nullable():
    columns_result = Mock()
    columns_result.fetchall.return_value = [
        ("purchase_date", "NO"),
        ("desc", "NO"),
    ]
    conn = SimpleNamespace(
        dialect=SimpleNamespace(name="mysql"),
        execute=AsyncMock(side_effect=[columns_result, Mock()]),
    )

    await ensure_device_inst_optional_fields(conn)

    migration_sql = str(conn.execute.await_args_list[1].args[0])
    assert "MODIFY COLUMN `purchase_date` DATE NULL" in migration_sql
    assert "MODIFY COLUMN `desc` VARCHAR(128) NULL" in migration_sql


@pytest.mark.asyncio
async def test_device_inst_optional_field_migration_is_idempotent():
    columns_result = Mock()
    columns_result.fetchall.return_value = [
        ("purchase_date", "YES"),
        ("desc", "YES"),
    ]
    conn = SimpleNamespace(
        dialect=SimpleNamespace(name="mysql"),
        execute=AsyncMock(return_value=columns_result),
    )

    await ensure_device_inst_optional_fields(conn)

    assert conn.execute.await_count == 1
