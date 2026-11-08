import time
from pathlib import Path
from typing import Any

import duckdb

from dce.execution.guardrails import SQLGuardrail, SQLSecurityViolationError
from dce.models import SQLExecutionResult


class SafeSQLExecutor:
    """Executes validated read-only SQL queries inside a hardened DuckDB sandbox."""

    def __init__(
        self,
        db_path: Path | str,
        guardrail: SQLGuardrail | None = None,
        max_memory: str = "512MB",
        timeout_seconds: float = 15.0,
    ) -> None:
        self.db_path = Path(db_path)
        self.guardrail = guardrail if guardrail is not None else SQLGuardrail()
        self.max_memory = max_memory
        self.timeout_seconds = timeout_seconds

    def execute(self, sql: str, max_rows: int = 1000) -> SQLExecutionResult:
        """Validate query with guardrails and safely execute on DuckDB."""
        start_time = time.perf_counter()

        # Step 1: Validate and rewrite SQL with AST guardrails
        try:
            guardrail_result = self.guardrail.validate_and_rewrite(sql, max_rows=max_rows)
        except SQLSecurityViolationError as err:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return SQLExecutionResult(
                query=sql,
                success=False,
                error_message=str(err),
                security_violation=True,
                execution_time_ms=round(elapsed_ms, 2),
            )
        except Exception as err:  # noqa: BLE001
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return SQLExecutionResult(
                query=sql,
                success=False,
                error_message=str(err),
                security_violation=False,
                execution_time_ms=round(elapsed_ms, 2),
            )

        # Step 2: Execute sanitized query inside DuckDB sandbox
        con: duckdb.DuckDBPyConnection | None = None
        try:
            con = duckdb.connect(
                str(self.db_path),
                read_only=True,
                config={
                    "enable_external_access": False,
                    "max_memory": self.max_memory,
                },
            )
            cursor = con.execute(guardrail_result.sanitized_sql)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            raw_rows = cursor.fetchall()
            rows: list[list[Any]] = [list(row) for row in raw_rows]

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return SQLExecutionResult(
                query=sql,
                sql_executed=guardrail_result.sanitized_sql,
                success=True,
                columns=columns,
                rows=rows,
                row_count=len(rows),
                execution_time_ms=round(elapsed_ms, 2),
                security_violation=False,
                tables_referenced=guardrail_result.tables_referenced,
                limit_applied=guardrail_result.limit_applied,
                governance_warnings=guardrail_result.governance_warnings,
            )
        except Exception as err:  # noqa: BLE001
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            err_str = str(err).lower()
            is_sec_violation = (
                "permission" in err_str
                or "external access" in err_str
                or "disabled by configuration" in err_str
            )
            return SQLExecutionResult(
                query=sql,
                sql_executed=guardrail_result.sanitized_sql,
                success=False,
                error_message=str(err),
                security_violation=is_sec_violation,
                execution_time_ms=round(elapsed_ms, 2),
                tables_referenced=guardrail_result.tables_referenced,
                limit_applied=guardrail_result.limit_applied,
                governance_warnings=guardrail_result.governance_warnings,
            )
        finally:
            if con is not None:
                con.close()
