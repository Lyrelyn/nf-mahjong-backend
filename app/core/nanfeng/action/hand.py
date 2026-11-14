"""手牌结构 ``HandState`` 与手牌操作 —— 对应前端 ``assets/scripts/core/action/hand.ts``。

不可变风格：``add_tile`` / ``remove_tile`` / ``add_meld`` 都返回**新的** ``HandState``，
不改动入参。这让回放、撤销与「先算一遍看结果」都能直接做 —— 状态机的 apply 因此可以写成
「算出新状态，校验不变量，失败就整个丢掉」，不会污染原状态。

张数口径：``concealed`` 只放**暗牌**，刚摸到的那张单独记在 ``drawn_tile`` 上
（庄家开局即 13 + 1 = 14），副露按 ``meld_tile_count`` 折算（碰 3、三种杠 4）。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from app.core.nanfeng.counts import Counts, counts_of, total_count
from app.core.nanfeng.melds import Meld, meld_tile_count
from app.core.nanfeng.rule_config import RuleConfig
from app.core.nanfeng.tiles import COUNT_SIZE, Tile


@dataclass(frozen=True)
class HandState:
    #: 暗牌计数（**不含** ``drawn_tile``，也不含副露）。长度 ``COUNT_SIZE``。
    concealed: Counts = field(default_factory=lambda: counts_of(()))
    #: 已经亮出来的碰与杠。
    melds: tuple[Meld, ...] = ()
    #: 刚摸到、还没打出的那张牌；不在摸牌阶段时为 ``None``。
    drawn_tile: int | None = None
    #: 本巡是否刚碰过 —— 碰后不能立即补杠。
    just_peng: bool = False


def create_hand() -> HandState:
    return HandState()


def hand_tile_count(hand: HandState) -> int:
    """手牌张数 = 暗牌 + 摸到的那张 + 副露折算。"""
    n = total_count(hand.concealed) + (0 if hand.drawn_tile is None else 1)
    for meld in hand.melds:
        n += meld_tile_count(meld)
    return n


def add_tile(hand: HandState, tile: Tile) -> HandState:
    concealed = bytearray(hand.concealed)
    concealed[tile] += 1
    return replace(hand, concealed=concealed)


def remove_tile(hand: HandState, tile: Tile) -> HandState:
    if hand.concealed[tile] == 0:
        raise ValueError(f'手牌里没有 {tile} 这张牌，不能移除')
    concealed = bytearray(hand.concealed)
    concealed[tile] -= 1
    return replace(hand, concealed=concealed)


def add_meld(hand: HandState, meld: Meld) -> HandState:
    return replace(hand, melds=hand.melds + (meld,))


def assert_hand_invariants(hand: HandState, _cfg: RuleConfig | None = None) -> None:
    """手牌级不变量：**同一种牌的总数不得超过 4 张**（暗牌 + 摸到的 + 全部副露一起算）。

    这里**故意不检查**「手牌张数符合阶段」—— 那是状态级不变量，由 ``assert_invariants`` 负责。
    """
    for tile in range(COUNT_SIZE):
        n = hand.concealed[tile]
        if hand.drawn_tile == tile:
            n += 1
        for meld in hand.melds:
            if meld.tile == tile:
                n += meld_tile_count(meld)
        if n > 4:
            raise ValueError(f'手牌不合法：牌码 {tile} 超过 4 张（实际 {n} 张）')
