"""``apply_action``：状态机的唯一入口 —— 对应前端 ``assets/scripts/core/state/apply.ts``。

纯函数 —— 返回**新的** ``GameState`` 与一串事件，绝不改动传入的状态
（所以「算完发现不合法就整个丢掉」是安全的）。三条贯穿全文件的约定：

    1. **先校验再变状态**：阶段、座位、动作合法性任一不满足就抛错，不产生半成品状态；
    2. **摸牌必须显式判定荒庄**：``wall_pos >= len(wall)`` → ``SETTLING`` + ``HUANG_ZHUANG``；
       绝不靠「下家摸不到牌抛异常」来兜底（那会变成死循环或崩溃）；
    3. **杠分即时入账**：直杠/暗杠当场记账；**补杠要等抢杠窗口关闭**才记（被抢则一分不计）。
       ``round_gang_score`` 自身永远零和。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal, Optional

from app.core.nanfeng.action.arbiter import arbitrate
from app.core.nanfeng.action.hand import HandState, add_meld, add_tile, remove_tile
from app.core.nanfeng.action.options import (
    ACTION_PRIORITY,
    ActionOption,
    ActionType,
    PlayerAction,
    collect_options,
)
from app.core.nanfeng.action.peng_gang import (
    can_an_gang,
    can_bu_gang,
    can_hu_ron,
    can_hu_self,
)
from app.core.nanfeng.counts import Counts
from app.core.nanfeng.fan_tags import FanTag
from app.core.nanfeng.hu.decompose import is_peng_peng_hu_dan_diao
from app.core.nanfeng.hu.judge import judge_hu
from app.core.nanfeng.melds import Meld, MeldKind
from app.core.nanfeng.rule_config import RuleConfig
from app.core.nanfeng.score.settle import FanDetail, settle_round
from app.core.nanfeng.state.game_state import (
    ClaimState,
    GameState,
    RoundOutcome,
    RoundWinner,
    clone_outcome,
    hand_counts_of,
)
from app.core.nanfeng.state.invariants import assert_invariants
from app.core.nanfeng.state.phase import LEGAL_ACTIONS
from app.core.nanfeng.tiles import Tile

GameEventType = Literal[
    'DRAW', 'DISCARD', 'PENG', 'GANG', 'HU', 'QIANG_GANG_HU', 'SETTLE', 'HUANG_ZHUANG',
]


@dataclass(frozen=True)
class GameEvent:
    """一次状态推进对外广播的事件（房间层负责翻译成 WS 消息）。"""

    type: GameEventType
    seat: Optional[int] = None
    tile: Optional[Tile] = None
    gang_kind: Optional[MeldKind] = None
    winners: tuple[RoundWinner, ...] = ()
    loser_seat: Optional[int] = None
    gang_seat: Optional[int] = None
    deltas: tuple[int, ...] = ()
    detail: tuple[FanDetail, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ApplyResult:
    state: GameState
    events: tuple[GameEvent, ...] = ()


def _fail(msg: str) -> None:
    raise ValueError(msg)


def _assert_phase(state: GameState, phase: str) -> None:
    if state.phase != phase:
        legal = LEGAL_ACTIONS[state.phase]
        _fail(f'阶段 {state.phase} 不接受该动作（要求 {phase}；'
              f'当前阶段合法动作：{"、".join(legal) if legal else "无"}）')


def _assert_turn(state: GameState, seat: int) -> None:
    if seat != state.turn:
        _fail(f'不是你的回合：现在轮到座位 {state.turn}，收到座位 {seat}')


def _set_hand(state: GameState, seat: int, hand: HandState) -> GameState:
    hands = list(state.hands)
    hands[seat] = hand
    return replace(state, hands=tuple(hands))


def _log_internal(state: GameState, kind: Literal['DEAL', 'DRAW'],
                  seat: int, tile: Optional[Tile]) -> GameState:
    """记录一次服务端内部推进（摸牌等）：**不**递增 seq，沿用当前 seq。"""
    entry = {'seq': state.seq, 'type': kind, 'seat': seat, 'tile': tile}
    return replace(state, action_log=state.action_log + (entry,))


def _accept_action(state: GameState, action: PlayerAction) -> GameState:
    """接受一次客户端动作：seq +1，动作入日志。"""
    seq = state.seq + 1
    entry = {'seq': seq, 'type': action.type, 'seat': action.seat, 'tile': action.tile}
    return replace(state, seq=seq, action_log=state.action_log + (entry,))


def _settle_into(state: GameState, outcome: RoundOutcome, cfg: RuleConfig
                 ) -> tuple[GameState, tuple[int, ...], tuple[FanDetail, ...]]:
    """结算并把结果落进累计分，**同时把明细存进 ``last_settle``**。

    ``deltas`` 里已经含了本局杠分，所以落账后必须**把本局台账清零** —— 否则同一笔杠分会被
    算两次，而且 ``Σ(scores + round_gang_score) == 0`` 立刻不成立。
    """
    settled = settle_round(state, outcome, cfg)
    deltas = settled.deltas
    next_state = replace(
        state,
        scores=tuple(value + deltas[i] for i, value in enumerate(state.scores)),
        round_gang_score=tuple(0 for _ in state.round_gang_score),
        last_settle={'deltas': list(deltas), 'detail': list(settled.detail)},
        # 胜负结果与账目一起留下：下一局谁坐庄、谁下场要的是「因」而不是「账」，
        # 而「放炮的是谁」在番型明细里根本没有。
        last_outcome=clone_outcome(outcome),
    )
    return next_state, deltas, settled.detail


def _draw_for(state: GameState, seat: int, cfg: RuleConfig,
              events: list[GameEvent], from_gang: bool) -> ApplyResult:
    """给 ``seat`` 摸一张；牌墙空了就是荒庄。``from_gang`` 决定「杠上开花」。

    **手里已经有一张摸到的牌时必须先把它并进 ``concealed``**：开杠之后补牌就属于这种情况
    （杠吃掉的是暗牌，原来的摸牌还在手上）。直接覆盖 ``drawn_tile`` 会凭空少一张牌、破坏守恒。
    """
    if state.wall_pos >= len(state.wall):
        settled_state, deltas, detail = _settle_into(
            replace(state, phase='SETTLING', claim=None, drawn_from_gang=False),
            RoundOutcome(kind='HUANG_ZHUANG'),
            cfg,
        )
        return ApplyResult(
            state=settled_state,
            events=tuple(events) + (
                GameEvent(type='HUANG_ZHUANG'),
                GameEvent(type='SETTLE', deltas=deltas, detail=detail),
            ),
        )

    tile = state.wall[state.wall_pos]
    hand = state.hands[seat]
    base: HandState = (
        hand if hand.drawn_tile is None
        else add_tile(replace(hand, drawn_tile=None), hand.drawn_tile)
    )

    advanced = replace(
        state,
        wall_pos=state.wall_pos + 1,
        phase='WAITING_PLAY',
        turn=seat,
        claim=None,
        drawn_from_gang=from_gang,
    )
    next_state = _set_hand(
        advanced, seat, replace(base, drawn_tile=tile, just_peng=False))
    return ApplyResult(
        state=_log_internal(next_state, 'DRAW', seat, tile),
        events=tuple(events) + (GameEvent(type='DRAW', seat=seat, tile=tile),),
    )


def _advance_turn(state: GameState, cfg: RuleConfig,
                  events: list[GameEvent]) -> ApplyResult:
    """出牌后无人响应（或窗口全过）→ 下家摸牌。"""
    next_seat = (state.turn + 1) % len(state.hands)
    return _draw_for(replace(state, turn=next_seat), next_seat, cfg, events, False)


def _take_from_discards(discards: tuple[tuple[Tile, ...], ...],
                        seat: int, tile: Tile) -> tuple[tuple[Tile, ...], ...]:
    """从牌河末尾拿走刚被打出的那张（碰/明杠把它变成了副露，不能既算牌河又算副露）。"""
    pile = discards[seat]
    if not pile or pile[-1] != tile:
        _fail(f'牌河里没有可被拿走的那张 {tile}（座位 {seat}）')
    return tuple(
        p[:-1] if index == seat else p for index, p in enumerate(discards))


# ---------------------------------------------------------------------------
# 自己回合的动作
# ---------------------------------------------------------------------------

def _apply_discard(state: GameState, action: PlayerAction, cfg: RuleConfig,
                   now: float) -> ApplyResult:
    _assert_phase(state, 'WAITING_PLAY')
    _assert_turn(state, action.seat)
    tile = action.tile
    if tile is None:
        _fail('出牌必须带 tile')

    hand = state.hands[action.seat]
    if hand.concealed[tile] + (1 if hand.drawn_tile == tile else 0) == 0:
        _fail(f'手牌里没有 {tile} 这张牌，不能打出')

    if hand.drawn_tile == tile:
        next_hand: HandState = replace(hand, drawn_tile=None)
    else:
        next_hand = remove_tile(hand, tile)
    next_hand = replace(next_hand, just_peng=False)

    discards = tuple(
        pile + (tile,) if seat == action.seat else pile
        for seat, pile in enumerate(state.discards))
    accepted = _accept_action(
        _set_hand(
            replace(
                state,
                discards=discards,
                last_discard={'seat': action.seat, 'tile': tile},
                drawn_from_gang=False,
            ),
            action.seat,
            next_hand,
        ),
        action,
    )

    events: list[GameEvent] = [
        GameEvent(type='DISCARD', seat=action.seat, tile=tile)]

    options = collect_options(action.seat, tile, accepted.hands, cfg, None)
    if not options:
        return _advance_turn(accepted, cfg, events)

    claim = ClaimState(
        trigger_seat=action.seat,
        trigger_tile=tile,
        gang_seat=None,
        pending=tuple(options.keys()),
        options=options,
        responses={},
        deadline_at=now + cfg.claim.window_ms,
    )
    return ApplyResult(state=replace(accepted, phase='CLAIM_WINDOW', claim=claim),
                       events=tuple(events))


def _apply_an_gang(state: GameState, action: PlayerAction, cfg: RuleConfig) -> ApplyResult:
    _assert_phase(state, 'WAITING_PLAY')
    _assert_turn(state, action.seat)
    tile = action.tile
    if tile is None:
        _fail('杠必须带 tile')

    hand = state.hands[action.seat]
    if not can_an_gang(hand, tile, cfg, True):
        _fail(f'座位 {action.seat} 不能暗杠 {tile}（手里需要正好 4 张）')

    next_hand = hand
    for _ in range(4):
        next_hand = remove_tile(next_hand, tile)
    next_hand = add_meld(next_hand, Meld(kind='AN_GANG', tile=tile, from_seat=None))

    each = cfg.score.gang.an_gang
    round_gang_score = tuple(
        value + 3 * each if index == action.seat else value - each
        for index, value in enumerate(state.round_gang_score))
    accepted = _accept_action(
        _set_hand(replace(state, round_gang_score=round_gang_score),
                  action.seat, next_hand),
        action,
    )
    return _draw_for(accepted, action.seat, cfg,
                     [GameEvent(type='GANG', seat=action.seat,
                                gang_kind='AN_GANG', tile=tile)], True)


def _apply_bu_gang(state: GameState, action: PlayerAction, cfg: RuleConfig,
                   now: float) -> ApplyResult:
    _assert_phase(state, 'WAITING_PLAY')
    _assert_turn(state, action.seat)
    tile = action.tile
    if tile is None:
        _fail('杠必须带 tile')

    hand = state.hands[action.seat]
    if not can_bu_gang(hand, tile, cfg, True):
        _fail(f'座位 {action.seat} 不能补杠 {tile}'
              '（要碰过这张、手里还有第 4 张，且本巡没刚碰过）')

    melds = tuple(
        Meld(kind='BU_GANG', tile=tile, from_seat=None)
        if (meld.kind == 'PENG' and meld.tile == tile) else meld
        for meld in hand.melds)
    next_hand: HandState = replace(hand, melds=melds)
    next_hand = (
        replace(next_hand, drawn_tile=None) if next_hand.drawn_tile == tile
        else remove_tile(next_hand, tile)
    )

    accepted = _accept_action(_set_hand(state, action.seat, next_hand), action)
    events: list[GameEvent] = [
        GameEvent(type='GANG', seat=action.seat, gang_kind='BU_GANG', tile=tile)]

    options = _qiang_gang_options(accepted, action.seat, tile, cfg)
    if not options:
        # 没人能抢 → 立刻入账，然后照常补一张（杠吃掉一张手牌，所以要补回来）
        credited = _credit_bu_gang_score(accepted, action.seat, cfg)
        return _draw_for(credited, action.seat, cfg, events, True)

    claim = ClaimState(
        trigger_seat=action.seat,
        trigger_tile=tile,
        gang_seat=action.seat,
        pending=tuple(options.keys()),
        options=options,
        responses={},
        deadline_at=now + cfg.claim.window_ms,
    )
    return ApplyResult(
        state=replace(accepted, phase='CLAIM_WINDOW', claim=claim, turn=action.seat),
        events=tuple(events),
    )


def _credit_bu_gang_score(state: GameState, seat: int, cfg: RuleConfig) -> GameState:
    """补杠入账：三家各付 ``bu_gang``，开杠者 +3×。

    **只记账**，不动阶段 —— 入账与「补一张」是两件事，被抢杠时前者要撤销、后者压根不发生。
    """
    each = cfg.score.gang.bu_gang
    round_gang_score = tuple(
        value + 3 * each if index == seat else value - each
        for index, value in enumerate(state.round_gang_score))
    return replace(state, round_gang_score=round_gang_score, claim=None, turn=seat)


def _qiang_gang_options(state: GameState, gang_seat: int, tile: Tile,
                        cfg: RuleConfig) -> dict[int, list[ActionOption]]:
    """抢杠窗口只允许「胡」与「过」，所以不能复用 ``collect_options``（那会给出碰/明杠）。"""
    result: dict[int, list[ActionOption]] = {}
    seat_count = len(state.hands)
    for distance in range(1, seat_count):
        seat = (gang_seat + distance) % seat_count
        if not can_hu_ron(state.hands[seat], tile, cfg):
            continue
        result[seat] = [
            ActionOption(type='HU', priority=ACTION_PRIORITY['HU'],
                         distance=distance, tile=tile),
            ActionOption(type='PASS', priority=ACTION_PRIORITY['PASS'],
                         distance=distance),
        ]
    return result


def _apply_zimo(state: GameState, action: PlayerAction, cfg: RuleConfig) -> ApplyResult:
    _assert_phase(state, 'WAITING_PLAY')
    _assert_turn(state, action.seat)

    hand = state.hands[action.seat]
    if not can_hu_self(hand, cfg):
        _fail(f'座位 {action.seat} 的手牌按自摸不成胡')

    gang_shang = state.drawn_from_gang
    counts: Counts = hand_counts_of(hand)
    tags: list[FanTag] = list(judge_hu(counts, hand.melds, cfg).tags)
    # 单钓将取决于「胡的是哪张」，而 judge_hu 只看到成牌形，所以标签在这里补
    # （同一个 14 张形既可能是单钓来的、也可能是对倒来的）。
    if hand.drawn_tile is not None and is_peng_peng_hu_dan_diao(
            counts, len(hand.melds), hand.drawn_tile):
        tags.append('PENG_PENG_HU_DAN_DIAO')
    if gang_shang:
        tags.append('GANG_SHANG_KAI_HUA')

    winner = RoundWinner(
        seat=action.seat,
        zimo=True,
        gang_shang=gang_shang,
        qiang_gang=False,
        tags=tuple(tags),
    )
    outcome = RoundOutcome(kind='HU', winners=(winner,), loser_seat=None)
    accepted = _accept_action(
        replace(state, phase='SETTLING', claim=None, drawn_from_gang=False), action)
    settled_state, deltas, detail = _settle_into(accepted, outcome, cfg)
    return ApplyResult(
        state=settled_state,
        events=(
            GameEvent(type='HU', winners=(winner,), loser_seat=None),
            GameEvent(type='SETTLE', deltas=deltas, detail=detail),
        ),
    )


# ---------------------------------------------------------------------------
# 鸣牌窗口内的响应
# ---------------------------------------------------------------------------

def _apply_claim_response(state: GameState, action: PlayerAction,
                          cfg: RuleConfig) -> ApplyResult:
    claim = state.claim
    if claim is None:
        _fail('内部错误：CLAIM_WINDOW 阶段却没有 claim')

    if action.seat not in claim.pending:
        _fail(f'座位 {action.seat} 不在鸣牌窗口内'
              f'（待响应：{"、".join(map(str, claim.pending)) or "无"}）')
    allowed = [option.type for option in claim.options.get(action.seat, [])]
    if action.type not in allowed:
        _fail(f'座位 {action.seat} 不能执行 {action.type}'
              f'（可选：{"、".join(allowed) or "无"}）')
    if action.tile is not None and action.tile != claim.trigger_tile:
        _fail(f'窗口内只能针对 {claim.trigger_tile} 行动，收到 {action.tile}')

    responses = dict(claim.responses)
    responses[action.seat] = action.type
    pending = tuple(seat for seat in claim.pending if seat != action.seat)

    accepted = _accept_action(
        replace(state, claim=replace(claim, responses=responses, pending=pending)),
        action,
    )
    if pending:
        return ApplyResult(state=accepted)
    return _resolve_claim(accepted, cfg)


def _resolve_claim(state: GameState, cfg: RuleConfig) -> ApplyResult:
    claim = state.claim
    if claim is None:
        _fail('内部错误：_resolve_claim 时 claim 为空')

    arbitration = arbitrate(claim.trigger_seat, claim.responses, cfg,
                            seat_count=len(state.hands))
    hu_winners = [winner for winner in arbitration.winners if winner.type == 'HU']

    if hu_winners:
        is_qiang_gang = claim.gang_seat is not None
        winners = tuple(
            RoundWinner(
                seat=winner.seat,
                zimo=False,
                gang_shang=False,
                qiang_gang=is_qiang_gang,
                tags=tuple(_ron_tags(state, winner.seat, claim.trigger_tile, cfg,
                                     is_qiang_gang)),
            )
            for winner in hu_winners
        )
        loser_seat = claim.gang_seat if is_qiang_gang else claim.trigger_seat
        outcome = RoundOutcome(kind='HU', winners=winners, loser_seat=loser_seat)
        settled_state, deltas, detail = _settle_into(
            replace(state, phase='SETTLING', claim=None), outcome, cfg)
        hu_event = (
            GameEvent(type='QIANG_GANG_HU', winners=winners, gang_seat=claim.gang_seat)
            if is_qiang_gang
            else GameEvent(type='HU', winners=winners, loser_seat=claim.trigger_seat)
        )
        return ApplyResult(
            state=settled_state,
            events=(hu_event, GameEvent(type='SETTLE', deltas=deltas, detail=detail)),
        )

    winners = arbitration.winners
    if not winners:
        # 这张牌没人要
        if claim.gang_seat is not None:
            # 抢杠窗口关闭且没人抢 → 补杠成立：入账 + 补一张
            credited = _credit_bu_gang_score(state, claim.gang_seat, cfg)
            return _draw_for(credited, claim.gang_seat, cfg, [], True)
        return _advance_turn(replace(state, claim=None), cfg, [])

    winner = winners[0]
    if winner.type == 'PENG':
        return _apply_claim_peng(state, winner.seat)
    if winner.type == 'MING_GANG':
        return _apply_claim_ming_gang(state, winner.seat, cfg)
    _fail(f'仲裁给出了无法处理的赢家类型：{winner.type}')
    raise AssertionError('不可达')


def _apply_claim_peng(state: GameState, seat: int) -> ApplyResult:
    claim = state.claim
    if claim is None:
        _fail('内部错误：碰的时候 claim 为空')

    hand = state.hands[seat]
    next_hand = remove_tile(remove_tile(hand, claim.trigger_tile), claim.trigger_tile)
    next_hand = add_meld(
        next_hand, Meld(kind='PENG', tile=claim.trigger_tile, from_seat=claim.trigger_seat))
    next_hand = replace(next_hand, just_peng=True)

    next_state = _set_hand(
        replace(
            state,
            claim=None,
            phase='WAITING_PLAY',
            turn=seat,
            discards=_take_from_discards(
                state.discards, claim.trigger_seat, claim.trigger_tile),
            last_discard=None,
            drawn_from_gang=False,
        ),
        seat,
        next_hand,
    )
    return ApplyResult(
        state=next_state,
        events=(GameEvent(type='PENG', seat=seat, tile=claim.trigger_tile),),
    )


def _apply_claim_ming_gang(state: GameState, seat: int, cfg: RuleConfig) -> ApplyResult:
    claim = state.claim
    if claim is None:
        _fail('内部错误：明杠的时候 claim 为空')

    hand = state.hands[seat]
    next_hand = hand
    for _ in range(3):
        next_hand = remove_tile(next_hand, claim.trigger_tile)
    next_hand = add_meld(
        next_hand,
        Meld(kind='MING_GANG', tile=claim.trigger_tile, from_seat=claim.trigger_seat))

    each = cfg.score.gang.ming_gang
    round_gang_score = tuple(
        value + each if index == seat
        else value - each if index == claim.trigger_seat
        else value
        for index, value in enumerate(state.round_gang_score))

    next_state = _set_hand(
        replace(
            state,
            claim=None,
            turn=seat,
            round_gang_score=round_gang_score,
            discards=_take_from_discards(
                state.discards, claim.trigger_seat, claim.trigger_tile),
            last_discard=None,
        ),
        seat,
        next_hand,
    )
    return _draw_for(
        next_state, seat, cfg,
        [GameEvent(type='GANG', seat=seat, gang_kind='MING_GANG',
                   tile=claim.trigger_tile)],
        True,
    )


def _ron_tags(state: GameState, seat: int, tile: Tile, cfg: RuleConfig,
              qiang_gang: bool) -> list[FanTag]:
    """点炮/抢杠胡的标签：把赢的那张并进手牌再判，再补上事件标签。

    **2026-10-06 修 bug**：前端原实现只写了「清掉 drawn_tile」，从没把 ``tile`` 并进去 ——
    于是 13 张的听牌手永远凑不满 14 张，``judge_hu`` 一律返回空标签集，**点炮胡全都按 0 炮结算**。
    这里按正确口径做：先把可能留着的 ``drawn_tile`` 折进暗牌，再并上胡牌张，得到真正的 14 张。
    """
    hand = state.hands[seat]
    folded = (
        hand if hand.drawn_tile is None
        else add_tile(replace(hand, drawn_tile=None), hand.drawn_tile)
    )
    counts = add_tile(folded, tile).concealed
    tags: list[FanTag] = list(judge_hu(counts, folded.melds, cfg).tags)
    if is_peng_peng_hu_dan_diao(counts, len(folded.melds), tile):
        tags.append('PENG_PENG_HU_DAN_DIAO')
    if qiang_gang:
        tags.append('QIANG_GANG_HU')
    return tags


def apply_action(state: GameState, action: PlayerAction, cfg: RuleConfig,
                 now: float) -> ApplyResult:
    """唯一入口。``now`` 是服务端时间（毫秒/秒均可，只要与 ``claim.window_ms`` 同单位）——
    引擎自己不看时钟，窗口截止时间由它推出来。

    **在变换前后各断言一次不变量**：入口这次挡住「喂进来的已经是坏状态」（反序列化、或某个上游
    bug），出口这次保证「我这次变换没把状态搞坏」。放在这一个地方，就等于覆盖了内部所有 return
    点，不必在每个分支里各写一遍。
    """
    assert_invariants(state, cfg)
    result = _apply_unchecked(state, action, cfg, now)
    assert_invariants(result.state, cfg)
    return result


def _apply_unchecked(state: GameState, action: PlayerAction, cfg: RuleConfig,
                     now: float) -> ApplyResult:
    if state.phase == 'CLAIM_WINDOW':
        return _apply_claim_response(state, action, cfg)

    if action.type == 'DISCARD':
        return _apply_discard(state, action, cfg, now)
    if action.type == 'AN_GANG':
        return _apply_an_gang(state, action, cfg)
    if action.type == 'BU_GANG':
        return _apply_bu_gang(state, action, cfg, now)
    if action.type == 'HU':
        return _apply_zimo(state, action, cfg)

    legal = LEGAL_ACTIONS[state.phase]
    _fail(f'阶段 {state.phase} 不接受动作 {action.type}'
          f'（合法动作：{"、".join(legal) if legal else "无"}）')
    raise AssertionError('不可达')
