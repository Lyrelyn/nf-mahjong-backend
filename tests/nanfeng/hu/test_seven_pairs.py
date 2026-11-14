"""``tests/core/hu/sevenPairs.test.ts`` 的 pytest 等价用例（七对 / is_seven_pairs）。"""

from __future__ import annotations

import pytest

from app.core.nanfeng.counts import counts_of
from app.core.nanfeng.hu.seven_pairs import is_seven_pairs


@pytest.mark.parametrize(
    ('tiles', 'expected'),
    [
        # TS: 7 个对子成立，且不要求 258 将
        ([11, 11, 12, 12, 13, 13, 21, 21, 22, 22, 41, 41, 53, 53], True),
        # TS: 4 张同牌算 2 对
        ([11, 11, 11, 11, 12, 12, 13, 13, 21, 21, 22, 22, 41, 41], True),
        # TS: 3 组四张 + 1 对（7 对）成立
        ([11, 11, 11, 11, 21, 21, 21, 21, 31, 31, 31, 31, 41, 41], True),
        # TS: 6 对 + 两张单张（14 张）不成立
        ([11, 11, 12, 12, 13, 13, 21, 21, 22, 22, 41, 41, 43, 44], False),
        # TS: 13 张不成立（张数不足）
        ([11, 11, 12, 12, 13, 13, 21, 21, 22, 22, 41, 41, 43], False),
        # TS: 15 张不成立（张数过多）
        ([11, 11, 12, 12, 13, 13, 21, 21, 22, 22, 41, 41, 43, 43, 44], False),
    ],
    ids=[
        'seven-pairs-no-258',
        'quad-counts-as-two-pairs',
        'three-quads-plus-pair',
        'six-pairs-plus-two-singles',
        'thirteen-tiles',
        'fifteen-tiles',
    ],
)
def test_is_seven_pairs(tiles: list[int], expected: bool) -> None:
    assert is_seven_pairs(counts_of(tiles)) is expected
