# Phase 1: Building the On-Disk Column Store

This document explains how the column store is built from the raw CSV in a single pass, including the role of every file and the use of all dictionary CSV files.

---

## 1. Overview

**Goal:** Convert the row-oriented source CSV (`ResalePricesSingapore.csv`) into a **column store**: each attribute is stored in its own binary file, with one value per row in the same order across all files. String attributes (Town, Flat_Model, Block) are **dictionary-coded** to integer IDs; the mapping from ID back to string is saved in `dict_*.csv` files for decoding in later phases and for inspection.

**Design choices:**
- **Single streaming pass** over the CSV (no pandas; line-by-line read).
- **Compact binary types** for smaller disk footprint and cache-friendly access.
- **Dictionary coding** for categorical strings to save space and speed up comparisons.

---

## 2. Folder Structure and File Layout

After Phase 1, the layout is:

```
data/
  raw/
    ResalePricesSingapore.csv   (source; or place CSV in project root)
  colstore/
    year.i16
    month.u8
    town_id.u8
    floor_area.f32
    resale_price.i32
    lease_year.i16
    block_id.u16
    flat_model_id.u16
    dict_town.csv
    dict_flat_model.csv
    dict_block.csv
```

- **Binary column files** (e.g. `year.i16`, `month.u8`): one value per row, same row index across all files. Row *i* in the relation is the *i*-th value in each column file.
- **Dictionary files** (`dict_*.csv`): there are **three** because we dictionary-code **three** string columns. Each dict maps that column’s integer ID back to the original string. Used when writing the final output (Town, Block, Flat_Model) and by the inspection helper.

**Why three dicts? What does each do?**

| Dictionary file       | Pairs with column   | What it does |
|-----------------------|---------------------|---------------|
| **`dict_town.csv`**   | `town_id.u8`        | Decodes town ID → town name (e.g. `0` → `"ANG MO KIO"`). |
| **`dict_flat_model.csv`** | `flat_model_id.u16` | Decodes flat model ID → model name (e.g. `1` → `"New Generation"`). |
| **`dict_block.csv`**  | `block_id.u16`      | Decodes block ID → block string (e.g. `0` → `"174"`, later IDs for values like `"316A"`). |

So: one dict per dictionary-coded column. When we need to show or output the **string** for that column, we look up the stored ID in the matching dict.

---

## 3. Column Types and Why

| Column file       | Type    | Python `struct` | Reason |
|-------------------|---------|-----------------|--------|
| `year.i16`        | int16   | `h`             | Years 2015–2025 fit in 16 bits. |
| `month.u8`        | uint8   | `B`             | Month 1–12. |
| `town_id.u8`      | uint8   | `B`             | Small number of distinct towns; ID fits in one byte. |
| `floor_area.f32`  | float32 | `f`             | Square meters; float32 is sufficient and compact. |
| `resale_price.i32`| int32   | `i`             | Price in dollars; fits in 32-bit signed int. |
| `lease_year.i16`  | int16   | `h`             | Lease commence year (e.g. 1966–2022). |
| `block_id.u16`    | uint16  | `H`             | Many distinct blocks (e.g. "174", "316A"); need 16 bits. |
| `flat_model_id.u16` | uint16 | `H`             | Distinct flat model names; 16 bits is enough. |

Using small fixed-width types keeps the column store compact and aligns with **page/block-oriented** access: sequential reads of a column file are cache-friendly and match the memory-hierarchy idea from the spec.

---

## 4. Single-Pass Build Process

The script `build_colstore.py` does the following in **one pass** over the CSV:

1. **Open all column files** for binary append (and create `data/colstore/` if needed).
2. **Initialize three in-memory maps:** `town_map`, `flat_model_map`, `block_map` (each: string → integer ID, assigned in first-seen order).
3. **For each CSV row:**
   - Parse `month` (e.g. `"Jan-15"`) into `(year, month)` (2015, 1). The source uses `Mon-YY`; year is 20YY for YY ≤ 25, else 19YY.
   - Map `town` → `town_id`, `flat_model` → `flat_model_id`, `block` → `block_id` using the three maps (new strings get the next ID).
   - Parse numeric fields: `floor_area_sqm`, `resale_price`, `lease_commence_date` (stored as `lease_year`).
   - **Append one value to each column file**, in the same order, so row alignment is preserved.
4. **Close all column files.**
5. **Write the three dictionary CSVs** (see below) so that any phase can decode IDs back to strings.

**Row-order invariant:** For every row index *i*, the *i*-th value in `year.i16`, the *i*-th value in `month.u8`, … and the *i*-th value in `flat_model_id.u16` all refer to the same logical row. There is no separate row index file; alignment is by position.

---

## 5. Dictionary Coding and the `dict_*.csv` Files

### 5.0 Why assign an ID to each name?

The column store files (e.g. `town_id.u8`) are **binary**: they hold only numbers, not text. We can’t write `"ANG MO KIO"` or `"New Generation"` into a `.u8` or `.u16` file. So we do two things:

