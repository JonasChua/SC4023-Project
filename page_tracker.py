"""
Simulated page cache for reporting hits and misses (e.g. 4KB page size).
Used to demonstrate memory-hierarchy / block access in the report.
"""

PAGE_SIZE_BYTES = 4096


class PageTracker:
    """Tracks which pages have been 'loaded'; counts hits (reuse) vs misses (first load)."""

    def __init__(self, page_size: int = PAGE_SIZE_BYTES):
        self.page_size_bytes = page_size
        self.loaded_pages: set[tuple[str, int]] = set()
        self.hits = 0
        self.misses = 0

    def access(self, column: str, row_index: int, element_size: int) -> None:
        """
        Simulate accessing one row in a column file. The row lives on a logical page.
        First access to that page = miss; subsequent access = hit.
        """
        page_id = (row_index * element_size) // self.page_size_bytes
        key = (column, page_id)
        if key in self.loaded_pages:
            self.hits += 1
        else:
            self.loaded_pages.add(key)
            self.misses += 1

    def record_scan_block(self, column: str, block_index: int) -> None:
        """
        Record that we read one block (page) during sequential scan.
        Typically all scan blocks are first-time reads = misses.
        """
        key = (column, block_index)
        if key in self.loaded_pages:
            self.hits += 1
        else:
            self.loaded_pages.add(key)
            self.misses += 1

    @property
    def total(self) -> int:
        return self.hits + self.misses

    def summary(self) -> str:
        return f"Page hits: {self.hits}, Page misses: {self.misses} (page size: {self.page_size_bytes} B)"
