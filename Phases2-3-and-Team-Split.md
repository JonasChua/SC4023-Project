# Phases 2–3 Plan and Team Work Split

This document describes the remaining work (Phase 2: query conditions from matric number; Phase 3: streaming scan + minima; output; validation) and suggests how to split it among **3 people** with clear interfaces and dependencies.

---

## Phase 2: Derive Query Conditions from Matric Number

### 2.1 What the spec says

- **Target year:** Last digit of matric number must match last digit of year (and the year must not be 2025 as the “target” for the query).
- **Start month:** Second-last digit of matric; **0 means October** (i.e. 10).
- **Town list:** Certain digits of the matric map to towns per **Table 1** (from the spec). You need the set of **town IDs** that correspond to those digits.
- **Valid (x, y) pairs:**  
  - \( x \in [1..8] \), \( y \in [80..150] \).  
  - A pair (x, y) is **valid** if there exists at least one row satisfying the (year, month range, town) filter for that x, with `floor_area >= y`, and the **minimum** price per sqm for those rows is **≤ 4725** (rounded).

### 2.2 Implementation tasks

1. **Parse matric number**  
   - Input: matric number string (e.g. from config or command line).  
   - Extract digits (e.g. last, second-last, and whatever digits define towns per Table 1).

2. **Compute derived values**  
   - `targetYear`: from last digit (e.g. digit 8 → year 2018; exclude 2025 if spec says “not 2025 as target”).  
   - `startMonth`: from second-last digit; map 0 → 10 (October).  
   - `townSet`: set of **town_id** values (integers) from the spec’s Table 1 mapping.

3. **Precompute month window per x**  
   - For each \( x \in 1..8 \):  
     - Month window = `startMonth` to `startMonth + x - 1` (same calendar year).  
     - If this window would go past December or into 2025, handle per spec (e.g. skip or cap).

4. **Expose a clear interface** (e.g. two functions the main script can call):  
   - `get_query_params(matric) -> (target_year, start_month, town_ids)`  
   - `get_month_range(x) -> (start_month, end_month)` for \( x \in 1..8 \).

### 2.3 Dependencies

- Needs **Table 1** from the spec (digit → town mapping).  
- Output is **numeric/sets only**; no column store or dict files needed for this phase’s logic (dicts only needed when writing final CSV).

---

## Phase 3: Processing Plan (Streaming Scan + Reuse)

### 3.1 Goal

- For each (x, y) with \( x \in 1..8 \), \( y \in 80..150 \), determine:
  - Either the **single row** that achieves the **minimum** price per sqm (with year/month/town/floor_area constraints),  
  - Or “No result” if no such row or min > 4725.

- Do this **without** 568 full scans: reuse work per x and use block-wise reads.

### 3.2 x-first strategy (reuse intermediate results)

For each **x** (1..8):

1. **Build `idx_x` (matching row indices)**  
   - One scan (or block-wise scan) over the column store.  
   - Keep only row indices where:  
     - `year == targetYear`  
     - `month` in [startMonth, startMonth + x - 1]  
     - `town_id` in `townSet`  
   - Store these indices in a list `idx_x`.

2. **For y = 80..150, compute best row per y using only `idx_x`**  
   - For each row index \( i \in idx_x \):  
     - Read `floor_area[i]`, `resale_price[i]`.  
     - `ppm = resale_price / floor_area`.  
     - This row qualifies for every \( y \le \min(150, \lfloor floor\_area \rfloor) \) (and \( y \ge 80 \)).  
   - Maintain `bestPrice[y]` and `bestRowIndex[y]`; update when a row gives a lower ppm for that y.  
   - One pass over `idx_x` updates **all** y values (no 71 separate scans).

3. **Validity**  
   - For each y: if `bestRowIndex[y]` is set and `round(bestPrice[y]) <= 4725` → output a row for (x, y); else “No result”.

