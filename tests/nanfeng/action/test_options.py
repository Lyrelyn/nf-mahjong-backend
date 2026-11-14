"""``action/options.py`` 的 pytest 对拍 —— 逐条翻译
``tests/core/action/options.test.ts``。

``collect_options`` ↔ ``collectOptions``（出牌响应窗口）、``own_turn_options`` ↔
``ownTurnOptions``（自己回合的按钮）、``ACTION_PRIORITY`` / ``ActionOption`` /
``PlayerAction`` 保持同名语义。
"""

from __future__ import annotations

from dataclasses import replace

from app.core.nanfeng.action.hand import (
    HandState,
    add_tile,
    create_hand,
)
from app.core.nanfeng.action.options import (
    ACTION_PRIORITY,
    collect_options,
    own_turn_options,
)
from app.core.nanfeng.counts import counts_of
from app.core.nanfeng.melds import Meld
from app.core.nanfeng.rule_config import DEFAULT_RULE_CONFIG

cfg = DEFAULT_RULE_CONFIG


# ---------------------------------------------------------------------------
# 共享手牌夹具（对应 tests/helpers/fixtures.ts）
# ---------------------------------------------------------------------------

def hand_of(tiles) -> HandState:
    hand = create_hand()
    for tile in tiles:
        hand = add_tile(hand, tile)
    return hand


def can_peng_hand() -> HandState:
    """13 张，手里 2 张 11 → 能碰 11。"""
    return hand_of([11, 11, 13, 15, 19, 21, 24, 27, 31, 34, 37, 41, 43])


def can_peng_gang_hand() -> HandState:
    """13 张，手里 3 张 11 → 能碰也能明杠。"""
    return hand_of([11, 11, 11, 13, 15, 19, 21, 24, 27, 31, 34, 37, 41])


def can_hu_hand() -> HandState:
    """13 张，并进一张 11 即胡。"""
    return hand_of([11, 12, 13, 21, 22, 23, 31, 31, 31, 41, 41, 41, 11])


def zimo_ready_hand() -> HandState:
    """``zimoReady(1).hands[1]``：13 张暗牌 + 摸到 11，自摸即胡。"""
    return HandState(
        concealed=counts_of([11, 11, 12, 13, 21, 22, 23, 31, 31, 31, 41, 41, 41]),
        drawn_tile=11,
    )


# ---------------------------------------------------------------------------
# 可操作项收集
# ---------------------------------------------------------------------------

def test_collects_claim_responses_from_next_seat_clockwise():
    """从出牌者下家开始顺时针，只收出牌响应类操作（不含暗杠/补杠/出牌）。"""
    options = collect_options(
        0, 11, [create_hand(), can_peng_hand(), create_hand(), create_hand()], cfg, None)
    assert list(options.keys()) == [1]

    types = [option.type for option in options[1]]
    assert 'PENG' in types
    assert 'AN_GANG' not in types
    assert 'BU_GANG' not in types
    assert 'DISCARD' not in types


def test_players_with_nothing_to_do_are_not_in_window():
    """无事可做的玩家不进窗口（只能 PASS 的人不入窗）。"""
    options = collect_options(
        0, 11, [create_hand(), create_hand(), create_hand(), create_hand()], cfg, None)
    assert len(options) == 0


def test_discarder_is_not_in_window():
    """出牌者自己不进窗口。"""
    # 座位 0 手里有 3 张 11，但他是出牌者
    options = collect_options(
        0, 11, [can_peng_gang_hand(), create_hand(), create_hand(), create_hand()], cfg, None)
    assert 0 not in options


def test_one_option_per_type_plus_pass():
    """每个玩家同一类型只保留一条，且始终带 PASS（priority 0）。"""
    options = collect_options(
        0, 11, [create_hand(), can_peng_gang_hand(), create_hand(), create_hand()], cfg, None)
    seat1 = options[1]
    assert len([option for option in seat1 if option.type == 'PENG']) == 1
    assert len([option for option in seat1 if option.type == 'MING_GANG']) == 1
    assert next(option for option in seat1 if option.type == 'PASS').priority \
        == ACTION_PRIORITY['PASS']
    assert ACTION_PRIORITY['PASS'] == 0
    assert ACTION_PRIORITY['HU'] > ACTION_PRIORITY['MING_GANG']
    assert ACTION_PRIORITY['MING_GANG'] > ACTION_PRIORITY['PENG']


def test_sorted_by_priority_desc_then_distance_asc():
    """按 priority 降序、同级按 distance 升序排序。"""
    options = collect_options(
        0, 11, [create_hand(), can_peng_gang_hand(), create_hand(), can_peng_hand()], cfg, None)
    flat = [option for group in options.values() for option in group]
    assert flat[0].priority >= flat[-1].priority

    seat1_priorities = [option.priority for option in options[1]]
    assert seat1_priorities == sorted(seat1_priorities, reverse=True)

    # 距离按顺时针算：0→1 是 1，0→3 是 3
    assert options[1][0].distance == 1
    assert options[3][0].distance == 3


def test_hu_sorts_before_peng():
    """能胡时 HU 排在 PENG 之前。"""
    # 座位 1 既能胡 11 又握着 3 张 11
    options = collect_options(
        0, 11, [create_hand(), can_hu_hand(), create_hand(), create_hand()], cfg, None)
    assert [option.type for option in options[1]] == ['HU', 'PENG', 'PASS']


def test_no_preview_provider_means_no_hu_preview():
    """传 None 的预览提供者时不计算胡分预估。"""
    options = collect_options(
        0, 11, [create_hand(), can_hu_hand(), create_hand(), create_hand()], cfg, None)
    assert next(option for option in options[1] if option.type == 'HU').hu_preview is None


