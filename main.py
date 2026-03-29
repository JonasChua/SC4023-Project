from column import FloatColumn, StringColumn, UnsignedCharColumn, UnsignedShortColumn
from constants import COLSTORE_DIR
from query import QueryEngine
from store import ColumnStore


def run_basic_store_query(matric_str):
    columns = dict(
        year=UnsignedShortColumn("year"),
        month=UnsignedCharColumn("month"),
        town=StringColumn("town", 16),
        flat_type=StringColumn("flat_type", 16),
        block=StringColumn("block", 4),
        street_name=StringColumn("street_name", 32),
        storey_range=StringColumn("storey_range", 8),
        floor_area_sqm=FloatColumn("floor_area_sqm"),
        flat_model=StringColumn("flat_model", 32),
        lease_commence_date=UnsignedShortColumn("lease_commence_date"),
        resale_price=FloatColumn("resale_price"),
    )
    store = ColumnStore(["basic"], COLSTORE_DIR / "basic", columns)
    query_engine = QueryEngine(store, matric_str)
    query_engine.execute_query()
    store.print_summary()


def run_compressed_store_query(matric_str):
    columns = dict(
        year=UnsignedShortColumn("year"),
        month=UnsignedCharColumn("month"),
        town=UnsignedCharColumn("town", enable_compression_map=True),
        flat_type=UnsignedCharColumn("flat_type", enable_compression_map=True),
        block=UnsignedShortColumn("block", enable_compression_map=True),
        street_name=UnsignedShortColumn("street_name", enable_compression_map=True),
        storey_range=UnsignedCharColumn("storey_range", enable_compression_map=True),
        floor_area_sqm=FloatColumn("floor_area_sqm"),
        flat_model=UnsignedShortColumn("flat_model", enable_compression_map=True),
        lease_commence_date=UnsignedShortColumn("lease_commence_date"),
        resale_price=FloatColumn("resale_price"),
    )
    store = ColumnStore(["compressed"], COLSTORE_DIR / "compressed", columns)
    query_engine = QueryEngine(store, matric_str)
    query_engine.execute_query()
    store.print_summary()


def run_zone_map_basic_store_query(matric_str):
    columns = dict(
        year=UnsignedShortColumn("year", enable_zone_map=True),
        month=UnsignedCharColumn("month", enable_zone_map=True),
        town=StringColumn("town", 16),
        flat_type=StringColumn("flat_type", 16),
        block=StringColumn("block", 4),
        street_name=StringColumn("street_name", 32),
        storey_range=StringColumn("storey_range", 8),
        floor_area_sqm=FloatColumn("floor_area_sqm", enable_zone_map=True),
        flat_model=StringColumn("flat_model", 32),
        lease_commence_date=UnsignedShortColumn(
            "lease_commence_date", enable_zone_map=True
        ),
        resale_price=FloatColumn("resale_price", enable_zone_map=True),
    )
    store = ColumnStore(["zone map", "basic"], COLSTORE_DIR / "basic", columns)
    query_engine = QueryEngine(store, matric_str)
    query_engine.execute_query()
    store.print_summary()


def run_indexed_basic_store_query(matric_str):
    columns = dict(
        year=UnsignedShortColumn("year"),
        month=UnsignedCharColumn("month"),
        town=StringColumn("town", 16),
        flat_type=StringColumn("flat_type", 16),
        block=StringColumn("block", 4),
        street_name=StringColumn("street_name", 32),
        storey_range=StringColumn("storey_range", 8),
        floor_area_sqm=FloatColumn("floor_area_sqm"),
        flat_model=StringColumn("flat_model", 32),
        lease_commence_date=UnsignedShortColumn("lease_commence_date"),
        resale_price=FloatColumn("resale_price"),
    )
    store = ColumnStore(["indexed", "basic"], COLSTORE_DIR / "basic", columns)
    query_engine = QueryEngine(store, matric_str)
    query_engine.execute_query()
    store.print_summary()


def run_indexed_zone_map_compressed_store_query(matric_str):
    columns = dict(
        year=UnsignedShortColumn("year"),
        month=UnsignedCharColumn("month"),
        town=UnsignedCharColumn("town", enable_compression_map=True),
        flat_type=UnsignedCharColumn("flat_type", enable_compression_map=True),
        block=UnsignedShortColumn("block", enable_compression_map=True),
        street_name=UnsignedShortColumn("street_name", enable_compression_map=True),
        storey_range=UnsignedCharColumn("storey_range", enable_compression_map=True),
        floor_area_sqm=FloatColumn("floor_area_sqm", enable_zone_map=True),
        flat_model=UnsignedShortColumn("flat_model", enable_compression_map=True),
        lease_commence_date=UnsignedShortColumn(
            "lease_commence_date", enable_zone_map=True
        ),
        resale_price=FloatColumn("resale_price", enable_zone_map=True),
    )
    store = ColumnStore(
        ["indexed", "zone map", "compressed"], COLSTORE_DIR / "compressed", columns
    )
    query_engine = QueryEngine(store, matric_str)
    query_engine.execute_query()
    store.print_summary()
    query_engine.export_results()


if __name__ == "__main__":
    matric_str = "A6626226B"
    run_basic_store_query(matric_str)
    run_compressed_store_query(matric_str)
    run_zone_map_basic_store_query(matric_str)
    run_indexed_basic_store_query(matric_str)
    run_indexed_zone_map_compressed_store_query(matric_str)
