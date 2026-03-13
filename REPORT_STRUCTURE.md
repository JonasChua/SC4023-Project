## SC4023 Semester Project Report

- **Module**: CE/CZ4123/SC4023 Big Data Management  
- **Project**: Column-Oriented HDB Resale Price Scanner  
- **Group Number**: \<Group Number\>  
- **Members**:  
  - \<Name 1\> — \<Matric 1\>  
  - \<Name 2\> — \<Matric 2\>  
  - \<Name 3\> — \<Matric 3\>  

---

## 1 Data Storage

- **1.1 Overall storage design**
  - Briefly describe why you chose a **column-store** approach instead of a row-store or tools like pandas/SQL.
  - Explain the **three variants** implemented in `main.py`:
    - basic column store
    - compressed column store
    - zone-map + compressed column store
  - State where on disk the data is stored (e.g. `data/store/basic`, `data/store/compressed`) and the role of `COLSTORE_DIR`.

- **1.2 Column layout and types**
  - Summarize the logical schema (year, month, town, flat_type, block, street_name, storey_range, floor_area_sqm, flat_model, lease_commence_date, resale_price).
  - Explain the **in-memory column abstractions** from `column.py`:
    - `UnsignedShortColumn`, `UnsignedCharColumn`, `FloatColumn`, `StringColumn`.
  - Explain how each logical field is mapped to a physical representation in the three configurations:
    - basic store: mostly fixed-length strings and numeric types.
    - compressed store: dictionary-encoded integers for repeated strings.
    - zone-map compressed store: compressed columns plus zone maps on selected numeric columns.

- **1.3 On-disk representation**
  - Describe how each column is stored in a **separate binary file** (`<name>.bin`) and how `Column.encode`/`decode` and `BLOCK_SIZE` define the physical layout.
  - Explain how the raw CSV (`ResalePricesSingapore.csv`) is loaded in `ColumnStore._initialize_column_files`:
    - parsing `month` into `(year, month)`  
    - converting values via `literal_eval` when possible  
    - writing encoded values sequentially per column.
  - Clarify the directory structure for:
    - basic column files  
    - compressed column files  
    - mapping CSV files (e.g. `<column>_map.csv`) written via `map_writer`.

- **1.4 Compression mappings**
  - Describe **dictionary encoding** for high-cardinality string columns:
    - how `Column.update_compression_mapping` assigns integer IDs to unique string values.
    - how mapping files are persisted and later reloaded by `map_loader` / `_load_compression_mappings`.
  - Explain how compressed IDs are transparently converted back to human-readable strings by:
    - `Column.unmap_value`  
    - the logic in `QueryEngine.select_row_data` that unmapped integer IDs when `enable_compression_map` is enabled.

- **1.5 Zone maps**
  - Explain the idea of a **zone map** and how it is stored per block in `Column._zone_map`.
  - Describe how `_initialize_zone_maps` scans each column’s blocks to compute `(min, max)` for numeric columns (year, month, floor_area_sqm, lease_commence_date, resale_price).
  - Clarify how `_match_zone_map` decides whether a block can be skipped for a given predicate (e.g. year or month range, minimum floor area).

- **1.6 File I/O and caching**
  - Explain how `ColumnStore._read_column` reads fixed-size blocks from disk and decodes values into Python types.
  - Describe the **block cache** (`self._cache`) and how it reduces repeated disk reads.
  - Mention how `file_read_count` and `print_summary` are used to report I/O statistics for each configuration.

- **1.7 Handling input/output and exceptions**
  - Describe assumptions and edge cases:
    - handling invalid month strings or missing data.
    - handling division by zero in price-per-square-meter computation (skipping zero floor area in `select_minimum_price_per_floor_area`).
  - Summarize how the program writes the final query output to `ScanResult_<Matric>.csv` in the `result` directory (path creation, header row, row format).

---

## 2 Data Processing

- **2.1 Query interpretation from matriculation number**
  - Explain how `QueryParser` extracts digits from the matriculation number and derives:
    - **target year** (last digit rule relative to 2010/2020).
    - **start month** (second-last digit, with 0 mapped to October).
    - **set of towns** based on `DIGIT_TO_TOWN` and all digits in the matriculation number.
  - Clarify how this matches the official specification in the assignment.