### 3.3 Block-wise (page-style) scan

- Read column files in **chunks** (e.g. 4KB, 64KB, or N rows per block).  
- For each block:  
  - Read the slice of `year`, `month`, `town_id` for that block.  
  - Compute a boolean mask `match_time_and_town`.  
  - Append matching **global** row indices to `idx_x`.  
- This aligns with “memory hierarchy” and “page/block access” for the report.

### 3.4 What to read from the column store

- **To build `idx_x`:** `year.i16`, `month.u8`, `town_id.u8` (and row index = file position / element size).  
- **To compute minima:** for each \( i \in idx_x \), read `floor_area.f32[i]`, `resale_price.i32[i]`.  
- **To write output:** for the winning row per (x, y), also need `lease_year`, `block_id`, `flat_model_id` (and year, month, town_id) for decoding via dicts.

### 3.5 Dependencies

- Phase 1 column store and dict files must exist.  
- Phase 2 must provide: `targetYear`, `startMonth`, `townSet`, and the month-range rule for each x.

---

## Output File: `ScanResult_<MatricNum>.csv`

### Format

- **Sort order:**  
  - Primary: x increasing (1..8).  
  - Secondary: for same x, y increasing (80..150).

- **Per (x, y) that is valid:** one row with columns:  
  `(x,y), Year, Month, Town, Block, Floor_Area, Flat_Model, Lease_Commence_Date, Price_Per_Square_Meter`

- **Per (x, y) that is “No result”:** one row with “No result” (exact wording per spec).

- **Decoding:**  
  - Use `dict_town.csv`, `dict_block.csv`, `dict_flat_model.csv` to map `town_id`, `block_id`, `flat_model_id` → strings.  
  - Month: can be output as integer or formatted (e.g. YYYY-MM) per spec.  
  - Price_Per_Square_Meter: rounded integer.

---

## Testing and Validation (for report)

1. Pick **3 (x, y) pairs:**  
   - One with a result,  
   - One borderline (min ppm close to 4725),  
   - One “No result”.

2. In Excel/Sheets:  
   - Filter raw CSV (or a copy) by: Year, Month range, Town (by name), Floor_Area ≥ y.  
   - Compute `Resale_Price / Floor_Area`, take **min**.  
   - Compare with program output and threshold 4725.

3. Screenshot filters, formula, and result; add to Report.pdf.

---

## Suggested Work Split for 3 People

Assume one shared repo, one main script or small module set, and clear handoffs.

---

### **Person A: Matric parsing and query parameters (Phase 2)**

**Scope**

- Implement matric parsing and all spec rules for:  
  target year, start month (0 → October), town set from Table 1.
- Precompute, for each x in 1..8, the month range (start_month, end_month) and any “skip 2025” rule.
- Provide **a few functions** that the main script (or other modules) can call—no separate “service” or API; just normal Python functions in a shared module.

**Deliverables**

- A module (e.g. `query_params.py` or `matric.py`) with functions such as:
  - `get_query_params(matric_str) -> (target_year: int, start_month: int, town_ids: set[int])`
  - `get_month_range(x: int) -> (start_month: int, end_month: int)` for x in 1..8 (or equivalent).
- Unit tests with 1–2 example matric numbers and expected target year, start month, town set.
- Short doc (in code or in this MD) of Table 1 mapping (digit → town name or town_id).

**Handoff**

- Person B and C just call these functions from the main script (or their modules); they don’t need to know digit positions or Table 1.

**Rough time**

- ~1–2 days (including reading spec for Table 1 and edge cases).

---

### **Person B: Block scan and index lists (Phase 3 – scan + idx_x)**

**Scope**

- Implement **block-wise** (page-style) reading of the column store.
- For a given (target_year, start_month, month_range for x, town_ids), **scan** the column store and produce **one list of row indices** `idx_x` per x.
- Do **not** implement the minima over y or the output file; only build and return `idx_x` (or an iterator over matching indices).

