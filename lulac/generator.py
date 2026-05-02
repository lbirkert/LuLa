import struct

# not required yet
def int_to_llvm(self, value: int, bits: int):
    hex_digits = (bits + 3) // 4
    if value < 0:
        value = (1 << bits) + value  # two's complement wrap
    return f"0x{value:0{hex_digits}x}"

def f32_to_llvm(self, value: float) -> str:
    bits = int.from_bytes(struct.pack("<f", value), "little")
    return f"0x{bits:08X}"

def f64_to_llvm(self, value: float) -> str:
    bits = int.from_bytes(struct.pack("<d", value), "little")
    return f"0x{bits:016X}"