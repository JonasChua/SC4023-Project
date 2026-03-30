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
    summary = store.return_summary("basic")
    return summary


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
    summary = store.return_summary("compressed")
    return summary


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
    summary = store.return_summary("zone map")
    return summary


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
    summary = store.return_summary("indexed")
    return summary


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
    summary = store.return_summary("indexed, zone map, compressed")
    # query_engine.export_results()
    return summary

import pandas as pd

if __name__ == "__main__":
    matric_str = "A6626226B"
    iterations = 50
    
    # List to hold every single run's dictionary
    all_runs_data = []

    print(f"Running {iterations} iterations...")
    for i in range(iterations):
        # Fetch results
        basic = run_basic_store_query(matric_str)
        compressed = run_compressed_store_query(matric_str)
        zone_map = run_zone_map_basic_store_query(matric_str)
        indexed = run_indexed_basic_store_query(matric_str)
        idx_zm_comp = run_indexed_zone_map_compressed_store_query(matric_str)
        
        # Tag each dictionary with the current iteration number for tracking
        for res in [basic, compressed, zone_map, indexed, idx_zm_comp]:
            res['iteration'] = i + 1
            all_runs_data.append(res)
            
    print("Processing results...")
    
    # 1. Convert the list of dictionaries into a flattened pandas DataFrame.
    # This automatically unpacks nested dicts into columns like 'phases.Initialisation' or 'totals.blocks'
    df_raw = pd.json_normalize(all_runs_data)
    
    # Save the raw data (50 iterations x 5 types = 250 rows)
    df_raw.to_csv("query_results_raw.csv", index=False)
    print("Saved 'query_results_raw.csv'")

    # 2. Calculate the average for the 50 runs, grouped by 'type'
    # .groupby('type') groups the data by your query type
    # .mean(numeric_only=True) calculates the average for all time and block/read columns
    df_avg = df_raw.groupby('type').mean(numeric_only=True).reset_index()
    
    # The 'iteration' average is meaningless (it will just be 25.5), so we drop it
    if 'iteration' in df_avg.columns:
        df_avg = df_avg.drop(columns=['iteration'])

    # Save the averaged data (5 rows)
    df_avg.to_csv("query_results_average.csv", index=False)
    print("Saved 'query_results_average.csv'")
