from argparse import ArgumentParser, ArgumentTypeError, Namespace

from export import export_query_statistics, export_query_statistics_txt, export_results
from plot import QueryStatisticsPlotter
from query import (
    QueryEngine,
    run_basic_store_query,
    run_compressed_store_query,
    run_indexed_basic_store_query,
    run_indexed_zone_map_compressed_store_query,
    run_zone_map_basic_store_query,
)


def _print_rows(query_engine: QueryEngine, limit: int = 10) -> None:
    """
    Print the first N rows of the query results.
    """
    rows = [
        (x, y, data)
        for (x, y), data in query_engine.results.items()
        if data is not None
    ]

    if not rows:
        print("No qualifying rows found.")
        return

    print(
        f"Query results for '{query_engine.query.matric_str}' (first {min(limit, len(rows))} rows):"
    )
    print(
        f"{'(x, y)':<8} {'Year':<6} {'Month':<6} {'Town':<15} "
        f"{'Block':<8} {'Floor_Area':<12} {'Flat_Model':<20} {'Lease_Start':<12} {'Price_Per_Sqm':<14}"
    )

    for x, y, data in rows[:10]:
        print(
            f"{f'({x}, {y})':<8} {data['year']:<6} {data['month']:<6} {str(data['town'])[:15]:<15} "
            f"{str(data['block'])[:8]:<8} {data['floor_area_sqm']:<12.2f} {str(data['flat_model'])[:20]:<20} "
            f"{data['lease_commence_date']:<12} {data['price_per_sqm']:<14}"
        )


def run_query(args: Namespace) -> None:
    matric_str = args.matric
    repeat = args.repeat

    if args.experiment:
        query_engine = run_indexed_zone_map_compressed_store_query(matric_str, repeat)
        _print_rows(query_engine, 10)
        return

    query_engines = {
        "Basic": run_basic_store_query(matric_str, repeat),
        "Compressed": run_compressed_store_query(matric_str, repeat),
        "Zone Map": run_zone_map_basic_store_query(matric_str, repeat),
        "Indexed": run_indexed_basic_store_query(matric_str, repeat),
        "Compressed + Zone Map + Indexed": run_indexed_zone_map_compressed_store_query(
            matric_str, repeat
        ),
    }
    export_query_statistics_txt(query_engines)
    if args.export_result:
        export_results(query_engines["Compressed + Zone Map + Indexed"])

    if args.export_stats:
        export_query_statistics(query_engines)


def run_plot() -> None:
    QueryStatisticsPlotter().plot()


def _positive_int(value: str) -> int:
    repeat = int(value)
    if repeat < 1:
        raise ArgumentTypeError("repeat count must be at least 1")

    return repeat


if __name__ == "__main__":
    parser = ArgumentParser(description="Run queries on the column store")
    subparsers = parser.add_subparsers(
        dest="command", help="Command to run", required=False
    )
    query_parser = subparsers.add_parser("query", help="Run queries and export results")
    query_parser.add_argument(
        "-m",
        "--matric",
        type=str,
        help="Matriculation number to use for the queries (default: A6626226B)",
        default="A6626226B",
    )
    query_parser.add_argument(
        "-r",
        "--export-result",
        action="store_true",
        help="Whether to export the query results to CSV file",
    )
    query_parser.add_argument(
        "-s",
        "--export-stats",
        action="store_true",
        help="Whether to export the query execution statistics to CSV & TXT files",
    )
    query_parser.add_argument(
        "-n",
        "--repeat",
        type=_positive_int,
        default=1,
        help="Number of times to run each query and average the timings (default: 1)",
    )
    query_parser.add_argument(
        "-e",
        "--experiment",
        action="store_true",
        help="Run only the indexed + zone map + compressed query and print the top 10 rows",
    )
    plot_parser = subparsers.add_parser("plot", help="Plot query execution statistics")
    args = parser.parse_args()

    match args.command:
        case "query":
            run_query(args)
        case "plot":
            run_plot()
        case _:
            parser.print_help()
