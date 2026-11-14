"""可操作项收集 —— 对应前端 ``assets/scripts/core/action/options.ts``。

一张牌打出后，算出**每个其他玩家**能做什么，供房间层开鸣牌窗口。
只有「有事可做」的玩家进入窗口（只能 PASS 的人不入窗，避免全桌等一个只能过的人 —— spec §6.2）。
窗口内恒定带一条 ``PASS``，所以 UI 永远有「过」可按。

只收出牌响应类操作：``HU`` / ``MING_GANG`` / ``PENG`` / ``PASS``。暗杠与补杠属自己回合，不下发。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Optional, Sequence

from app.core.nanfeng.action.hand import HandState
from app.core.nanfeng.action.peng_gang import (
    can_an_gang,
    can_bu_gang,
    can_hu_ron,
    can_hu_self,
    can_ming_gang,
    can_peng,
)
from app.core.nanfeng.rule_config import RuleConfig
from app.core.nanfeng.tiles import Tile

ActionType = Literal[
    'DISCARD', 'PENG', 'MING_GANG', 'AN_GANG', 'BU_GANG', 'HU', 'PASS',
]


@dataclass(frozen=True)
class PlayerAction:
    """客户端上行的一个意图。**不是状态** —— 只有房间层能改状态。"""

    type: ActionType
    seat: int
    tile: Optional[Tile] = None
    req_id: int = 0


@dataclass(frozen=True)
class ActionOption:
    type: ActionType
    priority: int
    distance: int
    #: 这条动作作用于哪张牌；``PASS`` 与出牌这类没有具体牌的为 ``None``。
    #:
    #: 为什么必须带上：界面只有「类型」是不够的 —— 手里同时能暗杠 1111 和 2222 时，
    #: 两条选项的 ``type`` 都是 ``AN_GANG``，界面上就成了两个一模一样的「暗杠」按钮。
    tile: Optional[Tile] = None
    #: 胡牌预估炮数；非 HU 选项与未提供预估时都是 ``None``。
    hu_preview: Optional[int] = None


#: 胡分预估：由调用方注入（计分要理解番型，这里的选项收集只留接口）。
HuPreviewProvider = Callable[[int, Tile], Optional[int]]

#: 仲裁优先级（规则文档 §4，Task 0 已确认）。**只有出牌响应类操作有优先级** ——
#: 暗杠/补杠/出牌不经仲裁，所以它们不在这张表里。
ACTION_PRIORITY: dict[str, int] = {
    'HU': 40,
    'MING_GANG': 30,
    'PENG': 20,
    'PASS': 0,
}

ClaimActionType = Literal['HU', 'MING_GANG', 'PENG', 'PASS']


def collect_options(
    trigger_seat: int,
    trigger_tile: Tile,
    hands: Sequence[HandState],
    cfg: RuleConfig,
    hu_preview: Optional[HuPreviewProvider] = None,
) -> dict[int, list[ActionOption]]:
    """收集窗口内每个玩家的可操作项。

    ``distance`` 是从出牌者往下家数的顺时针距离（1..seat_count-1）；同级优先级按它升序，
    即「距出牌者最近者优先」。
    """
    seat_count = len(hands)
    result: dict[int, list[ActionOption]] = {}

    for distance in range(1, seat_count):
        seat = (trigger_seat + distance) % seat_count
        hand = hands[seat]
        options: list[ActionOption] = []

        # 每类最多一条，所以不需要事后去重。
        if can_hu_ron(hand, trigger_tile, cfg):
            options.append(ActionOption(
                type='HU',
                priority=ACTION_PRIORITY['HU'],
                distance=distance,
                tile=trigger_tile,
                hu_preview=None if hu_preview is None else hu_preview(seat, trigger_tile),
            ))
        if can_ming_gang(hand, trigger_tile, cfg):
            options.append(ActionOption(
                type='MING_GANG',
                priority=ACTION_PRIORITY['MING_GANG'],
                distance=distance,
                tile=trigger_tile,
            ))
        if can_peng(hand, trigger_tile, cfg):
            options.append(ActionOption(
                type='PENG',
                priority=ACTION_PRIORITY['PENG'],
                distance=distance,
                tile=trigger_tile,
            ))

        if not options:
            continue  # 只能 PASS 的玩家不进窗口

        options.append(ActionOption(
            type='PASS',
            priority=ACTION_PRIORITY['PASS'],
            distance=distance,
        ))
        options.sort(key=lambda option: (-option.priority, option.distance))
        result[seat] = options

    return result


def _own_option(action_type: ActionType, tile: Tile) -> ActionOption:
    """一条「不经仲裁」的自家动作：没有距离可言，也没有炮数预估。"""
    return ActionOption(
        type=action_type,
        priority=ACTION_PRIORITY['HU'] if action_type == 'HU' else ACTION_PRIORITY['PASS'],
        distance=0,
        tile=tile,
    )


def own_turn_options(hand: HandState, cfg: RuleConfig) -> list[ActionOption]:
    """轮到自己出牌时的可操作项：暗杠 / 补杠 / 自摸。

    **出牌本身不在这里** —— 点一张牌就是出牌。

    为什么必须由服务端算好下发、而不是客户端自己判断：``can_bu_gang`` 要看 ``just_peng``
    （「本巡刚碰过，不能立刻补杠同一张」），而 ``just_peng`` **不在公开视图里**；客户端要自己算，
    就得把这份规则抄第二遍，两份规则迟早不一致 —— 表现为「按钮亮着但点下去被服务端拒」。
    """
    options: list[ActionOption] = []
    # 自摸那条的 tile 是刚摸到的那张 —— 计分要用它，界面上也是「胡这张」的意思。
    if hand.drawn_tile is not None and can_hu_self(hand, cfg):
        options.append(_own_option('HU', hand.drawn_tile))

    for tile in range(11, len(hand.concealed)):
        if can_an_gang(hand, tile, cfg, True):
            options.append(_own_option('AN_GANG', tile))
        if can_bu_gang(hand, tile, cfg, True):
            options.append(_own_option('BU_GANG', tile))

    # 排序：HU 在前（优先级 40 > 0），杠类按牌码升序、同码先暗杠后补杠（稳定排序保留入列顺序）。
    options.sort(key=lambda option: -option.priority)
    return options
