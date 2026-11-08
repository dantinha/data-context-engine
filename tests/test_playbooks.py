from pathlib import Path

import pytest

from dce.context.clarifier import SemanticClarifier
from dce.context.loader import load_metadata_catalog
from dce.context.retriever import HybridRetriever
from dce.execution.executor import SafeSQLExecutor
from dce.execution.guardrails import SQLSecurityViolationError
from dce.playbooks.store import PlaybookStore
from dce.warehouse.builder import build_warehouse


def test_saving_playbook_persists_hot_reloads_retriever_and_skips_reclarification(tmp_path: Path):
    db_path = build_warehouse(tmp_path / "wh.duckdb", sample_orders_count=200, seed=42)
    catalog = load_metadata_catalog(Path("metadata"))
    retriever = HybridRetriever(catalog)
    clarifier = SemanticClarifier(catalog)
    executor = SafeSQLExecutor(db_path)
    store = PlaybookStore(
        storage_path=tmp_path / "saved_playbooks.json",
        retriever=retriever,
        executor=executor,
    )

    pb = store.save_playbook(
        title="Top 5 Clientes por LTV em SP",
        question="Quem são os melhores clientes de SP?",
        sql_query="SELECT customer_unique_id, lifetime_value FROM marts.dim_customers WHERE customer_state = 'SP' ORDER BY lifetime_value DESC LIMIT 5",
        resolved_metric_id="customer_ltv",
        tags=["clientes", "vip"],
    )
    assert pb.tables_used == ["marts.dim_customers"]
    assert pb.used_tables == ["marts.dim_customers"]
    assert pb.sql_query != ""
    assert pb.sanitized_sql != ""

    # 1. Ao reexecutar o Playbook salvo, passa resolved_metric_id e NÃO pede clarificação de novo
    clarification = clarifier.analyze(pb.question, selected_metric_id=pb.resolved_metric_id)
    assert clarification.needs_clarification is False

    # 2. Hot-reload no HybridRetriever: consulta com include_user_playbooks=True recupera o Playbook salvo
    bundle_ui = retriever.retrieve("Quais os melhores clientes do estado de RJ?", include_user_playbooks=True)
    assert any(ex.source == "saved_playbook" and ex.id == pb.id for ex in bundle_ui.retrieved_examples)

    # 3. Isolamento do Benchmark: include_user_playbooks=False ignora Playbooks da UI
    bundle_bench = retriever.retrieve("Quais os melhores clientes do estado de RJ?", include_user_playbooks=False)
    assert all(ex.source == "static_few_shot" for ex in bundle_bench.retrieved_examples)


def test_list_playbooks_tag_filtering_and_empty(tmp_path: Path):
    store = PlaybookStore(
        storage_path=tmp_path / "saved_playbooks.json",
    )
    # File does not exist yet
    assert store.list_playbooks() == []
    assert store.list_playbooks(tag="vip") == []

    pb1 = store.save_playbook(
        title="Playbook 1",
        question="Pergunta 1",
        sql_query="SELECT customer_city FROM marts.dim_customers LIMIT 10",
        tags=["clientes", "vip"],
    )
    pb2 = store.save_playbook(
        title="Playbook 2",
        question="Pergunta 2",
        sql_query="SELECT total_orders FROM marts.dim_customers LIMIT 10",
        tags=["pedidos", "financeiro"],
    )
    pb3 = store.save_playbook(
        title="Playbook 3",
        question="Pergunta 3",
        sql_query="SELECT lifetime_value FROM marts.dim_customers LIMIT 10",
        tags=["vip", "marketing"],
    )

    all_pbs = store.list_playbooks()
    assert len(all_pbs) == 3
    assert {p.id for p in all_pbs} == {pb1.id, pb2.id, pb3.id}

    vip_pbs = store.list_playbooks(tag="vip")
    assert len(vip_pbs) == 2
    assert {p.id for p in vip_pbs} == {pb1.id, pb3.id}

    fin_pbs = store.list_playbooks(tag="financeiro")
    assert len(fin_pbs) == 1
    assert fin_pbs[0].id == pb2.id

    assert store.list_playbooks(tag="inexistente") == []


