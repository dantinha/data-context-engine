from pathlib import Path

import duckdb

from dce.models import (
    AssembledContext,
    ClarificationOption,
    ClarificationRequest,
    ContextInspectionReport,
    ContextLevel,
    GeneratedSQLResponse,
    QueryTurnResult,
    RetrievedExampleInfo,
    SavedPlaybook,
    SelectedMetricInfo,
    SelectedTableInfo,
    SQLExecutionResult,
)
from dce.warehouse.builder import build_warehouse
from dce.warehouse.sample_generator import generate_olist_sample


def test_models_contracts():
    """Verify that all core Pydantic models instantiate and validate as expected."""
    opt = ClarificationOption(
        metric_id="net_revenue",
        label="Receita Líquida",
        description="Faturamento realizado",
        business_rule_reference="RN-02",
    )
    req = ClarificationRequest(
        is_ambiguous=True,
        ambiguity_group_id="revenue_group",
        question="Qual foi a receita?",
        options=[opt],
    )
    assert req.is_ambiguous is True
    assert len(req.options) == 1

    report = ContextInspectionReport(
        selected_tables=[
            SelectedTableInfo(
                table_name="fct_orders",
                schema_name="marts",
                columns=["order_id", "total_payment_value"],
                retrieval_reason="faturamento",
            )
        ],
        selected_metrics=[
            SelectedMetricInfo(
                metric_id="net_revenue",
                name="Receita Líquida",
                canonical_sql="SUM(total_payment_value)",
                base_table="marts.fct_orders",
            )
        ],
        few_shot_examples=[
            RetrievedExampleInfo(
                id="ex1",
                question="Quanto faturamos?",
                sql="SELECT SUM(total_payment_value) FROM marts.fct_orders WHERE order_status = 'delivered';",
            )
        ],
        raw_schema_tokens=500,
        compressed_context_tokens=180,
        token_reduction_percentage=64.0,
        latency_ms=12.5,
    )
    assembled = AssembledContext(
        level=ContextLevel.L2,
        system_prompt="Você é um assistente SQL.",
        schema_ddl="CREATE TABLE marts.fct_orders ...",
        semantic_metrics="net_revenue: ...",
        inspection_report=report,
    )
    assert assembled.level == ContextLevel.L2
    assert assembled.inspection_report.token_reduction_percentage == 64.0

    exec_result = SQLExecutionResult(
        query="SELECT 1;",
        success=True,
        columns=["val"],
        rows=[[1]],
        row_count=1,
        execution_time_ms=1.2,
    )
    assert exec_result.success is True

    gen_sql = GeneratedSQLResponse(
        raw_sql="SELECT 1",
        sanitized_sql="SELECT 1",
        reasoning="Simple query",
        confidence=1.0,
    )
    assert gen_sql.confidence == 1.0

    turn = QueryTurnResult(
        question="Quanto faturamos?",
        context_level=ContextLevel.L2,
        assembled_context=assembled,
        generated_sql=gen_sql,
        execution_result=exec_result,
        correction_attempts=0,
    )
    assert turn.correction_attempts == 0

    playbook = SavedPlaybook(
        id="pb-001",
        title="Receita Realizada",
        question="Qual o faturamento?",
        sanitized_sql="SELECT SUM(total_payment_value) FROM marts.fct_orders WHERE order_status = 'delivered';",
        resolved_metric_id="net_revenue",
        used_tables=["marts.fct_orders"],
        created_at="2026-11-08T12:00:00Z",
    )
    assert playbook.id == "pb-001"
    assert playbook.resolved_metric_id == "net_revenue"


def test_sample_generator_determinism():
    """Verify that sample generator produces identical datasets with identical seed."""
    s1 = generate_olist_sample(orders_count=100, seed=42)
    s2 = generate_olist_sample(orders_count=100, seed=42)

    assert set(s1.keys()) == set(s2.keys())
    for key in ["orders", "order_items", "order_payments", "customers", "products", "sellers"]:
        assert len(s1[key]) == len(s2[key])
        assert s1[key].equals(s2[key])


