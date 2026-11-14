"""``action/peng_gang.py`` 的 pytest 对拍 —— 逐条翻译
``tests/core/action/pengGang.test.ts``。

六个纯谓词：``can_peng / can_ming_gang / can_an_gang / can_bu_gang /
can_hu_self / can_hu_ron``。
"""

from __future__ import annotations

from dataclasses import replace

from app.core.nanfeng.action.hand import (
    HandState,
    add_meld,
    add_tile,
    create_hand,
)
from app.core.nanfeng.action.peng_gang import (
    can_an_gang,
    can_bu_gang,
    can_hu_ron,
    can_hu_self,
    can_ming_gang,
    can_peng,
)
from app.core.nanfeng.melds import Meld
from app.core.nanfeng.rule_config import DEFAULT_RULE_CONFIG, JiaHuConfig

cfg = DEFAULT_RULE_CONFIG


def peng(tile: int) -> Meld:
    """TS ``PENG(tile)``：``{ kind: 'PENG', tile, fromSeat: 2 }``。"""
    return Meld(kind='PENG', tile=tile, from_seat=2)


def hand_of(tiles) -> HandState:
    hand = create_hand()
    for tile in tiles:
        hand = add_tile(hand, tile)
    return hand


def no_ron_config():
    """``{ ...cfg, hu: { ...cfg.hu, jiaHu: { enabled: true, allowRon: false } } }``。"""
    return replace(cfg, hu=replace(cfg.hu, jia_hu=JiaHuConfig(enabled=True, allow_ron=False)))


# ---------------------------------------------------------------------------
# 碰与明杠的门槛
# ---------------------------------------------------------------------------

def test_peng_needs_two_ming_gang_needs_three():
    """碰需要两张，明杠需要三张。"""
    hand = hand_of([11, 11, 11])
    assert can_peng(hand, 11, cfg) is True
    assert can_ming_gang(hand, 11, cfg) is True

    hand2 = hand_of([11, 11])
    assert can_peng(hand2, 11, cfg) is True
    assert can_ming_gang(hand2, 11, cfg) is False


def test_single_copy_cannot_peng():
    """只有一张就碰不了。"""
    assert can_peng(hand_of([11]), 11, cfg) is False
    assert can_ming_gang(hand_of([11]), 11, cfg) is False


def test_no_missed_peng_restriction():
    """漏碰没有限制：随时能碰（R-06）。"""
    # 上一巡放弃了碰，这一巡同一张牌再来照样能碰 —— 不存在任何禁碰状态
    assert can_peng(hand_of([11, 11]), 11, cfg) is True


# ---------------------------------------------------------------------------
# 暗杠与补杠必须轮到自己
# ---------------------------------------------------------------------------

def test_an_gang_needs_exactly_four_and_own_turn():
    """暗杠要手里正好 4 张，且 ownTurn 为真。"""
    hand = hand_of([11, 11, 11, 11])
    assert can_an_gang(hand, 11, cfg, True) is True
    assert can_an_gang(hand, 11, cfg, False) is False  # 越权调用

    assert can_an_gang(hand_of([11, 11, 11]), 11, cfg, True) is False
    assert can_an_gang(hand_of([11, 11, 11, 11, 11]), 11, cfg, True) is False  # 不可能状态也不放行


def test_bu_gang_needs_peng_plus_fourth_and_own_turn():
    """补杠要"碰过这张 + 手里还有第 4 张"，且轮到自己。"""
    base = add_meld(add_tile(create_hand(), 11), peng(11))
    assert can_bu_gang(base, 11, cfg, True) is True
    assert can_bu_gang(base, 11, cfg, False) is False

    # 没有碰过这张 → 不能补杠（那是暗杠）
    assert can_bu_gang(add_tile(create_hand(), 11), 11, cfg, True) is False


def test_drawn_tile_counts_as_fourth_for_bu_gang():
    """刚摸到的那张也算第 4 张（补杠通常是摸上来的）。"""
    base = add_meld(create_hand(), peng(11))
    assert can_bu_gang(replace(base, drawn_tile=11), 11, cfg, True) is True


def test_just_peng_blocks_bu_gang():
    """碰后不能立即补杠。"""
    hand = add_meld(add_tile(create_hand(), 11), peng(11))
    assert can_bu_gang(replace(hand, just_peng=True), 11, cfg, True) is False
    assert can_bu_gang(replace(hand, just_peng=False), 11, cfg, True) is True


# ---------------------------------------------------------------------------
# 自摸与点炮
# ---------------------------------------------------------------------------

