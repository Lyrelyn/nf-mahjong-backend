"""鸣牌仲裁 —— 对应前端 ``assets/scripts/core/action/arbiter.ts``。

窗口关闭后，用把一堆「我想碰/杠/胡」的响应收成一个结果。规则（规则文档 §4，已确认）：
    - 优先级 ``HU(40) > MING_GANG(30) > PENG(20) > PASS(0)``；
    - **一炮多响**（Q-05）：``claim.allow_multiple_hu`` 为真时，HU 这一档**全部**响应者都算胡，
      放炮者分别付给每家；为假时只取距出牌者最近的一家；
    - 碰/杠永远只出一个赢家，同级取最近者。

``winners`` 按「距出牌者的顺时针距离」升序返回 —— 顺序固定，服务端与各客户端看到的数组一致，
不会因为 dict 插入顺序不同而分叉。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.nanfeng.action.options import ACTION_PRIORITY, ActionType
from app.core.nanfeng.rule_config import RuleConfig


@dataclass(frozen=True)
class ArbitrationWinner:
    seat: int
    type: ActionType


@dataclass(frozen=True)
class ArbitrationResult:
    winners: tuple[ArbitrationWinner, ...] = ()
    #: 未入选的响应者（不含 PASS），按座位号升序。
    others: tuple[int, ...] = field(default_factory=tuple)


def _rank_of(action_type: str) -> int:
    return ACTION_PRIORITY.get(action_type, -1)


def arbitrate(
    trigger_seat: int,
    responses: dict[int, ActionType],
    cfg: RuleConfig,
    seat_count: int = 4,
) -> ArbitrationResult:
    def distance_of(seat: int) -> int:
        return ((seat - trigger_seat) % seat_count + seat_count) % seat_count

    # 距离升序 = 离出牌者越来越远；座位互不相同，所以不会有并列距离。
    active = sorted(
        ((seat, action) for seat, action in responses.items() if action != 'PASS'),
        key=lambda item: distance_of(item[0]),
    )

    if not active:
        return ArbitrationResult()

    top_rank = max(_rank_of(action) for _, action in active)
    if top_rank < 0:
        # 全是窗口外动作（暗杠/补杠/出牌）：没有赢家，但它们确实「响」过，交给上层处理。
        return ArbitrationResult(others=tuple(sorted(seat for seat, _ in active)))

    top = [(seat, action) for seat, action in active if _rank_of(action) == top_rank]
    winners = top if (top[0][1] == 'HU' and cfg.claim.allow_multiple_hu) else top[:1]

    winner_seats = {seat for seat, _ in winners}
    others = tuple(sorted(seat for seat, _ in active if seat not in winner_seats))

    return ArbitrationResult(
        winners=tuple(ArbitrationWinner(seat=seat, type=action) for seat, action in winners),
        others=others,
    )
