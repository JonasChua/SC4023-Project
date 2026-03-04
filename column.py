from abc import ABC, abstractmethod
from struct import calcsize, pack, unpack
from typing import Any


class Column(ABC):
    def __init__(
        self,
        name: str,
        format: str,
        size: int,
        enable_compression_map: bool = False,
        enable_zone_map: bool = False,
    ) -> None:
        self.name = name
        self.format = format
        self.size = size
        self.enable_compression_map = enable_compression_map
        self.enable_zone_map = enable_zone_map
        self._compression_map: dict[str, int] = {}
        self._zone_map: list[tuple[int, int]] = []

    @property
    def filename(self) -> str:
        return f"{self.name}.bin"

    def check_compression_map_enabled(self) -> None:
        if not self.enable_compression_map:
            raise ValueError(
                f"Compression mapping is not enabled for column '{self.name}'"
            )

    def update_compression_mapping(self, value: str) -> int:
        self.check_compression_map_enabled()
        if value not in self._compression_map:
            self._compression_map[value] = len(self._compression_map)

        return self._compression_map[value]

    def map_value(self, value: str, default: int = -1) -> int:
        self.check_compression_map_enabled()
        return self._compression_map.get(value, default)

    def unmap_value(self, id: int, default: str | None = None) -> str | None:
        self.check_compression_map_enabled()
        for value, mapped_id in self._compression_map.items():
            if mapped_id == id:
                return value

        return default

    def check_zone_map_enabled(self) -> None:
        if not self.enable_zone_map:
            raise ValueError(f"Zone mapping is not enabled for column '{self.name}'")

    def get_block_zone(self, block_index: int) -> tuple[int, int]:
        self.check_zone_map_enabled()
        if block_index < 0 or block_index >= len(self._zone_map):
            raise IndexError(
                f"Block index {block_index} out of range for column '{self.name}'"
            )

        return self._zone_map[block_index]

    @abstractmethod
    def encode(self, value: Any) -> bytes:
        pass

    @abstractmethod
    def decode(self, raw_value: bytes) -> Any:
        pass


class NumericColumn(Column):
    def __init__(
        self,
        name: str,
        format: str,
        enable_compression_map: bool = False,
        enable_zone_map: bool = False,
    ):
        super().__init__(
            name, format, calcsize(format), enable_compression_map, enable_zone_map
        )

    def encode(self, value: Any) -> bytes:
        return pack(self.format, value)

    def decode(self, raw_value: bytes) -> Any:
        return unpack(self.format, raw_value)[0]


class UnsignedCharColumn(NumericColumn):
    def __init__(
        self,
        name: str,
        enable_compression_map: bool = False,
        enable_zone_map: bool = False,
    ):
        super().__init__(name, "B", enable_compression_map, enable_zone_map)


class UnsignedShortColumn(NumericColumn):
    def __init__(
        self,
        name: str,
        enable_compression_map: bool = False,
        enable_zone_map: bool = False,
    ):
        super().__init__(name, "H", enable_compression_map, enable_zone_map)


class FloatColumn(NumericColumn):
    def __init__(
        self,
        name: str,
        enable_compression_map: bool = False,
        enable_zone_map: bool = False,
    ):
        super().__init__(name, "f", enable_compression_map, enable_zone_map)


class StringColumn(Column):
    def __init__(
        self,
        name: str,
        length: int,
        enable_compression_map: bool = False,
        enable_zone_map: bool = False,
    ):
        super().__init__(
            name,
            f"{length}s",
            calcsize(f"{length}s"),
            enable_compression_map,
            enable_zone_map,
        )

    def encode(self, value: str) -> bytes:
        return pack(self.format, value.encode("utf-8"))

    def decode(self, raw_value: bytes) -> str:
        return unpack(self.format, raw_value)[0].decode("utf-8").rstrip("\x00")
