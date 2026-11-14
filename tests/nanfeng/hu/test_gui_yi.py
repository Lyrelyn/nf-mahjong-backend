"""``tests/core/hu/guiYi.test.ts`` 的 pytest 等价用例。

覆盖三个 describe：
    - 副露折算：组数与张数（melds.meld_set_count / melds.meld_tile_count）
    - 归一计数（R-07：该牌码的 4 张全归你就行，杠也算）
    - 归一标签映射（gui_yi.gui_yi_tag）
"""

from __future__ import annotations

import pytest

from app.core.nanfeng.counts import counts_of
from app.core.nanfeng.hu.gui_yi import count_gui_yi, gui_yi_tag
from app.core.nanfeng.melds import Meld, meld_set_count, meld_tile_count


# --------------------------------------------------------------------------- #
# describe('副露折算：组数与张数')
# --------------------------------------------------------------------------- #


def test_every_gang_counts_as_one_set() -> None:
    """TS: 面子需求：杠算刻，三种杠都占 1 组。"""
    assert meld_set_count(Meld(kind='AN_GANG', tile=11, from_seat=None)) == 1
    assert meld_set_count(Meld(kind='BU_GANG', tile=11, from_seat=None)) == 1
    assert meld_set_count(Meld(kind='PENG', tile=11, from_seat=2)) == 1


@pytest.mark.parametrize(
    ('meld', 'expected'),
    [
        (Meld(kind='PENG', tile=11, from_seat=2), 3),
        (Meld(kind='MING_GANG', tile=11, from_seat=2), 4),
        (Meld(kind='AN_GANG', tile=11, from_seat=None), 4),
        (Meld(kind='BU_GANG', tile=11, from_seat=None), 4),
    ],
    ids=['PENG-3', 'MING_GANG-4', 'AN_GANG-4', 'BU_GANG-4'],
)
def test_meld_tile_count(meld: Meld, expected: int) -> None:
    """TS: 张数折算：碰 3 张，三种杠各 4 张（R-07：归一与张数同口径）。"""
    assert meld_tile_count(meld) == expected


# --------------------------------------------------------------------------- #
# describe('归一计数（R-07：该牌码的 4 张全归你就算，杠也算）')
# --------------------------------------------------------------------------- #


def test_counts_tiles_whose_total_with_melds_is_four() -> None:
    """TS: 统计"暗牌 + 全部副露"总数为 4 的牌码个数。

    11：碰 3 + 暗 1 = 4；22：暗 4 = 4 → 两个归一。
    """
    melds = [Meld(kind='PENG', tile=11, from_seat=1)]
    assert count_gui_yi(counts_of([11, 22, 22, 22, 22]), melds) == 2


def test_all_three_gang_kinds_count_as_gui_yi() -> None:
    """TS: 明杠、暗杠、补杠的 4 张都算归一（R-07 前明杠不算，现在算）。"""
    assert count_gui_yi(counts_of([]), [Meld(kind='MING_GANG', tile=11, from_seat=2)]) == 1
    assert count_gui_yi(counts_of([]), [Meld(kind='AN_GANG', tile=11, from_seat=None)]) == 1
    assert count_gui_yi(counts_of([]), [Meld(kind='BU_GANG', tile=11, from_seat=None)]) == 1


def test_gui_yi_survives_bu_gang_after_a_peng() -> None:
    """TS: 碰过的那张牌补杠后归一仍在（R-04：做了个合法动作不该掉分）。

    补杠前后是同一批 4 张牌：碰 3 张 + 手里第 4 张 → 补杠后这 4 张全在副露里。
    """
    assert count_gui_yi(counts_of([11]), [Meld(kind='PENG', tile=11, from_seat=1)]) == 1
    assert count_gui_yi(counts_of([]), [Meld(kind='BU_GANG', tile=11, from_seat=None)]) == 1


def test_gui_yi_survives_an_gang_of_four_concealed_tiles() -> None:
    """TS: 手里暗持 4 张去暗杠后归一仍在（R-04 的同一条原则）。"""
    assert count_gui_yi(counts_of([11, 11, 11, 11]), []) == 1
    assert count_gui_yi(counts_of([]), [Meld(kind='AN_GANG', tile=11, from_seat=None)]) == 1


def test_three_tiles_is_not_gui_yi() -> None:
    """TS: 只有 3 张不算归一（碰走 3 张、手里没有第 4 张 → 不算）。"""
    assert count_gui_yi(counts_of([11, 11, 11]), []) == 0
    assert count_gui_yi(counts_of([]), [Meld(kind='PENG', tile=11, from_seat=2)]) == 0


def test_two_tiles_with_four_each_gives_two_gui_yi() -> None:
    """TS: 两种牌各 4 张 → 2 个归一。"""
    assert count_gui_yi(counts_of([11, 11, 11, 11, 41, 41, 41, 41]), []) == 2


# --------------------------------------------------------------------------- #
# describe('归一标签映射')
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ('quad_count', 'expected'),
    [
        (0, None),
        (1, 'SI_GUI_YI'),
        (2, 'BA_GUI_YI'),
        (3, 'SHI_ER_GUI_YI'),
        (4, None),
    ],
    ids=['0-none', '1-si', '2-ba', '3-shi-er', '4-none'],
)
def test_gui_yi_tag(quad_count: int, expected: str | None) -> None:
    """TS: 一个个数对应一个标签，0 与 4 个都不给标签。"""
    assert gui_yi_tag(quad_count) == expected
