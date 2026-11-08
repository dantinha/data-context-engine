from pathlib import Path

import pytest

from dce.context.clarifier import SemanticClarifier
from dce.context.loader import load_metadata_catalog
from dce.context.retriever import HybridRetriever
from dce.models import (
    ClarificationRequest,
    RetrievalBundle,
    SelectedTableInfo,
)


@pytest.fixture
def catalog():
    return load_metadata_catalog(Path("metadata"))


@pytest.fixture
def clarifier(catalog):
    return SemanticClarifier(catalog)


@pytest.fixture
def retriever(catalog):
    return HybridRetriever(catalog)


def test_semantic_clarifier_ambiguity_detection(clarifier):
    """Detect ambiguity in generic 'melhores clientes' question and generate candidate options."""
    question = "Quem são os nossos 10 melhores clientes?"
    res = clarifier.analyze(question)

    assert isinstance(res, ClarificationRequest)
    assert res.needs_clarification is True
    assert res.is_ambiguous is True
    assert res.ambiguity_group_id == "melhor_cliente"
    assert res.question == question
    assert len(res.options) == 3

    option_ids = [opt.metric_id for opt in res.options]
    assert option_ids == ["customer_ltv", "customer_order_count", "customer_avg_ticket"]

    # Verify descriptions and business rule references
    ltv_opt = next(opt for opt in res.options if opt.metric_id == "customer_ltv")
    assert "LTV" in ltv_opt.label or "Lifetime" in ltv_opt.label
    assert ltv_opt.business_rule_reference == "RN-01"


def test_semantic_clarifier_resolution_with_selected_metric(clarifier):
    """When a selected_metric_id is explicitly provided, bypass clarification."""
    question = "Quem são os nossos 10 melhores clientes?"
    res = clarifier.analyze(question, selected_metric_id="customer_ltv")

    assert isinstance(res, ClarificationRequest)
    assert res.needs_clarification is False
    assert res.is_ambiguous is False
    assert res.resolved_metric_id == "customer_ltv"
    assert len(res.options) == 0

    # Invalid metric raises ValueError
    with pytest.raises(ValueError, match="not found|não encontrada"):
        clarifier.analyze(question, selected_metric_id="invalid_metric_xyz")


def test_semantic_clarifier_direct_unambiguous_question(clarifier):
    """Questions specifically mentioning unambiguous metrics resolve without prompting."""
    res_delay = clarifier.analyze("Qual a taxa de atraso na entrega?")
    assert res_delay.needs_clarification is False
    assert res_delay.resolved_metric_id == "delivery_delay_rate"

    res_ltv = clarifier.analyze("Qual o LTV dos clientes?")
    assert res_ltv.needs_clarification is False
    assert res_ltv.resolved_metric_id == "customer_ltv"

    # Completely non-metric general question does not require clarification
    res_general = clarifier.analyze("Quais cidades possuem clientes cadastrados?")
    assert res_general.needs_clarification is False
    assert res_general.resolved_metric_id is None


def test_hybrid_retriever_graph_bridge_expansion(retriever):
    """Disconnected dimensions dim_products and dim_customers must be bridged via fct_order_items."""
    question = "Qual categoria de produto mais vende para clientes do estado de SP?"
    bundle = retriever.retrieve(question, top_k_tables=2)

    assert isinstance(bundle, RetrievalBundle)
    table_names = {t.table_name for t in bundle.selected_tables}

    assert "marts.dim_products" in table_names
    assert "marts.dim_customers" in table_names
    assert "marts.fct_order_items" in table_names

    products_info = next(t for t in bundle.selected_tables if "dim_products" in t.table_name)
    customers_info = next(t for t in bundle.selected_tables if "dim_customers" in t.table_name)
    bridge_info = next(t for t in bundle.selected_tables if "fct_order_items" in t.table_name)

    assert products_info.selection_type == "direct_match"
    assert customers_info.selection_type == "direct_match"
    assert bridge_info.selection_type == "graph_bridge"
    assert "dim_products" in bridge_info.reason and "dim_customers" in bridge_info.reason


