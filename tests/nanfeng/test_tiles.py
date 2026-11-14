"""牌编码用例 —— 对应前端 ``tests/core/tiles.test.ts``。

每条 pytest 用例与 TS 的 ``it`` 一一对应（docstring 里标出 TS 标题），断言值与 TS 完全一致。
语言层差异：
    - ``suitOf`` / ``rankOf`` → ``suit_of`` / ``rank_of``；
    - TS 抛 ``RangeError`` 的两处，移植版统一抛 ``ValueError``；
    - ``Uint8Array`` → ``bytearray``（用 ``counts_of`` 构造）。
"""

import pytest

from app.core.nanfeng.counts import counts_of, total_count
from app.core.nanfeng.tiles import (
    COUNT_SIZE,
    WALL_SIZE,
    full_wall,
    is_dragon,
    is_number_tile,
    is_wind,
    is_word,
    rank_of,
    suit_of,
)


@pytest.mark.parametrize(
    'tile, suit',
    [
        (11, 'WAN'),
        (19, 'WAN'),
        (29, 'TIAO'),
        (35, 'TONG'),
        (41, 'WIND'),
        (53, 'DRAGON'),
    ],
)
def test_suit_of(tile: int, suit: str) -> None:
    """TS: 编码区间符合约定 —— suitOf 的 6 个区间取样点。"""
    assert suit_of(tile) == suit


@pytest.mark.parametrize('tile, expected', [(41, True), (51, True), (39, False)])
def test_is_word(tile: int, expected: bool) -> None:
    """TS: 编码区间符合约定 —— isWord(41/51/39)。"""
    assert is_word(tile) is expected


@pytest.mark.parametrize('tile, rank', [(11, 1), (19, 9), (44, 4), (53, 3)])
def test_rank_of(tile: int, rank: int) -> None:
    """TS: 编码区间符合约定 —— rankOf(11/19/44/53)。"""
    assert rank_of(tile) == rank


@pytest.mark.parametrize('tile, expected', [(11, True), (39, True), (41, False)])
def test_is_number_tile(tile: int, expected: bool) -> None:
    """TS: 合法性谓词与 suitOf 一致 —— isNumberTile。"""
    assert is_number_tile(tile) is expected


@pytest.mark.parametrize('tile, expected', [(41, True), (44, True), (51, False)])
def test_is_wind(tile: int, expected: bool) -> None:
    """TS: 合法性谓词与 suitOf 一致 —— isWind。"""
    assert is_wind(tile) is expected


@pytest.mark.parametrize('tile, expected', [(51, True), (53, True), (41, False)])
def test_is_dragon(tile: int, expected: bool) -> None:
    """TS: 合法性谓词与 suitOf 一致 —— isDragon。"""
    assert is_dragon(tile) is expected


@pytest.mark.parametrize('bad', [0, 10, 20, 40, 45, 50, 54, 99])
def test_非法牌码直接报错(bad: int) -> None:
    """TS: 非法牌码直接报错，而不是静默返回（S-09 的编码区间隐患）。

    TS 逐张断言 ``suitOf(bad)`` 与 ``rankOf(bad)`` 都抛错；Python 侧统一抛 ``ValueError``。
    """
    with pytest.raises(ValueError):
        suit_of(bad)
    with pytest.raises(ValueError):
        rank_of(bad)


def test_full_wall() -> None:
    """TS: fullWall 是 136 张且每种恰好 4 张。"""
    wall = full_wall()
    assert len(wall) == WALL_SIZE
    assert total_count(counts_of(wall)) == WALL_SIZE
    counts = counts_of(wall)
    for tile in range(11, 54):
        if is_number_tile(tile) or is_word(tile):
            assert counts[tile] == 4, f'牌码 {tile}'


def test_count_size() -> None:
    """TS: COUNT_SIZE 与编码区间一致（54..60 保留，61+ 留给马牌）。"""
    assert COUNT_SIZE == 54
