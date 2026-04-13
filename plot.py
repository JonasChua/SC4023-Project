from textwrap import fill

import pandas as pd
from matplotlib import pyplot as plt
from matplotlib.ticker import StrMethodFormatter

from constants import PROJECT_ROOT


class QueryStatisticsPlotter:
    def __init__(self) -> None:
        self.result_dir = PROJECT_ROOT / "result"
        self.input_path = self.result_dir / "QueryStatistics.csv"
        self.performance_overview_output_path = (
            self.result_dir / "PerformanceOverview.png"
        )
        self.block_comparison_output_path = (
            self.result_dir / "BlockCountBasicVsCompressed.png"
        )
        self.time_comparison_output_path = (
            self.result_dir / "InitializationAndExecutionTime.png"
        )
        self.dataframe = None

    def load_data(self) -> bool:
        if not self.input_path.exists():
            print(f"Query statistics file not found: {self.input_path}")
            print("Run the queries with --export-stats first.")
            return False

        dataframe = pd.read_csv(self.input_path)
        if dataframe.empty:
            print(f"No rows found in query statistics file: {self.input_path}")
            return False

        required_columns = [
            "column_store",
            "initialisation_time",
            "execution_time",
            "total_time_taken",
            "total_block_count",
            "total_block_read_count",
        ]
        missing_columns = [
            column for column in required_columns if column not in dataframe.columns
        ]
        if missing_columns:
            print(
                "Missing required columns in query statistics file: "
                + ", ".join(missing_columns)
            )
            return False

        for column in required_columns:
            if column == "column_store":
                dataframe[column] = dataframe[column].astype(str).str.strip()
            else:
                dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce")

        dataframe = dataframe.dropna(subset=required_columns)
        if dataframe.empty:
            print(f"No valid rows found in query statistics file: {self.input_path}")
            return False

        self.dataframe = dataframe
        print(self.dataframe[required_columns].to_string(index=False))
        return True

    def plot_performance_overview(self) -> None:
        if self.dataframe is None:
            return

        dataframe = self.dataframe
        wrapped_labels = [fill(label, width=14) for label in dataframe["column_store"]]
        x_positions = list(range(len(dataframe)))
        total_block_counts = dataframe["total_block_count"].astype(int).tolist()
        total_block_read_counts = (
            dataframe["total_block_read_count"].astype(int).tolist()
        )
        initialisation_times = dataframe["initialisation_time"].tolist()
        execution_times = dataframe["execution_time"].tolist()

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        axis_blocks, axis_reads = axes[0]
        axis_init, axis_exec = axes[1]

        # Total block counts subplot
        time_bars = axis_blocks.bar(
            x_positions, total_block_counts, color="#0055ee", alpha=0.75
        )
        axis_blocks.set_title("Total Block Counts by Column Store")
        axis_blocks.set_ylabel("Blocks")
        axis_blocks.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
        axis_blocks.set_xticks(x_positions)
        axis_blocks.set_xticklabels(wrapped_labels, rotation=0, ha="center")

        threshold = max(total_block_counts) / 2
        for bar, value in zip(time_bars, total_block_counts):
            axis_blocks.annotate(
                f"{value:,}",
                xy=(bar.get_x() + bar.get_width() / 2, value),
                xytext=(0, 2) if value < threshold else (0, -5),
                textcoords="offset points",
                ha="center",
                va="bottom" if value < threshold else "top",
                fontsize=10,
                color="black" if value < threshold else "white",
            )

        # Block read counts subplot
        blocks_bars = axis_reads.bar(
            x_positions, total_block_read_counts, color="#ee9900", alpha=0.75
        )
        axis_reads.set_title("Block Read Counts by Column Store")
        axis_reads.set_ylabel("Blocks Read")
        axis_reads.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
        axis_reads.set_xticks(x_positions)
        axis_reads.set_xticklabels(wrapped_labels, rotation=0, ha="center")

        threshold = max(total_block_read_counts) / 2
        for bar, value in zip(blocks_bars, total_block_read_counts):
            axis_reads.annotate(
                f"{value:,}",
                xy=(bar.get_x() + bar.get_width() / 2, value),
                xytext=(0, 2) if value < threshold else (0, -5),
                textcoords="offset points",
                ha="center",
                va="bottom" if value < threshold else "top",
                fontsize=10,
            )

        # Initialization time subplot
        init_bars = axis_init.bar(
            x_positions, initialisation_times, color="#00ee22", alpha=0.75
        )
        axis_init.set_title("Initialization Time by Column Store")
        axis_init.set_ylabel("Time (s)")
        axis_init.set_xticks(x_positions)
        axis_init.set_xticklabels(wrapped_labels, rotation=0, ha="center")

        threshold = max(initialisation_times) / 2
        for bar, value in zip(init_bars, initialisation_times):
            axis_init.annotate(
                f"{value:.3f}s",
                xy=(bar.get_x() + bar.get_width() / 2, value),
                xytext=(0, 2) if value < threshold else (0, -5),
                textcoords="offset points",
                ha="center",
                va="bottom" if value < threshold else "top",
                fontsize=10,
            )

        # Execution time subplot
        exec_bars = axis_exec.bar(
            x_positions, execution_times, color="#ee00cc", alpha=0.75
        )
        axis_exec.set_title("Query Execution Time by Column Store")
        axis_exec.set_ylabel("Time (s)")
        axis_exec.set_xticks(x_positions)
        axis_exec.set_xticklabels(wrapped_labels, rotation=0, ha="center")

        threshold = max(execution_times) / 2
        for bar, value in zip(exec_bars, execution_times):
            axis_exec.annotate(
                f"{value:.3f}s",
                xy=(bar.get_x() + bar.get_width() / 2, value),
                xytext=(0, 2) if value < threshold else (0, -5),
                textcoords="offset points",
                ha="center",
                va="bottom" if value < threshold else "top",
                fontsize=10,
                color="black" if value < threshold else "white",
            )

        fig.suptitle("Column Store Performance Overview", fontsize=14)
        fig.tight_layout()
        fig.savefig(self.performance_overview_output_path, dpi=300, bbox_inches="tight")
        print(
            f"Performance overview plot saved to: {self.performance_overview_output_path.relative_to(PROJECT_ROOT)}"
        )

    def plot_basic_vs_compressed_block_counts(self) -> None:
        COLUMNS_TO_COMPARE = [
            "town",
            "flat_type",
            "block",
            "street_name",
            "storey_range",
            "flat_model",
        ]
        if self.dataframe is None:
            return

        dataframe = self.dataframe
        by_store = {
            row["column_store"].casefold(): row
            for _, row in dataframe.iterrows()
            if row["column_store"]
        }

        if "basic" not in by_store or "compressed" not in by_store:
            print(
                "Basic/Compressed rows not found. Skipping block count comparison figure."
            )
            return

        basic_counts = [
            int(by_store["basic"][f"{column}_block_count"])
            for column in COLUMNS_TO_COMPARE
        ]
        compressed_counts = [
            int(by_store["compressed"][f"{column}_block_count"])
            for column in COLUMNS_TO_COMPARE
        ]

        fig, axis = plt.subplots(figsize=(10, 5))
        bar_width = 0.38
        x_positions = list(range(len(COLUMNS_TO_COMPARE)))
        basic_positions = [x - bar_width / 2 for x in x_positions]
        compressed_positions = [x + bar_width / 2 for x in x_positions]

        basic_bars = axis.bar(
            basic_positions,
            basic_counts,
            width=bar_width,
            color="#0055ee",
            label="Basic",
        )
        compressed_bars = axis.bar(
            compressed_positions,
            compressed_counts,
            width=bar_width,
            color="#ee9900",
            label="Compressed",
        )

        axis.set_title("Basic vs Compressed")
        axis.set_ylabel("Block Count")
        axis.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
        axis.set_xticks(x_positions)
        axis.set_xticklabels([fill(column, width=12) for column in COLUMNS_TO_COMPARE])
        axis.legend(loc="upper left")

        threshold = max(max(basic_counts), max(compressed_counts)) / 2
        for bar in basic_bars:
            height = int(bar.get_height())
            axis.annotate(
                f"{height:,}",
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 2) if height < threshold else (0, -5),
                textcoords="offset points",
                ha="center",
                va="bottom" if height < threshold else "top",
                fontsize=10,
                color="black" if height < threshold else "white",
            )

        for bar in compressed_bars:
            height = int(bar.get_height())
            axis.annotate(
                f"{height:,}",
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 2) if height < threshold else (0, -5),
                textcoords="offset points",
                ha="center",
                va="bottom" if height < threshold else "top",
                fontsize=10,
            )

        fig.suptitle("Block Count Comparison", fontsize=14)
        fig.tight_layout()
        fig.savefig(self.block_comparison_output_path, dpi=300, bbox_inches="tight")
        print(
            "Block-count comparison plot saved to: "
            f"{self.block_comparison_output_path.relative_to(PROJECT_ROOT)}"
        )

    def plot(self) -> None:
        if not self.load_data():
            return

        self.plot_performance_overview()
        self.plot_basic_vs_compressed_block_counts()