1. **Assign a unique integer ID to each distinct string** (e.g. first town seen → 0, next → 1, …). We store *only that ID* in the column file. That’s why the column is called `town_id`, not `town`: it holds an ID, not the name.
2. **Save the mapping “ID → name”** in a dictionary CSV. Later, when we need to show or output the actual name (e.g. in the final result or in the inspector), we read the ID from the column store and look it up in the dict to get the string back.

So we assign IDs so that (a) the column store can stay numeric and compact, and (b) we still have a way to recover the original names—the three `dict_*.csv` files are that lookup table for each of the three string columns we coded.

### 5.1 Why dictionary coding?

- **Smaller storage:** Store a small integer (e.g. 1 byte for town) instead of a long string (e.g. `"ANG MO KIO"`) in the column file.
- **Faster comparisons:** Phase 2/3 filter by town set; comparing integers is cheaper than comparing strings.
- **Clear separation:** The “meaning” of each ID lives in the dictionary files; the column store itself stays numeric and compact.

### 5.2 Which columns are dictionary-coded?

- **Town** → `town_id` (stored in `town_id.u8`).
- **Flat_Model** → `flat_model_id` (stored in `flat_model_id.u16`).
- **Block** → `block_id` (stored in `block_id.u16`). Block in the CSV can be numeric or alphanumeric (e.g. `"174"`, `"316A"`); we treat it as a string and assign an ID.

### 5.3 Format of each `dict_*.csv`

Each dictionary file has two columns:

- **`id`** – the integer ID (0, 1, 2, …) assigned during the single pass.
- **`value`** – the original string (Town name, Flat_Model name, or Block string).

Example **`dict_town.csv`**:

```csv
id,value
0,ANG MO KIO
1,BEDOK
2,BISHAN
...
```

Example **`dict_flat_model.csv`**:

```csv
id,value
0,Improved
1,New Generation
2,Model A
...
```

Example **`dict_block.csv`** (same structure; many more rows):

```csv
id,value
0,174
1,541
2,163
...
```

IDs are assigned in **encounter order** during the CSV pass: the first distinct string gets 0, the next gets 1, and so on. The build script writes these files at the end so that `id` matches the values written in the corresponding `*_id` column files.

### 5.4 How the dictionary files are used

- **Phase 2 / Phase 3 (query and output):** When writing the final result (e.g. `ScanResult_<MatricNum>.csv`), each row must output **Town**, **Block**, and **Flat_Model** as strings. The query phase reads the column store and gets `town_id`, `block_id`, `flat_model_id` for the chosen row; it then uses `dict_town.csv`, `dict_block.csv`, and `dict_flat_model.csv` to map those IDs back to the strings to write.
- **Inspection helper (`inspect_colstore.py`):** To show a human-readable preview of the column store, the helper loads each `dict_*.csv` into an array (index = id, value = string) and uses it to decode the IDs in the first N rows when printing the table.

So: **dict_*.csv = decode ID → original string** wherever the pipeline needs to output or display text.

---

## 6. Source CSV Mapping

The source CSV columns are mapped as follows:

| CSV column            | Column store column   | Notes |
|-----------------------|------------------------|-------|
| `month`               | `year` + `month`       | Parsed from `Mon-YY` (e.g. Jan-15 → 2015, 1). |
| `town`                | `town_id`              | Dictionary-coded. |
| `floor_area_sqm`      | `floor_area`           | Float, stored as float32. |
| `resale_price`        | `resale_price`         | Int32. |
| `lease_commence_date` | `lease_year`           | Int16 (year only). |
| `block`               | `block_id`             | Dictionary-coded (string as in CSV). |
| `flat_model`          | `flat_model_id`        | Dictionary-coded. |

Other CSV columns (e.g. `flat_type`, `street_name`, `storey_range`) are not stored in the column store for this project.

---

## 7. How to Run and Verify

**Build the column store (Phase 1):**

```bash
python build_colstore.py
```

- Reads from `data/raw/ResalePricesSingapore.csv` if present, otherwise from `ResalePricesSingapore.csv` in the project root.
- Writes all column files and the three `dict_*.csv` files under `data/colstore/`.
- Prints the number of rows written.

**Inspect the column store:**

```bash
python inspect_colstore.py           # summary + first 10 rows (decoded)
python inspect_colstore.py -n 20      # first 20 rows
python inspect_colstore.py -n 0       # summary only
python inspect_colstore.py --stats    # summary + min/max per column
```

The inspector uses the **dict_*.csv** files to show Town, Block, and Flat_Model as strings in the printed table; without them, only numeric IDs would be visible.

---

## 8. Summary

- Phase 1 converts the CSV into a **column store**: one binary file per attribute, same row order everywhere.
- **Dictionary coding** is used for Town, Flat_Model, and Block; their IDs are stored in `town_id.u8`, `flat_model_id.u16`, and `block_id.u16`.
- **`dict_town.csv`**, **`dict_flat_model.csv`**, and **`dict_block.csv`** store the mapping **id → string** and are used whenever we need to decode those IDs (final output or inspection). They are written once at the end of the single CSV pass and then read by later phases and by the inspection helper.
