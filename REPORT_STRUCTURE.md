# SC4023 Column Store Project Report

**Matriculation Number:** A6626226B

---

## 1 Data Storage

### 1.1 Column Store Implementation

The system implements an on-disk **column-oriented store** for Singapore HDB resale flat price data. Unlike a row store, where all attributes of a record are stored contiguously, each column is persisted as a separate binary file. This design allows queries to read only the columns they need, avoiding unnecessary I/O on irrelevant attributes.

The source dataset (`ResalePricesSingapore.csv`, ~20 MB, 259,237 records) is decomposed into 11 columns. The original CSV `month` field (formatted as `MMM-YY`, e.g. `Jan-15`) is split into two separate numeric columns -- `year` and `month` -- during ingestion.

Five progressively optimised store variants are implemented for side-by-side comparison:

| # | Variant | Description |
|---|---------|-------------|
| 1 | **Basic** | Strings stored as fixed-length byte arrays; no compression or indexing. Serves as the baseline. |
| 2 | **Compressed** | Dictionary encoding applied to all categorical string columns; each unique string is mapped to a small integer ID. |
| 3 | **Zone Map** | Per-page `(min, max)` metadata held in memory; pages whose range cannot satisfy a predicate are skipped entirely. |
| 4 | **Indexed** | In-memory composite hash index on `(year, month, town)` for O(1) candidate-row lookup. |
| 5 | **Combined** | All three optimisations (compression + zone maps + composite index) applied together. |

The implementation is structured across several Python modules:

- `column.py` -- Column type hierarchy (abstract `Column`, `NumericColumn`, `StringColumn`, and concrete subclasses `UnsignedCharColumn`, `UnsignedShortColumn`, `FloatColumn`)
- `store.py` -- `ColumnStore` class responsible for file I/O, caching, zone maps, composite index, and page-level scanning
- `query.py` -- `QueryParser` (matriculation number decoding) and `QueryEngine` (predicate filtering and result selection)
- `constants.py` -- Project-wide constants (`BLOCK_SIZE = 4096`, `MONTH_ABBR`, `DIGIT_TO_TOWN` mapping, column metadata classes)
- `mapping.py` -- Compression dictionary persistence (`map_writer`, `map_loader`)
- `main.py` -- Entry point that runs all five store variants sequentially

> **Suggested figure:** A diagram showing the column store architecture -- CSV ingestion on the left, individual `.bin` column files in the middle, and query engine reading selectively on the right.

### 1.2 Data Column Design