**Deliverables**

- Module (e.g. `scan.py` or `colstore_scan.py`) with something like:
  - `build_index_list(colstore_path, target_year, start_month, end_month, town_ids) -> list[int]`
  - Internally: read `year.i16`, `month.u8`, `town_id.u8` in blocks; compute mask; collect global row indices.
- Configurable block size (e.g. 4096 or 65536 bytes, or N rows) and a one-line comment linking to “page/block” for the report.
- Use Person A’s functions to get `target_year`, `start_month`, and per-x month range when integrating.

**Handoff**

- Person C will call `build_index_list(...)` for each x and get back `idx_x`. Person C is responsible for reading `floor_area`, `resale_price`, and computing minima.

**Rough time**

- ~2–3 days (column store layout, block sizing, testing with Phase 1 data).

---

### **Person C: Minima, validity, output file and validation (Phase 3 – results + CSV + testing)**

**Scope**

- For each x, take `idx_x` from Person B; read `floor_area` and `resale_price` for those rows; implement the **single-pass-over-idx_x** loop that updates `bestPrice[y]` and `bestRowIndex[y]` for y in 80..150.
- Apply validity rule: round(bestPrice[y]) ≤ 4725 and row exists → output row; else “No result”.
- **Write** `ScanResult_<MatricNum>.csv`: correct order (x, then y), correct columns, decoding town/block/flat_model via dict_*.csv.
- Run the full pipeline (A + B + C) for at least one matric number.
- Perform **Excel validation** for 3 (x,y) pairs and prepare screenshots for the report.

**Deliverables**

- Module (e.g. `minima.py` or `results.py`) that:
  - Takes `idx_x`, reads floor_area and resale_price for those indices, returns per-y best row index and best ppm (or equivalent).
- Output module (e.g. `output_csv.py`) that:
  - Takes the full result structure (per (x,y): either row id + fields or “No result”), decodes via dicts, writes CSV.
- **Main/runner** (e.g. `run_scan.py`) that:
  - Takes matric number (and paths to colstore/dicts);
  - Calls A → gets params;
  - For each x, calls B → gets idx_x;
  - For each x, calls C’s minima logic → gets best per y;
  - Applies validity, then calls output writer.
- Document the 3 (x,y) validation pairs and add Excel validation screenshots (for Report.pdf).

**Handoff**

- Person C depends on A and B; integration and end-to-end testing are Person C’s responsibility. Person C also owns the “Experiment Result” and “Validation” parts of the report.

**Rough time**

- ~2–3 days (minima logic, dict decoding, CSV format, integration, validation).

---

## Integration and Report

- **Integration:** One person (e.g. Person C) runs the full pipeline and fixes any interface mismatches (e.g. exact return types of `get_month_range` or `build_index_list`). All three should agree on function names and types early.
- **Report.pdf:**  
  - **Data storage:** Can be written by anyone (e.g. Person A or B) using Phase1.md and the column store layout; mention block-wise read.  
  - **Data processing:** Person B (block scan, idx_x) + Person C (single-pass minima, reuse).  
  - **Experiment result and validation:** Person C (screenshots, Excel validation).

---

## Summary Table

| Person | Main focus                         | Key deliverable                         | Depends on     |
|--------|-------------------------------------|-----------------------------------------|----------------|
| **A**  | Phase 2: matric → query params      | `query_params` module + tests + Table 1  | Spec (Table 1) |
| **B**  | Phase 3: block scan → `idx_x`       | `scan` module with block-wise read      | Phase 1, A’s module |
| **C**  | Phase 3: minima, output CSV, tests  | Minima + output module + runner + validation | A, B, Phase 1 (dicts) |

This keeps Phase 2 and the “scan” part of Phase 3 separate from the “minima and output” part, so two people can work in parallel (A and B), and C integrates and finishes the pipeline and report validation.
