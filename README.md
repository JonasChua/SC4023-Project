# SC4023-Project

## Overview

This project implements an on-disk **column store** for Singapore HDB resale flat price data, supporting three progressively optimised variants. Each column in the relation is stored as a separate binary file so that queries only read the columns they actually need, avoiding unnecessary I/O on unrelated attributes.

---

## Column Store Design

The source CSV (`ResalePricesSingapore.csv`) is converted to binary column files during initialisation. Each column file stores values in row order using compact binary types (e.g. `uint8`, `uint16`, `float32`). Data is accessed in **4 KB blocks**; the store tracks how many blocks are allocated per column and how many are actually read per query.

Three store variants are implemented, each building on the last:

### 1. Basic Column Store
Strings are stored as fixed-length byte arrays (e.g. `town` as 32 bytes, `flat_type` as 16 bytes). No compression is applied. This is the baseline.

### 2. Compressed Column Store
**Dictionary encoding** is applied to all categorical string columns (`town`, `flat_type`, `block`, `street_name`, `storey_range`, `flat_model`). Each unique string value is assigned a small integer ID, and only the ID is stored on disk:

| Column         | Basic type       | Compressed type    | Space saving |
| -------------- | ---------------- | ------------------ | ------------ |
| `town`         | `32s` (32 bytes) | `uint8` (1 byte)   | 32×          |
| `flat_type`    | `16s` (16 bytes) | `uint8` (1 byte)   | 16×          |
| `block`        | `8s` (8 bytes)   | `uint16` (2 bytes) | 4×           |
| `street_name`  | `32s` (32 bytes) | `uint16` (2 bytes) | 16×          |
| `storey_range` | `8s` (8 bytes)   | `uint8` (1 byte)   | 8×           |
| `flat_model`   | `32s` (32 bytes) | `uint16` (2 bytes) | 16×          |

The ID-to-string mappings are persisted to `*_map.csv` files and loaded back at query time for decoding. Storing smaller values means more rows fit per 4 KB block, reducing the total block count from **7,665 → 1,399** (an 82% reduction).

### 3. Zone Map Compressed Column Store
Adds **zone maps** on top of the compressed store. A zone map records the `(min, max)` value for each block of a column and is held in memory. During a scan with a range or equality predicate, any block whose `[min, max]` range cannot possibly satisfy the predicate is **skipped entirely** without an I/O read. This is particularly effective for columns with some natural ordering (e.g. `year`, `month`), allowing large swaths of the file to be pruned at query time. Blocks read drop from **189 → 72** compared to the compressed store alone.

---

## Optimisation Summary

| Technique                           | Benefit                                                                            |
| ----------------------------------- | ---------------------------------------------------------------------------------- |
| **Column-oriented storage**         | Only columns referenced by the query are read from disk                            |
| **Compact binary types**            | Smaller per-value footprint; more rows fit per block                               |
| **Dictionary encoding**             | Categorical strings replaced by 1–2 byte integer IDs; fewer blocks allocated       |
| **Zone maps (block-level min/max)** | Entire blocks skipped when predicate cannot match; significantly fewer block reads |
| **Block cache**                     | Previously read blocks are cached in memory to avoid redundant I/O within a query  |

---

## Statistics
Statistics for the three column stores when executing the same query (matric number: A6626226B):
```
========== Basic Column Store ==========
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

======= Compressed Column Store ========
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

=== Zone Map Compressed Column Store ===
Column                  Blocks      Read
----------------------------------------
year                       127        11
month                       64         5
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
Total                     1399        72
```