Each column is defined by a name, a binary format string (using Python's `struct` module), and a byte size. The `Column` abstract base class (`column.py:6`) provides the shared interface; concrete subclasses handle encoding/decoding.

**Basic store column layout (no compression):**

| Column | Type | Format | Size (bytes) | Rows per 4 KB page |
|--------|------|--------|:------------:|:-------------------:|
| `year` | `UnsignedShortColumn` | `H` (uint16) | 2 | 2048 |
| `month` | `UnsignedCharColumn` | `B` (uint8) | 1 | 4096 |
| `town` | `StringColumn` | `16s` | 16 | 256 |
| `flat_type` | `StringColumn` | `16s` | 16 | 256 |
| `block` | `StringColumn` | `4s` | 4 | 1024 |
| `street_name` | `StringColumn` | `32s` | 32 | 128 |
| `storey_range` | `StringColumn` | `8s` | 8 | 512 |
| `floor_area_sqm` | `FloatColumn` | `f` (float32) | 4 | 1024 |
| `flat_model` | `StringColumn` | `32s` | 32 | 128 |
| `lease_commence_date` | `UnsignedShortColumn` | `H` (uint16) | 2 | 2048 |
| `resale_price` | `FloatColumn` | `f` (float32) | 4 | 1024 |

**Compressed store column layout (dictionary encoding):**

When compression is enabled, categorical string columns are replaced by integer IDs:

| Column | Basic type | Compressed type | Compression ratio |
|--------|-----------|----------------|:-----------------:|
| `town` | `16s` (16 bytes) | `B` uint8 (1 byte) | 16x |
| `flat_type` | `16s` (16 bytes) | `B` uint8 (1 byte) | 16x |
| `block` | `4s` (4 bytes) | `H` uint16 (2 bytes) | 2x |
| `street_name` | `32s` (32 bytes) | `H` uint16 (2 bytes) | 16x |
| `storey_range` | `8s` (8 bytes) | `B` uint8 (1 byte) | 8x |
| `flat_model` | `32s` (32 bytes) | `H` uint16 (2 bytes) | 16x |

The ID-to-string mappings are persisted as `*_map.csv` files alongside the binary column files and loaded at query time for decoding results.

Total page count drops from **7,665** (basic) to **1,399** (compressed) -- an **82% reduction** in on-disk storage footprint.

> **Suggested figure:** A bar chart comparing total allocated pages per column between the basic and compressed store variants.

### 1.3 File I/O Operations

All data access is performed through **4 KB page-aligned reads** (`BLOCK_SIZE = 4096`). The `_read_column` method (`store.py:265`) reads exactly one page at a time using `file.seek()` and `file.read(BLOCK_SIZE)`, then decodes the raw bytes into a list of typed values.

**Page read workflow:**

1. Compute the file offset: `block_index * BLOCK_SIZE`
2. Open the column's `.bin` file in binary mode
3. Seek to the offset and read exactly 4,096 bytes
4. Decode values by iterating in `column.size`-byte steps using `struct.unpack`
5. Return the list of decoded values

**Caching:** A dictionary `_cache[(column_name, block_index)]` stores previously read pages in memory. Subsequent accesses to the same page are served from cache without disk I/O. File read counters (`_file_read_counters`) track how many *unique* page reads occur per column during query execution, enabling precise I/O measurement.

**Page count calculation** (`store.py:227`):

```
page_count = ceil(file_size / BLOCK_SIZE)
```

**Row-to-page mapping** (`store.py:237`):

```
page_index = (row_index * column.size) // BLOCK_SIZE
```

This ensures that given any row index, the system can compute the exact page to fetch, enabling random access when using the composite index.

> **Suggested figure:** A flowchart of the page read path -- cache check, file seek, raw read, decode, cache store.

### 1.4 Exception Handling

The codebase implements defensive validation at several levels:

- **Column name validation** (`store.py:59`): `_validate_column_name` raises `ValueError` if a queried column does not exist in the store.
- **Page index bounds** (`store.py:273`): Negative page indices raise `ValueError`; out-of-range indices return an empty list gracefully.
- **Row index bounds** (`store.py:360`): `get_value` raises `IndexError` if the within-page index exceeds the page's decoded length.
- **Zone map bounds** (`column.py:56`): `get_block_zone` raises `IndexError` for out-of-range page indices.
- **Compression map guards** (`column.py:27`): Operations on compression mappings raise `ValueError` if the feature is not enabled for the column.
- **Month parsing** (`store.py:43`): Invalid `MMM-YY` strings raise `ValueError` with descriptive messages.
- **CSV field parsing** (`store.py:112`): Numeric fields that fail `literal_eval` default to `0` instead of crashing, ensuring the ingestion pipeline is resilient to malformed data.
- **Division by zero** (`query.py:129`): When computing price per square metre, rows with `floor_area == 0` are skipped to avoid `ZeroDivisionError`.

---

## 2 Data Processing

### 2.1 Scanning Strategy

The query is derived from the matriculation number **A6626226B** using the following rules:

- **Digits extracted:** `[6, 6, 2, 6, 2, 2, 6]`
- **Target year:** Last digit `6` -> `2016`
- **Start month:** Second-last digit `2` -> month `2` (February)
- **Towns:** Unique digits `{6, 2}` -> `{PASIR RIS, CLEMENTI}` (from `DIGIT_TO_TOWN` mapping)

The query searches for the HDB resale transaction with the **minimum price per square metre** across all combinations of:
- `x` (number of consecutive months): 1 to 8 (i.e. Feb only, Feb--Mar, ..., Feb--Sep)
- `y` (minimum floor area): 80 to 150 sqm

This produces **8 x 71 = 568** parameter combinations per store variant.

**Scan approach varies by store variant:**

**Full scan (basic, compressed, zone map):**
1. Scan the `year` column to find all rows where `year == 2016`
2. From those rows, scan `month` for `start_month <= month <= end_month`
3. From those rows, scan `town` for membership in the target town set
4. From those rows, filter by `floor_area_sqm >= y`
5. For surviving rows, compute `resale_price / floor_area_sqm` and select the minimum

The filtering is applied progressively -- each step narrows the candidate set before the next column is scanned. When indices are provided to `scan_column` (`store.py:306`), only the pages containing those row indices are read, and within each page only the relevant rows are checked.

**Indexed scan (indexed, combined):**
1. For each `(month, town)` combination in the query range, perform an O(1) hash lookup into the composite index to retrieve pre-filtered row indices
2. Skip the year/month/town column scans entirely
3. Apply `floor_area_sqm >= y` filter and select the minimum price per sqm

> **Suggested figure:** A side-by-side flowchart comparing the full-scan path vs. the indexed-scan path.

### 2.2 Data Retrieval

**Baseline sequential scan (basic store):**

In the default basic store, data retrieval follows a straightforward sequential scan. The `scan_column` method (`store.py:306`) iterates through every page of a column from page 0 to the last page. For each page, it calls `_read_column` (`store.py:265`) which reads a 4 KB page from disk, decodes all values, and applies the predicate function to each value. Matching row indices are collected and passed to the next column's scan as a filter.

The scan is **progressive** -- each column narrows the candidate set before the next column is scanned. For example, scanning `year` first may reduce 259,237 rows to ~26,000 rows for year 2016. Subsequent scans of `month` and `town` then only check rows within pages that contain those candidate indices, rather than scanning every page again. This pre-filtering is handled by the `indices` parameter in `scan_column`: when provided, the method computes which pages overlap with the given row indices and skips pages that contain none (`store.py:329-334`).

However, even with progressive filtering, the first column (`year`) must still be scanned in its entirety -- all 127 pages are read. This is the fundamental limitation that the efficiency enhancements in Section 2.3 address.

**Value retrieval by row index:**

Once candidate row indices are identified (either by scanning or via index lookup), individual values are retrieved using `get_value` (`store.py:352`). This method computes the target page index from the row index (`page_index = row_index * column.size // BLOCK_SIZE`), reads the page (served from cache if already loaded), and extracts the value at the correct within-page offset. This random-access pattern is used for reading `floor_area_sqm` and `resale_price` when computing price per square metre, and for assembling the final result row.

**Result row assembly:**

Once the best row index (minimum price per sqm) is identified by `select_minimum_price_per_floor_area` (`query.py:115`), the method `select_row_data` (`query.py:137`) reads all 11 column values for that row using `get_value`. For compressed columns, the integer ID is decoded back to the original string via `unmap_value` to produce human-readable output.

**Result export:**

Results for all 568 `(x, y)` parameter combinations are exported to `result/ScanResult_A6626226B.csv` with columns: `(x, y)`, Year, Month, Town, Block, Floor_Area, Flat_Model, Lease_Commence_Date, Price_Per_Square_Meter. Combinations where no qualifying transaction exists are omitted from the output.

### 2.3 Efficiency Enhancements

Three key optimisations are implemented, each reducing I/O and/or computation:

**1. Dictionary Compression**

Categorical string columns are replaced by 1--2 byte integer IDs via dictionary encoding. This reduces:
- **Storage:** Total pages from 7,665 to 1,399 (82% reduction)
- **I/O per page read:** Smaller values = more rows per page
- **Comparison cost:** Integer comparison vs. string comparison during scans

The trade-off is a small initialisation overhead for writing and loading the `*_map.csv` mapping files (~0.014s vs ~0.001s).

Additionally, when scanning a compressed column (e.g. `town`), the `QueryEngine` maps the target string values to their integer IDs *before* scanning (`query.py:95`). This avoids decompressing each value during the scan -- the predicate operates directly on integer comparisons, which is faster.

**2. Zone Maps**

Per-page `(min, max)` metadata is built during initialisation and held in memory. During a scan, the `_match_zone_map` method (`store.py:243`) checks whether a page's min/max range can possibly satisfy the predicate. If not, the entire page is skipped without any file I/O.

For numeric predicates (e.g. `year == 2016`), the method evaluates the predicate against `min`, `max`, and all integer values in `[min, max]`, supporting both equality and range predicates.

Zone maps are particularly effective for `year` and `month` because the data has natural temporal ordering -- consecutive pages tend to contain similar values, enabling large contiguous skips. Results:
- Pages read reduced from **248 to 131** (47% reduction vs. basic)
- Most effective on `year` (127 -> 11 pages read) due to temporal ordering
- Initialisation cost: ~0.936s (building zone maps requires a full scan of each zone-mapped column)

**3. Composite Index on (year, month, town)**

The composite index (`store.py:172`) is a Python dictionary mapping `(year, month, town)` tuples to lists of row indices. It is built once during initialisation by reading all three columns sequentially. At query time, `query_composite_index` (`store.py:202`) returns matching rows in O(1), completely eliminating the need to scan year, month, and town columns:
- Pages read: **248 -> 76** (69% reduction vs. basic)
- Query time: **165.439s -> 2.388s** (98.6% reduction)
- Initialisation cost: ~0.929s (reading three columns to build the index)

**Combined effect (all three):**

| Metric | Basic | Combined |
|--------|------:|--------:|
| Total pages allocated | 7,665 | 1,399 |
| Total pages read | 248 | 65 |
| Initialisation time (s) | 0.001 | 0.920 |
| Query execution time (s) | 165.439 | 2.460 |
| **Total time (s)** | **165.441** | **3.380** |

The combined variant achieves a **97.96% reduction in total execution time** and a **73.8% reduction in pages read** compared to the baseline.

> **Suggested figure:** A table or grouped bar chart comparing all 5 variants across initialisation time, query time, total pages allocated, and total pages read.

---

## 3 Experiment Result

### 3.1 Execution Output

The program is executed via `python main.py` with matriculation number `A6626226B`. All five store variants run sequentially against the same query. Below is the complete benchmark output:

```
========= Column Store Summary =========
Compression:   Off
Zone Maps:     Off
Indexed:       Off

Phase                           Time (s)
----------------------------------------
Initialisation                     0.001
Query Execution                  165.439
----------------------------------------
Total                            165.441

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
Initialisation                     0.014
Query Execution                   50.102
----------------------------------------
Total                             50.116

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
Initialisation                     0.936
Query Execution                  147.276
----------------------------------------
Total                            148.212

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
Indexed:       On (year, month, town)

Phase                           Time (s)
----------------------------------------
Initialisation                     0.929
Query Execution                    2.388
----------------------------------------
Total                              3.316

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
Indexed:       On (year, month, town)

Phase                           Time (s)
----------------------------------------
Initialisation                     0.920
Query Execution                    2.460
----------------------------------------
Total                              3.380

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

The final variant also exports query results to `result/ScanResult_A6626226B.csv`. A sample of the output:

| (x, y) | Year | Month | Town | Block | Floor_Area | Flat_Model | Lease_Commence_Date | Price_Per_Square_Meter |
|---------|------|-------|------|-------|-----------|------------|--------------------|-----------------------|
| (1, 80) | 2016 | 2 | PASIR RIS | 149 | 126.0 | Improved | 1995 | 3413 |
| (2, 80) | 2016 | 2 | PASIR RIS | 149 | 126.0 | Improved | 1995 | 3413 |
| (3, 80) | 2016 | 2 | PASIR RIS | 149 | 126.0 | Improved | 1995 | 3413 |
| (8, 80) | 2016 | 2 | PASIR RIS | 149 | 126.0 | Improved | 1995 | 3413 |
| (1, 126) | 2016 | 2 | PASIR RIS | 149 | 126.0 | Improved | 1995 | 3413 |
| (1, 127) | -- | -- | -- | -- | -- | -- | -- | -- |

The result for `(x=1, y=80)` shows that the cheapest transaction per sqm in February 2016 in PASIR RIS/CLEMENTI with floor area >= 80 sqm was at Block 149 PASIR RIS, a 126 sqm Improved flat (lease from 1995) at $3,413/sqm. As `y` increases beyond 126, no qualifying records exist and the result becomes empty.

> **Suggested figure:** A screenshot of the terminal output showing all five benchmark summaries side by side. Also a screenshot or table of the first few rows of the CSV result file.

### 3.2 Correctness Evaluation

Correctness is validated by verifying that all five store variants produce **identical query results** for the same `(x, y)` parameter combinations. Since only the final combined variant exports to CSV, we confirm that:

1. **All variants identify the same best row** for each `(x, y)` pair -- the minimum-price-per-sqm transaction is deterministic regardless of which optimisation path is used.
2. **The composite index returns the same candidate rows** as the sequential year -> month -> town scan. The index is built from the same underlying column data, so the mapping is exact.
3. **Compression does not alter values** -- the dictionary encoding is lossless. Original string values are recoverable via `unmap_value` at result time, and numeric columns (`year`, `month`, `floor_area_sqm`, `resale_price`, `lease_commence_date`) are never compressed.
4. **Zone maps only skip pages guaranteed to not match** -- the `(min, max)` check is conservative. A page is skipped only if no value in `[min, max]` can satisfy the predicate. This preserves completeness (no false negatives).
5. **Page read counts differ but results are identical** -- the optimisations reduce I/O but never alter the logical result set. This is the fundamental correctness invariant.

The exported CSV (`ScanResult_A6626226B.csv`) contains 568 rows corresponding to all `(x, y)` combinations from `(1, 80)` to `(8, 150)`. Rows where no qualifying transaction exists are omitted from the CSV.

> **Suggested figure:** A comparison table showing that a few sample `(x, y)` pairs return the same result across all 5 variants (e.g. pick 3-4 representative pairs and show the matching output).
