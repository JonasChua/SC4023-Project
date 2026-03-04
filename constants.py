from dataclasses import dataclass
from pathlib import Path
from struct import calcsize

PROJECT_ROOT = Path(__file__).resolve().parent
COLSTORE_DIR = PROJECT_ROOT / "data/store"
RAW_CSV = PROJECT_ROOT / "data/raw/ResalePricesSingapore.csv"
BLOCK_SIZE = 4096  # 4KB

MONTH_ABBR = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}

# For query processing
DIGIT_TO_TOWN = {
    0: "BEDOK",
    1: "BUKIT PANJANG",
    2: "CLEMENTI",
    3: "CHOA CHU KANG",
    4: "HOUGANG",
    5: "JURONG WEST",
    6: "PASIR RIS",
    7: "TAMPINES",
    8: "WOODLANDS",
    9: "YISHUN",
}

COLUMNS = [
    "year",
    "month",
    "town",
    "flat_type",
    "block",
    "street_name",
    "storey_range",
    "floor_area",
    "flat_model",
    "lease_year",
    "resale_price",
]


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    filename: str
    fmt: str
    size: int


class BaseColumns:
    @classmethod
    def get_filenames(cls) -> list[str]:
        return [
            col.filename for col in cls.__dict__.values() if isinstance(col, ColumnInfo)
        ]

    @classmethod
    def get_columns(cls) -> list[ColumnInfo]:
        return [col for col in cls.__dict__.values() if isinstance(col, ColumnInfo)]


class BasicColumns(BaseColumns):
    # Basic columns without optimizations
    # year:         uint16
    # month:        uint8
    # town:         byte32
    # flat_type:    byte16
    # block:        byte8
    # street_name:  byte32
    # storey_range:  byte8
    # floor_area:   float32
    # flat_model:   byte32
    # lease_year:   uint16
    # resale_price: float32
    directory = Path("basic")
    year = ColumnInfo("year", "year.u16", "H", calcsize("H"))
    month = ColumnInfo("month", "month.u8", "B", calcsize("B"))
    town = ColumnInfo("town", "town.s32", "32s", calcsize("32s"))
    flat_type = ColumnInfo("flat_type", "flat_type.s16", "16s", calcsize("16s"))
    block = ColumnInfo("block", "block.s8", "8s", calcsize("8s"))
    street_name = ColumnInfo("street_name", "street_name.s32", "32s", calcsize("32s"))
    storey_range = ColumnInfo("storey_range", "storey_range.s8", "8s", calcsize("8s"))
    floor_area = ColumnInfo("floor_area", "floor_area.f32", "f", calcsize("f"))
    flat_model = ColumnInfo("flat_model", "flat_model.s32", "32s", calcsize("32s"))
    lease_year = ColumnInfo("lease_year", "lease_year.u16", "H", calcsize("H"))
    resale_price = ColumnInfo("resale_price", "resale_price.f32", "f", calcsize("f"))


class CompressedColumns(BaseColumns):
    # Compressed columns with dictionary encoding for strings
    # year:         uint16
    # month:        uint8
    # town:         uint8 (dict encoding)
    # flat_type:    uint8 (dict encoding)
    # block:        uint16 (dict encoding)
    # street_name:  uint16 (dict encoding)
    # storey_range: uint8 (dict encoding)
    # floor_area:   float32
    # flat_model:   uint8 (dict encoding)
    # lease_year:   uint16
    # resale_price: float32
    directory = Path("compressed")
    year = ColumnInfo("year", "year.u16", "H", calcsize("H"))
    month = ColumnInfo("month", "month.u8", "B", calcsize("B"))
    town = ColumnInfo("town", "town.u8", "B", calcsize("B"))
    flat_type = ColumnInfo("flat_type", "flat_type.u8", "B", calcsize("B"))
    block = ColumnInfo("block", "block.u16", "H", calcsize("H"))
    street_name = ColumnInfo("street_name", "street_name.u16", "H", calcsize("H"))
    storey_range = ColumnInfo("storey_range", "storey_range.u8", "B", calcsize("B"))
    floor_area = ColumnInfo("floor_area", "floor_area.f32", "f", calcsize("f"))
    flat_model = ColumnInfo("flat_model", "flat_model.u8", "B", calcsize("B"))
    lease_year = ColumnInfo("lease_year", "lease_year.u16", "H", calcsize("H"))
    resale_price = ColumnInfo("resale_price", "resale_price.f32", "f", calcsize("f"))

    town_map_filename = "town_map.csv"
    flat_type_map_filename = "flat_type_map.csv"
    block_map_filename = "block_map.csv"
    street_name_map_filename = "street_name_map.csv"
    storey_range_map_filename = "storey_range_map.csv"
    flat_model_map_filename = "flat_model_map.csv"

    @classmethod
    def get_map_filenames(cls) -> list[str]:
        return [
            getattr(cls, attr) for attr in dir(cls) if attr.endswith("_map_filename")
        ]