def test_warehouse_schemas_and_natural_traps(tmp_path: Path):
    """Verify warehouse build and compliance with business rules RN-01 through RN-07."""
    db_path = tmp_path / "test_warehouse.duckdb"
    build_warehouse(db_path=db_path, sample_orders_count=600, seed=42)

    con = duckdb.connect(str(db_path), read_only=True)
    schemas = {r[0] for r in con.execute("SELECT schema_name FROM information_schema.schemata").fetchall()}
    assert {"raw", "staging", "marts"}.issubset(schemas)

    # RN-01: clientes com múltiplos customer_id para o mesmo customer_unique_id
    total_orders_cust_ids = con.execute("SELECT COUNT(DISTINCT customer_id) FROM marts.fct_orders").fetchone()[0]
    unique_customers = con.execute("SELECT COUNT(DISTINCT customer_unique_id) FROM marts.dim_customers").fetchone()[0]
    assert total_orders_cust_ids > unique_customers

    # RN-02: presença de pedidos delivered, canceled, unavailable, shipped, invoiced
    statuses = {r[0] for r in con.execute("SELECT DISTINCT order_status FROM marts.fct_orders").fetchall()}
    assert {"delivered", "canceled", "unavailable", "shipped", "invoiced"}.issubset(statuses)

    # RN-03: prevenção de fan-out (PK única em fct_orders mesmo com múltiplos itens e parcelas)
    orders_cnt = con.execute("SELECT COUNT(*), COUNT(DISTINCT order_id) FROM marts.fct_orders").fetchone()
    assert orders_cnt[0] == orders_cnt[1] == 600

    # RN-04: conferência de métricas de valor
    totals = con.execute("""
        SELECT
            SUM(total_items_price),
            SUM(total_freight_value),
            SUM(total_order_value),
            SUM(total_payment_value)
        FROM marts.fct_orders
    """).fetchone()
    assert totals[0] > 0
    assert totals[1] > 0
    assert totals[2] > totals[0]  # items + freight > items
    assert totals[3] > 0

    # RN-05: atrasos de entrega
    delayed_cnt = con.execute("SELECT COUNT(*) FROM marts.fct_orders WHERE is_delayed = TRUE").fetchone()[0]
    assert delayed_cnt > 0

    # Para pedidos entregues sem atraso, delay_days deve ser 0
    ontime_delays = con.execute(
        "SELECT COUNT(*) FROM marts.fct_orders WHERE order_status = 'delivered' AND is_delayed = FALSE AND delay_days != 0"
    ).fetchone()[0]
    assert ontime_delays == 0

    # Para pedidos não entregues, delay_days e delivery_days devem ser NULL
    nondelivered_delays = con.execute(
        "SELECT COUNT(*) FROM marts.fct_orders WHERE order_status != 'delivered' AND (delay_days IS NOT NULL OR delivery_days IS NOT NULL)"
    ).fetchone()[0]
    assert nondelivered_delays == 0

    # RN-06: tradução de categorias sem nulos e presença dos fallbacks
    null_cats = con.execute(
        "SELECT COUNT(*) FROM marts.dim_products WHERE category_name_pt IS NULL OR category_name_en IS NULL"
    ).fetchone()[0]
    assert null_cats == 0

    fallback_cats = con.execute(
        "SELECT COUNT(*) FROM marts.dim_products WHERE category_name_pt = 'nao_informado' AND category_name_en = 'not_informed'"
    ).fetchone()[0]
    assert fallback_cats > 0

    # Check dim_customers attributes
    sample_customer = con.execute(
        "SELECT customer_unique_id, customer_city, customer_state, total_orders, delivered_orders, lifetime_value, avg_ticket, is_repeat_customer FROM marts.dim_customers WHERE total_orders > 1 LIMIT 1"
    ).fetchone()
    assert sample_customer is not None
    assert sample_customer[3] > 1  # total_orders > 1

    # Check dim_sellers attributes
    sample_seller = con.execute(
        "SELECT seller_id, seller_city, seller_state, total_orders_sold, total_items_sold, total_revenue_generated, avg_review_score FROM marts.dim_sellers LIMIT 1"
    ).fetchone()
    assert sample_seller is not None
    assert sample_seller[3] > 0  # total_orders_sold > 0

    # Check fct_order_items and fct_order_payments
    items_cnt = con.execute("SELECT COUNT(*) FROM marts.fct_order_items").fetchone()[0]
    payments_cnt = con.execute("SELECT COUNT(*) FROM marts.fct_order_payments").fetchone()[0]
    assert items_cnt >= 600
    assert payments_cnt >= 600

    con.close()
