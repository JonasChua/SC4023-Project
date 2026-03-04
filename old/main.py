"""
SC4023 Semester Group Project: Column-store resale HDB query.

Command-line interface:
  1. Inspect col store  - show column store summary and optional row preview
  2. Input Matric Card  - run query for a matriculation number, output ScanResult_<MatricNum>.csv

Usage:
  python main.py                    # interactive menu
  python main.py inspect [options]  # inspect column store
  python main.py query <matric>     # run query for matriculation number (e.g. A5656567B)
"""

import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

from constants import COLSTORE_DIR


def cmd_inspect(args: Namespace) -> int:
    """Run inspect_colstore logic."""
    import inspect_colstore

    inspect_colstore.run_inspect(COLSTORE_DIR, rows=args.rows, stats=args.stats)
    return 0


def cmd_query(matric: str, output_path: Path | None = None) -> int:
    """Run query for matriculation number; write ScanResult_<MatricNum>.csv."""
    from run_query import run_query

    if not COLSTORE_DIR.exists():
        print(f"Column store not found: {COLSTORE_DIR}")
        print("Run build_colstore.py first.")
        return 1
    try:
        out_path, page_tracker = run_query(
            COLSTORE_DIR, matric, output_path=output_path
        )
        print(f"Wrote {out_path}")
        print(page_tracker.summary())
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def menu() -> int:
    """Interactive menu: 1 = Inspect col store, 2 = Input Matric Card."""
    print("SC4023 Column-store Resale HDB Query")
    print("  1. Inspect col store")
    print("  2. Input Matric Card (for querying)")
    try:
        choice = input("Enter choice (1 or 2): ").strip()
    except EOFError:
        return 0
    if choice == "1":
        return cmd_inspect(Namespace(rows=10, stats=False))
    if choice == "2":
        try:
            matric = input("Enter matriculation number (e.g. A5656567B): ").strip()
        except EOFError:
            return 0
        if not matric:
            print("No matriculation number entered.")
            return 1
        return cmd_query(matric)
    print("Invalid choice. Enter 1 or 2.")
    return 1


def main() -> int:
    parser = ArgumentParser(
        description="SC4023 Project: column-store resale HDB query (inspect or query by matric)."
    )
    subparsers = parser.add_subparsers(dest="command", help="command")

    inspect_parser = subparsers.add_parser(
        "inspect", help="Inspect column store (summary and optional row preview)"
    )
    inspect_parser.add_argument(
        "-n", "--rows", type=int, default=10, help="Number of rows to print (0 = none)"
    )
    inspect_parser.add_argument(
        "--stats", action="store_true", help="Print min/max stats only"
    )

    query_parser = subparsers.add_parser(
        "query",
        help="Run query for matriculation number; output ScanResult_<MatricNum>.csv",
    )
    query_parser.add_argument("matric", help="Matriculation number (e.g. A5656567B)")
    query_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output CSV path (default: ScanResult_<MatricNum>.csv in project root)",
    )

    args = parser.parse_args()

    if args.command == "inspect":
        return cmd_inspect(args)
    if args.command == "query":
        return cmd_query(args.matric, args.output)
    # No subcommand: show menu
    return menu()


if __name__ == "__main__":
    sys.exit(main())