def test_preview_provider_fills_hu_only():
    """给了预览提供者就填上胡分预估，且只填在 HU 上。"""
    def preview(seat: int, tile: int):
        return 8 if seat == 1 and tile == 11 else None

    options = collect_options(
        0, 11, [create_hand(), can_hu_hand(), create_hand(), create_hand()], cfg, preview)
    seat1 = options[1]
    assert next(option for option in seat1 if option.type == 'HU').hu_preview == 8
    assert next(option for option in seat1 if option.type == 'PENG').hu_preview is None
    assert next(option for option in seat1 if option.type == 'PASS').hu_preview is None


def test_shi_san_lan_five_words_has_no_hu_option():
    """十三烂字牌 5 张的手牌：点炮窗口里根本没有 HU 选项（R-05 联动）。"""
    # 座位 1 手里 13 张，并进 52 正好是"字牌 5 张"的十三烂 —— 只许自摸
    lan = hand_of([11, 14, 17, 21, 24, 27, 31, 34, 37, 41, 42, 43, 51])
    options = collect_options(0, 52, [create_hand(), lan, create_hand(), create_hand()], cfg, None)
    assert len(options) == 0  # 既碰不了也胡不了 → 不入窗


def test_qi_xing_shi_san_lan_has_hu_option():
    """七星十三烂（字牌 7 张）在点炮窗口里出现 HU（R-05）。"""
    qi_xing = hand_of([11, 15, 21, 25, 31, 35, 39, 41, 42, 43, 44, 51, 52])
    options = collect_options(0, 53, [create_hand(), qi_xing, create_hand(), create_hand()], cfg, None)
    assert [option.type for option in options[1]] == ['HU', 'PASS']


def test_distance_wraps_around():
    """距离环绕：出牌者是座位 3 时，座位 0 的距离是 1。"""
    options = collect_options(
        3, 11, [can_peng_hand(), create_hand(), create_hand(), create_hand()], cfg, None)
    assert options[0][0].distance == 1


# ---------------------------------------------------------------------------
# 自己回合的可操作项
# ---------------------------------------------------------------------------

def types_of(hand: HandState) -> list[str]:
    return [option.type for option in own_turn_options(hand, cfg)]


def test_zimo_pattern_offers_hu():
    """自摸的牌形给出 HU。"""
    assert types_of(zimo_ready_hand()) == ['HU']


def test_four_identical_codes_offer_an_gang():
    """手里正好 4 张同一牌码 → 暗杠。"""
    hand = hand_of([11, 11, 11, 11, 13, 15, 19, 21, 24, 27, 31, 34, 37, 41])
    assert types_of(hand) == ['AN_GANG']


def test_penged_tile_with_fourth_offers_bu_gang():
    """碰过这张、手里还留着第 4 张 → 补杠。"""
    hand = replace(
        hand_of([11, 13, 15, 19, 21, 24, 27, 31, 34, 37]),
        melds=(Meld(kind='PENG', tile=11, from_seat=0),),
    )
    assert types_of(hand) == ['BU_GANG']


def test_just_peng_suppresses_bu_gang():
    """本巡刚碰过 → 不提示补杠（碰完不能立刻补同一张）。"""
    hand = replace(
        hand_of([11, 13, 15, 19, 21, 24, 27, 31, 34, 37]),
        melds=(Meld(kind='PENG', tile=11, from_seat=0),),
        just_peng=True,
    )
    assert types_of(hand) == []


def test_nothing_to_do_is_empty_list():
    """什么都不能做时是空数组，不是 undefined（没有选项就一个按钮都不显示）。"""
    assert types_of(can_peng_hand()) == []


def test_own_turn_never_offers_claim_window_actions():
    """不给出鸣牌窗口才有的那些（碰/明杠/过在这里没有意义）。"""
    hand = hand_of([11, 11, 11, 11, 13, 15, 19, 21, 24, 27, 31, 34, 37, 41])
    types = types_of(hand)
    for action_type in ('PENG', 'MING_GANG', 'PASS', 'DISCARD'):
        assert action_type not in types


def test_hu_sorts_first_when_gang_also_available():
    """能自摸又有杠时，HU 排在最前（优先级高者在前，界面才不用自己排）。"""
    # 111 111 的情况：concealed 里正好 4 张 11，同时是能自摸的牌形
    hand = replace(
        hand_of([11, 12, 13, 21, 22, 23, 31, 31, 31, 41, 41, 41, 11]),
        drawn_tile=11,
    )
    assert types_of(hand)[0] == 'HU'


def test_every_option_names_its_tile():
    """每条选项都指明作用于哪张牌；过牌这条没有牌。"""
    options = collect_options(
        0, 11, [create_hand(), can_peng_gang_hand(), create_hand(), create_hand()], cfg, None)
    seat1 = options[1]
    assert next(option for option in seat1 if option.type == 'MING_GANG').tile == 11
    assert next(option for option in seat1 if option.type == 'PENG').tile == 11
    assert next(option for option in seat1 if option.type == 'PASS').tile is None


def test_two_an_gangs_are_distinguished_by_tile():
    """同时能暗杠两张不同的牌时，两条选项靠 tile 区分开。"""
    hand = hand_of([11, 11, 11, 11, 21, 21, 21, 21, 13, 15, 19, 31, 34, 37])
    options = own_turn_options(hand, cfg)
    assert [option.type for option in options] == ['AN_GANG', 'AN_GANG']
    assert [option.tile for option in options] == [11, 21]


def test_hu_option_carries_drawn_tile():
    """自摸那条带的是刚摸到的那张（算炮数预估要用它）。"""
    option = own_turn_options(zimo_ready_hand(), cfg)[0]
    assert (option.type, option.tile) == ('HU', 11)
