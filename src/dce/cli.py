"""Unified CLI entrypoint for Data Context Engine."""

import argparse
import subprocess
import sys
from pathlib import Path

from dce.warehouse.builder import build_warehouse


def cmd_build_db(args: argparse.Namespace) -> None:
    """Builds the local DuckDB analytical warehouse with deterministic data."""
    db_path = Path(args.db_path)
    print(f"Building warehouse at {db_path} (samples={args.samples}, seed={args.seed})...")
    out_path = build_warehouse(
        db_path=db_path,
        sample_orders_count=args.samples,
        seed=args.seed,
    )
    print(f"Warehouse built successfully at: {out_path}")


def cmd_bench(args: argparse.Namespace) -> None:
    """Executes the benchmark evaluation across all context levels (L0-L4)."""
    from dce.benchmark.runner import BenchmarkRunner
    from dce.models import ContextLevel

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"Warehouse not found at {db_path}. Auto-building first...")
        build_warehouse(db_path=db_path, sample_orders_count=600, seed=42)

    runner = BenchmarkRunner(
        db_path=db_path,
        output_dir=Path(args.output_dir),
    )
    replay_only = not args.live
    print(f"Running benchmark suite (replay_only={replay_only}, output_dir={args.output_dir})...")
    summary = runner.run_suite(
        levels=[
            ContextLevel.L0,
            ContextLevel.L1,
            ContextLevel.L2,
            ContextLevel.L3,
            ContextLevel.L4,
        ],
        replay_only=replay_only,
    )
    print("\nBenchmark Summary:")
    for lm in summary.level_metrics:
        print(
            f"  {lm.level.value}: single-shot={lm.single_shot_accuracy*100:.1f}%, "
            f"corrected={lm.corrected_accuracy*100:.1f}%, "
            f"avg_tokens={lm.avg_tokens:.0f}, savings={lm.token_savings_pct:.1f}%"
        )
    print(f"\nReport generated at: {Path(args.output_dir) / 'benchmark_report.md'}")


def cmd_mcp(args: argparse.Namespace) -> None:
    """Starts the FastMCP server over stdio for LLM agents."""
    from dce.mcp_server import create_mcp_server

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"Warehouse not found at {db_path}. Auto-building...")
        build_warehouse(db_path=db_path, sample_orders_count=200, seed=42)

    server = create_mcp_server(
        db_path=db_path,
        playbooks_path=Path(args.playbooks_path),
        metadata_dir=Path(args.metadata_dir),
    )
    print("Starting Data Context Engine MCP Server over stdio...", file=sys.stderr)
    server.run(transport="stdio")


def cmd_ui(args: argparse.Namespace) -> None:
    """Launches the Streamlit analytical workbench."""
    app_path = Path("app/streamlit_app.py")
    if not app_path.exists():
        print(f"Streamlit application file not found at {app_path}", file=sys.stderr)
        sys.exit(1)

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
    ]
    if args.port:
        cmd.extend(["--server.port", str(args.port)])
    print(f"Launching Streamlit app: {' '.join(cmd)}")
    subprocess.run(cmd, check=False)


def main() -> None:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="dce",
        description="Data Context Engine: Semantic layer, active clarification, prefix caching and SQL guardrails",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # build-db
    p_build = subparsers.add_parser("build-db", help="Generate local DuckDB analytical warehouse")
    p_build.add_argument(
        "--db-path", default="data/warehouse/olist.duckdb", help="Output DuckDB file path"
    )
    p_build.add_argument(
        "--samples", type=int, default=2000, help="Number of sample orders to generate"
    )
    p_build.add_argument(
        "--seed", type=int, default=42, help="Random seed for deterministic generation"
    )

    # bench
    p_bench = subparsers.add_parser("bench", help="Run benchmark across L0-L4 context levels")
    p_bench.add_argument(
        "--db-path", default="data/warehouse/olist.duckdb", help="Path to DuckDB warehouse"
    )
    p_bench.add_argument(
        "--replay",
        dest="live",
        action="store_false",
        default=False,
        help="Use replay cache (default)",
    )
    p_bench.add_argument(
        "--live",
        dest="live",
        action="store_true",
        help="Call live LLM instead of replay cache",
    )
    p_bench.add_argument(
        "--output-dir", default="results", help="Directory to save benchmark results"
    )

    # mcp
    p_mcp = subparsers.add_parser("mcp", help="Start FastMCP server for LLM agents")
    p_mcp.add_argument(
        "--db-path", default="data/warehouse/olist.duckdb", help="Path to DuckDB warehouse"
    )
    p_mcp.add_argument(
        "--playbooks-path",
        default="data/playbooks/saved_playbooks.json",
        help="Path to playbooks file",
    )
    p_mcp.add_argument(
        "--metadata-dir", default="metadata", help="Metadata directory"
    )

    # ui / demo
    p_ui = subparsers.add_parser("ui", help="Launch Streamlit analytical workbench")
    p_ui.add_argument("--port", type=int, default=8501, help="Port for Streamlit server")
    p_demo = subparsers.add_parser("demo", help="Alias for ui")
    p_demo.add_argument("--port", type=int, default=8501, help="Port for Streamlit server")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "build-db":
        cmd_build_db(args)
    elif args.command == "bench":
        cmd_bench(args)
    elif args.command == "mcp":
        cmd_mcp(args)
    elif args.command in ("ui", "demo"):
        cmd_ui(args)


if __name__ == "__main__":
    main()
