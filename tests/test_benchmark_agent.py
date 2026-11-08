from decimal import Decimal
from pathlib import Path

import yaml

from dce.benchmark.comparator import ComparisonResult, ResultComparator
from dce.benchmark.runner import BenchmarkRunner, verify_no_prompt_leakage
from dce.context.assembler import ContextAssembler
from dce.context.loader import load_metadata_catalog
from dce.context.retriever import HybridRetriever
from dce.execution.agent import SQLAgent
from dce.execution.executor import SafeSQLExecutor
from dce.models import ContextLevel, QueryTurnResult
from dce.warehouse.builder import build_warehouse


def test_result_comparator_handles_decimal_float_and_column_permutation():
    """Validates matching between Decimal and float with column permutations and row ordering."""
    comparator = ResultComparator()

    gold_rows = [
        {"seller_id": "s_01", "revenue": Decimal("1540.50"), "order_count": 12},
        {"seller_id": "s_02", "revenue": Decimal("980.25"), "order_count": 8},
        {"seller_id": "s_03", "revenue": Decimal("450.00"), "order_count": 3},
    ]

    # gen_rows has different column ordering, different row ordering, float instead of Decimal, and different alias
    gen_rows = [
        {"total_revenue": 980.2501, "orders": 8, "vendedor": "s_02"},
        {"total_revenue": 450.0, "orders": 3, "vendedor": "s_03"},
        {"total_revenue": 1540.499, "orders": 12, "vendedor": "s_01"},
    ]

    result = comparator.compare(gold_rows, gen_rows, atol=1e-2, rtol=1e-2)
    assert isinstance(result, ComparisonResult)
    assert result.is_match is True
    assert result.rows_compared == 3
    assert result.matched_columns == 3


def test_result_comparator_detects_mismatch():
    """Validates that ResultComparator detects row count, value, and column count mismatches."""
    comparator = ResultComparator()

    gold_rows = [{"val": 10.0}]
    gen_wrong_val = [{"val": 20.0}]
    gen_diff_len = [{"val": 10.0}, {"val": 20.0}]

    assert comparator.compare(gold_rows, gen_wrong_val).is_match is False
    assert comparator.compare(gold_rows, gen_diff_len).is_match is False


