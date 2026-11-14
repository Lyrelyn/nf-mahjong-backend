"""规则文档 ↔ 代码的口径一致性对拍 —— 对应前端 ``tests/core/rules-conformance.test.ts``。

这个文件存在的理由只有一条：``docs/rules-confirmed.md`` 是**唯一**的规则权威，而「文档说一致」
这句话会腐烂 —— 改一个 ``rule_config`` 里的数字，文档不会自己跟着改。所以把可机械核对的那几条
**锁在这里**：谁改了实现，谁就得同时改这条用例、并且去看一眼文档。

这里只做**文档 ↔ 代码的对照**：数值、开关、以及「某个状态根本不存在」这类结构事实；
行为怎么算的用例在 ``tests/nanfeng/`` 的其它文件与主仓库的同名测试里。
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import asdict, replace

import pytest

from app.core.nanfeng.counts import counts_of
from app.core.nanfeng.hu.gui_yi import count_gui_yi
from app.core.nanfeng.hu.shi_san_lan import requires_self_draw
from app.core.nanfeng.melds import Meld, meld_tile_count
from app.core.nanfeng.rule_config import (
    DEFAULT_RULE_CONFIG,
    validate_rule_config,
)
from app.core.nanfeng.score.score_table import (
    QI_XING_SCORE,
    STRUCTURE_SCORE,
    score_of_tags,
)
from app.core.nanfeng.score.settle import settle_round
from app.core.nanfeng.state.game_state import (
    RoundOutcome,
    RoundWinner,
    next_round_seating,
    start_round,
)
from app.core.nanfeng.tiles import full_wall
from tests.nanfeng.fixtures import start_base

CFG = DEFAULT_RULE_CONFIG


def peng(tile: int) -> Meld:
    return Meld(kind='PENG', tile=tile, from_seat=0)


def gang(kind: str, tile: int) -> Meld:
    return Meld(kind=kind, tile=tile, from_seat=None)


# ---------------------------------------------------------------------------
# R-01 牌张：136 张、有字牌、无花牌
# ---------------------------------------------------------------------------

class TestR01TileSet:
    @pytest.mark.parametrize('tile', [41, 42, 43, 44, 51, 52, 53])
    def test_words_exist_four_copies_each(self, tile):
        """TS：字牌 41..44（东南西北）+ 51..53（中发白）各 4 张"""
        assert full_wall().count(tile) == 4, f'牌码 {tile}'

    def test_no_flower_tiles_and_136_total(self):
        """TS：整副 136 张、34 种，字牌（东南西北中发白）在，花牌不在"""
        wall = full_wall()
        assert len(wall) == 136
        assert len(set(wall)) == 34
        # 花牌（规则文档里编到 61+）一张都不该在牌墙里
        assert not any(tile >= 61 for tile in wall)

    def test_config_says_full_136(self):
        """TS：配置里也写着 FULL_136（不是「代码恰好凑够了 136」）"""
        assert CFG.tile_set == 'FULL_136'


# ---------------------------------------------------------------------------
# R-02 坐庄与 5 人轮换：四种结果各自谁坐庄、谁下场
# ---------------------------------------------------------------------------

class TestR02Seating:
    def _state(self):
        return replace(start_round(start_base()), dealer=1)

    def test_dealer_hu_keeps_dealership_and_opposite_sits_out(self):
        """TS：庄家胡（含自摸）→ 庄家连庄，**对家**下场"""
        outcome = RoundOutcome(
            kind='HU', winners=(RoundWinner(seat=1, zimo=True),), loser_seat=None)
        assert next_round_seating(self._state(), outcome) == {
            'dealer': 1, 'sitting_out': 3}

    def test_ron_moves_dealership_to_the_winner_and_loser_sits_out(self):
        """TS：别人**点炮**胡 → 胡牌者坐庄，**放炮者**下场"""
        outcome = RoundOutcome(
            kind='HU', winners=(RoundWinner(seat=2, zimo=False),), loser_seat=0)
        assert next_round_seating(self._state(), outcome) == {
            'dealer': 2, 'sitting_out': 0}

    def test_non_dealer_zimo_moves_dealership_and_opposite_sits_out(self):
        """TS：别人**自摸**胡 → 胡牌者坐庄，自摸者的**对家**下场（这一条是原设计漏的，R-02 补的）"""
        outcome = RoundOutcome(
            kind='HU', winners=(RoundWinner(seat=2, zimo=True),), loser_seat=None)
        assert next_round_seating(self._state(), outcome) == {
            'dealer': 2, 'sitting_out': 0}

    def test_huang_zhuang_gives_dealership_to_opposite_and_dealer_sits_out(self):
        """TS：荒庄 → 庄家的**对家**坐庄，**庄家**下场"""
        assert next_round_seating(self._state(), RoundOutcome(kind='HUANG_ZHUANG')) == {
            'dealer': 3, 'sitting_out': 1}

    def test_dealer_pays_each_one_no_doubling(self):
        """TS：庄家付款**不加倍**：荒庄是庄家赔每家 1 分（共 3 分），不是 2 分"""
        assert CFG.score.huang_zhuang.dealer_pays_each == 1
        settled = settle_round(
            replace(start_round(start_base()), dealer=0),
            RoundOutcome(kind='HUANG_ZHUANG'),
            CFG,
        )
        assert list(settled.deltas) == [-3, 1, 1, 1]


# ---------------------------------------------------------------------------
# R-03 假胡算胡，自摸与点炮都能胡
# ---------------------------------------------------------------------------

class TestR03JiaHu:
    def test_jia_hu_enabled_and_ron_path_open(self):
        """TS：开关是开着的，而且**点炮路径**没有关掉（allowRon）"""
        assert CFG.hu.jia_hu.enabled is True
        assert CFG.hu.jia_hu.allow_ron is True

    def test_all_four_hand_type_switches_are_on(self):
        """TS：四个牌型开关都是开的（假胡/七对/十三烂/字牌顺）—— 关掉任何一个都等于改了规则"""
        assert CFG.hu.qi_dui is True
        assert CFG.hu.shi_san_lan is True
        assert CFG.hu.word_straight is True


# ---------------------------------------------------------------------------
# R-04 + R-07 归一：4 张全归你就算，**杠也算**，补杠之后不归零
# ---------------------------------------------------------------------------

class TestR04R07GuiYi:
    def test_peng_three_plus_concealed_one_counts(self):
        """TS：碰 3 + 暗 1 = 四归一（这是最容易漏的一条：副露里的牌也要数）"""
        assert count_gui_yi(counts_of([11]), [peng(11)]) == 1

    @pytest.mark.parametrize('kind', ['MING_GANG', 'AN_GANG', 'BU_GANG'])
    def test_all_gang_kinds_count_as_four_tiles(self, kind):
        """TS：三种杠都按 4 张折算（明杠/暗杠/补杠），而不是 3 张"""
        assert meld_tile_count(gang(kind, 21)) == 4
        assert count_gui_yi(counts_of([]), [gang(kind, 21)]) == 1

    def test_peng_upgraded_to_bu_gang_keeps_the_gui_yi(self):
        """TS：碰 3 张再补成杠：归一**还在**（「做了个合法动作反而掉分」这条已经改了）"""
        # 补杠前：碰在副露里、手里没有第 4 张 → 3 张，不算归一
        assert count_gui_yi(counts_of([]), [peng(31)]) == 0
        # 补杠后：副露变成 4 张 → 归一
        assert count_gui_yi(counts_of([]), [gang('BU_GANG', 31)]) == 1


# ---------------------------------------------------------------------------
# R-05 十三烂：合法性与炮数是**两件事**
# ---------------------------------------------------------------------------

def lan(words: int) -> list[int]:
    """十三烂的手牌：数牌按 1/4/7 取，字牌取前 n 种。"""
    number_tiles: list[int] = []
    for suit in (1, 2, 3):
        for rank in (1, 4, 7):
            if len(number_tiles) < 14 - words:
                number_tiles.append(suit * 10 + rank)
    word_pool = [41, 42, 43, 44, 51, 52, 53]
    return number_tiles + word_pool[:words]


class TestR05ShiSanLan:
    @pytest.mark.parametrize('words', [5, 6])
    def test_five_or_six_words_must_self_draw(self, words):
        """TS：13 张时字牌 5 或 6 种 → **只能自摸**（点炮路径必须直接拒胡）"""
        assert requires_self_draw(counts_of(lan(words))) is True

    def test_seven_stars_can_ron(self):
        """TS：七星（7 种字牌）→ 点炮也能胡"""
        assert requires_self_draw(counts_of(lan(7))) is False

    def test_qi_xing_scores_four_zimo_two_ron(self):
        """TS：**炮数取 QI_XING_SCORE（自摸 4 / 点炮 2）** —— 不是文档汇总表 R-05 行里那个「3 炮」"""
        # 来源：同一份文档的 R-11（第二轮计分）与 M6-5 改动行：「七星 5/3 → 4/2」。
        # R-05 那一行的「降到 3 炮」是**改动之前的**数值，没能跟上。
        assert QI_XING_SCORE == {'zimo': 4, 'ron': 2}
        assert score_of_tags({'QI_XING_SHI_SAN_LAN'}, CFG, zimo=True).score == 4
        assert score_of_tags({'QI_XING_SHI_SAN_LAN'}, CFG, zimo=False).score == 2

    def test_plain_shi_san_lan_zimo_is_three_fan(self):
        """TS：普通十三烂（5/6 种字牌）自摸是 3 炮，与 R-05 的「5 张 3 炮」一致"""
        assert score_of_tags({'SHI_SAN_LAN'}, CFG, zimo=True).score == 3


# ---------------------------------------------------------------------------
# R-06 漏碰 / 漏胡：**这两条限制不存在**，所以状态里也不该有它们的影子
# ---------------------------------------------------------------------------

class TestR06NoMissedClaimBookkeeping:
    @pytest.mark.parametrize(
        'forbidden', ['forgot', 'forgotten', 'passed', 'missed', 'banned'])
    def test_game_state_has_no_memory_of_missed_claims(self, forbidden):
        """TS：牌局状态里没有任何「漏过什么」的账（Task 13 因此整条取消）"""
        keys = [field.name for field in dataclasses.fields(start_round(start_base()))]
        assert [key for key in keys if forbidden in key.lower()] == []

    @pytest.mark.parametrize('forbidden', ['forget', 'ban', 'missed'])
    def test_config_has_no_ban_switches(self, forbidden):
        """TS：配置里也没有「禁碰/禁胡」这类开关（加了就等于把 R-06 改了）"""
        text = json.dumps(asdict(CFG), ensure_ascii=False).lower()
        assert forbidden not in text


# ---------------------------------------------------------------------------
# R-08 荒庄：庄家赔每家 1 分，不看听牌
# ---------------------------------------------------------------------------

class TestR08HuangZhuang:
    def test_deltas_do_not_depend_on_waiting_tenpai(self):
        """TS：deltas 与牌型无关（没有「听牌」这个输入）"""
        settled = settle_round(
            replace(start_round(start_base()), dealer=2),
            RoundOutcome(kind='HUANG_ZHUANG'),
            CFG,
        )
        assert list(settled.deltas) == [1, 1, -3, 1]
        assert settled.detail == ()  # 荒庄没有番型明细


# ---------------------------------------------------------------------------
# R-11 第二轮计分：封顶 8、只有杠能突破
# ---------------------------------------------------------------------------

class TestR11ScoringCap:
    def test_cap_is_eight_and_only_settlement_applies_it(self):
        """TS：封顶是 8，而且**只有结算那一层**取 min（计分表给的是封顶前的原始分）"""
        assert CFG.score.cap == 8
        # 清一色真在表里是 10，落到 8 是 cap 的功劳 —— 所以计分表不能自己取 min
        assert score_of_tags({'PING_HU', 'QING_YI_SE_ZHEN'}, CFG, zimo=False).score > CFG.score.cap

    def test_peng_peng_hu_four_and_dan_diao_eight(self):
        """TS：碰碰胡 4、碰碰胡单调 8（后者正好吃满封顶）"""
        assert STRUCTURE_SCORE['PENG_PENG_HU'] == 4
        assert STRUCTURE_SCORE['PENG_PENG_HU_DAN_DIAO'] == 8
        assert STRUCTURE_SCORE['PENG_PENG_HU_DAN_DIAO'] == CFG.score.cap

    def test_buy_code_cannot_be_enabled_in_v1(self):
        """TS：买码分 V1 不结算（R-09 / R-11 留到 V1.1），而且**配置层面不允许打开**"""
        assert CFG.buy_code_enabled is False
        # ``validate_rule_config`` 明确拒绝打开买码（它会破坏零和不变量）—— 所以「V1 不结算」
        # 不只是没人写，而是**打不开**。
        # 报错文案里用的是字段名 ``buy_code``（Python 侧 snake_case；前端是 ``buyCode``）。
        with pytest.raises(ValueError, match='buy_code'):
            validate_rule_config(replace(CFG, buy_code_enabled=True))


# ---------------------------------------------------------------------------
# R-10 口令：已经取消，只有 6 位房号
# ---------------------------------------------------------------------------

class TestR10NoPassphrase:
    def test_refuse_reason_table_has_no_passphrase_codes(self):
        """TS：拒绝原因表里没有任何跟口令有关的码（「口令错了」这种提示不该存在）

        后端**没有**对应的 ``REFUSE_REASONS`` 表：那是前端 ``net/messages`` 的传输层常量，
        本次移植的范围是规则内核（``app/core/nanfeng``），入口校验还没搬过来，
        所以这条结构事实暂时无处可查。留成 skip 而不是删掉，是为了让「没有对手」这件事可见。
        """
        pytest.skip('后端尚无 net/messages 的 REFUSE_REASONS 等价表（传输层未移植）')