- **2.2 Scanning strategy and filter pipeline**
  - Describe the filter order in `QueryEngine.execute_query` for each \((x, y)\):
    - filter by target year (`filter_year_index`).
    - filter by month range from `start_month` to `end_month` (`filter_month_index`).
    - filter by towns (`filter_town_index`), using mapping IDs when compression is enabled.
    - filter by minimum floor area (`filter_minimum_floor_area_index`).
  - Explain how `ColumnStore.scan_column`:
    - computes the row indices affected by each block.  
    - optionally uses pre-filtered indices to avoid scanning rows that cannot match previous filters.

- **2.3 Computing minimum price per square meter**
  - Explain how `select_minimum_price_per_floor_area`:
    - iterates over candidate row indices.  
    - reads `floor_area_sqm` and `resale_price` using `get_value`.  
    - computes price-per-square-meter and keeps track of the minimum.
  - Describe how the result is stored in `self.results[(x, y)]` and how the program handles pairs with no qualifying record (storing `None`).

- **2.4 Zone-map pruning and caching behavior**
  - Explain how `scan_column` interacts with zone maps:
    - `_match_zone_map` checks whether a block’s \((\min, \max)\) can satisfy the predicate; if not, the block is skipped entirely.
    - this is especially useful for range predicates on year, month, floor area, and lease commencement date.
  - Discuss how the **block cache** and **zone maps** together reduce disk I/O:
    - cache avoids rereading hot blocks.  
    - zone maps prevent reading blocks that cannot contain matching rows.

- **2.5 Complexity and performance considerations**
  - Provide a qualitative analysis of time and space complexity:
    - number of scans: iterating over all \((x, y)\) pairs (x from 1 to 8, y from 80 to 150).  
    - cost per pair: sequential scans over selected columns.
  - Compare expected performance among:
    - basic store (no compression / zone maps).  
    - compressed store (smaller I/O but still full scans).  
    - zone-map compressed store (fewer blocks scanned for selective predicates).

- **2.6 Limitations and possible improvements**
  - Mention limitations such as:
    - zone maps on numeric columns only; dictionary-encoded columns not yet zone-mapped.  
    - assuming data fits on disk and can be scanned multiple times.
  - Suggest potential improvements:
    - adding multi-column zone maps or bitmap indexes.  
    - experimenting with different block sizes.  
    - incremental indexing or precomputed query results for reused \((x, y)\) ranges.

---

## 3 Experiment Result

- **3.1 Experimental setup**
  - Describe the environment:
    - hardware (CPU, RAM, storage).  
    - OS and Python version.  
    - data size (number of rows in `ResalePricesSingapore.csv`).
  - State the matriculation number used and the derived:
    - target year, start month, and set of towns.

- **3.2 Correctness validation**
  - Explain how you validated the correctness of selected \((x, y)\) outputs:
    - choose a few representative \((x, y)\) pairs.  
    - reproduce the same filters in Excel / Google Sheets or another tool.  
    - compute the minimum price-per-square-meter and compare with your program’s result.
  - Include (or refer to appendix for):
    - screenshots of the external tool showing filtered rows and computed minimum.  
    - screenshots of your `ScanResult_<Matric>.csv` or console output for the same pairs.

- **3.3 Performance comparison**
  - Present a small table or summary comparing:
    - basic vs compressed vs zone-map compressed runs.  
    - metrics such as:
      - total runtime per configuration (if measured).  
      - per-column block count and read count from `print_summary`.  
  - Interpret the results:
    - how compression affects disk usage and read counts.  
    - how zone maps reduce the number of blocks scanned for selective queries.  
    - discuss any observed trade-offs (e.g. preprocessing time to build zone maps).

- **3.4 Discussion**
  - Reflect on whether the implementation meets the assignment goals:
    - column-oriented storage.  
    - ability to answer all required \((x, y)\) queries.  
    - optimizations and design sophistication.
  - Summarize key takeaways about column stores, compression, and simple indexing (zone maps) for analytical workloads.

---

## Appendix (Optional, Figures Only)

- **Screenshots**
  - Program execution screenshots showing successful runs of:
    - basic store.  
    - compressed store.  
    - zone-map compressed store (including summary output).  
  - Screenshots comparing your CSV output with Excel/Sheets results for selected \((x, y)\) pairs.

- **Additional figures**
  - Any diagrams or sketches of your column-store architecture, compression workflow, or zone-map layout that did not fit into the main 5 pages.

---

## Contribution Form (Submitted Separately)

- **Note**: Follow the assignment’s official **Contribution Form** template. In the final submission, include the filled and signed form alongside:
  - `ScanResult_<Matric>.csv`  
  - source code folder  
  - final `Report.pdf` based on the structure above.