def test_get_and_delete_playbook(tmp_path: Path):
    store = PlaybookStore(
        storage_path=tmp_path / "saved_playbooks.json",
    )

    pb = store.save_playbook(
        title="Playbook Test",
        question="Pergunta Test",
        sql_query="SELECT * FROM marts.dim_customers LIMIT 5",
        resolved_metric_id="customer_ltv",
        tags=["teste"],
    )

    retrieved = store.get_playbook(pb.id)
    assert retrieved is not None
    assert retrieved.id == pb.id
    assert retrieved.title == "Playbook Test"
    assert retrieved.resolved_metric_id == "customer_ltv"
    assert retrieved.tags == ["teste"]

    assert store.get_playbook("pb_inexistente") is None

    # Delete
    assert store.delete_playbook(pb.id) is True
    assert store.get_playbook(pb.id) is None
    assert store.list_playbooks() == []

    # Second delete returns False
    assert store.delete_playbook(pb.id) is False


def test_few_shot_anti_pollution_between_ambiguity_group_metrics(tmp_path: Path):
    catalog = load_metadata_catalog(Path("metadata"))
    retriever = HybridRetriever(catalog)
    store = PlaybookStore(
        storage_path=tmp_path / "saved_playbooks.json",
        retriever=retriever,
    )

    pb_ltv = store.save_playbook(
        title="Melhores Clientes por LTV",
        question="Quem são os melhores clientes?",
        sql_query="SELECT customer_unique_id, lifetime_value FROM marts.dim_customers ORDER BY lifetime_value DESC LIMIT 5",
        resolved_metric_id="customer_ltv",
        tags=["ltv"],
    )
    pb_orders = store.save_playbook(
        title="Melhores Clientes por Pedidos",
        question="Quem são os melhores clientes?",
        sql_query="SELECT customer_unique_id, total_orders FROM marts.dim_customers ORDER BY total_orders DESC LIMIT 5",
        resolved_metric_id="customer_order_count",
        tags=["pedidos"],
    )

    # Verify JSON content has enriched [Critério: ...] in indexed question when loaded
    bundle_ltv = retriever.retrieve(
        "Quem são os melhores clientes?",
        selected_metric_id="customer_ltv",
        include_user_playbooks=True,
    )
    top_ex_ltv = bundle_ltv.retrieved_examples[0]
    assert top_ex_ltv.id == pb_ltv.id
    assert top_ex_ltv.resolved_metric_id == "customer_ltv"

    bundle_orders = retriever.retrieve(
        "Quem são os melhores clientes?",
        selected_metric_id="customer_order_count",
        include_user_playbooks=True,
    )
    top_ex_orders = bundle_orders.retrieved_examples[0]
    assert top_ex_orders.id == pb_orders.id
    assert top_ex_orders.resolved_metric_id == "customer_order_count"


def test_playbook_store_blocks_malicious_query(tmp_path: Path):
    store = PlaybookStore(
        storage_path=tmp_path / "saved_playbooks.json",
    )

    with pytest.raises(SQLSecurityViolationError):
        store.save_playbook(
            title="Malicious Playbook",
            question="Drop table",
            sql_query="DROP TABLE marts.dim_customers",
        )

    # Ensure nothing persisted
    assert store.list_playbooks() == []


def test_playbook_store_ast_fallback_without_executor(tmp_path: Path):
    store = PlaybookStore(
        storage_path=tmp_path / "saved_playbooks.json",
        retriever=None,
        executor=None,
    )

    pb = store.save_playbook(
        title="Top Sellers",
        question="Quais os principais sellers?",
        sql_query="SELECT seller_id, total_revenue_generated FROM marts.dim_sellers ORDER BY total_revenue_generated DESC LIMIT 10",
    )
    assert pb.tables_used == ["marts.dim_sellers"]
    assert pb.verified is True
    assert pb.created_at != ""


