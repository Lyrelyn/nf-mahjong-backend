"""计数工具用例 —— 对应前端 ``tests/core/counts.test.ts``。

``Uint8Array`` 在移植版里是 ``bytearray``，一律用 ``counts_of([...])`` 构造。
每条 pytest 用例与 TS 的 ``it`` 一一对应（docstring 里标出 TS 标题）。
"""

from app.core.nanfeng.counts import counts_key, counts_of, first_non_zero, total_count
from app.core.nanfeng.tiles import COUNT_SIZE


def test_counts_of_统计每种牌的张数() -> None:
    """TS: countsOf 统计每种牌的张数。"""
    counts = counts_of([11, 11, 23])
    assert counts[11] == 2
    assert counts[23] == 1
    assert counts[12] == 0
    assert total_count(counts) == 3


def test_counts_of_每次返回新数组() -> None:
    """TS: countsOf 每次返回长度 COUNT_SIZE 的新数组。"""
    assert len(counts_of([11])) == COUNT_SIZE
    # TS 用 `.not.toBe(...)` 比较对象身份，Python 对应 `is not`。
    assert counts_of([11]) is not counts_of([11])


def test_first_non_zero() -> None:
    """TS: firstNonZero 返回最小非零牌码。"""
    counts = counts_of([11, 11, 23, 45])
    assert first_non_zero(counts) == 11
    counts[11] = 0
    counts[23] = 0
    assert first_non_zero(counts) == 45
    assert first_non_zero(counts_of([])) == -1


def test_counts_key() -> None:
    """TS: countsKey 对相同计数稳定、对不同计数不同。"""
    assert counts_key(counts_of([11, 12])) == counts_key(counts_of([12, 11]))
    assert counts_key(counts_of([11, 12])) != counts_key(counts_of([11, 13]))
