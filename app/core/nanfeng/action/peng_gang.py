"""碰 / 杠 / 胡的合法性判定 —— 对应前端 ``assets/scripts/core/action/pengGang.ts``。

全部是**纯谓词**：只看手牌与配置，不看阶段、不看谁在等谁。阶段相关的事由调用方显式传进来
（``own_turn``）或由状态机把关 —— 这样每条规则都能单独写单测，包括「越权调用应当返回 False」。

R-06 之后这里**没有禁碰 / 禁胡状态**：漏了随时能碰、随时能胡，也不需要「摸牌后清除标记」。
"""

from __future__ import annotations

from app.core.nanfeng.action.hand import HandState
from app.core.nanfeng.counts import Counts
from app.core.nanfeng.hu.judge import judge_hu
from app.core.nanfeng.hu.shi_san_lan import requires_self_draw
from app.core.nanfeng.rule_config import RuleConfig
from app.core.nanfeng.tiles import Tile


def _with_tile(counts: Counts, tile: Tile) -> Counts:
    result = bytearray(counts)
    result[tile] += 1
    return result


def _full_counts(hand: HandState) -> Counts:
    """手里的全部暗牌：``concealed`` + 刚摸到的那张。"""
    if hand.drawn_tile is None:
        return hand.concealed
    return _with_tile(hand.concealed, hand.drawn_tile)


def _concealed_copies(hand: HandState, tile: Tile) -> int:
    """某张牌在「暗牌 + 刚摸到的」里共有几张。"""
    return hand.concealed[tile] + (1 if hand.drawn_tile == tile else 0)


def can_peng(hand: HandState, tile: Tile, _cfg: RuleConfig | None = None) -> bool:
    """碰：手里至少 2 张。"""
    return hand.concealed[tile] >= 2


def can_ming_gang(hand: HandState, tile: Tile, _cfg: RuleConfig | None = None) -> bool:
    """明杠（直杠）：手里至少 3 张。"""
    return hand.concealed[tile] >= 3


def can_an_gang(hand: HandState, tile: Tile, _cfg: RuleConfig | None = None,
                own_turn: bool = False) -> bool:
    """暗杠：手里**正好** 4 张，且必须轮到自己。"""
    return own_turn and hand.concealed[tile] == 4


def can_bu_gang(hand: HandState, tile: Tile, _cfg: RuleConfig | None = None,
                own_turn: bool = False) -> bool:
    """补杠（弯杠）：碰过这张、手里还有第 4 张，且必须轮到自己。

    ``just_peng`` 为真表示本巡刚碰过 —— 碰完不能立刻补杠同一张。
    """
    if not own_turn or hand.just_peng:
        return False
    penged = any(meld.kind == 'PENG' and meld.tile == tile for meld in hand.melds)
    return penged and _concealed_copies(hand, tile) >= 1


def _is_winning_hand(hand: HandState, counts: Counts, cfg: RuleConfig, zimo: bool) -> bool:
    """这手牌能否按 ``zimo`` 的方式胡。

    两条与「怎么胡」有关的规则在这里落地：
        - **假胡的点炮开关**（``hu.jia_hu.allow_ron``）：``structure == 'NONE'`` 说明这手牌只有
          假胡标签，开关为假时点炮拒胡、自摸照常（R-03）；
        - **十三烂的自摸限制**（R-05）：字牌 5 / 6 张时只能自摸 —— 这是胡牌合法性限制，
          不只是计分，所以判定要用**并入待胡那张牌之后**的 14 张手牌。
    """
    result = judge_hu(counts, hand.melds, cfg)
    if not result.tags:
        return False
    if zimo:
        return True
    if result.structure == 'NONE' and not cfg.hu.jia_hu.allow_ron:
        return False
    return not requires_self_draw(counts)


def can_hu_self(hand: HandState, cfg: RuleConfig) -> bool:
    """自摸：手里已经是成胡的 14 张。"""
    return _is_winning_hand(hand, _full_counts(hand), cfg, True)


def can_hu_ron(hand: HandState, tile: Tile, cfg: RuleConfig) -> bool:
    """点炮 / 抢杠：把别人打出的那张并进来，看是否成胡。"""
    return _is_winning_hand(hand, _with_tile(_full_counts(hand), tile), cfg, False)
