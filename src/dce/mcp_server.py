"""FastMCP Server providing 7 tools for LLM agents to interact with the Data Context Engine."""

import argparse
import sys
from pathlib import Path
from typing import Any

from dce.context.assembler import ContextAssembler
from dce.context.clarifier import SemanticClarifier
from dce.context.loader import load_metadata_catalog
from dce.context.retriever import HybridRetriever
from dce.execution.executor import SafeSQLExecutor
from dce.models import ContextLevel
from dce.playbooks.store import PlaybookStore

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP as MCPServer
    except ImportError:
        from mcp.server import MCPServer  # type: ignore


class DCEToolsContainer:
    """Encapsulates the 7 Data Context Engine tools for programmatic and MCP server usage."""

    def __init__(
        self,
        db_path: Path | str,
        playbooks_path: Path | str = Path("data/playbooks/saved_playbooks.json"),
        metadata_dir: Path | str = Path("metadata"),
    ) -> None:
        self.db_path = Path(db_path)
        self.playbooks_path = Path(playbooks_path)
        self.metadata_dir = Path(metadata_dir)

        self.catalog = load_metadata_catalog(self.metadata_dir)
        self.retriever = HybridRetriever(
            catalog=self.catalog,
            playbooks_path=self.playbooks_path,
        )
        self.clarifier = SemanticClarifier(catalog=self.catalog)
        self.executor = SafeSQLExecutor(db_path=self.db_path)
        self.store = PlaybookStore(
            storage_path=self.playbooks_path,
            retriever=self.retriever,
            executor=self.executor,
        )
        self.assembler = ContextAssembler(
            catalog=self.catalog,
            retriever=self.retriever,
            db_path=self.db_path,
        )

    def clarify_and_assemble_context(
        self,
        question: str,
        selected_metric_id: str | None = None,
        level: str = "L4",
    ) -> dict[str, Any]:
        """Disambiguate questions against business metrics and assemble minimal token context."""
        clarif = self.clarifier.analyze(question, selected_metric_id=selected_metric_id)
        if clarif.needs_clarification and not selected_metric_id:
            return {
                "needs_clarification": True,
                "agent_directive": "STOP_AND_ASK_USER",
                "clarification_message": clarif.clarification_message or clarif.message,
                "options": [opt.model_dump() for opt in clarif.options],
                "question": question,
            }

        lvl = ContextLevel(level) if isinstance(level, str) else level
        resolved_metric = selected_metric_id or clarif.resolved_metric_id
        assembled = self.assembler.assemble(
            question=question,
            level=lvl,
            selected_metric_id=resolved_metric,
        )
        return {
            "needs_clarification": False,
            "agent_directive": "PROCEED",
            "static_prefix": assembled.static_prefix,
            "dynamic_suffix": assembled.dynamic_suffix,
            "full_prompt": assembled.full_prompt,
            "inspection": assembled.inspection.model_dump(),
        }

    def search_warehouse_context(
        self,
        query: str,
        top_k_per_category: int = 3,
    ) -> dict[str, Any]:
        """Retrieve relevant marts tables, canonical metrics, and few-shot examples."""
        bundle = self.retriever.retrieve(
            query,
            top_k_tables=top_k_per_category,
            top_k_examples=top_k_per_category,
        )
        return {
            "tables": [t.model_dump() for t in bundle.selected_tables],
            "metrics": [m.model_dump() for m in bundle.selected_metrics],
            "examples": [e.model_dump() for e in bundle.few_shot_examples],
            "forbidden_joins": [f.model_dump() for f in self.catalog.semantic_layer.forbidden_joins],
        }

    def get_canonical_metric(self, metric_id: str) -> dict[str, Any]:
        """Fetch canonical business formula, required filters, and SQL definitions."""
        if metric_id == "*":
            return {"metrics": [m.model_dump() for m in self.catalog.metrics]}

        metric = self.catalog.get_metric(metric_id)
        if metric is not None:
            return metric.model_dump()
        return {"error": f"Metric '{metric_id}' not found in semantic catalog."}

    def describe_mart_table(self, table_name: str, sample_rows: int = 3) -> dict[str, Any]:
        """Inspect schema, primary keys, and sample records of an analytical mart table."""
        clean_name = table_name.strip()
        if clean_name.startswith("marts."):
            clean_name = clean_name.replace("marts.", "", 1)

        table = self.catalog.get_table(f"marts.{clean_name}") or self.catalog.get_table(clean_name)
        safe_limit = max(1, min(sample_rows, 50))
        exec_res = self.executor.execute(f"SELECT * FROM marts.{clean_name} LIMIT {safe_limit}")

        return {
            "table_name": table.name if table else clean_name,
            "schema_name": table.schema_name if table else "marts",
            "description": table.description if table else "",
            "primary_key": table.primary_key if table else None,
            "columns": [col.model_dump() for col in table.columns] if table else [],
            "sample_data": exec_res.rows,
            "columns_returned": exec_res.columns,
        }

    def list_saved_playbooks(self, tag: str | None = None) -> list[dict[str, Any]]:
        """List verified analytical SQL procedures saved by analysts or agents."""
        playbooks = self.store.list_playbooks(tag=tag)
        return [pb.model_dump() for pb in playbooks]

    def save_verified_playbook(
        self,
        title: str,
        question: str,
        sql_query: str,
        resolved_metric_id: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Save and index an audited SQL query into persistent few-shot memory."""
        pb = self.store.save_playbook(
            title=title,
            question=question,
            sql_query=sql_query,
            resolved_metric_id=resolved_metric_id,
            tags=tags,
        )
        return pb.model_dump()

    def execute_safe_sql(self, sql_query: str, max_rows: int = 100) -> dict[str, Any]:
        """Execute read-only SQL with AST security guardrails against the DuckDB sandbox."""
        exec_res = self.executor.execute(sql_query, max_rows=max_rows)
        return {
            "success": exec_res.success,
            "ast_verified": not exec_res.security_violation,
            "columns": exec_res.columns,
            "rows": exec_res.rows[:max_rows],
            "row_count": len(exec_res.rows[:max_rows]),
            "execution_time_ms": exec_res.execution_time_ms,
            "tables_referenced": exec_res.tables_referenced,
            "governance_warnings": exec_res.governance_warnings,
            "error_message": exec_res.error_message,
        }


def create_dce_mcp_tools(
    db_path: Path | str,
    playbooks_path: Path | str = Path("data/playbooks/saved_playbooks.json"),
    metadata_dir: Path | str = Path("metadata"),
) -> DCEToolsContainer:
    """Factory creating a DCEToolsContainer instance."""
    return DCEToolsContainer(
        db_path=db_path,
        playbooks_path=playbooks_path,
        metadata_dir=metadata_dir,
    )


def create_mcp_server(
    db_path: Path | str,
    playbooks_path: Path | str = Path("data/playbooks/saved_playbooks.json"),
    metadata_dir: Path | str = Path("metadata"),
) -> Any:
    """Creates and configures an MCP server exposing all 7 Data Context Engine tools."""
    container = create_dce_mcp_tools(
        db_path=db_path,
        playbooks_path=playbooks_path,
        metadata_dir=metadata_dir,
    )
    server = MCPServer("data-context-engine")

    @server.tool()
    def clarify_and_assemble_context(
        question: str,
        selected_metric_id: str | None = None,
        level: str = "L4",
    ) -> dict[str, Any]:
        """Disambiguate questions against business metrics and assemble minimal token context."""
        return container.clarify_and_assemble_context(
            question=question,
            selected_metric_id=selected_metric_id,
            level=level,
        )

    @server.tool()
    def search_warehouse_context(query: str, top_k_per_category: int = 3) -> dict[str, Any]:
        """Retrieve relevant marts tables, canonical metrics, and few-shot examples."""
        return container.search_warehouse_context(query=query, top_k_per_category=top_k_per_category)

    @server.tool()
    def get_canonical_metric(metric_id: str) -> dict[str, Any]:
        """Fetch canonical business formula, required filters, and SQL definitions."""
        return container.get_canonical_metric(metric_id=metric_id)

    @server.tool()
    def describe_mart_table(table_name: str, sample_rows: int = 3) -> dict[str, Any]:
        """Inspect schema, primary keys, and sample records of an analytical mart table."""
        return container.describe_mart_table(table_name=table_name, sample_rows=sample_rows)

    @server.tool()
    def list_saved_playbooks(tag: str | None = None) -> list[dict[str, Any]]:
        """List verified analytical SQL procedures saved by analysts or agents."""
        return container.list_saved_playbooks(tag=tag)

    @server.tool()
    def save_verified_playbook(
        title: str,
        question: str,
        sql_query: str,
        resolved_metric_id: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Save and index an audited SQL query into persistent few-shot memory."""
        return container.save_verified_playbook(
            title=title,
            question=question,
            sql_query=sql_query,
            resolved_metric_id=resolved_metric_id,
            tags=tags,
        )

    @server.tool()
    def execute_safe_sql(sql_query: str, max_rows: int = 100) -> dict[str, Any]:
        """Execute read-only SQL with AST security guardrails against the DuckDB sandbox."""
        return container.execute_safe_sql(sql_query=sql_query, max_rows=max_rows)

    return server


def main() -> None:
    """CLI entrypoint for running the MCP server over stdio."""
    parser = argparse.ArgumentParser(description="Data Context Engine FastMCP Server")
    parser.add_argument("--db-path", default="wh.duckdb", help="Path to DuckDB warehouse")
    parser.add_argument(
        "--playbooks-path",
        default="data/playbooks/saved_playbooks.json",
        help="Path to saved playbooks store",
    )
    parser.add_argument(
        "--metadata-dir",
        default="metadata",
        help="Directory containing YAML metadata",
    )
    args = parser.parse_args()

    server = create_mcp_server(
        db_path=args.db_path,
        playbooks_path=args.playbooks_path,
        metadata_dir=args.metadata_dir,
    )
    try:
        server.run(transport="stdio")
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
