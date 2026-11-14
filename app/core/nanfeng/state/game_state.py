"""牌局状态 —— 对应前端 ``assets/scripts/core/state/gameState.ts``。

``GameState`` 是**唯一真相**，在联机模式下只存在于服务端进程里。
时间与随机数都由参数注入（spec §3.3）：``start_round`` 收一个随机源，``apply_action`` 收一个 ``now``。

与前端版本的唯一差别：**服务端就是裁判**，所以没有 ``host_id`` / ``host_seat``，
也没有「房主迁移」需要的私有手牌上报 —— 那些在联机架构里整体消失。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, Literal, Optional

from app.core.nanfeng.action.hand import HandState, add_tile, create_hand
from app.core.nanfeng.action.options import ActionOption, ActionType
from app.core.nanfeng.fan_tags import FanTag
from app.core.nanfeng.prng import Rng, rng_from, shuffle_wall
from app.core.nanfeng.rule_config import RuleConfig, validate_rule_config
from app.core.nanfeng.state.phase import Phase
from app.core.nanfeng.tiles import Tile, full_wall


@dataclass(frozen=True)
class ClaimState:
    """一个鸣牌窗口。``gang_seat`` 非空表示这是**抢杠窗口**（只允许 HU / PASS）。"""

    #: 出牌者；抢杠窗口里是补杠那一家。
    trigger_seat: int
    trigger_tile: Tile
    #: 补杠的那一家；普通点炮窗口为 ``None``。
    gang_seat: Optional[int]
    #: 还没响应的座位。
    pending: tuple[int, ...]
    options: dict[int, list[ActionOption]]
    responses: dict[int, ActionType]
    deadline_at: float


@dataclass(frozen=True)
class RoundWinner:
    """一个赢家。``tags`` 是判胡标签（已并入杠上开花 / 抢杠这类事件标签）。"""

    seat: int
    zimo: bool
    gang_shang: bool = False
    qiang_gang: bool = False
    tags: tuple[FanTag, ...] = ()


@dataclass(frozen=True)
class RoundOutcome:
    kind: Literal['HU', 'HUANG_ZHUANG']
    winners: tuple[RoundWinner, ...] = ()
    #: 放炮者；自摸与荒庄为 ``None``。
    loser_seat: Optional[int] = None


@dataclass(frozen=True)
class GameState:
    phase: Phase
    round: int
    dealer: int
    #: 当前该谁出牌。
    turn: int
    #: 每个座位的玩家 id（对应房间层的 roster）。昵称/准备状态不在这里。
    seats: tuple[str, ...]
    #: **还没被摸走**的牌墙（发牌时已经抽掉了庄家的第 14 张）。
    wall: tuple[Tile, ...]
    #: 已经从这个牌墙里摸走了几张。``wall_pos >= len(wall)`` 就是荒庄。
    wall_pos: int
    hands: tuple[HandState, ...]
    discards: tuple[tuple[Tile, ...], ...]
    #: 跨局累计得分。
    scores: tuple[int, ...]
    #: **本局**杠分净额，开杠即时入账、荒庄也保留（Q-02）。
    round_gang_score: tuple[int, ...]
    last_discard: Optional[dict] = None
    #: 本局的结算结果（账）；还没结算时为 ``None``。
    last_settle: Optional[dict] = None
    #: 本局的胜负结果（因）；还没结算时为 ``None``。
    #:
    #: 与 ``last_settle`` 是两件事，都必须留着：前者是**账**（各家净得分 + 番型），
    #: 后者是**因**（谁赢谁输）。下一局谁坐庄、谁下场要的是后者 ——
    #: 而「放炮的是谁」在番型明细里根本没有，光看账推不出来。
    last_outcome: Optional[RoundOutcome] = None
    #: 刚摸到的那张是不是杠后补的牌（决定「杠上开花」）。
    drawn_from_gang: bool = False
    claim: Optional[ClaimState] = None
    #: 只由服务端递增；一次客户端动作 +1（随之而来的摸牌不额外加）。
    seq: int = 0
    epoch: int = 1
    action_log: tuple[dict, ...] = field(default_factory=tuple)
    #: 本局开局时用的规则配置 —— 重放必须用同一份，所以它是牌局身份的一部分。
    cfg: RuleConfig = field(default_factory=RuleConfig)


def clone_outcome(outcome: RoundOutcome) -> RoundOutcome:
    """拷一份胜负结果（``winners`` 是 dataclass，本身不可变，这里只做防御性复制）。"""
    if outcome.kind == 'HUANG_ZHUANG':
        return RoundOutcome(kind='HUANG_ZHUANG')
    return RoundOutcome(
        kind='HU',
        winners=tuple(
            RoundWinner(
                seat=winner.seat,
                zimo=winner.zimo,
                gang_shang=winner.gang_shang,
                qiang_gang=winner.qiang_gang,
                tags=tuple(winner.tags),
            )
            for winner in outcome.winners
        ),
        loser_seat=outcome.loser_seat,
    )


def hand_counts_of(hand: HandState) -> bytearray:
    """手里的全部暗牌：``concealed`` 并入刚摸到的那张。"""
    if hand.drawn_tile is None:
        return hand.concealed
    merged = bytearray(hand.concealed)
    merged[hand.drawn_tile] += 1
    return merged


@dataclass(frozen=True)
class StartRoundOptions:
    #: 每个座位的玩家 id。
    seats: tuple[str, ...]
    dealer: int
    cfg: RuleConfig
    rng: Optional[Rng | Callable[[], float] | int] = None
    round: int = 1
    epoch: int = 1


def start_round(opts: StartRoundOptions) -> GameState:
    """开局：洗牌 → 每家 13 张 → 庄家多摸一张（放在 ``drawn_tile`` 上，不进 ``concealed``）。

    ``wall`` 里留下的是**还没被摸走**的牌，``wall_pos`` 从 0 开始 —— 所以「剩余张数」就是
    ``len(wall) - wall_pos``，荒庄判定也只是一次比较。

    第一局的 ``dealer`` 由调用方传房主座位（Q-06：房主坐庄）；之后用 ``next_round_seating``。
    """
    seats = tuple(opts.seats)
    cfg = opts.cfg
    validate_rule_config(cfg)
    if len(seats) != 4:
        raise ValueError(f'座位数必须是 4，收到 {len(seats)}')
    if not 0 <= opts.dealer < len(seats):
        raise ValueError(f'庄家座位越界：{opts.dealer}')

    next_random = rng_from(opts.rng)
    shuffled = shuffle_wall(full_wall(), _CallableRng(next_random))

    hands: list[HandState] = []
    cursor = 0
    for _seat in range(len(seats)):
        hand = create_hand()
        for _ in range(13):
            hand = add_tile(hand, shuffled[cursor])
            cursor += 1
        hands.append(hand)
    hands[opts.dealer] = replace(hands[opts.dealer], drawn_tile=shuffled[cursor])
    cursor += 1
    wall = tuple(shuffled[cursor:])

    return GameState(
        phase='WAITING_PLAY',
        round=opts.round,
        dealer=opts.dealer,
        turn=opts.dealer,
        seats=seats,
        wall=wall,
        wall_pos=0,
        hands=tuple(hands),
        discards=tuple(() for _ in seats),
        scores=tuple(0 for _ in seats),
        round_gang_score=tuple(0 for _ in seats),
        epoch=opts.epoch,
        cfg=cfg,
    )


@dataclass
class _CallableRng:
    """把 ``() -> float`` 包成 ``Rng`` 协议（``shuffle_wall`` 只要求 ``next()``）。"""

    next: Callable[[], float]


def start_lobby(seats: tuple[str, ...], cfg: RuleConfig, epoch: int = 1) -> GameState:
    """大厅：**还没开局**的那一段时间（一局都没开过，``round`` 为 0）。

    为什么不能直接拿 ``start_round`` 顶替：它硬要求恰好 4 个座位，而「等人到齐」这个阶段
    座位表**本来就不满**。大厅不需要新的状态机，只需要一个**一副牌都还没发**的开局状态。
    """
    seats = tuple(seats)
    validate_rule_config(cfg)
    if not seats:
        raise ValueError('大厅至少要有一个座位（房主自己）')

    return GameState(
        phase='LOBBY',
        round=0,
        dealer=0,
        turn=0,
        seats=seats,
        # 整副牌原封不动躺在牌墙里，所以守恒天然成立（见 invariants 第 2 条）。
        wall=tuple(full_wall()),
        wall_pos=0,
        hands=tuple(create_hand() for _ in seats),
        discards=tuple(() for _ in seats),
        scores=tuple(0 for _ in seats),
        round_gang_score=tuple(0 for _ in seats),
        epoch=epoch,
        cfg=cfg,
    )


def next_round_seating(state: GameState, outcome: RoundOutcome) -> dict[str, int]:
    """本局结束后谁坐庄、谁下场买码（R-02 / C-9）。

    ================  ==================  ==================
    本局结果           下局庄家             下场的人
    ================  ==================  ==================
    庄家胡（含自摸）    庄家连庄             庄家的**对家**
    别人**点炮**胡       **胡牌者**坐庄        **放炮者**
    别人**自摸**胡       **胡牌者**坐庄        自摸者的**对家**
    荒庄               庄家的**对家**        **庄家**
    ================  ==================  ==================

    第三行是原设计漏掉的一种情形 —— R-02 的表只写了「庄家自摸 / 别人点炮 / 流局」三种，
    少了「非庄家自摸」（**没有放炮者**）。补法沿用牌友原话「自摸对家下场」，
    即**自摸者的对家**下场（庄家自摸时它也等价于「庄家的对家」）。

    用 ``zimo`` 区分「自摸」与「点炮忘了给放炮者」：``zimo=False`` 且 ``loser_seat is None``
    属编程错误，直接抛。

    多家同时胡时取 ``winners`` 的第一家 —— ``arbitrate`` 已按「距放炮者顺时针距离」升序返回。
    """
    seat_count = len(state.hands)

    def opposite(seat: int) -> int:
        return (seat + seat_count // 2) % seat_count

    if outcome.kind == 'HUANG_ZHUANG':
        return {'dealer': opposite(state.dealer), 'sitting_out': state.dealer}

    if any(winner.seat == state.dealer for winner in outcome.winners):
        return {'dealer': state.dealer, 'sitting_out': opposite(state.dealer)}
    if not outcome.winners:
        raise ValueError('胡牌结果里没有赢家')

    winner = outcome.winners[0]
    if outcome.loser_seat is not None:
        return {'dealer': winner.seat, 'sitting_out': outcome.loser_seat}
    if all(w.zimo for w in outcome.winners):
        return {'dealer': winner.seat, 'sitting_out': opposite(winner.seat)}
    raise ValueError('点炮胡必须给出放炮者（loser_seat），否则无法定下一个庄家与下场的人')
