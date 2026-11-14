"""单局结算 —— 对应前端 ``assets/scripts/core/score/settle.ts``。

把 ``RoundOutcome`` 变成四家「净得分」，并**硬校验零和**::

    炮数     = score_of_tags(tags, cfg, zimo) + (杠上开花 ? 4 : 0)
    单家实付 = 炮数 × (自摸且 zimo_double ? 2 : 1)      # Q-01 之后 zimo_double 默认 False
             → cap > 0 时再取 min(实付, cap)
    点炮：放炮者分别付给**每个**赢家（Q-05 一炮多响）
    自摸：其余三家各付一份（自摸不可能多响）
    荒庄：庄家赔每家 1 分（共 3 分），不看听牌（R-08）

**杠分不在这一层重算**：开杠时已经把净额记进 ``state.round_gang_score``（补杠要等抢杠窗口关闭）。
这里只把它并进来 —— 所以荒庄时已经开过的杠照样算（Q-02），而胡牌分与杠分是两笔独立收支。

任何路径都以 ``Σ deltas == 0`` 结尾；不满足直接抛异常，**不做静默修正**（spec §12.4 不变量 3）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.nanfeng.fan_tags import FanTag
from app.core.nanfeng.rule_config import RuleConfig
from app.core.nanfeng.score.score_table import score_of_tags
from app.core.nanfeng.state.game_state import GameState, RoundOutcome


@dataclass(frozen=True)
class FanDetail:
    """一家赢家这一局的账目明细，给结算面板直接渲染。"""

    seat: int
    tags: tuple[FanTag, ...]
    zimo: bool
    gang_shang: bool
    #: 牌型炮数（不含杠上开花的 +4）。
    fan: int
    #: 单家实付（封顶之后）。
    unit: int
    #: 这家这一局从胡牌上收入多少（自摸 = 3×unit，点炮 = unit）。
    income: int


@dataclass(frozen=True)
class SettleResult:
    #: 四家的本局净得分（含杠分）。
    deltas: tuple[int, ...] = field(default_factory=tuple)
    detail: tuple[FanDetail, ...] = field(default_factory=tuple)


def settle_round(state: GameState, outcome: RoundOutcome, cfg: RuleConfig) -> SettleResult:
    seat_count = len(state.hands)
    deltas = [0] * seat_count
    detail: list[FanDetail] = []

    if outcome.kind == 'HUANG_ZHUANG':
        each = cfg.score.huang_zhuang.dealer_pays_each
        deltas[state.dealer] -= each * (seat_count - 1)
        for seat in range(seat_count):
            if seat != state.dealer:
                deltas[seat] += each
    else:
        for winner in outcome.winners:
            tags = frozenset(winner.tags)
            #: 明细里保留**判胡时追加标签的顺序**：TS 是 ``Array.from(new Set(tags))`` ——
            #: 去重且保序。直接 ``tuple(frozenset)`` 会让顺序随 PYTHONHASHSEED 变，明细不可复现。
            ordered_tags = tuple(dict.fromkeys(winner.tags))
            gang_shang = winner.gang_shang
            fan = score_of_tags(tags, cfg, zimo=winner.zimo).score
            if gang_shang:
                fan += cfg.score.gang_shang_kai_hua

            doubled = 2 if (winner.zimo and cfg.score.zimo_double) else 1
            unit = fan * doubled
            if cfg.score.cap > 0:
                unit = min(unit, cfg.score.cap)

            if winner.zimo:
                # 自摸：其余三家各付一份
                income = unit * (seat_count - 1)
                for seat in range(seat_count):
                    if seat != winner.seat:
                        deltas[seat] -= unit
            else:
                if outcome.loser_seat is None:
                    raise ValueError('结算失败：点炮胡必须给出放炮者（loser_seat）')
                income = unit
                deltas[outcome.loser_seat] -= unit
            deltas[winner.seat] += income

            detail.append(FanDetail(
                seat=winner.seat,
                tags=ordered_tags,
                zimo=winner.zimo,
                gang_shang=gang_shang,
                fan=fan,
                unit=unit,
                income=income,
            ))

    # 杠分并入（独立于胡牌分；荒庄也保留）
    for seat in range(seat_count):
        deltas[seat] += state.round_gang_score[seat]

    total = sum(deltas)
    if total != 0:
        raise ValueError(
            f'结算失败：零和被破坏（Σ = {total}）—— 这是账目 bug，不做静默修正。'
            f'检查本局杠分台账 {list(state.round_gang_score)}')

    return SettleResult(deltas=tuple(deltas), detail=tuple(detail))
