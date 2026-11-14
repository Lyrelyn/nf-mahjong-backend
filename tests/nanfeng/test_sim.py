"""无头随机对局 fuzz 对拍 —— 对应前端 ``tests/core/sim.test.ts``。

这里是「规则引擎能不能自己跑起来」的总闸：``apply_action`` 每次变换前后都断言全局不变量，
所以「跑不崩」就等于「不变量恒成立」。

前端的驱动器 ``sim/randomAgent.ts`` 不是规则内核（在 ``assets/scripts/core`` 之外），后端还没有
对应模块，所以这里把它**逐行移植**进测试文件：策略、每一次 ``rng.next()`` 的调用顺序、digest 的
拼法都保持一致。随机源是 ``create_rng(seed)``（xorshift128，与 TS 逐位一致），因此同一个 seed
在两边会走出同一局 —— fuzz 挂了把 seed 抄进用例就能复现。
"""

from __future__ import annotations

import re
from typing import Optional

from app.core.nanfeng.action.options import PlayerAction
from app.core.nanfeng.action.peng_gang import can_an_gang, can_bu_gang, can_hu_self
from app.core.nanfeng.counts import Counts
from app.core.nanfeng.prng import Rng, create_rng
from app.core.nanfeng.rule_config import DEFAULT_RULE_CONFIG, RuleConfig
from app.core.nanfeng.state.apply import apply_action
from app.core.nanfeng.state.game_state import (
    GameState,
    RoundOutcome,
    StartRoundOptions,
    next_round_seating,
    start_round,
)
from tests.nanfeng.fixtures import CraftedHandSpec, crafted_round

CFG = DEFAULT_RULE_CONFIG

SEATS: tuple[str, ...] = ('a', 'b', 'c', 'd')
HOST_SEAT = 0
#: 一局最多走多少步；超了就是死循环，宁可报错也不要挂住。
MAX_STEPS_PER_ROUND = 3000
#: 时间推进的步长（毫秒）。引擎不看时钟，``now`` 只用来算窗口截止时间。
STEP_MS = 100


# ---------------------------------------------------------------------------
# 随机驱动器（逐行移植自 sim/randomAgent.ts）
# ---------------------------------------------------------------------------