def test_gold_questions_integrity():
    """Validates that benchmarks/gold_questions.yml satisfies all 30 question specs and trap coverage."""
    gold_path = Path("benchmarks/gold_questions.yml")
    assert gold_path.exists(), "benchmarks/gold_questions.yml must exist"

    with open(gold_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    questions = data.get("gold_questions", [])
    assert len(questions) == 30, f"Expected exactly 30 questions, found {len(questions)}"

    difficulties = [q.get("difficulty") for q in questions]
    assert difficulties.count("easy") == 10
    assert difficulties.count("medium") == 10
    assert difficulties.count("hard") == 10

    all_traps = set()
    for q in questions:
        assert q.get("id"), "Question must have an id"
        assert q.get("question"), "Question must have question text"
        assert q.get("gold_sql"), "Question must have gold_sql"
        traps = q.get("trap_tags", [])
        assert len(traps) > 0, f"Question {q['id']} must have at least one trap tag"
        all_traps.update(traps)

    # Validate that all 7 natural traps RN-01 through RN-07 are covered
    expected_traps = {f"RN-0{i}" for i in range(1, 8)}
    assert expected_traps.issubset(all_traps), f"Missing trap tags: {expected_traps - all_traps}"


def test_no_leakage_between_gold_questions_and_few_shot_pool():
    """Validates total absence of leakage between gold_questions.yml and few_shot_examples.yml."""
    gold_path = Path("benchmarks/gold_questions.yml")
    few_shot_path = Path("metadata/few_shot_examples.yml")

    assert gold_path.exists(), "benchmarks/gold_questions.yml must exist"
    assert few_shot_path.exists(), "metadata/few_shot_examples.yml must exist"

    is_leakage_free = verify_no_prompt_leakage(gold_path, few_shot_path)
    assert is_leakage_free is True


def test_sql_agent_replay_cache_and_self_correction(tmp_path: Path):
    """Validates SQLAgent deterministic caching, self-correction retry and turn outputs."""
    db_path = tmp_path / "test_agent.duckdb"
    build_warehouse(db_path=db_path, sample_orders_count=100, seed=42)

    cache_dir = tmp_path / "cache"
    catalog = load_metadata_catalog(Path("metadata"))
    retriever = HybridRetriever(catalog)
    assembler = ContextAssembler(catalog=catalog, retriever=retriever, db_path=db_path)
    executor = SafeSQLExecutor(db_path=db_path)

    agent = SQLAgent(
        catalog=catalog,
        assembler=assembler,
        executor=executor,
        cache_dir=cache_dir,
    )

    # Execute a turn with self-correction enabled
    question = (
        "Qual é a receita total obtida com todos os pedidos que foram efetivamente entregues?"
    )
    turn_result = agent.run_turn(
        question=question,
        level=ContextLevel.L4,
        selected_metric_id="net_revenue",
        replay_only=True,
        max_retries=2,
    )

    assert isinstance(turn_result, QueryTurnResult)
    assert turn_result.execution_result.success is True
    assert turn_result.context_level == ContextLevel.L4
    assert len(turn_result.execution_result.rows) > 0

    # Verify cache files were written
    cache_files = list(cache_dir.glob("*.json"))
    assert len(cache_files) >= 1

    # Second execution should hit the cache seamlessly
    turn_result_cached = agent.run_turn(
        question=question,
        level=ContextLevel.L4,
        selected_metric_id="net_revenue",
        replay_only=True,
    )
    assert turn_result_cached.execution_result.success is True
    assert turn_result_cached.generated_sql.raw_sql == turn_result.generated_sql.raw_sql


def test_benchmark_runner_replay_produces_monotonic_accuracy_gain(tmp_path: Path):
    """Runs benchmark suite in replay_only=True mode and validates monotonic accuracy progression."""
    db_path = tmp_path / "test_benchmark.duckdb"
    build_warehouse(db_path=db_path, sample_orders_count=600, seed=42)

    output_dir = tmp_path / "results"
    runner = BenchmarkRunner(
        db_path=db_path,
        output_dir=output_dir,
        cache_dir=output_dir / "cache",
        metadata_dir=Path("metadata"),
        gold_questions_path=Path("benchmarks/gold_questions.yml"),
    )

    levels = [
        ContextLevel.L0,
        ContextLevel.L1,
        ContextLevel.L2,
        ContextLevel.L3,
        ContextLevel.L4,
    ]

    summary = runner.run_suite(levels=levels, replay_only=True)

    # Validate results present for all levels
    assert len(summary.results) == 5

    results_by_level = {r.level: r for r in summary.results}

    acc_l0 = results_by_level[ContextLevel.L0].corrected_accuracy
    acc_l1 = results_by_level[ContextLevel.L1].corrected_accuracy
    acc_l2 = results_by_level[ContextLevel.L2].corrected_accuracy
    acc_l3 = results_by_level[ContextLevel.L3].corrected_accuracy
    acc_l4 = results_by_level[ContextLevel.L4].corrected_accuracy

    # Monotonic accuracy progression: acc[L0] < acc[L1] < acc[L2] < acc[L3] < acc[L4]
    assert acc_l0 < acc_l1 < acc_l2 < acc_l3 < acc_l4, (
        f"Monotonic accuracy violated: L0={acc_l0}, L1={acc_l1}, L2={acc_l2}, L3={acc_l3}, L4={acc_l4}"
    )

    # Acceptance criterion: acc[L4] >= 0.85
    assert acc_l4 >= 0.85, f"L4 accuracy {acc_l4} is below required 0.85"

    # Validate output files generated
    report_file = output_dir / "benchmark_report.md"
    svg_file = output_dir / "accuracy_by_level.svg"
    json_file = output_dir / "benchmark_summary.json"

    assert report_file.exists(), "benchmark_report.md must be generated"
    assert svg_file.exists(), "accuracy_by_level.svg must be generated"
    assert json_file.exists(), "benchmark_summary.json must be generated"

    report_content = report_file.read_text(encoding="utf-8")
    assert "# Benchmark Report" in report_content
    assert "L4" in report_content

    svg_content = svg_file.read_text(encoding="utf-8")
    assert "<svg" in svg_content
    assert "</svg>" in svg_content
