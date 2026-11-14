"""``tests/core/hu/wordStraight.test.ts`` 的 pytest 等价用例。

覆盖两个 describe：
    - 字牌顺子模式表（word_straight.WORD_PATTERNS / word_patterns_starting_at）
    - 字牌顺子参与面子分解（is_standard 在 word_straight 开关下的行为）
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.core.nanfeng.counts import counts_of
from app.core.nanfeng.hu.decompose import is_standard
from app.core.nanfeng.hu.word_straight import WORD_PATTERNS, word_patterns_starting_at
from app.core.nanfeng.rule_config import DEFAULT_RULE_CONFIG
from app.core.nanfeng.tiles import is_dragon, is_wind

WITH_WORD_STRAIGHT = DEFAULT_RULE_CONFIG
WITHOUT_WORD_STRAIGHT = replace(
    DEFAULT_RULE_CONFIG, hu=replace(DEFAULT_RULE_CONFIG.hu, word_straight=False))


# --------------------------------------------------------------------------- #
# describe('字牌顺子模式表')
# --------------------------------------------------------------------------- #


def test_exactly_five_patterns_each_ascending() -> None:
    """TS: 恰好 5 种模式，且每种按牌码升序。"""
    assert len(WORD_PATTERNS) == 5
    assert [','.join(str(tile) for tile in pattern) for pattern in WORD_PATTERNS] == [
        '41,42,43',
        '41,42,44',
        '41,43,44',
        '42,43,44',
        '51,52,53',
    ]
    for pattern in WORD_PATTERNS:
        assert list(pattern) == sorted(pattern)


@pytest.mark.parametrize('pattern', WORD_PATTERNS, ids=[','.join(map(str, p)) for p in WORD_PATTERNS])
def test_wind_and_dragon_never_mixed(pattern: tuple[int, ...]) -> None:
    """TS: 风与箭不可混搭。"""
    assert (all(is_wind(tile) for tile in pattern)
            or all(is_dragon(tile) for tile in pattern)), ','.join(map(str, pattern))


@pytest.mark.parametrize(('tile', 'count'), [(41, 3), (42, 1), (51, 1)])
def test_pattern_count_indexed_by_smallest_tile(tile: int, count: int) -> None:
    """TS: 按最小元素索引：41 起 3 种、42 起 1 种、51 起 1 种。"""
    assert len(word_patterns_starting_at(tile)) == count


@pytest.mark.parametrize('tile', [43, 44])
def test_tiles_43_and_44_can_never_be_the_smallest_non_zero_tile(tile: int) -> None:
    """TS: wordPatternsStartingAt(43) / (44) 都是空数组。"""
    assert word_patterns_starting_at(tile) == ()


# --------------------------------------------------------------------------- #
# describe('字牌顺子参与面子分解')
# --------------------------------------------------------------------------- #


def _hand() -> bytearray:
    return counts_of([41, 42, 43, 11, 12, 13, 21, 22, 23, 31, 31, 31, 51, 51])


def test_word_straight_counts_as_a_set_when_enabled() -> None:
    """TS: 开启时字牌顺子可作一组面子。"""
    assert is_standard(_hand(), 0, WITH_WORD_STRAIGHT) is True


def test_disabled_word_straight_degrades_to_triplets() -> None:
    """TS: 关闭时退化为刻子判定，同一手牌不成立。"""
    assert is_standard(_hand(), 0, WITHOUT_WORD_STRAIGHT) is False


def test_dragon_straight_also_works() -> None:
    """TS: 中发白顺子同样成立。"""
    c = counts_of([51, 52, 53, 11, 12, 13, 21, 22, 23, 31, 31, 31, 41, 41])
    assert is_standard(c, 0, WITH_WORD_STRAIGHT) is True


def test_wind_and_dragon_mixed_is_not_a_set() -> None:
    """TS: 风与箭混搭不成面子（41,42,51 不是任何模式，且无法用刻子补齐）。"""
    c = counts_of([41, 42, 51, 11, 12, 13, 21, 22, 23, 31, 31, 31, 43, 43])
    assert is_standard(c, 0, WITH_WORD_STRAIGHT) is False
