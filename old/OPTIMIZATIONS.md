# Possible Optimizations (for report / future work)

Below are optimizations that fit the column-store project and the spec’s “design sophistication” (compression, reuse, indexing, handling large data). **Already done** vs **easy** vs **larger** is a rough guide.

---

## 1. Compression

| Idea | What it does | Status / effort |
|------|----------------|-----------------|
| **Dictionary coding** | Store categoricals (Town, Flat_Model, Block) as integer IDs; decode via dict. | ✅ **Already done** (Phase 1). |
| **Run-length encoding (RLE)** | If a column has long runs (e.g. same year for many rows), store (value, count) instead of value repeated. | **Easy.** Good if CSV is roughly ordered by time. Reduces size and can speed scans. |
| **Bit-packing** | Store year as offset from 2015 (0–10) in 4 bits; month in 4 bits; combine into one byte. | **Easy.** Saves space; decode on read. |
| **Delta encoding** | Store deltas (e.g. resale_price − previous) when column is sorted. | **Medium.** Helps if you sort first; decode step needed. |
| **Block compression** | Compress each 4KB (or N-row) block of a column with zstd/lz4; decompress when reading that block. | **Medium.** Good “compression” story for the report; need to integrate with block reader. |

---

## 2. Ordering / external sort

| Idea | What it does | Status / effort |
|------|----------------|-----------------|
| **Sort column store by (year, month, town_id)** | After Phase 1, sort the relation on disk by these keys (external sort), then rewrite column files. Scan for a given (year, month range, towns) only touches a **contiguous segment** of the file → far fewer pages read, many more “hits” if you re-query. | **Larger.** Requires external sort (e.g. merge sort over row ranges), then rewriting all columns. Big win for repeated queries. |
| **Sort matching indices before minima** | After building `idx_x`, sort `idx_x` by row index. Then when you iterate and “access” `floor_area[i]`, `resale_price[i]`, you touch pages in **ascending order** → sequential access → better cache/page hits in the simulator. | **Easy.** One line: `idx_x.sort()`. No change to result; only access pattern improves. |

---

## 3. Indexing

| Idea | What it does | Status / effort |
|------|----------------|-----------------|
| **Simple range index** | Build a small structure: for each (year, month), store “rows [start, end]” that have that (year, month). Then for a query you only read those ranges instead of the full columns. | **Medium.** Need to build index at colstore build time and use it in `build_index_list`. |
| **Sparse index / block min-max** | For each 4KB block, store (min_year, max_year, min_month, max_month, set of town_ids). Skip block entirely if it can’t contain a match. | **Medium.** Cuts scan work when many blocks don’t match. |

---

## 4. Reuse of intermediate results

| Idea | What it does | Status / effort |
|------|----------------|-----------------|
| **One idx per x** | Build `idx_x` once per x and reuse for all y. | ✅ **Already done.** |
| **Reuse idx across x** | For month range [start, start+x−1], `idx_{x+1}` is a superset of `idx_x`. So: scan once for the **largest** x (e.g. x=8), get `idx_8`; then derive `idx_7` by filtering `idx_8` (keep rows with month ≤ start+6), etc. **One full scan** instead of 8. | **Easy–medium.** Fewer scans; same minima logic per x. |

---

## 5. Memory / streaming (for “data too large to fit in main memory”)

| Idea | What it does | Status / effort |
|------|----------------|-----------------|
| **Don’t load full columns** | Instead of loading full `floor_area` and `resale_price`, for each x stream only the rows in `idx_x`: read column in blocks, extract values at indices in `idx_x`, then run minima. No full-column list in RAM. | **Medium.** More complex reads; good for report “large data” discussion. |
| **Memory-mapped files** | Use `mmap` on column files so the OS handles paging; “access” by row index without loading the whole file. | **Easy.** Reduces explicit memory use; page tracker still sees access pattern. |

---

## 6. Parallelism

| Idea | What it does | Status / effort |
|------|----------------|-----------------|
| **Parallel scan** | Split each column file into chunks; each thread scans one chunk and produces partial index lists; merge partial lists. | **Medium.** Need thread-safe or per-thread page tracker aggregation. |
| **Parallel x** | Run the loop over x in parallel: each x builds its own `idx_x` and minima; merge results at the end. | **Medium.** Easy with `concurrent.futures`; watch shared colstore reads. |

---

## 7. Column pruning / deferred read

| Idea | What it does | Status / effort |
|------|----------------|-----------------|
| **Defer output columns** | Don’t load `block_id`, `flat_model_id`, `lease_year` (and dicts) until we know the **winning row** per (x,y). Then read only those rows from the column files. | **Easy–medium.** Saves memory if you have many columns; slightly more complex output phase. |

---

## Quick wins you can add soon

1. **Sort `idx_x`** before the minima loop (sequential access → better page hits).
2. **Reuse idx across x**: build `idx_8` with one scan, then filter by month to get `idx_7`, …, `idx_1`.
3. **Memory-mapped columns** for `floor_area` and `resale_price` instead of loading full lists.
4. **RLE or bit-packing** on year/month in Phase 1 if you want a concrete “compression” example in the report.

If you say which of these you want (e.g. “sort idx_x + reuse idx across x”), the next step is to wire them into `scan.py` / `run_query.py` and keep the same output and page stats.
