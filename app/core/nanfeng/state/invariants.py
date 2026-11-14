"""全局不变量 —— 对应前端 ``assets/scripts/core/state/invariants.ts``。

每次状态变更前后都断言，坏状态一律在**产生它的那一次变换**上炸掉，
而不是漂到几巡之后变成「分数对不上」。四条检查（spec §12.4）：

    1. 每种牌的总数不得超过 4 张；
    2. 牌张守恒：牌墙 + 暗牌 + 副露 + 牌河 = 136；
    3. 手牌数符合阶段；
    4. 得分零和：``scores`` + ``round_gang_score`` 合计为 0。

两个「张数」概念必须分清：
    - **物理张数**（``physical_hand_size``，杠算 4）—— 守恒用；
    - **结构张数**（``effective_hand_size``，一副露固定占 3 个位）—— 手牌数用。
这是因为「杠」占 4 张实体牌但只算一组面子：手里有一个杠的人，物理上比常人多一张牌，
结构上却和别人一样。
"""

from __future__ import annotations

from typing import Optional

from app.core.nanfeng.action.hand import HandState
from app.core.nanfeng.counts import total_count
from app.core.nanfeng.melds import meld_tile_count
from app.core.nanfeng.rule_config import RuleConfig
from app.core.nanfeng.state.game_state import GameState
from app.core.nanfeng.tiles import WALL_SIZE, Tile


def effective_hand_size(hand: HandState) -> int:
    """结构张数：暗牌 + 摸到的那张 + 每副露 3 个位（杠也占 3 个位）。"""
    return (total_count(hand.concealed)
            + (0 if hand.drawn_tile is None else 1)
            + 3 * len(hand.melds))


def physical_hand_size(hand: HandState) -> int:
    """物理张数：暗牌 + 摸到的那张 + 副露实体张数（碰 3、杠 4）。"""
    n = total_count(hand.concealed) + (0 if hand.drawn_tile is None else 1)
    for meld in hand.melds:
        n += meld_tile_count(meld)
    return n


def _expected_hand_sizes(state: GameState) -> Optional[list[int]]:
    """当前阶段下四家各应有多少**结构**张牌；返回 ``None`` 表示这个阶段不做检查。"""
    seat_count = len(state.hands)
    if state.phase == 'WAITING_PLAY':
        return [14 if seat == state.turn else 13 for seat in range(seat_count)]
    if state.phase == 'CLAIM_WINDOW':
        # 普通点炮窗口与抢杠窗口都是「四家各 13 张」：
        # 出牌者刚打出一张（14→13）；补杠的人把摸到的第 4 张并进副露（结构上仍是 13）。
        return [13] * seat_count
    return None


def _tally_all_tiles(state: GameState) -> dict[Tile, int]:
    """把整局里每一张牌按牌码数出来（牌墙剩余 + 四家 + 牌河）。"""
    tally: dict[Tile, int] = {}

    def add(tile: Tile, n: int = 1) -> None:
        tally[tile] = tally.get(tile, 0) + n

    for i in range(state.wall_pos, len(state.wall)):
        add(state.wall[i])
    for hand in state.hands:
        concealed = hand.concealed
        for tile in range(len(concealed)):
            if concealed[tile] > 0:
                add(tile, concealed[tile])
        if hand.drawn_tile is not None:
            add(hand.drawn_tile)
        for meld in hand.melds:
            add(meld.tile, meld_tile_count(meld))
    for pile in state.discards:
        for tile in pile:
            add(tile)

    return tally


def assert_invariants(state: GameState, _cfg: RuleConfig | None = None) -> None:
    # 1) 逐牌上限。先查这条：它比守恒更具体，报出来的牌码直接指向出错的那张牌。
    for tile, n in _tally_all_tiles(state).items():
        if n > 4:
            raise ValueError(f'状态不合法：牌码 {tile} 超过 4 张（实际 {n} 张）')

    # 2) 牌张守恒
    total = len(state.wall) - state.wall_pos
    for hand in state.hands:
        total += physical_hand_size(hand)
    for pile in state.discards:
        total += len(pile)
    if total != WALL_SIZE:
        raise ValueError(
            f'状态不合法：牌张守恒被破坏（牌墙 {len(state.wall) - state.wall_pos} '
            f'+ 暗牌副露 + 牌河 = {total}，应为 {WALL_SIZE}）')

    # 3) 手牌数符合阶段
    expected = _expected_hand_sizes(state)
    if expected is not None:
        for seat, hand in enumerate(state.hands):
            actual = effective_hand_size(hand)
            if actual != expected[seat]:
                raise ValueError(
                    f'状态不合法：手牌数不符合阶段（座位 {seat} 结构上有 {actual} 张，'
                    f'{state.phase} 阶段应为 {expected[seat]} 张）')

    # 4) 得分零和（跨局累计得分 + 本局杠分台账）
    total_score = sum(state.scores) + sum(state.round_gang_score)
    if total_score != 0:
        raise ValueError(f'状态不合法：得分不为零（Σ scores + round_gang_score = {total_score}）')