def is_isolated(concealed: Counts, tile: int) -> bool:
    """这张牌是不是「孤张」：手里只 1 张，而且同花色左右两格内都没有邻牌。

    字牌只看张数 —— 单张字牌既不能成顺也不能成刻，一律算孤张。
    """
    if concealed[tile] > 1:
        return False
    if tile >= 41:
        return True
    base = (tile // 10) * 10
    rank = tile % 10
    for delta in (-2, -1, 1, 2):
        neighbour = rank + delta
        if neighbour < 1 or neighbour > 9:
            continue
        if concealed[base + neighbour] > 0:
            return False
    return True


def choose_action(state: GameState, cfg: RuleConfig, rng: Rng,
                  now: float) -> Optional[PlayerAction]:
    """在给定的状态上挑一个合法动作；没有合法动作时返回 ``None``。"""
    if state.phase == 'CLAIM_WINDOW':
        claim = state.claim
        if claim is None:
            return None
        seat = claim.pending[int(rng.next() * len(claim.pending))]
        options = claim.options.get(seat, [])
        if not options:
            return None
        pick = options[int(rng.next() * len(options))]
        return PlayerAction(
            type=pick.type,
            seat=seat,
            tile=None if pick.type == 'PASS' else claim.trigger_tile,
            req_id=now,
        )

    if state.phase != 'WAITING_PLAY':
        return None

    seat = state.turn
    hand = state.hands[seat]
    candidates: list[PlayerAction] = []

    if can_hu_self(hand, cfg):
        candidates.append(PlayerAction('HU', seat, None, now))

    probed = [tile for tile in range(len(hand.concealed)) if hand.concealed[tile] > 0]
    if hand.drawn_tile is not None:
        probed.append(hand.drawn_tile)
    for tile in probed:
        if can_an_gang(hand, tile, cfg, True):
            candidates.append(PlayerAction('AN_GANG', seat, tile, now))
        if can_bu_gang(hand, tile, cfg, True):
            candidates.append(PlayerAction('BU_GANG', seat, tile, now))

    # 出牌：手里任意一张都合法，但**优先打孤张**。
    #
    # 为什么要有这个偏好：纯随机出牌几乎不可能成牌，实测胡 1% / 荒庄 99% —— 那样 fuzz 只压得实
    # 「荒庄」一条路，判胡 → 计分 → 结算整条路径几乎没被覆盖。优先打孤张会保留对子与搭子，
    # 胡牌率抬到两位数百分比，Phase 4 才算真的「实用检查点」。
    held: list[int] = []
    for tile in range(len(hand.concealed)):
        for _copy in range(hand.concealed[tile]):
            held.append(tile)
    if hand.drawn_tile is not None:
        held.append(hand.drawn_tile)

    isolated = [tile for tile in held if is_isolated(hand.concealed, tile)]
    pool = isolated if isolated else held
    if pool:
        candidates.append(PlayerAction(
            'DISCARD', seat, pool[int(rng.next() * len(pool))], now))

    if not candidates:
        return None
    return candidates[int(rng.next() * len(candidates))]


def play_round(initial: GameState, cfg: RuleConfig, rng: Rng, start_at: float) -> dict:
    """跑完一局，返回终局状态与本局结局（结局用来算下一局谁坐庄）。"""
    state = initial
    now = start_at
    steps = 0

    while steps < MAX_STEPS_PER_ROUND:
        action = choose_action(state, cfg, rng, now)
        if action is None:
            raise RuntimeError(
                f'无合法动作可走：phase={state.phase}，turn={state.turn}')
        result = apply_action(state, action, cfg, now)
        state = result.state
        steps += 1
        now += STEP_MS

        ending = next(
            (event for event in result.events
             if event.type in ('HU', 'QIANG_GANG_HU', 'HUANG_ZHUANG')),
            None,
        )
        if ending is None:
            continue

        if ending.type == 'HUANG_ZHUANG':
            return {'state': state, 'outcome': RoundOutcome(kind='HUANG_ZHUANG'),
                    'steps': steps, 'now': now}
        if ending.type == 'HU':
            return {'state': state, 'outcome': RoundOutcome(
                kind='HU', winners=ending.winners, loser_seat=ending.loser_seat),
                'steps': steps, 'now': now}
        # 抢杠胡：补杠那一家是唯一付款方（Q-02）
        return {'state': state, 'outcome': RoundOutcome(
            kind='HU', winners=ending.winners, loser_seat=ending.gang_seat),
            'steps': steps, 'now': now}

    raise RuntimeError(
        f'一局步数超过 {MAX_STEPS_PER_ROUND} —— 疑似死循环：phase={state.phase}')


def simulate(seed: int, cfg: RuleConfig, max_rounds: int) -> dict:
    rng = create_rng(seed)
    dealer = HOST_SEAT  # Q-06：第一局房主坐庄
    state = start_round(StartRoundOptions(
        seats=SEATS, dealer=dealer, cfg=cfg, rng=rng, round=1, epoch=1))

    hu = 0
    huang_zhuang = 0
    steps = 0
    now = 1000
    rounds = 1

    for index in range(max_rounds):
        played = play_round(state, cfg, rng, now)
        state = played['state']
        steps += played['steps']
        now = played['now']
        rounds = index + 1
        if played['outcome'].kind == 'HUANG_ZHUANG':
            huang_zhuang += 1
        else:
            hu += 1

        if index == max_rounds - 1:
            break
        seating = next_round_seating(state, played['outcome'])
        dealer = seating['dealer']
        state = start_round(StartRoundOptions(
            seats=SEATS, dealer=dealer, cfg=cfg, rng=rng, round=rounds + 1, epoch=1))

    return {
        'hu': hu,
        'huang_zhuang': huang_zhuang,
        'rounds': rounds,
        'digest': (f'rounds={rounds} hu={hu} hz={huang_zhuang} steps={steps} '
                   f'scores={",".join(str(score) for score in state.scores)}'),
    }


def run_one_game(seed: int, cfg: RuleConfig, max_rounds: int = 3) -> dict:
    """跑一局（默认 3 圈）。同一 seed 的结果必须完全一致。"""
    result = simulate(seed, cfg, max_rounds)
    return {'rounds': result['rounds'], 'ok': True, 'digest': result['digest']}


def run_many_games(n: int, cfg: RuleConfig, max_rounds: int = 3) -> dict:
    """跑 ``n`` 局，统计失败局数与**第一个失败**（带 seed，方便直接复现）。

    不抛异常 —— fuzz 的价值在于「跑完再报告」，而不是在第一个失败上停住。
    """
    failed = 0
    first_failure = None
    for seed in range(1, n + 1):
        try:
            simulate(seed, cfg, max_rounds)
        except Exception as error:  # noqa: BLE001 —— 故意兜住一切，好把 seed 报出来
            failed += 1
            if first_failure is None:
                first_failure = {'seed': seed, 'error': str(error)}
    return {'games': n, 'failed': failed, 'first_failure': first_failure}


def run_stats(n: int, cfg: RuleConfig, max_rounds: int = 1) -> dict:
    """统计覆盖率：胡了多少次、荒庄多少次 —— 用来确认 fuzz 不是在空转。"""
    hu = 0
    huang_zhuang = 0
    rounds = 0
    for seed in range(1, n + 1):
        result = simulate(seed, cfg, max_rounds)
        hu += result['hu']
        huang_zhuang += result['huang_zhuang']
        rounds += result['rounds']
    return {'hu': hu, 'huang_zhuang': huang_zhuang, 'rounds': rounds}


# ---------------------------------------------------------------------------
# 无头随机对局
# ---------------------------------------------------------------------------

class TestHeadlessRandomGames:
    def test_one_hundred_and_twenty_games_three_rounds_zero_failures(self):
        """TS：跑 120 局（每局 3 圈）零失败"""
        result = run_many_games(120, CFG, 3)
        assert result['first_failure'] is None
        assert result['failed'] == 0
        assert result['games'] == 120

    def test_same_seed_replays_identically(self):
        """TS：同一 seed 的两局完全一致（可重放）"""
        a = run_one_game(7, CFG)
        b = run_one_game(7, CFG)
        assert a == b
        # 摘要里含分数与步数，所以这条断言真的在比「整局走向」，不只是比局数
        assert re.search(r'rounds=3 .*scores=', a['digest'])

    def test_different_seeds_usually_diverge(self):
        """TS：不同 seed 通常走出不同的局（随机性没有被压平）"""
        digests = {run_one_game(seed, CFG)['digest'] for seed in (1, 2, 3, 4, 5)}
        assert len(digests) > 1

    def test_hu_and_huang_zhuang_both_get_substantial_coverage(self):
        """TS：胡与荒庄都达到实质覆盖（加了孤张偏好后胡牌率应是两位数百分比）"""
        stats = run_stats(200, CFG, 1)
        assert stats['rounds'] == 200
        # 纯随机乱打时这里只有 ~1%（实测胡 1 / 荒庄 199）——那样「判胡 → 计分 → 结算」整条路
        # 几乎没被 fuzz 压到。加了「优先打孤张」之后实测约 30%。阈值取 40（20%）留余量。
        assert stats['hu'] > 40
        assert stats['huang_zhuang'] > 40
        assert stats['hu'] + stats['huang_zhuang'] == 200

    def test_every_round_actually_reaches_settlement(self):
        """TS：每局都真的打到了结算（不会因为步数超限而被截断）"""
        # 步数超限会抛异常 → runManyGames 会把它计成失败；这条用例把「上限没被踩到」钉住
        result = run_many_games(30, CFG, 3)
        assert result['first_failure'] is None


# ---------------------------------------------------------------------------
# 出牌偏好孤张
# ---------------------------------------------------------------------------

def isolated_ready() -> GameState:
    """座位 1：四组面子 + 一张孤张 19，外加摸到 25（25 与手里的 23 是搭子，不算孤张）。"""
    return crafted_round(
        hands=[
            None,
            CraftedHandSpec(
                concealed=[11, 12, 13, 21, 22, 23, 31, 31, 31, 41, 41, 41, 19],
                drawn_tile=25,
            ),
            None,
            None,
        ],
        turn=1,
    )


class TestIsolatedTilePreference:
    def test_discards_the_only_isolated_tile_across_thirty_seeds(self):
        """TS：手里只有一张孤张时，总打它（跨 30 个种子都成立）"""
        state = isolated_ready()
        picked: set[int] = set()
        for seed in range(1, 31):
            action = choose_action(state, CFG, create_rng(seed), 1000)
            assert action is not None
            assert action.type == 'DISCARD'
            picked.add(action.tile)
        assert sorted(picked) == [19]

    def test_picks_randomly_among_several_isolated_tiles(self):
        """TS：孤张不止一张时在其中随机挑（不是写死第一张）"""
        # 19 与 29 都是孤张（万子只剩 19；条子只有 21,22,23，29 距 23 有 6 格）
        state = crafted_round(
            hands=[
                None,
                CraftedHandSpec(
                    concealed=[11, 12, 13, 21, 22, 23, 31, 31, 31, 41, 41, 41, 29],
                    drawn_tile=19,
                ),
                None,
                None,
            ],
            turn=1,
        )
        picked: set[int] = set()
        for seed in range(1, 41):
            action = choose_action(state, CFG, create_rng(seed), 1000)
            assert action is not None
            picked.add(action.tile)
        assert sorted(picked) == [19, 29]

    def test_falls_back_to_any_tile_when_no_tile_is_isolated(self):
        """TS：没有孤张时退回「手里任意一张」（不会无牌可打）"""
        state = crafted_round(
            hands=[
                None,
                CraftedHandSpec(
                    concealed=[11, 12, 13, 21, 22, 23, 31, 31, 31, 41, 41, 41, 14],
                    drawn_tile=15,
                ),
                None,
                None,
            ],
            turn=1,
        )
        action = choose_action(state, CFG, create_rng(3), 1000)
        assert action is not None
        assert action.type == 'DISCARD'