def test_structured_self_draw_wins():
    """成胡的自摸成立。"""
    hand = hand_of([11, 12, 13, 11, 12, 13, 14, 15, 16, 17, 17, 17, 18, 18])
    assert can_hu_self(hand, cfg) is True


def test_mixed_suit_non_winning_self_draw_fails():
    """没成胡的自摸不成立（混花色，连假胡都不是）。"""
    hand = hand_of([11, 12, 14, 11, 12, 15, 21, 22, 24, 21, 22, 25, 31, 31])
    assert can_hu_self(hand, cfg) is False


def test_jia_hu_self_draw_wins():
    """全同一花色但不成结构 → 假胡，自摸成立（R-03）。"""
    hand = hand_of([11, 12, 14, 11, 12, 15, 11, 12, 13, 17, 17, 17, 18, 18])
    assert can_hu_self(hand, cfg) is True


def test_ron_judges_with_the_claimed_tile_added():
    """张数不是 14 不成立（点炮只差那一张）。"""
    hand = hand_of([11, 12, 13, 11, 12, 13, 14, 15, 16, 17, 17, 17, 18])
    assert can_hu_ron(hand, 18, cfg) is True
    assert can_hu_ron(hand, 19, cfg) is True  # 全万子 → 假胡，默认允许点炮（R-03）
    assert can_hu_ron(hand, 21, cfg) is False  # 混进条子 → 既不成结构也不是假胡
    assert can_hu_self(hand, cfg) is False  # 手里只有 13 张


def test_ron_merges_the_tile_before_judging():
    """点炮时把待胡的牌并进手牌再判：差一张就是胡。"""
    hand = hand_of([11, 12, 13, 11, 12, 13, 21, 22, 23, 31, 31, 31, 41])
    assert can_hu_ron(hand, 41, cfg) is True
    assert can_hu_self(add_tile(hand, 41), cfg) is True


# ---------------------------------------------------------------------------
# 十三烂的自摸限制（R-05）
# ---------------------------------------------------------------------------

def test_shi_san_lan_five_words_only_self_draw():
    """字牌 5 张时点炮拒胡、自摸照常。"""
    hand = hand_of([11, 14, 17, 21, 24, 27, 31, 34, 37, 41, 42, 43, 51])  # 字牌 41,42,43,51
    assert can_hu_ron(hand, 52, cfg) is False  # 第 5 张字牌 → 只许自摸
    assert can_hu_self(add_tile(hand, 52), cfg) is True


def test_shi_san_lan_six_words_only_self_draw():
    """字牌 6 张时同样只能自摸。"""
    hand = hand_of([11, 15, 19, 21, 25, 29, 31, 35, 41, 42, 43, 44, 51])
    assert can_hu_ron(hand, 52, cfg) is False
    assert can_hu_self(add_tile(hand, 52), cfg) is True


def test_qi_xing_shi_san_lan_allows_ron():
    """七星十三烂（字牌 7 张）允许点炮。"""
    hand = hand_of([11, 15, 21, 25, 31, 35, 39, 41, 42, 43, 44, 51, 52])
    assert can_hu_ron(hand, 53, cfg) is True


def test_non_shi_san_lan_is_not_restricted():
    """不是十三烂的手牌不受这条限制。"""
    hand = hand_of([11, 12, 13, 11, 12, 13, 21, 22, 23, 31, 31, 31, 41])
    assert can_hu_ron(hand, 41, cfg) is True


# ---------------------------------------------------------------------------
# 假胡的点炮开关（hu.jiaHu.allowRon）
# ---------------------------------------------------------------------------

#: 全万子、拆不出结构 → 假胡
JIA_HU_13 = (11, 11, 12, 14, 15, 17, 17, 19, 19, 11, 12, 14, 15)


def test_jia_hu_may_ron_when_allowed():
    """allowRon 为真时假胡可以点炮。"""
    assert can_hu_ron(hand_of(JIA_HU_13), 17, cfg) is True


def test_jia_hu_cannot_ron_when_disallowed():
    """allowRon 为假时假胡只能自摸。"""
    no_ron = no_ron_config()
    assert can_hu_ron(hand_of(JIA_HU_13), 17, no_ron) is False
    assert can_hu_self(hand_of(JIA_HU_13 + (17,)), no_ron) is True


def test_allow_ron_false_only_blocks_jia_hu():
    """allowRon 为假只挡住假胡，真结构照常点炮。"""
    no_ron = no_ron_config()
    hand = hand_of([11, 12, 13, 11, 12, 13, 21, 22, 23, 31, 31, 31, 41])
    assert can_hu_ron(hand, 41, no_ron) is True
