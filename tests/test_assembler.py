from pathlib import Path

from dce.context.assembler import ContextAssembler
from dce.context.loader import load_metadata_catalog
from dce.context.retriever import HybridRetriever
from dce.models import ContextLevel
from dce.warehouse.builder import build_warehouse


def test_context_assembler_levels_and_token_savings(tmp_path: Path):
    db_path = build_warehouse(tmp_path / "wh.duckdb", sample_orders_count=200, seed=42)
    catalog = load_metadata_catalog(Path("metadata"))
    retriever = HybridRetriever(catalog)
    assembler = ContextAssembler(catalog=catalog, retriever=retriever, db_path=db_path)

    q = "Qual a receita realizada dos pedidos entregues em 2018?"
    ctx_l0 = assembler.assemble(q, level=ContextLevel.L0)
    ctx_l1 = assembler.assemble(q, level=ContextLevel.L1)
    ctx_l2 = assembler.assemble(q, level=ContextLevel.L2)
    ctx_l3 = assembler.assemble(q, level=ContextLevel.L3)
    ctx_l4 = assembler.assemble(q, level=ContextLevel.L4, selected_metric_id="net_revenue")

    # Verify all levels instantiate correctly
    assert ctx_l0.level == ContextLevel.L0
    assert ctx_l1.level == ContextLevel.L1
    assert ctx_l2.level == ContextLevel.L2
    assert ctx_l3.level == ContextLevel.L3
    assert ctx_l4.level == ContextLevel.L4

    # Structure checks
    assert ctx_l0.schema_ddl == ""
    assert ctx_l0.few_shot_block == ""
    assert q in ctx_l0.dynamic_suffix

    assert ctx_l1.inspection.token_savings_pct == 0.0
    assert "CREATE TABLE" in ctx_l1.schema_ddl
    assert len(ctx_l1.inspection.selected_tables) >= 15

    # L2 compressed DDL of all 6 marts
    assert "marts.fct_orders" in ctx_l2.schema_ddl
    assert "marts.dim_customers" in ctx_l2.schema_ddl
    assert len(ctx_l2.inspection.selected_tables) == 6

    # L3 includes all canonical metrics and rules
    assert "RN-01" in ctx_l3.static_prefix
    assert len(ctx_l3.inspection.selected_metrics) == len(catalog.metrics)

    # L4 Context Inspection & Token Savings
    assert ctx_l0.inspection.assembled_context_tokens < ctx_l4.inspection.assembled_context_tokens
    assert ctx_l4.inspection.assembled_context_tokens < ctx_l1.inspection.raw_full_schema_tokens
    assert ctx_l4.inspection.token_savings_pct >= 50.0
    assert ctx_l4.inspection.prefix_cacheable_pct > 40.0
    assert "marts.fct_orders" in {t.table_name for t in ctx_l4.inspection.selected_tables}
    assert ctx_l4.static_prefix in ctx_l4.full_prompt
    assert ctx_l4.dynamic_suffix in ctx_l4.full_prompt

    # Inspection report aliases / sync compatibility
    assert ctx_l4.inspection.raw_schema_tokens == ctx_l4.inspection.raw_full_schema_tokens
    assert ctx_l4.inspection.compressed_context_tokens == ctx_l4.inspection.assembled_context_tokens
    assert ctx_l4.inspection.token_reduction_percentage == ctx_l4.inspection.token_savings_pct
    assert ctx_l4.inspection_report == ctx_l4.inspection
    assert ctx_l4.system_prompt == ctx_l4.static_prefix


def test_context_assembler_without_db_path():
    catalog = load_metadata_catalog(Path("metadata"))
    retriever = HybridRetriever(catalog)
    assembler = ContextAssembler(catalog=catalog, retriever=retriever, db_path=None)

    q = "Qual o ticket médio por pedido?"
    ctx_l4 = assembler.assemble(q, level=ContextLevel.L4, selected_metric_id="average_order_value")

    assert ctx_l4.inspection.raw_full_schema_tokens > 3000
    assert ctx_l4.inspection.token_savings_pct >= 50.0
    assert ctx_l4.inspection.prefix_cacheable_pct > 40.0
    assert "marts.fct_orders" in {t.table_name for t in ctx_l4.inspection.selected_tables}


def test_context_assembler_graph_bridge_and_few_shot():
    catalog = load_metadata_catalog(Path("metadata"))
    retriever = HybridRetriever(catalog)
    assembler = ContextAssembler(catalog=catalog, retriever=retriever, db_path=None)

    q = "Qual categoria de produto mais vende para clientes do estado de SP?"
    ctx_l4 = assembler.assemble(q, level=ContextLevel.L4)

    table_names = {t.table_name for t in ctx_l4.inspection.selected_tables}
    assert "marts.dim_products" in table_names
    assert "marts.dim_customers" in table_names
    assert "marts.fct_order_items" in table_names
    assert len(ctx_l4.inspection.few_shot_examples) >= 1
    assert ctx_l4.inspection.latency_ms > 0.0
    assert ctx_l4.inspection.token_budget == 2500