def test_hybrid_retriever_metric_selection_and_base_table_priority(retriever):
    """Specifying selected_metric_id guarantees base table priority and metric inclusion."""
    bundle = retriever.retrieve("Qual o faturamento realizado?", selected_metric_id="net_revenue")

    assert bundle.resolved_metric_id == "net_revenue"
    assert any(m.metric_id == "net_revenue" for m in bundle.selected_metrics)

    # Base table marts.fct_orders must be top direct match
    assert len(bundle.selected_tables) >= 1
    top_table = bundle.selected_tables[0]
    assert top_table.table_name == "marts.fct_orders"
    assert top_table.selection_type == "direct_match"


def test_hybrid_retriever_few_shot_ranking(retriever):
    """Few-shot examples matching the resolved metric or tokens must be prioritized and ranked."""
    bundle = retriever.retrieve(
        "Quais são os principais clientes em LTV?",
        selected_metric_id="customer_ltv",
        top_k_examples=2,
    )

    assert len(bundle.few_shot_examples) == 2
    top_example = bundle.few_shot_examples[0]
    assert top_example.resolved_metric_id == "customer_ltv"
    assert top_example.similarity_score >= bundle.few_shot_examples[1].similarity_score


def test_selected_table_info_backwards_compatibility():
    """Ensure SelectedTableInfo supports both new and legacy field names."""
    info = SelectedTableInfo(
        table_name="marts.dim_products",
        schema_name="marts",
        selection_type="direct_match",
        reason="Matched on category",
        columns_included=["product_id", "category_name_pt"],
    )
    assert info.columns_included == ["product_id", "category_name_pt"]
    assert info.columns == ["product_id", "category_name_pt"]
    assert info.reason == "Matched on category"
    assert info.retrieval_reason == "Matched on category"


def test_semantic_clarifier_specific_revenue_metric(clarifier):
    """Even though 'faturamento' is ambiguous, 'faturamento líquido' resolves directly."""
    res = clarifier.analyze("Qual o faturamento líquido total dos pedidos?")
    assert res.needs_clarification is False
    assert res.resolved_metric_id == "net_revenue"


def test_hybrid_retriever_already_connected_tables_no_bridge(retriever):
    """When direct match tables are already directly connected, no graph bridge is added."""
    question = "Quais são os pedidos de clientes de São Paulo?"
    bundle = retriever.retrieve(question, top_k_tables=2)

    table_names = {t.table_name for t in bundle.selected_tables}
    assert "marts.fct_orders" in table_names
    assert "marts.dim_customers" in table_names

    # All tables should be direct_match since fct_orders directly connects to dim_customers
    bridge_tables = [t for t in bundle.selected_tables if t.selection_type == "graph_bridge"]
    assert len(bridge_tables) == 0


def test_hybrid_retriever_seller_customer_bridge(retriever):
    """dim_sellers and dim_customers must be bridged via fct_order_items."""
    question = "Quais vendedores tiveram compras de clientes do estado do Rio de Janeiro?"
    bundle = retriever.retrieve(question, top_k_tables=2)

    table_names = {t.table_name for t in bundle.selected_tables}
    assert "marts.dim_sellers" in table_names
    assert "marts.dim_customers" in table_names
    assert "marts.fct_order_items" in table_names

    bridge = next(t for t in bundle.selected_tables if t.selection_type == "graph_bridge")
    assert "fct_order_items" in bridge.table_name
    assert "dim_sellers" in bridge.reason and "dim_customers" in bridge.reason


def test_hybrid_retriever_with_saved_playbooks(retriever, tmp_path, monkeypatch):
    """Retrieval includes saved playbooks when present."""
    import json

    playbooks_dir = tmp_path / "data" / "playbooks"
    playbooks_dir.mkdir(parents=True, exist_ok=True)
    pb_file = playbooks_dir / "saved_playbooks.json"

    dummy_playbooks = [
        {
            "id": "pb_test_01",
            "title": "Clientes VIP por LTV",
            "question": "Quais são os clientes com maior LTV acumulado?",
            "sanitized_sql": "SELECT * FROM marts.dim_customers ORDER BY lifetime_value DESC LIMIT 10;",
            "resolved_metric_id": "customer_ltv",
            "used_tables": ["marts.dim_customers"],
        }
    ]
    pb_file.write_text(json.dumps(dummy_playbooks), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    bundle = retriever.retrieve(
        "Quais clientes tem maior LTV?",
        selected_metric_id="customer_ltv",
        include_user_playbooks=True,
    )

    origins = {ex.origin for ex in bundle.few_shot_examples}
    assert "saved_playbook" in origins
