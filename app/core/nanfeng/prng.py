"""伪随机数 —— 对应前端 ``assets/scripts/core/prng.ts``。

引擎禁区里**唯一**允许的随机来源：时间与随机数一律由参数注入，同一颗种子可以完整重放一局。
xorshift128 + splitmix32 播种，与 TS 实现逐位一致（因此前端 golden 牌墙可以直接对拍）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, Sequence, TypeVar

_U32 = 0xFFFFFFFF

T = TypeVar('T')


class Rng(Protocol):
    """``[0, 1)`` 的伪随机数来源。"""

    def next(self) -> float: ...


def _u32(value: int) -> int:
    return value & _U32


def _imul(a: int, b: int) -> int:
    """对齐 JS ``Math.imul``：32 位有符号乘法，但我们只保留低 32 位。"""
    return _u32(a * b)


@dataclass
class XorShift128Rng:
    """xorshift128，种子先用 splitmix32 摊成 4 个状态字并预热 16 轮。"""

    a: int
    b: int
    c: int
    d: int

    def _next_uint32(self) -> int:
        t = _u32(self.a ^ _u32(self.a << 11))
        self.a = self.b
        self.b = self.c
        self.c = self.d
        self.d = _u32(self.d ^ (self.d >> 19) ^ t ^ (t >> 8))
        return self.d

    def next(self) -> float:
        return self._next_uint32() / 0x100000000


def create_rng(seed: int) -> XorShift128Rng:
    state = _u32(seed)

    def next_seed() -> int:
        nonlocal state
        state = _u32(state + 0x9E3779B9)
        z = state
        z = _imul(z ^ (z >> 16), 0x21F0AAAD)
        z = _imul(z ^ (z >> 15), 0x735A2D97)
        return _u32(z ^ (z >> 15))

    a = next_seed()
    b = next_seed()
    c = next_seed()
    d = next_seed()
    rng = XorShift128Rng(a=a, b=b, c=c, d=d)
    for _ in range(16):  # 预热
        rng._next_uint32()
    return rng


def shuffle_wall(wall: Sequence[T], rng: Rng) -> list[T]:
    """Fisher–Yates 洗牌，返回新列表（不改动入参）。"""
    out = list(wall)
    for i in range(len(out) - 1, 0, -1):
        j = int(rng.next() * (i + 1))
        out[i], out[j] = out[j], out[i]
    return out


def rng_from(seed: int | Rng | Callable[[], float] | None) -> Callable[[], float]:
    """把「种子 / Rng 对象 / 无参函数」统一成一个 ``() -> float``。

    房间层用 ``random.Random`` 注入，引擎只认这个协议。
    """
    if seed is None:
        raise ValueError('必须显式注入随机源（引擎内不允许隐式随机）')
    if isinstance(seed, int):
        return create_rng(seed).next
    if hasattr(seed, 'next'):
        return seed.next  # type: ignore[union-attr]
    return seed
