"""只读 SQL 工具必须拒绝 DROP/INSERT/多语句。"""

import pytest

from app.tools.sql_query import assert_readonly_select


def test_select_ok():
    assert "id" in assert_readonly_select("SELECT id FROM documents LIMIT 1")


def test_reject_drop():
    with pytest.raises(ValueError):
        assert_readonly_select("DROP TABLE users")


def test_reject_insert():
    with pytest.raises(ValueError):
        assert_readonly_select("INSERT INTO users(username) VALUES ('x')")


def test_reject_multi_statement():
    with pytest.raises(ValueError):
        assert_readonly_select("SELECT 1; SELECT 2")


def test_reject_system_catalog():
    with pytest.raises(ValueError):
        assert_readonly_select("SELECT * FROM pg_catalog.pg_tables")
