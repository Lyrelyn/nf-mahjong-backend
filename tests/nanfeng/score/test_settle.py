"""``score/settle.py`` 的 pytest 对拍 —— 逐条翻译 ``tests/core/score/settle.test.ts``。

``settleRound(state, outcome, cfg)`` → ``settle_round(state, outcome, cfg)``。
TS 的 ``RoundOutcome`` / ``RoundWinner`` 对应 ``state.game_state`` 里的同名 frozen dataclass
（``gangShang`` → ``gang_shang``、``loserSeat`` → ``loser_seat``）。

``stateOf`` 用真实的 ``start_round`` 造状态，再用 ``dataclasses.replace`` 覆盖庄家与本局杠分台账
—— 结算只看 ``hands`` 的长度、``dealer`` 与 ``round_gang_score``。
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.core.nanfeng.action.hand import HandState, add_tile, create_hand
from app.core.nanfeng.action.options import PlayerAction
from app.core.nanfeng.counts import counts_of
from app.core.nanfeng.rule_config import DEFAULT_RULE_CONFIG
from app.core.nanfeng.score.settle import settle_round
from app.core.nanfeng.state.apply import apply_action
from app.core.nanfeng.state.game_state import (
    GameState,
    RoundOutcome,
    RoundWinner,
    StartRoundOptions,
    start_round,
)
from app.core.nanfeng.tiles import COUNT_SIZE, full_wall

cfg = DEFAULT_RULE_CONFIG

#: 显式关掉封顶，用来验证"封顶前"的分层公式。
NO_CAP = replace(cfg, score=replace(cfg.score, cap=0))


def state_of(round_gang_score=(0, 0, 0, 0), dealer: int = 0) -> GameState:
    """造一个只关心"庄家 + 本局杠分台账"的结算输入。"""
    base = start_round(StartRoundOptions(
        seats=('a', 'b', 'c', 'd'), dealer=dealer, cfg=cfg, rng=7))
    return replace(base, turn=dealer, round_gang_score=tuple(round_gang_score))


def winner(seat: int, zimo: bool, tags, gang_shang: bool = False) -> RoundWinner:
    """TS ``{ seat, zimo, tags, gangShang? }``。"""
    return RoundWinner(seat=seat, zimo=zimo, gang_shang=gang_shang, tags=tuple(tags))


def hu(winners, loser_seat):
    """TS ``hu(winners, loserSeat)`` → ``{ kind: 'HU', winners, loserSeat }``。"""
    return RoundOutcome(kind='HU', winners=tuple(winners), loser_seat=loser_seat)


def total(deltas) -> int:
    return sum(deltas)


# ---------------------------------------------------------------------------
# 自摸与点炮的单价（Q-01：自摸不翻倍）
# ---------------------------------------------------------------------------

def test_zimo_pays_same_unit_as_ron():
    """自摸：三家各付一份，单价与点炮相同。"""
    result = settle_round(state_of(), hu([winner(0, True, ('PING_HU',))], None), cfg)
    assert result.deltas == (3, -1, -1, -1)
    assert total(result.deltas) == 0


def test_ron_only_loser_pays():
    """点炮：只有放炮者付，单价还是 1。"""
    result = settle_round(state_of(), hu([winner(0, False, ('PING_HU',))], 2), cfg)
    assert result.deltas == (1, 0, -1, 0)


def test_qi_xing_ron_is_two():
    """七星十三烂点炮只有 2 炮（2026-10-06 改规；分档在结算里同样生效）。"""
    result = settle_round(
        state_of(),
        hu([winner(0, False, ('QI_XING_SHI_SAN_LAN',))], 1),
        cfg,
    )
    assert result.deltas[0] == 2


def test_qi_xing_zimo_is_four_each():
    """七星十三烂自摸是 4 炮 → 三家各付 4。"""
    result = settle_round(
        state_of(),
        hu([winner(0, True, ('QI_XING_SHI_SAN_LAN',))], None),
        cfg,
    )
    assert result.deltas[0] == 12
    assert list(result.deltas[1:]) == [-4, -4, -4]


# ---------------------------------------------------------------------------
# 一炮多响（Q-05）
# ---------------------------------------------------------------------------

def test_multiple_ron_loser_pays_each_winner():
    """放炮者分别付给每个赢家，零和仍成立。"""
    result = settle_round(
        state_of(),
        hu(
            [
                winner(1, False, ('PING_HU',)),
                winner(3, False, ('QI_DUI',)),
            ],
            0,
        ),
        cfg,
    )
    assert result.deltas == (-(1 + 8), 1, 0, 8)
    assert total(result.deltas) == 0


def test_three_winners_each_have_detail():
    """三个赢家都算，detail 里逐家一条。"""
    result = settle_round(
        state_of(),
        hu(
            [
                winner(1, False, ('PING_HU',)),
                winner(2, False, ('PING_HU',)),
                winner(3, False, ('QI_DUI',)),
            ],
            0,
        ),
        cfg,
    )
    assert result.deltas[0] == -(1 + 1 + 8)
    assert [detail.seat for detail in result.detail] == [1, 2, 3]


# ---------------------------------------------------------------------------
# 事件与牌型（分层公式的结算侧）
# ---------------------------------------------------------------------------

def test_gang_shang_kai_hua_adds_four():
    """杠上开花 +4 炮（叠加在牌型分上）。"""
    result = settle_round(
        state_of(),
        hu([winner(1, False, ('PING_HU',), gang_shang=True)], 0),
        cfg,
    )
    assert result.deltas[1] == 5
    assert result.deltas[0] == -5


def test_multi_dimension_before_cap():
    """多维牌型（封顶前）：平胡 + 字一色真 + 十二归一 = 1 + 20 + 9 = 30。"""
    result = settle_round(
        state_of(),
        hu([winner(0, False, ('PING_HU', 'ZI_YI_SE_ZHEN', 'SHI_ER_GUI_YI'))], 1),
        NO_CAP,
    )
    assert result.deltas[0] == 30


def test_dealer_does_not_pay_double():
    """庄家作为付款方不加倍（Q-04）。"""
    result = settle_round(
        state_of((0, 0, 0, 0), 0),
        hu([winner(1, True, ('PING_HU',))], None),
        cfg,
    )
    assert result.deltas[0] == -1  # 与其它两家一样，没有加倍


# ---------------------------------------------------------------------------
# 封顶（2026-10-06：默认 8 炮，只有杠能突破）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('tag_set', [
    ('PING_HU', 'QING_YI_SE_ZHEN'),
    ('PING_HU', 'ZI_YI_SE_ZHEN'),
    ('ZI_YI_SE_JIA',),
    ('PENG_PENG_HU_DAN_DIAO',),
    ('QI_DUI', 'SHI_ER_GUI_YI'),
], ids=['qing-yi-se-zhen', 'zi-yi-se-zhen', 'zi-yi-se-jia', 'peng-peng-dan-diao',
        'qi-dui-shi-er-gui-yi'])
def test_default_cap_is_eight(tag_set):
    """默认封顶 8：清一色真 / 字一色真假 / 七对加归一 全都被压到 8。"""
    result = settle_round(
        state_of(),
        hu([winner(0, True, tag_set)], None),
        cfg,
    )
    assert result.deltas[0] == 24, '+'.join(tag_set)  # 三家 × 8
    assert list(result.deltas[1:]) == [-8, -8, -8], '+'.join(tag_set)


@pytest.mark.parametrize(('tag_set', 'unit'), [
    (('QING_YI_SE_JIA',), 4),
    (('PENG_PENG_HU',), 4),
    (('SHI_SAN_LAN',), 3),
    (('PING_HU',), 1),
], ids=['qing-yi-se-jia', 'peng-peng-hu', 'shi-san-lan', 'ping-hu'])
def test_patterns_within_cap_are_untouched(tag_set, unit):
    """封顶线以内的牌型不受影响：清一色假 4、七星 2/4、碰碰胡 4、平胡 1。"""
    result = settle_round(state_of(), hu([winner(0, False, tag_set)], 1), cfg)
    assert result.deltas[0] == unit, '+'.join(tag_set)


def test_cap_zero_means_uncapped():
    """cap = 0 表示不封顶。"""
    result = settle_round(
        state_of(),
        hu([winner(0, False, ('PING_HU', 'ZI_YI_SE_ZHEN', 'SHI_ER_GUI_YI'))], 1),
        NO_CAP,
    )
    assert result.deltas[0] == 30


def test_cap_limits_each_payer():
    """cap > 0 时单家实付不超过 cap。"""
    capped = replace(cfg, score=replace(cfg.score, cap=20))
    result = settle_round(
        state_of(),
        hu([winner(0, False, ('PING_HU', 'ZI_YI_SE_ZHEN', 'SHI_ER_GUI_YI'))], 1),
        capped,
    )
    assert result.deltas[0] == 20
    assert result.deltas[1] == -20


def test_cap_applies_per_payer_not_to_zimo_total():
    """封顶只作用于单家实付，自摸仍是三家各付。"""
    capped = replace(cfg, score=replace(cfg.score, cap=5))
    result = settle_round(
        state_of(),
        hu([winner(0, True, ('QI_DUI',))], None),
        capped,
    )
    assert result.deltas == (15, -5, -5, -5)


def test_gang_score_merges_after_cap():
    """杠分在封顶之后并入 → 只有杠能突破封顶。"""
    result = settle_round(
        state_of((0, 12, -4, -8), 1),
        hu([winner(1, False, ('PING_HU', 'ZI_YI_SE_ZHEN'))], 0),
        cfg,
    )
    # 胡牌分封顶 8（座 1 +8、座 0 -8），杠分台账再并上去 → 座 1 净得 20，超过封顶线
    assert result.deltas == (-8, 20, -4, -8)
    assert total(result.deltas) == 0


# ---------------------------------------------------------------------------
# 本局杠分并入结算（Q-02）
# ---------------------------------------------------------------------------

def test_huang_zhuang_with_gang_scores():
    """荒庄：庄家赔每家 1 分（共 3 分），已经开过的杠照常保留。"""
    result = settle_round(state_of((2, -2, 0, 0), 0), RoundOutcome(kind='HUANG_ZHUANG'), cfg)
    assert result.deltas == (-3 + 2, 1 - 2, 1, 1)
    assert total(result.deltas) == 0


def test_huang_zhuang_without_gang_scores():
    """没有杠的荒庄：庄家 -3、其余各 +1。"""
    result = settle_round(state_of(), RoundOutcome(kind='HUANG_ZHUANG'), cfg)
    assert result.deltas == (-3, 1, 1, 1)


def test_huang_zhuang_dealer_not_seat_zero():
    """荒庄时庄家不是座位 0 也照样由庄家赔。"""
    result = settle_round(state_of((0, 0, 0, 0), 2), RoundOutcome(kind='HUANG_ZHUANG'), cfg)
    assert result.deltas == (1, 1, -3, 1)


def test_hu_gang_score_merges_too():
    """胡牌时杠分同样并入（杠分独立于胡牌分）。"""
    result = settle_round(
        state_of((-2, 6, -2, -2), 1),
        hu([winner(1, True, ('PING_HU',))], None),
        cfg,
    )
    # 座位 1：+3（自摸）+6（暗杠）；其余：-1（付胡）-2（付杠）
    assert result.deltas == (-3, 9, -3, -3)
    assert total(result.deltas) == 0


# ---------------------------------------------------------------------------
# 零和是硬校验，不是静默修正
# ---------------------------------------------------------------------------

def test_broken_ledger_raises():
    """台账本身就破坏零和时抛异常。"""
    with pytest.raises(ValueError, match='零和'):
        settle_round(
            state_of((5, 0, 0, 0), 0),
            hu([winner(0, False, ('PING_HU',))], 1),
            cfg,
        )


@pytest.mark.parametrize('outcome', [
    hu([winner(0, True, ('QI_DUI',))], None),
    hu([winner(2, False, ('PENG_PENG_HU',))], 3),
    hu([
        winner(0, False, ('PING_HU', 'QING_YI_SE_ZHEN')),
        winner(2, False, ('ZI_YI_SE_JIA',)),
    ], 1),
    RoundOutcome(kind='HUANG_ZHUANG'),
], ids=['zimo', 'ron', 'multi-ron', 'huang-zhuang'])
def test_every_path_is_zero_sum(outcome):
    """每条路径都零和（自摸 / 点炮 / 多响 / 荒庄）。"""
    assert total(settle_round(state_of((1, -1, 0, 0), 3), outcome, cfg).deltas) == 0


# ---------------------------------------------------------------------------
# 与状态机的集成（apply.py 在 SETTLING 时结算）
# ---------------------------------------------------------------------------

def _draw_junk_hands(pool: list[int], seats) -> dict[int, HandState]:
    """从 ``pool`` 里按 round-robin 发杂牌（每手内不重复、不含 11），返回各座位手牌。"""
    hands = {seat: create_hand() for seat in seats}
    seen = {seat: set() for seat in seats}
    dealt = {seat: 0 for seat in seats}
    while True:
        progressed = False
        for seat in seats:
            if dealt[seat] >= 13:
                continue
            index = next(
                (i for i, tile in enumerate(pool) if tile != 11 and tile not in seen[seat]),
                None,
            )
            if index is None:
                continue
            tile = pool.pop(index)
            hands[seat] = add_tile(hands[seat], tile)
            seen[seat].add(tile)
            dealt[seat] += 1
            progressed = True
        if not progressed:
            break
    return hands


def crafted_state(primary_seat: int, concealed, drawn_tile) -> GameState:
    """按指定手牌造一个**不变量成立**的开局状态，其余座位发杂牌（对应 ``craftedRound``）。

    牌墙 = 136 张里没被用掉的那些，所以牌张守恒天然成立。
    """
    reserved: dict[int, int] = {}
    for tile in concealed:
        reserved[tile] = reserved.get(tile, 0) + 1
    if drawn_tile is not None:
        reserved[drawn_tile] = reserved.get(drawn_tile, 0) + 1

    left = {tile: 4 - reserved.get(tile, 0) for tile in range(COUNT_SIZE)}
    pool: list[int] = []
    for tile in full_wall():
        if left.get(tile, 0) > 0:
            pool.append(tile)
            left[tile] -= 1

    junk_seats = [seat for seat in range(4) if seat != primary_seat]
    hands = _draw_junk_hands(pool, junk_seats)
    hands[primary_seat] = HandState(concealed=counts_of(list(concealed)),
                                    drawn_tile=drawn_tile)

    return GameState(
        phase='WAITING_PLAY',
        round=1,
        dealer=primary_seat,
        turn=primary_seat,
        seats=('a', 'b', 'c', 'd'),
        wall=tuple(pool),
        wall_pos=0,
        hands=tuple(hands[seat] for seat in range(4)),
        discards=((), (), (), ()),
        scores=(0, 0, 0, 0),
        round_gang_score=(0, 0, 0, 0),
        cfg=cfg,
    )


#: ``zimoReady(1).hands[1]``：13 张暗牌 + 摸到 11，自摸即胡（平胡 1 炮）。
ZIMO_HAND = (11, 11, 12, 13, 21, 22, 23, 31, 31, 31, 41, 41, 41)


def test_zimo_hu_settles_into_scores():
    """自摸胡之后：累计分累加、本局杠分台账清零。"""
    state = crafted_state(1, ZIMO_HAND, 11)
    result = apply_action(
        state, PlayerAction(type='HU', seat=1, tile=None, req_id=1), cfg, 1)
    assert result.state.phase == 'SETTLING'
    assert result.state.scores == (-1, 3, -1, -1)
    assert result.state.round_gang_score == (0, 0, 0, 0)
    assert total(result.state.scores) == 0


def test_huang_zhuang_settles_into_scores():
    """荒庄之后累计分同样落账。"""
    state = replace(state_of((0, 0, 0, 0), 0), wall=())
    result = settle_round(state, RoundOutcome(kind='HUANG_ZHUANG'), cfg)
    assert total(result.deltas) == 0
    assert result.deltas[0] == -3
