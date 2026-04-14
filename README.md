# SC4023-Project

## Overview

This project implements an on-disk column store for Singapore HDB resale flat price data, supporting five progressively optimised variants. Each column in the relation is stored as a separate binary file so that queries only read the columns they actually need, avoiding unnecessary I/O on unrelated attributes.

## Key Files and Folders

- `main.py`: CLI entry point for running query and plotting workflows.
- `store.py`: Core column store implementation.
- `query.py`: Query execution pipeline and predicate evaluation and variant initialisation logic.
- `column.py`: Column-level binary storage, reads, and block accounting.
- `mapping.py`: Dictionary encoding and decoding helpers for compressed categorical columns.
- `constants.py`: Shared constants such as schema details, paths, and data layout parameters.
- `plot.py`: Benchmark visualisation utilities and chart generation.
- `export.py`: Result export helpers for CSV/text outputs.
- `data/raw/`: Input dataset source files (including `ResalePricesSingapore.csv`).
- `data/store/basic/`: Persisted files for the baseline (uncompressed) column store.
- `data/store/compressed/`: Persisted files and mapping tables for compressed variants.
- `result/`: Generated benchmark outputs, scan results, and performance figures.
- `result/ScanResult_*.csv`: CSV files containing the query results for each column store variant.
- `result/ValidationResult.xlsx`: Excel file containing the query results for the validation query.

## Before Running

This project uses `uv` for dependency management and task execution. If you choose to not use `uv`, replace `uv run` with `python` in the commands below.

## Run Query

Run the query workflow:

```powershell
uv run main.py query
```

Use `-m` or `--matric` to specify the matric number for the query (default: `A6626226B`):

```powershell
uv run main.py query -m A6626226B
```

Use `-n` or `--repeat` to specify how many times to run the query and average the timings (default: 1):

```powershell
uv run main.py query -n 1
```

Use `-r` or `--export-results` to export the query results to a `ScanResult_*.csv` file in the `result/` folder:

```powershell
uv run main.py query -r
```

Use `-s` or `--export-stats` to export the query statistics to text and CSV files in the `result/` folder:

```powershell
uv run main.py query -s
```

Use `-e` or `--experiment` to run only the indexed + zone map + compressed experiment query and print the first 10 result rows in the terminal:

```powershell
uv run main.py query -e -m A6626226B
```

## Run Plot

`matplotlib` and `pandas` are required to run the plotting workflow. If you have not installed these dependencies, you can do so with:

```powershell
uv sync
```

or without `uv`:

```powershell
pip install matplotlib pandas
```

Run the plot workflow:

```powershell
uv run main.py plot
```

---

## Column Store Design

The source CSV (`ResalePricesSingapore.csv`) is converted to binary column files during initialisation. Each column file stores values in row order using compact binary types (e.g. `uint8`, `uint16`, `float32`). Data is accessed in **4 KB blocks**; the store tracks how many blocks are allocated per column and how many are actually read per query.

Five store variants are implemented for side-by-side comparison. The statistics section reports both block reads and runtime split into initialisation and query execution so the cost-benefit of each optimisation is explicit.

### Overall Performance Overview

![Column Store Performance Overview](result/PerformanceOverview.png)

The overall averaged performance overview for the five column store after 10 runs per variant. The optimised variants show significant query-time improvements over the basic column store, with the indexed variants giving the largest gains.

### 1. Basic Column Store

Strings are stored as fixed-length byte arrays (e.g. `town` as 32 bytes, `flat_type` as 16 bytes). No compression is applied. This is the baseline design: lowest setup overhead, but highest query-time I/O and runtime in the benchmark.

In the benchmark, this baseline records **0.001 s** initialisation, **162.916 s** query time, and **248** total blocks read (out of **7,665** allocated).

### 2. Compressed Column Store

**Compression** is applied to all categorical string columns (`town`, `flat_type`, `block`, `street_name`, `storey_range`, `flat_model`). Each unique string value is assigned a small integer ID, and only the ID is stored on disk:

| Column         | Basic type      | Compressed type    | Space saving |
| -------------- | --------------- | ------------------ | ------------ |
| `town`         | `16` (16 bytes) | `uint8` (1 byte)   | 16×          |
| `flat_type`    | `16` (16 bytes) | `uint8` (1 byte)   | 16×          |
| `block`        | `4` (4 bytes)   | `uint16` (2 bytes) | 2×           |
| `street_name`  | `32` (32 bytes) | `uint16` (2 bytes) | 16×          |
| `storey_range` | `8` (8 bytes)   | `uint8` (1 byte)   | 8×           |
| `flat_model`   | `32` (32 bytes) | `uint16` (2 bytes) | 16×          |

#### Basic vs Compressed Block Counts by Column

![Block Count Comparison](result/BlockCountBasicVsCompressed.png)

The ID-to-string mappings are persisted to `*_map.csv` files and loaded back at query time for decoding. Storing smaller values means more rows fit per 4 KB block, reducing the total block count from **7,665 → 1,399** (an 82% reduction).

