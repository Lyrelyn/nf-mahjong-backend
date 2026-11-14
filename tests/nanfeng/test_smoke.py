"""工具链冒烟 —— 对应前端 ``tests/core/smoke.test.ts``。

TS 只验证 vitest 自身能跑起来；pytest 侧同样只验证「测试框架可执行」。
"""


def test_runs_pytest() -> None:
    """TS: runs vitest。"""
    assert 1 + 1 == 2
