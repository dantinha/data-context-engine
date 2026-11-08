from pathlib import Path

import pytest

from dce.context.loader import load_metadata_catalog


def test_metadata_catalog_completeness():
    catalog = load_metadata_catalog(Path("metadata"))
    mart_tables = {t.name for t in catalog.tables if t.schema_name == "marts"}
    assert mart_tables == {
        "marts.fct_orders",
        "marts.fct_order_items",
        "marts.fct_order_payments",
        "marts.dim_customers",
        "marts.dim_products",
        "marts.dim_sellers",
    }
    assert len(catalog.metrics) >= 10
    assert len(catalog.ambiguity_groups) >= 4
    assert len(catalog.business_rules) == 7
    assert any(
        j.from_table == "marts.fct_order_items" and j.to_table == "marts.dim_customers"
        for j in catalog.allowed_joins
    )
    assert len(catalog.forbidden_joins) >= 2
    assert len(catalog.few_shot_examples) >= 8


def test_metadata_catalog_helper_methods():
    catalog = load_metadata_catalog(Path("metadata"))

    # Test get_table with and without schema prefix
    table_full = catalog.get_table("marts.fct_orders")
    assert table_full is not None
    assert table_full.name == "marts.fct_orders"

    table_short = catalog.get_table("fct_orders")
    assert table_short is not None
    assert table_short.name == "marts.fct_orders"

    assert catalog.get_table("unknown_table") is None

    # Test get_metric
    metric = catalog.get_metric("net_revenue")
    assert metric is not None
    assert metric.id == "net_revenue"
    assert metric.base_table == "marts.fct_orders"
    assert catalog.get_metric("non_existent_metric") is None

    # Test find_ambiguity_group
    group = catalog.find_ambiguity_group("melhor cliente")
    assert group is not None
    assert group.id == "melhor_cliente"
    assert "customer_ltv" in group.candidate_metrics

    group_faturamento = catalog.find_ambiguity_group("faturamento")
    assert group_faturamento is not None
    assert group_faturamento.id == "faturamento_receita"

    assert catalog.find_ambiguity_group("termo_completamente_aleatorio") is None


def test_table_columns_and_schema():
    catalog = load_metadata_catalog(Path("metadata"))
    fct_orders = catalog.get_table("marts.fct_orders")
    assert fct_orders is not None
    assert fct_orders.schema_name == "marts"
    col_names = {c.name for c in fct_orders.columns}
    assert "order_id" in col_names
    assert "total_order_value" in col_names
    assert "is_delayed" in col_names

    pk_cols = [c.name for c in fct_orders.columns if c.is_primary_key]
    assert "order_id" in pk_cols

    dim_products = catalog.get_table("marts.dim_products")
    assert dim_products is not None
    p_col_names = {c.name for c in dim_products.columns}
    assert "category_name_pt" in p_col_names
    assert "category_name_en" in p_col_names


def test_semantic_layer_rules_and_relationships():
    catalog = load_metadata_catalog(Path("metadata"))

    # Check 7 business rules RN-01 to RN-07
    rule_ids = {r.id for r in catalog.business_rules}
    for expected_id in ["RN-01", "RN-02", "RN-03", "RN-04", "RN-05", "RN-06", "RN-07"]:
        assert expected_id in rule_ids

    # Check forbidden joins
    forbidden_pairs = {(fj.from_table, fj.to_table) for fj in catalog.forbidden_joins}
    assert ("marts.fct_order_items", "marts.fct_order_payments") in forbidden_pairs
    assert ("marts.fct_orders", "marts.dim_customers") in forbidden_pairs


def test_few_shot_examples_structure():
    catalog = load_metadata_catalog(Path("metadata"))
    assert len(catalog.few_shot_examples) >= 8

    for ex in catalog.few_shot_examples:
        assert ex.id
        assert ex.question
        assert "SELECT" in ex.sql.upper()
        assert "marts." in ex.sql
        assert len(ex.tables_used) > 0
        assert ex.explanation


def test_metadata_catalog_missing_dir():
    with pytest.raises(FileNotFoundError):
        load_metadata_catalog(Path("non_existent_metadata_dir"))