In the current benchmark, this translates to **0.010 s** initialisation, **48.894 s** query time, and **189** total blocks read (vs **248** in basic mode).

### 3. Zone Map Column Store

Adds **zone maps** to the column store. A zone map records the `(min, max)` value for each block of a column and is held in memory. During a scan with a range or equality predicate, any block whose `[min, max]` range cannot possibly satisfy the predicate is **skipped entirely** without an I/O read. This is particularly effective for columns with some natural ordering (e.g. `year`, `month`), allowing large swaths of the file to be pruned at query time.

In the current benchmark, this variant records **0.812 s** initialisation, **149.529 s** query time, and **131** total blocks read (down from **248** in the basic store).

### 4. Indexed Column Store

Introduces an in-memory **composite index** on `(year, month, town)`. During initialisation, it builds a hash map mapping each unique combination of `(year, month, town)` to a list of matching row indices. At query time, instead of scanning columns to evaluate predicates, the engine performs direct $O(1)$ key lookup to fetch candidate rows.

This largely bypasses full-column scan work for indexed predicates and gives the largest query-time gain in the benchmark: in indexed basic mode, initialisation is **0.894 s**, query time drops from **162.916 s → 2.292 s**, and total blocks read drop from **248 → 76** versus the basic store.

### 5. Indexed Zone Map Compressed Column Store

Combines all three optimisations: compression, zone maps, and composite index. In the benchmark, this variant records **0.859 s** initialisation, **2.377 s** query time, and **65** total blocks read (with **1,399** total blocks allocated).

---

## Optimisation Summary

| Technique           | Benefit                                                                                             |
| ------------------- | --------------------------------------------------------------------------------------------------- |
| **Compression**     | Categorical strings replaced by 1–2 byte integer IDs; fewer blocks allocated                        |
| **Zone maps**       | Entire blocks skipped when predicate cannot match; significantly fewer block reads                  |
| **Composite Index** | Direct \(O(1)\) lookup for specific predicates; eliminates block scans entirely for indexed columns |

---

## Benchmark Results

Average benchmark results for the five column store variants when executing the same query 10 times (matric number: A6626226B):

```
========= Column Store Summary =========
Compression:   Off
Zone Maps:     Off
Indexed:       Off

Phase                           Time (s)
----------------------------------------
Initialisation                     0.001
Query Execution                  162.916
----------------------------------------
Total                            162.917

Column                  Blocks      Read
----------------------------------------
year                       127       127
month                       64         6
town                      1013        54
flat_type                 1013         6
block                      254         6
street_name               2026         7
storey_range               507         6
floor_area_sqm             254        12
flat_model                2026         7
lease_commence_date        127         5
resale_price               254        12
----------------------------------------
Total                     7665       248
========================================

========= Column Store Summary =========
Compression:   On
Zone Maps:     Off
Indexed:       Off

Phase                           Time (s)
----------------------------------------
Initialisation                     0.010
Query Execution                   48.894
----------------------------------------
Total                             48.904

Column                  Blocks      Read
----------------------------------------
year                       127       127
month                       64         6
town                        64         4
flat_type                   64         4
block                      127         5
street_name                127         5
storey_range                64         4
floor_area_sqm             254        12
flat_model                 127         5
lease_commence_date        127         5
resale_price               254        12
----------------------------------------
Total                     1399       189
========================================

========= Column Store Summary =========
Compression:   Off
Zone Maps:     On
Indexed:       Off

Phase                           Time (s)
----------------------------------------
Initialisation                     0.812
Query Execution                  149.529
----------------------------------------
Total                            150.340

Column                  Blocks      Read
----------------------------------------
year                       127        11
month                       64         5
town                      1013        54
flat_type                 1013         6
block                      254         6
street_name               2026         7
storey_range               507         6
floor_area_sqm             254        12
flat_model                2026         7
lease_commence_date        127         5
resale_price               254        12
----------------------------------------
Total                     7665       131
========================================

========= Column Store Summary =========
Compression:   Off
Zone Maps:     Off
Indexed:       (year, month, town)

Phase                           Time (s)
----------------------------------------
Initialisation                     0.894
Query Execution                    2.292
----------------------------------------
Total                              3.186

Column                  Blocks      Read
----------------------------------------
year                       127         5
month                       64         4
town                      1013         6
flat_type                 1013         6
block                      254         6
street_name               2026         7
storey_range               507         6
floor_area_sqm             254        12
flat_model                2026         7
lease_commence_date        127         5
resale_price               254        12
----------------------------------------
Total                     7665        76
========================================

========= Column Store Summary =========
Compression:   On
Zone Maps:     On
Indexed:       (year, month, town)

Phase                           Time (s)
----------------------------------------
Initialisation                     0.859
Query Execution                    2.377
----------------------------------------
Total                              3.236

Column                  Blocks      Read
----------------------------------------
year                       127         5
month                       64         4
town                        64         4
flat_type                   64         4
block                      127         5
street_name                127         5
storey_range                64         4
floor_area_sqm             254        12
flat_model                 127         5
lease_commence_date        127         5
resale_price               254        12
----------------------------------------
Total                     1399        65
========================================
```
