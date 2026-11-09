import re
import sqlglot
from pydantic import BaseModel, Field
from sqlglot import errors, exp


class _ViolationCode:
    """Lightweight value holder for backward-compatible violation_type.value access."""

    def __init__(self, value: str) -> None:
        self.value = value

    def __str__(self) -> str:
        return self.value


class SQLSecurityViolationError(Exception):
    """Raised when a SQL query violates security guardrails."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is None:
            match = re.search(r"\b(SEC-0[1-5])\b", message)
            code = match.group(1) if match else "SEC-01"
        self.code = code
        self.violation_type = _ViolationCode(code)


class GuardrailResult(BaseModel):
    is_safe: bool
    sanitized_sql: str
    tables_referenced: list[str] = Field(default_factory=list)
    cte_names: list[str] = Field(default_factory=list)
    limit_applied: int | None = None
    governance_warnings: list[str] = Field(default_factory=list)
    violation_reason: str | None = None

    @property
    def tables_used(self) -> list[str]:
        """Alias for tables_referenced for UI compatibility."""
        return self.tables_referenced


# Node types that represent mutations or admin actions in AST
_MUTATION_NODE_NAMES = [
    "Insert",
    "Update",
    "Delete",
    "Drop",
    "Create",
    "Alter",
    "Command",
    "Grant",
    "Attach",
    "Detach",
    "Copy",
    "Pragma",
    "Set",
    "Load",
    "Install",
    "Kill",
    "Transaction",
    "Commit",
    "Rollback",
    "Into",
    "Merge",
    "Truncate",
]

MUTATION_NODES = tuple(
    cls for cls in (getattr(exp, name, None) for name in _MUTATION_NODE_NAMES) if cls is not None
)

# Explicit file I/O node types
FILE_IO_NODES = tuple(
    cls
    for cls in (getattr(exp, "ReadCSV", None), getattr(exp, "ReadParquet", None))
    if cls is not None
)

# Prohibited built-in functions that access files or external databases
PROHIBITED_FUNCTIONS = {
    "read_csv",
    "read_csv_auto",
    "read_parquet",
    "scan_parquet",
    "read_json",
    "read_json_auto",
    "read_ndjson",
    "read_ndjson_auto",
    "read_text",
    "read_blob",
    "scan_csv",
    "sniff_csv",
    "glob",
    "parquet_scan",
    "sqlite_scan",
    "postgres_scan",
    "duckdb_secrets",
    "pg_sleep",
    "sleep",
}

# File extensions that indicate a replacement scan or file reference
PROHIBITED_EXTENSIONS = (
    ".csv",
    ".parquet",
    ".json",
    ".db",
    ".duckdb",
    ".sqlite",
    ".txt",
)


class SQLGuardrail:
    """AST-based security guardrail and rewriter for SQL queries in DuckDB."""

    def __init__(self, default_schema: str = "marts") -> None:
        self.default_schema = default_schema

    def validate_and_sanitize(self, sql: str, max_rows: int = 1000) -> GuardrailResult:
        """Alias for validate_and_rewrite for UI compatibility."""
        return self.validate_and_rewrite(sql, max_rows=max_rows)

    def validate_and_rewrite(self, sql: str, max_rows: int = 1000) -> GuardrailResult:
        """Validate SQL query against SEC-01..SEC-05 rules and inject safety limit."""
        if not sql or not sql.strip():
            raise SQLSecurityViolationError("SQL query is empty.")

        # SEC-01: Parse statement and ensure exactly one statement
        try:
            parsed_statements = sqlglot.parse(sql, read="duckdb")
        except (errors.ParseError, errors.SqlglotError) as err:
            raise SQLSecurityViolationError(f"SQL parsing failed: {err}") from err

        valid_statements = [s for s in parsed_statements if s is not None]
        if len(valid_statements) == 0:
            raise SQLSecurityViolationError("Query contains no valid SQL statements.")
        if len(valid_statements) > 1:
            raise SQLSecurityViolationError(
                f"Multiple SQL statements detected ({len(valid_statements)} found). "
                "Batch execution is prohibited (SEC-01)."
            )

        parsed = valid_statements[0]

        # SEC-02: Somente Leitura (Unwrap Subquery & Verify Root is Select / SetOperation)
        while isinstance(parsed, exp.Subquery) and parsed.this is not None:
            parsed = parsed.this

        if not isinstance(parsed, (exp.Select, exp.SetOperation)):
            raise SQLSecurityViolationError(
                f"Root query expression must be SELECT or SetOperation, got: {type(parsed).__name__} (SEC-02)."
            )

        for node in parsed.walk():
            if isinstance(node, MUTATION_NODES):
                raise SQLSecurityViolationError(
                    f"Prohibited mutation or administrative statement detected: {type(node).__name__} (SEC-02)."
                )

        # SEC-03: Bloqueio de I/O de Arquivo e Replacement Scans
        try:
            tokens = sqlglot.tokenize(sql, read="duckdb")
            str_types = {sqlglot.TokenType.STRING}
            for attr in ("RAW_STRING", "HEREDOC_STRING", "NATIONAL_STRING"):
                if hasattr(sqlglot.TokenType, attr):
                    str_types.add(getattr(sqlglot.TokenType, attr))

            for i in range(len(tokens) - 1):
                if tokens[i].token_type in (sqlglot.TokenType.FROM, sqlglot.TokenType.JOIN):
                    j = i + 1
                    while j < len(tokens) and tokens[j].token_type == sqlglot.TokenType.COMMENT:
                        j += 1
                    if j < len(tokens) and tokens[j].token_type in str_types:
                        raise SQLSecurityViolationError(
                            f"Literal string used as table reference in FROM/JOIN (DuckDB replacement scan prohibited): '{tokens[j].text}' (SEC-03)."
                        )
        except errors.TokenError as err:
            raise SQLSecurityViolationError(f"Tokenization error in SQL: {err} (SEC-01).") from err

        for node in parsed.walk():
            if isinstance(node, FILE_IO_NODES):
                raise SQLSecurityViolationError(
                    f"Prohibited file I/O node detected: {type(node).__name__} (SEC-03)."
                )

        for func in parsed.find_all(exp.Func):
            func_name = ""
            if isinstance(func, exp.Anonymous):
                func_name = (func.name or "").lower()
            elif hasattr(func, "sql_name"):
                func_name = func.sql_name().lower()
            elif hasattr(func, "name"):
                func_name = (func.name or "").lower()

            if not func_name and hasattr(func, "this"):
                func_name = str(func.this).lower()

            if func_name in PROHIBITED_FUNCTIONS:
                raise SQLSecurityViolationError(
                    f"Prohibited external function call detected: '{func_name}' (SEC-03)."
                )

        for table in parsed.find_all(exp.Table):
            # Replacement Scan detection: In DuckDB, literal strings as table names trigger file reads
            if isinstance(table.this, exp.Literal):
                raise SQLSecurityViolationError(
                    f"Literal string used as table reference (DuckDB replacement scan prohibited): '{table.sql()}' (SEC-03)."
                )

            tbl_name = (table.name or "").strip()
            tbl_sql = table.sql(dialect="duckdb").strip()
            db_name = (table.db or "").strip()

            # Path separators check or hidden file reference
            if tbl_name.startswith(".") or any(sep in tbl_name or sep in tbl_sql or sep in db_name for sep in ("/", "\\")):
                raise SQLSecurityViolationError(
                    f"Prohibited path separator or hidden file in table reference: '{tbl_name}' (SEC-03)."
                )

            # Prohibited extensions check
            tbl_name_lower = tbl_name.lower()
            tbl_sql_lower = tbl_sql.lower()
            for ext in PROHIBITED_EXTENSIONS:
                if tbl_name_lower.endswith(ext) or ext in tbl_name_lower or tbl_sql_lower.endswith(ext) or ext in tbl_sql_lower:
                    raise SQLSecurityViolationError(
                        f"Prohibited file extension '{ext}' in table reference: '{tbl_name}' (SEC-03)."
                    )

        # SEC-04: Restrição de Schemas e Isolamento de CTEs
        cte_names_set = {
            c.alias_or_name.lower()
            for c in parsed.find_all(exp.CTE)
            if c.alias_or_name
        }
        cte_names_list = sorted(cte_names_set)

        tables_referenced: list[str] = []
        governance_warnings: list[str] = []

        for table in parsed.find_all(exp.Table):
            t_name = (table.name or "").strip()
            if not t_name:
                continue

            schema_name = (table.db or "").strip()
            if not schema_name and t_name.lower() in cte_names_set:
                continue

            full_table_name = f"{schema_name}.{t_name}" if schema_name else t_name

            if full_table_name not in tables_referenced:
                tables_referenced.append(full_table_name)

            if schema_name.lower() != self.default_schema:
                if schema_name:
                    warning = (
                        f"Query references table '{full_table_name}' in schema '{schema_name}' "
                        f"outside recommended '{self.default_schema}' schema."
                    )
                else:
                    warning = (
                        f"Query references table '{full_table_name}' without explicit "
                        f"'{self.default_schema}' schema qualification."
                    )
                if warning not in governance_warnings:
                    governance_warnings.append(warning)

        # SEC-05: Injeção de LIMIT de Segurança
        limit_node = parsed.args.get("limit")
        limit_applied: int | None = None

        if limit_node is None:
            parsed = parsed.limit(max_rows)
            limit_applied = max_rows
        else:
            limit_expr = limit_node.expression if limit_node.expression is not None else limit_node.this
            current_val: int | None = None
            if isinstance(limit_expr, exp.Literal) and limit_expr.is_int:
                try:
                    current_val = int(limit_expr.this)
                except (ValueError, TypeError):
                    current_val = None

            if current_val is None or current_val > max_rows:
                if limit_node.expression is not None:
                    limit_node.set("expression", exp.Literal.number(max_rows))
                else:
                    limit_node.set("this", exp.Literal.number(max_rows))
                limit_applied = max_rows
            else:
                limit_applied = current_val

        sanitized_sql = parsed.sql(dialect="duckdb")

        return GuardrailResult(
            is_safe=True,
            sanitized_sql=sanitized_sql,
            tables_referenced=tables_referenced,
            cte_names=cte_names_list,
            limit_applied=limit_applied,
            governance_warnings=governance_warnings,
        )
