"""``action/hand.py`` 的 pytest 对拍 —— 逐条翻译 ``tests/core/action/hand.test.ts``。

对应关系：``createHand / addTile / removeTile / addMeld / handTileCount /
assertHandInvariants`` ↔ ``create_hand / add_tile / remove_tile / add_meld /
hand_tile_count / assert_hand_invariants``；``HandState`` 是 frozen dataclass。
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.core.nanfeng.action.hand import (
    HandState,
    add_meld,
    add_tile,
    assert_hand_invariants,
    create_hand,
    hand_tile_count,
    remove_tile,
)
from app.core.nanfeng.melds import Meld, meld_tile_count
from app.core.nanfeng.rule_config import DEFAULT_RULE_CONFIG

cfg = DEFAULT_RULE_CONFIG


def peng(tile: int) -> Meld:
    """TS ``PENG(tile)``：``{ kind: 'PENG', tile, fromSeat: 1 }``。"""
    return Meld(kind='PENG', tile=tile, from_seat=1)


# ---------------------------------------------------------------------------
# 手牌张数
# ---------------------------------------------------------------------------

def test_hand_tile_count_concealed_plus_meld():
    """暗牌 + 副露折算（碰算 3 张）。"""
    hand = add_meld(add_tile(create_hand(), 11), peng(22))
    assert hand_tile_count(hand) == 4


@pytest.mark.parametrize('meld', [
    Meld(kind='MING_GANG', tile=11, from_seat=2),
    Meld(kind='AN_GANG', tile=11, from_seat=None),
    Meld(kind='BU_GANG', tile=11, from_seat=None),
], ids=['MING_GANG', 'AN_GANG', 'BU_GANG'])
def test_all_gang_kinds_count_as_four_tiles(meld):
    """三种杠都按 4 张折算，与 meld_tile_count 同口径（C-1 校准）。"""
    assert hand_tile_count(add_meld(create_hand(), meld)) == meld_tile_count(meld)
    assert hand_tile_count(add_meld(create_hand(), meld)) == 4


def test_drawn_tile_counts_but_is_kept_apart():
    """刚摸到的那张单独记在 drawn_tile 上，同样计入张数。"""
    assert hand_tile_count(replace(create_hand(), drawn_tile=11)) == 1

    # 13 张暗牌 + 摸到的 1 张 = 14（庄家开局的形态）
    hand: HandState = replace(create_hand(), drawn_tile=11)
    for tile in (12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 23, 24, 25):
        hand = add_tile(hand, tile)
    assert hand_tile_count(hand) == 14


def test_empty_hand_is_zero():
    """空手牌是 0 张。"""
    assert hand_tile_count(create_hand()) == 0


# ---------------------------------------------------------------------------
# 不可变更新
# ---------------------------------------------------------------------------

def test_add_tile_returns_new_object():
    """addTile 返回新对象，不改动原对象。"""
    before = create_hand()
    after = add_tile(before, 11)
    assert after is not before
    assert after.concealed is not before.concealed
    assert hand_tile_count(before) == 0
    assert hand_tile_count(after) == 1


def test_remove_tile_returns_new_object():
    """removeTile 返回新对象，不改动原对象。"""
    before = add_tile(add_tile(create_hand(), 11), 11)
    after = remove_tile(before, 11)
    assert hand_tile_count(before) == 2
    assert hand_tile_count(after) == 1


def test_add_meld_appends_without_overwriting():
    """addMeld 追加而不覆盖已有副露。"""
    hand = add_meld(add_meld(create_hand(), peng(11)), peng(22))
    assert len(hand.melds) == 2
    assert [meld.tile for meld in hand.melds] == [11, 22]


def test_remove_missing_tile_raises():
    """不可移除不存在的牌。"""
    with pytest.raises(ValueError, match='没有'):
        remove_tile(create_hand(), 11)


# ---------------------------------------------------------------------------
# 手牌不变量
# ---------------------------------------------------------------------------

def test_valid_hand_does_not_raise():
    """合法手牌不抛。"""
    hand = create_hand()
    for tile in (11, 11, 11, 12, 12, 12, 13, 13, 13, 21, 21, 21, 31, 31):
        hand = add_tile(hand, tile)
    assert_hand_invariants(hand, cfg)


def test_four_concealed_copies_are_legal():
    """单独暗持 4 张是合法的（那正是暗杠的前置）。"""
    hand = create_hand()
    for _ in range(4):
        hand = add_tile(hand, 11)
    assert_hand_invariants(hand, cfg)


def test_tile_cap_counts_melds_too():
    """每种牌总数不得超过 4：暗牌与副露要一起算。"""
    hand = create_hand()
    for _ in range(4):
        hand = add_tile(hand, 11)
    hand = add_meld(hand, peng(11))
    with pytest.raises(ValueError, match='超过 4 张'):
        assert_hand_invariants(hand, cfg)


def test_peng_three_plus_two_in_hand_is_five():
    """碰走 3 张 + 手里还有 2 张 = 第 5 张，超限（故意构造的坏状态）。"""
    hand = add_meld(add_tile(add_tile(create_hand(), 11), 11), peng(11))
    with pytest.raises(ValueError, match='超过 4 张'):
        assert_hand_invariants(hand, cfg)
