from pathlib import Path

import pytest

from dce.mcp_server import create_dce_mcp_tools, create_mcp_server
from dce.warehouse.builder import build_warehouse


def test_all_seven_mcp_tools_end_to_end(tmp_path: Path):
    db_path = build_warehouse(tmp_path / "wh.duckdb", sample_orders_count=200, seed=42)
    tools = create_dce_mcp_tools(db_path=db_path, playbooks_path=tmp_path / "playbooks.json")

    # Tool 1: Clarify & Assemble (ambiguous vs resolved)
    ambig = tools.clarify_and_assemble_context("Quem são os melhores clientes?")
    assert ambig["needs_clarification"] is True
    assert ambig["agent_directive"] == "STOP_AND_ASK_USER"
    assert len(ambig["options"]) > 0

    assembled = tools.clarify_and_assemble_context(
        "Quem são os melhores clientes?", selected_metric_id="customer_ltv"
    )
    assert assembled["needs_clarification"] is False
    assert assembled["agent_directive"] == "PROCEED"
    assert assembled["inspection"]["token_savings_pct"] >= 50.0

    # Tool 2, 3, 4: Search, Metric, Describe Table
    search_res = tools.search_warehouse_context("atraso na entrega por categoria")
    assert len(search_res["tables"]) > 0
    assert "metrics" in search_res
    assert "forbidden_joins" in search_res

    metric_res = tools.get_canonical_metric("net_revenue")
    assert metric_res["id"] == "net_revenue"

    all_metrics = tools.get_canonical_metric("*")
    assert isinstance(all_metrics, list) or "metrics" in all_metrics

    table_res = tools.describe_mart_table("fct_orders", sample_rows=2)
    assert len(table_res["sample_data"]) == 2
    assert "columns" in table_res

    # Also test describe_mart_table with 'marts.' prefix
    table_res_prefix = tools.describe_mart_table("marts.fct_orders", sample_rows=2)
    assert len(table_res_prefix["sample_data"]) == 2

    # Tool 5 & 6: Save & List Playbooks
    saved = tools.save_verified_playbook(
        title="Receita por Estado",
        question="Qual a receita por estado?",
        sql_query="SELECT customer_state, SUM(lifetime_value) AS rev FROM marts.dim_customers GROUP BY 1",
        resolved_metric_id="net_revenue",
    )
    assert saved["id"]
    assert len(tools.list_saved_playbooks()) == 1

    # Tool 7: Execute Safe SQL (with default max_rows=100)
    exec_res = tools.execute_safe_sql("SELECT order_status, COUNT(*) AS cnt FROM marts.fct_orders GROUP BY 1")
    assert exec_res["success"] is True
    assert exec_res["ast_verified"] is True
    assert exec_res["row_count"] > 0

    # Execute Safe SQL blocking malicious attempt
    malicious_res = tools.execute_safe_sql("DROP TABLE marts.fct_orders")
    assert malicious_res["success"] is False
    assert malicious_res["ast_verified"] is False


@pytest.mark.anyio
async def test_mcp_server_instance_registration(tmp_path: Path):
    db_path = build_warehouse(tmp_path / "wh.duckdb", sample_orders_count=50, seed=42)
    server = create_mcp_server(db_path=db_path, playbooks_path=tmp_path / "playbooks.json")

    tool_list = await server.list_tools()
    tool_names = [t.name for t in tool_list]
    expected_tools = [
        "clarify_and_assemble_context",
        "search_warehouse_context",
        "get_canonical_metric",
        "describe_mart_table",
        "list_saved_playbooks",
        "save_verified_playbook",
        "execute_safe_sql",
    ]
    for expected in expected_tools:
        assert expected in tool_names
