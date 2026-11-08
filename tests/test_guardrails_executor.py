from pathlib import Path

import pytest

from dce.execution.executor import SafeSQLExecutor
from dce.execution.guardrails import GuardrailResult, SQLGuardrail, SQLSecurityViolationError
from dce.models import SQLExecutionResult
from dce.warehouse.builder import build_warehouse


@pytest.fixture(scope="module")
def warehouse_db(tmp_path_factory) -> Path:
    """Build a deterministic small DuckDB warehouse for testing executor."""
    temp_dir = tmp_path_factory.mktemp("warehouse")
    db_path = temp_dir / "test_exec.duckdb"
    build_warehouse(db_path=db_path, sample_orders_count=100, seed=42)
    return db_path


class TestSQLGuardrailMaliciousQueries:
    """SEC-01 through SEC-03: Block hostile and mutating SQL statements."""

    @pytest.fixture
    def guardrail(self) -> SQLGuardrail:
        return SQLGuardrail()

    @pytest.mark.parametrize(
        "malicious_sql",
        [
            "DROP TABLE marts.fct_orders",
            "DELETE FROM marts.fct_orders WHERE 1=1",
            "UPDATE marts.fct_orders SET order_status = 'delivered'",
            "SELECT 1; DROP TABLE marts.fct_orders",
            "SELECT * FROM read_csv('secret.csv')",
            "SELECT * FROM read_csv_auto('/etc/passwd')",
            "SELECT * FROM read_parquet('dump.parquet')",
            "SELECT * FROM 'local_file.csv'",
            "COPY marts.fct_orders TO 'out.csv'",
            "ATTACH 'other.db' AS other",
            "INSTALL httpfs; LOAD httpfs",
            "INSERT INTO marts.fct_orders (order_id) VALUES ('fake')",
            "ALTER TABLE marts.fct_orders ADD COLUMN hacked INT",
            "SELECT glob('*.csv')",
            "SELECT * FROM parquet_scan('dump.parquet')",
            "SELECT * FROM 'nested/secret.parquet'",
            'SELECT * FROM "passwords.txt"',
        ],
    )
    def test_blocks_malicious_queries(self, guardrail: SQLGuardrail, malicious_sql: str):
        with pytest.raises(SQLSecurityViolationError):
            guardrail.validate_and_rewrite(malicious_sql)


class TestSQLGuardrailLegitimateQueries:
    """SEC-04 and SEC-05: Allow legitimate analytical queries, handle CTEs and LIMIT."""

    @pytest.fixture
    def guardrail(self) -> SQLGuardrail:
        return SQLGuardrail()

    def test_standard_select_applies_limit(self, guardrail: SQLGuardrail):
        sql = "SELECT order_id, total_order_value FROM marts.fct_orders WHERE order_status = 'delivered'"
        result = guardrail.validate_and_rewrite(sql, max_rows=1000)

        assert isinstance(result, GuardrailResult)
        assert result.is_safe is True
        assert "LIMIT 1000" in result.sanitized_sql.upper()
        assert result.limit_applied == 1000
        assert "marts.fct_orders" in result.tables_referenced
        assert len(result.governance_warnings) == 0

    def test_cte_query_without_false_positives(self, guardrail: SQLGuardrail):
        sql = "WITH sp_orders AS (SELECT order_id FROM marts.fct_orders) SELECT * FROM sp_orders"
        result = guardrail.validate_and_rewrite(sql, max_rows=500)

        assert result.is_safe is True
        assert "sp_orders" in result.cte_names
        assert "marts.fct_orders" in result.tables_referenced
        # CTE local name should NOT be classified as an external physical table
        assert "sp_orders" not in result.tables_referenced
        assert "LIMIT 500" in result.sanitized_sql.upper()
        assert result.limit_applied == 500

    def test_limit_rewriting_caps_high_limits(self, guardrail: SQLGuardrail):
        sql = "SELECT * FROM marts.fct_orders LIMIT 5000"
        result = guardrail.validate_and_rewrite(sql, max_rows=1000)

        assert result.is_safe is True
        assert "LIMIT 1000" in result.sanitized_sql.upper()
        assert result.limit_applied == 1000

    def test_limit_rewriting_preserves_smaller_limits(self, guardrail: SQLGuardrail):
        sql = "SELECT * FROM marts.fct_orders LIMIT 50"
        result = guardrail.validate_and_rewrite(sql, max_rows=1000)

        assert result.is_safe is True
        assert "LIMIT 50" in result.sanitized_sql.upper()
        assert result.limit_applied == 50

    def test_unwraps_subquery(self, guardrail: SQLGuardrail):
        sql = "(SELECT order_id FROM marts.fct_orders)"
        result = guardrail.validate_and_rewrite(sql, max_rows=100)

        assert result.is_safe is True
        assert "LIMIT 100" in result.sanitized_sql.upper()

    def test_governance_warning_for_non_marts_tables(self, guardrail: SQLGuardrail):
        sql = "SELECT * FROM raw.raw_orders"
        result = guardrail.validate_and_rewrite(sql, max_rows=100)

        assert result.is_safe is True
        assert len(result.governance_warnings) > 0
        assert any("marts" in w.lower() for w in result.governance_warnings)


class TestSafeSQLExecutor:
    """Sandbox execution on DuckDB."""

    def test_blocks_malicious_query_in_executor(self, warehouse_db: Path):
        executor = SafeSQLExecutor(db_path=warehouse_db)
        res = executor.execute("DROP TABLE marts.fct_orders")

        assert isinstance(res, SQLExecutionResult)
        assert res.success is False
        assert res.security_violation is True
        assert res.error_message is not None
        assert "DROP" in res.error_message.upper() or "MUTATION" in res.error_message.upper() or "SECURITY" in res.error_message.upper() or "VIOLATION" in res.error_message.upper()

    def test_executes_valid_query(self, warehouse_db: Path):
        executor = SafeSQLExecutor(db_path=warehouse_db)
        sql = "SELECT order_id, order_status, total_order_value FROM marts.fct_orders WHERE order_status = 'delivered'"
        res = executor.execute(sql, max_rows=10)

        assert isinstance(res, SQLExecutionResult)
        assert res.success is True
        assert res.security_violation is False
        assert res.error_message is None
        assert res.columns == ["order_id", "order_status", "total_order_value"]
        assert 0 < res.row_count <= 10
        assert len(res.rows) == res.row_count
        assert res.execution_time_ms >= 0.0
        assert res.limit_applied == 10
        assert "marts.fct_orders" in res.tables_referenced

    def test_executes_cte_query(self, warehouse_db: Path):
        executor = SafeSQLExecutor(db_path=warehouse_db)
        sql = "WITH delivered AS (SELECT order_id FROM marts.fct_orders WHERE order_status = 'delivered') SELECT count(*) AS cnt FROM delivered"
        res = executor.execute(sql)

        assert res.success is True
        assert res.security_violation is False
        assert res.columns == ["cnt"]
        assert len(res.rows) == 1
        assert res.rows[0][0] > 0

    def test_handles_duckdb_runtime_error_gracefully(self, warehouse_db: Path):
        executor = SafeSQLExecutor(db_path=warehouse_db)
        # Nonexistent column passes AST parse if valid syntax, but fails DuckDB execution
        sql = "SELECT column_does_not_exist FROM marts.fct_orders"
        res = executor.execute(sql)

        assert res.success is False
        assert res.security_violation is False
        assert res.error_message is not None
        assert "column_does_not_exist" in res.error_message.lower() or "not found" in res.error_message.lower() or "referenced" in res.error_message.lower()
