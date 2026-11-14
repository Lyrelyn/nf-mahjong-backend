"""南丰规则内核测试夹具 —— 对应前端 ``tests/helpers/fixtures.ts``。

只移植「牌局夹具」那一半（``startBase`` / ``craftedRound`` / ``playToDiscard`` / …），
因为另外一半（``handOf`` / ``makeFiveClientRoom``）依赖前端独有的 host/client 会话层。

所有名字、参数、语义都与前端逐一对应，**不在各用例里自己发明夹具** —— 这样 TS 与 pytest
两边逐条对拍时，差的一定是内核行为而不是夹具构造。

两类：
    1. **牌局夹具**（``play_to_discard`` / ``ming_gang_ready`` / …）：造完整 ``GameState``。
    2. **构造器**（``crafted_round``）：需要精确控制某家手牌时用它，
       **没写的座位自动填「谁也惹不起」的杂牌**（见 ``JUNK_DEAL`` 的说明）。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from typing import Iterable, Optional, Sequence

from app.core.nanfeng.action.hand import HandState, add_tile, create_hand
from app.core.nanfeng.action.options import PlayerAction
from app.core.nanfeng.counts import counts_of
from app.core.nanfeng.melds import Meld, meld_tile_count
from app.core.nanfeng.prng import create_rng, shuffle_wall
from app.core.nanfeng.rule_config import DEFAULT_RULE_CONFIG, RuleConfig
from app.core.nanfeng.state.apply import apply_action
from app.core.nanfeng.state.game_state import (
    GameState,
    StartRoundOptions,
    start_round,
)
from app.core.nanfeng.tiles import Tile, full_wall

SEATS: tuple[str, ...] = ('a', 'b', 'c', 'd')


# ---------------------------------------------------------------------------
# 开局参数
# ---------------------------------------------------------------------------

def start_base(**over) -> StartRoundOptions:
    """``start_round`` 的入参：每次调用都造**新的 rng**（rng 有状态，共享一个会得到不同牌墙）。"""
    params = dict(
        seats=SEATS,
        cfg=DEFAULT_RULE_CONFIG,
        rng=create_rng(7),
        round=1,
        epoch=1,
        dealer=0,
    )
    params.update(over)
    return StartRoundOptions(**params)


def start_state(**over) -> GameState:
    """``start_round(start_base(**over))`` 的简写。"""
    return start_round(start_base(**over))


# ---------------------------------------------------------------------------
# 牌局夹具
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CraftedHandSpec:
    """一家手牌的描述（对应前端 ``CraftedHandSpec``）。"""

    concealed: Sequence[Tile]
    melds: Sequence[Meld] = ()
    drawn_tile: Optional[Tile] = None


def crafted_round(
    hands: Sequence[Optional[CraftedHandSpec]],
    *,
    turn: int = 0,
    dealer: Optional[int] = None,
    seats: Sequence[str] = SEATS,
    round_no: int = 1,
    epoch: int = 1,
    wall_seed: int = 99,
    cfg: RuleConfig = DEFAULT_RULE_CONFIG,
) -> GameState:
    """按**指定的手牌**造一个开局状态；牌墙 = 136 张里没被用掉的那些（洗过）。

    比「随机发牌再碰运气」可控得多：需要某家手里有 3 张 11 时就直写 3 张 11。
    会校验「每种牌不超过 4 张」，写错牌立刻报错，而不是造出一个假状态混进测试。
    """
    dealer = turn if dealer is None else dealer

    used: dict[Tile, int] = {}

    def reserve(tile: Tile, n: int = 1) -> None:
        total = used.get(tile, 0) + n
        if total > 4:
            raise ValueError(f'夹具造出了非法牌局：牌码 {tile} 共 {total} 张（上限 4）')
        used[tile] = total

    hand_states: list[HandState] = []

    for seat in range(4):
        spec = hands[seat] if seat < len(hands) else None
        if spec is not None:
            for tile in spec.concealed:
                reserve(tile)
            if spec.drawn_tile is not None:
                reserve(spec.drawn_tile)
            for meld in spec.melds:
                reserve(meld.tile, meld_tile_count(meld))
            hand_states.append(HandState(
                concealed=counts_of(list(spec.concealed)),
                melds=tuple(spec.melds),
                drawn_tile=spec.drawn_tile,
                just_peng=False,
            ))
        else:
            hand_states.append(create_hand())

    # 杂牌：每手内不重复，且只用牌墙里还剩的牌
    junk = _allocate_junk(used)
    for seat in range(4):
        if (hands[seat] if seat < len(hands) else None) is not None:
            continue
        dealt = junk[seat][:14] if seat == turn else junk[seat][:13]
        hand = create_hand()
        for tile in dealt[:13]:
            reserve(tile)  # 发出去的杂牌必须从牌墙里扣掉，否则同一张牌会被算两次
            hand = add_tile(hand, tile)
        if seat == turn:
            reserve(dealt[13])
            hand = replace(hand, drawn_tile=dealt[13])
        hand_states[seat] = hand

    wall = shuffle_wall(_build_rest(used), create_rng(wall_seed))

    return GameState(
        phase='WAITING_PLAY',
        round=round_no,
        dealer=dealer,
        turn=turn,
        seats=tuple(seats),
        wall=tuple(wall),
        wall_pos=0,
        hands=tuple(hand_states),
        discards=tuple(() for _ in range(4)),
        scores=(0, 0, 0, 0),
        round_gang_score=(0, 0, 0, 0),
        epoch=epoch,
        cfg=cfg,
    )


def _allocate_junk(reserved: dict[Tile, int]) -> list[list[Tile]]:
    """按 round-robin 发杂牌：保证每手内不重复、每种牌总数不超过 4，且**绝不含 11**。"""
    # 11 是全部夹具的「触发牌」：杂牌手里一旦有 11 就可能碰/杠/胡，夹具就不再是「零响应」了。
    pool = [tile for tile in _build_rest(reserved) if tile != 11]
    hands: list[list[Tile]] = [[], [], [], []]
    seen: list[set[Tile]] = [set(), set(), set(), set()]
    want = 14  # 每家最多 13 张杂牌 + 1 张摸到的
    guard = 0
    while pool and guard < 5000:
        guard += 1
        progressed = False
        for seat in range(4):
            if len(hands[seat]) >= want:
                continue
            index = next(
                (i for i, tile in enumerate(pool) if tile not in seen[seat]), -1)
            if index < 0:
                continue
            tile = pool.pop(index)
            hands[seat].append(tile)
            seen[seat].add(tile)
            progressed = True
        if not progressed:
            break
    return hands


def _build_rest(reserved: dict[Tile, int]) -> list[Tile]:
    """136 张里扣掉 ``reserved`` 之后剩下的牌（多重集）。"""
    left = dict(reserved)
    rest: list[Tile] = []
    for tile in full_wall():
        n = left.get(tile, 0)
        if n > 0:
            left[tile] = n - 1
        else:
            rest.append(tile)
    return rest


def play_to_discard(turn: int = 0) -> GameState:
    """一个「零响应」的杂牌局：座位 ``turn`` 手里 13 张杂牌 + 摸到 11。"""
    return crafted_round(
        hands=[CraftedHandSpec(concealed=[11, *junk_tail(turn, 12)], drawn_tile=11)],
        turn=turn,
        dealer=turn,
    )


def with_wall_almost_empty(state: GameState) -> GameState:
    """牌墙抽干（剩下的牌当作已经被打掉，塞进座位 0 的牌河）。

    不能只把 ``wall_pos`` 推到末尾 —— 那样那些牌就凭空消失了，守恒会先报错，
    荒庄这条路径反而测不到。
    """
    leftover = state.wall[state.wall_pos:]
    discards = tuple(
        pile + tuple(leftover) if seat == 0 else pile
        for seat, pile in enumerate(state.discards))
    return replace(state, wall=state.wall[:state.wall_pos], discards=discards)


def corrupt_state() -> GameState:
    """故意造一个**只破坏牌张守恒**的状态：从牌墙里抽走一张（谁也没拿到）。

    为什么是「抽走」而不是「多塞一张」：合法状态里每个牌码恰好 4 张，多塞一张必然同时触发
    「不得超过 4 张」，而那条检查排在守恒之前 —— 断言的报错就不确定了。
    """
    state = play_to_discard(0)
    if not state.wall:
        raise ValueError('夹具：牌墙为空，没法抽走一张来破坏守恒')
    return replace(state, wall=state.wall[1:])


def an_gang_ready(seat: int = 1, tile: Tile = 11) -> GameState:
    """轮到 ``seat``，手里 4 张 ``tile`` → 可以暗杠。"""
    junk = junk_hand(seat)
    return crafted_round(
        hands=seat_hands(seat, CraftedHandSpec(
            concealed=[tile, tile, tile, tile, *junk[:9]], drawn_tile=junk[9])),
        turn=seat,
    )


def ming_gang_ready(tile: Tile = 11, gang_seat: int = 1,
                    discard_seat: int = 0) -> GameState:
    """座位 ``discard_seat`` 打出 ``tile``（第 4 张），``gang_seat`` 手里 3 张 → 明杠窗口。"""
    state = crafted_round(
        hands=seat_hands(
            discard_seat,
            CraftedHandSpec(concealed=junk_tail(discard_seat, 13), drawn_tile=tile),
            {gang_seat: CraftedHandSpec(
                concealed=[tile, tile, tile, *junk_tail(gang_seat, 10)])},
        ),
        turn=discard_seat,
    )
    return apply_action(
        state, PlayerAction('DISCARD', discard_seat, tile, 1), state.cfg, 1).state


def bu_gang_ready(seat: int = 1, tile: Tile = 11,
                  robber_seat: Optional[int] = 2) -> GameState:
    """轮到 ``seat``：碰过 ``tile`` + 刚摸到第 4 张 → 可以补杠。

    ``robber_seat`` 非空时，那家的手牌**正好能在 ``tile`` 上抢杠胡**（手里一张 ``tile`` 都没有，
    靠 ``11-12-13`` 凑）；为 ``None`` 时四家都是杂牌，抢杠窗口无人可胡。
    """
    meld = Meld(kind='PENG', tile=tile, from_seat=2)
    extra = {} if robber_seat is None else {
        robber_seat: CraftedHandSpec(concealed=ron_winner_hand(0))}
    return crafted_round(
        hands=seat_hands(
            seat,
            CraftedHandSpec(
                concealed=junk_tail(seat, 10), melds=[meld], drawn_tile=tile),
            extra,
        ),
        turn=seat,
    )


def ron_ready(tile: Tile = 11, winner_seats: Iterable[int] = (1,),
              discard_seat: int = 0) -> GameState:
    """座位 ``discard_seat`` 打出 ``tile``，``winner_seats`` 里的每一家都能在它上面胡 → 点炮窗口。"""
    extra: dict[int, CraftedHandSpec] = {}
    for index, seat in enumerate(winner_seats):
        extra[seat] = CraftedHandSpec(concealed=ron_winner_hand(index))
    state = crafted_round(
        hands=seat_hands(
            discard_seat,
            CraftedHandSpec(concealed=junk_tail(discard_seat, 13), drawn_tile=tile),
            extra,
        ),
        turn=discard_seat,
    )
    return apply_action(
        state, PlayerAction('DISCARD', discard_seat, tile, 1), state.cfg, 1).state


def zimo_ready(seat: int = 1) -> GameState:
    """13 张，自摸 11 即胡（``11,11`` 将 + ``11-12-13`` + 三组刻子）。"""
    return crafted_round(
        hands=seat_hands(seat, CraftedHandSpec(
            concealed=[11, 11, 12, 13, 21, 22, 23, 31, 31, 31, 41, 41, 41],
            drawn_tile=11)),
        turn=seat,
    )


def seat_hands(primary_seat: int, primary: CraftedHandSpec,
               extra: Optional[dict[int, CraftedHandSpec]] = None
               ) -> list[Optional[CraftedHandSpec]]:
    """造「四家」数组，只覆盖指定座位，其余为 ``None``（自动杂牌）。"""
    out: list[Optional[CraftedHandSpec]] = [None, None, None, None]
    out[primary_seat] = primary
    for seat, spec in (extra or {}).items():
        out[seat] = spec
    return out


def junk_tail(seat: int, n: int) -> list[Tile]:
    """取该座位杂牌的前 ``n`` 张（``junk_hand`` 的简写）。"""
    return junk_hand(seat)[:n]


#: 第 ``i`` 手杂牌：跨花色、同花色内间隔 >=3、互不重复，且**不含 11**。
#:
#: - 每张牌在一手里只出现一次 → 没有刻子；间隔 >=3 → 没有顺子 → **拆不出任何结构**；
#: - 跨花色 → **不是假胡**；
#: - 并进一张 11 后要么万子里 11 与 12 相邻、要么数牌凑到 10 张（每花色最多 3 张，不可能）
#:   → **也不可能被 11 点炮胡**。
#:
#: 所以「其余座位用杂牌」就等价于「这些家不会响应任何出牌」，夹具因此完全确定。
_JUNK_CODES: tuple[Tile, ...] = tuple(
    [base + rank for base in (10, 20, 30) for rank in (2, 5, 8)]
    + [41, 42, 51, 52, 43, 53, 44]
)


def _junk_deal() -> tuple[tuple[Tile, ...], ...]:
    hands: list[list[Tile]] = [[], [], [], []]
    cursor = 0
    for code in _JUNK_CODES:
        for _copy in range(4):
            hands[cursor % 4].append(code)
            cursor += 1
    return tuple(tuple(hand) for hand in hands)


_JUNK_DEAL = _junk_deal()


def junk_hand(index: int) -> list[Tile]:
    return list(_JUNK_DEAL[index % 4])[:13]


#: 两套**互不相交**的听牌手，专给「点炮 / 抢杠胡」用：都不含 11，并进一张 11 即胡。
#: 用互不相交的牌码，所以可以让两家同时胡同一张 11（一炮多响用例）。
RON_WINNER_HANDS: tuple[tuple[Tile, ...], ...] = (
    (12, 13, 21, 22, 23, 31, 31, 31, 41, 41, 41, 19, 19),
    (12, 13, 24, 25, 26, 32, 32, 32, 51, 51, 51, 29, 29),
)


def ron_winner_hand(variant: int = 0) -> list[Tile]:
    return list(RON_WINNER_HANDS[variant % len(RON_WINNER_HANDS)])


def clone(state: GameState) -> GameState:
    """深拷贝一份状态，方便「改坏它再看断言」（对应 ``structuredClone``）。"""
    return copy.deepcopy(state)