def test_playbook_store_disk_edge_cases_corrupt_and_empty(tmp_path: Path):
    """Testa resiliência de leitura quando o arquivo JSON estiver corrompido ou vazio."""
    storage_file = tmp_path / "deep" / "nested" / "saved_playbooks.json"
    store = PlaybookStore(storage_path=storage_file)

    # 1. Diretório profundamente aninhado criado automaticamente
    assert storage_file.parent.exists()
    assert store.list_playbooks() == []

    # 2. Arquivo vazio (0 bytes)
    storage_file.write_text("", encoding="utf-8")
    assert store.list_playbooks() == []

    # 3. JSON corrompido / truncado
    storage_file.write_text('{"invalid_json": [true, ', encoding="utf-8")
    assert store.list_playbooks() == []

    # 4. JSON válido mas não é lista
    storage_file.write_text('{"message": "not a list"}', encoding="utf-8")
    assert store.list_playbooks() == []

    # 5. Recuperação: salvar novo playbook sobrescreve o arquivo corrompido com sucesso
    pb = store.save_playbook(
        title="Recovered Playbook",
        question="Qual o total de pedidos?",
        sql_query="SELECT COUNT(*) AS total FROM marts.fct_orders",
    )
    assert len(store.list_playbooks()) == 1
    assert store.get_playbook(pb.id) is not None


def test_playbook_store_query_edge_cases(tmp_path: Path):
    """Testa edge cases de queries SQL: sem tabelas, comentários, UTF-8 e rejeição de sintaxe inválida."""
    store = PlaybookStore(storage_path=tmp_path / "saved_playbooks.json")

    # 1. Query sem tabelas (ex: SELECT 1)
    pb_no_tables = store.save_playbook(
        title="Query Sem Tabelas",
        question="Apenas um ping de verificação",
        sql_query="SELECT 1 AS status",
    )
    assert pb_no_tables.tables_used == []
    assert "SELECT 1" in pb_no_tables.sanitized_sql

    # 2. Query com comentários e caracteres UTF-8 (acentos em português)
    sql_utf8 = (
        "-- Query de verificação de clientes de São Paulo\n"
        "SELECT customer_city, 'São Paulo - Capital' AS regiao "
        "FROM marts.dim_customers WHERE customer_state = 'SP'"
    )
    pb_utf8 = store.save_playbook(
        title="Clientes de São Paulo",
        question="Onde estão os clientes de SP com descrição regional?",
        sql_query=sql_utf8,
        tags=["região", "são_paulo"],
    )
    assert pb_utf8.tables_used == ["marts.dim_customers"]
    assert "são_paulo" in pb_utf8.tags

    # 3. Múltiplos statements devem falhar por violação de segurança (SEC-01)
    with pytest.raises(SQLSecurityViolationError):
        store.save_playbook(
            title="Batch Statements",
            question="Tentativa de executar duas queries",
            sql_query="SELECT 1; SELECT 2;",
        )

    # 4. Query com erro crasso de sintaxe SQL deve falhar
    with pytest.raises(SQLSecurityViolationError):
        store.save_playbook(
            title="Malformed SQL",
            question="Query com sintaxe corrompida",
            sql_query="SELECT FROM WHERE GROUP BY",
        )


def test_benchmark_leakage_strict_isolation_even_with_exact_question_match(tmp_path: Path):
    """Garante isolamento absoluto do benchmark mesmo com match léxico 100% idêntico."""
    catalog = load_metadata_catalog(Path("metadata"))
    retriever = HybridRetriever(catalog)
    store = PlaybookStore(
        storage_path=tmp_path / "saved_playbooks.json",
        retriever=retriever,
    )

    exact_question = "Qual o faturamento total da empresa?"
    pb = store.save_playbook(
        title="Faturamento Total Playbook",
        question=exact_question,
        sql_query="SELECT SUM(total_item_value) AS total_revenue FROM marts.fct_order_items",
        resolved_metric_id="gross_revenue",
    )

    # Com include_user_playbooks=True -> Retorna o playbook do usuário
    bundle_ui = retriever.retrieve(
        exact_question,
        selected_metric_id="gross_revenue",
        include_user_playbooks=True,
    )
    assert any(ex.id == pb.id for ex in bundle_ui.retrieved_examples)

    # Com include_user_playbooks=False (Benchmark) -> Exclui estritamente mesmo com 100% de similaridade
    bundle_bench = retriever.retrieve(
        exact_question,
        selected_metric_id="gross_revenue",
        include_user_playbooks=False,
    )
    assert not any(ex.id == pb.id for ex in bundle_bench.retrieved_examples)
    assert all(ex.source == "static_few_shot" for ex in bundle_bench.retrieved_examples)

