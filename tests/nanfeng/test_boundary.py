"""引擎禁区守护 —— 对应前端 ``tests/core/boundary.test.ts``（spec §3.3 的硬性规则）。

前端用例扫描 ``assets/scripts/core`` 与 ``assets/scripts/game`` 两个**纯逻辑**目录：
不得依赖 Cocos、IO 或任何不确定来源，时间与随机数一律由参数注入。
Python 移植版的对应纯逻辑层是 ``app/core/nanfeng``（南丰规则内核），本用例扫描它。

5 条禁区到 Python 的映射（与 TS 的 ``FORBIDDEN`` 逐条对应）：
    Cocos ``from 'cc'``   → ``import cc`` / ``from cc import ...``
    ``Math.random(``      → ``random.random(`` / ``random.randint(`` 等未注入随机源
    ``Date.now(``         → ``time.time(`` / ``datetime.now(``
    ``performance.now(``  → ``time.perf_counter(``
    ``fetch(``            → ``fetch(`` / ``requests.`` / ``httpx.`` / ``urllib`` / ``socket``

两条避免误报的措施（TS 的 Ruling 5，原样保留）：
    1. 先剥离块注释再扫描 —— 注释里讨论这些名字（例如说明「不许用 random.random」）不该算违规；
    2. 调用类模式要求后跟括号 —— 只抓真正的调用点。

与 TS 的差异（后端没有对应的纯 ``game/`` 层，详见报告）：
    - TS 的 ``PURE_DIRS`` 有 ``core/**`` 与 ``game/**`` 两个目录，Python 侧只有一个纯逻辑目录
      ``app/core/nanfeng``（``app/game`` 按设计承担 IO 与房间循环，不属于禁区内核）；
    - TS 断言 ``files.some(f => f.includes('game'))`` 因此不适用；
    - ``.ts`` 扩展名过滤换成 ``.py``。
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

PURE_DIRS = [REPO_ROOT / 'app' / 'core' / 'nanfeng']

_CC_IMPORT = re.compile(r'\b(?:from|import)\s+cc\b')
_RANDOM_SOURCE = re.compile(
    r'\brandom\s*\.\s*(?:random|randint|randrange|choice|shuffle|uniform|getrandbits)\s*\(')
_DATE_NOW = re.compile(r'\b(?:time\s*\.\s*time|datetime\s*\.\s*(?:datetime\s*\.\s*)?now)\s*\(')
_PERF_NOW = re.compile(r'\btime\s*\.\s*perf_counter\s*\(')
_NETWORK_IO = re.compile(r'\b(?:fetch|requests|httpx|aiohttp|urllib|socket)\s*[.(]')

FORBIDDEN: list[tuple[re.Pattern[str], str]] = [
    (_CC_IMPORT, 'Cocos 引擎（cc）'),
    (_RANDOM_SOURCE, '未注入的随机源（random.*）'),
    (_DATE_NOW, 'Date.now 等价（time.time / datetime.now）'),
    (_PERF_NOW, 'performance.now 等价（time.perf_counter）'),
    (_NETWORK_IO, '网络 IO（fetch / requests / httpx / urllib）'),
]

_BLOCK_COMMENT = re.compile(r'/\*.*?\*/', re.DOTALL)


def strip_block_comments(src: str) -> str:
    """剥离块注释（对应 TS 的 ``stripBlockComments``）。"""
    return _BLOCK_COMMENT.sub('', src)


def walk(directory: Path) -> list[Path]:
    """递归收集目录下的 ``.py`` 文件（对应 TS 的 ``walk`` + ``.endsWith('.ts')``）。"""
    return sorted(path for path in directory.rglob('*.py') if path.is_file())


def all_pure_files() -> list[Path]:
    return [path for directory in PURE_DIRS for path in walk(directory)]


def test_至少扫描到纯净层下的文件() -> None:
    """TS: 至少扫描到 core 与 game 两个目录下的文件（防止空目录导致守护测试空转）。"""
    files = all_pure_files()
    assert len(files) > 0
    for directory in PURE_DIRS:
        assert len(walk(directory)) > 0, f'{directory} 一个文件都没扫到'


def test_纯净层不得依赖_cocos_io_或不确定来源() -> None:
    """TS: 纯净层不得依赖 Cocos、IO 或不确定来源。"""
    for path in all_pure_files():
        src = strip_block_comments(path.read_text(encoding='utf-8'))
        for pattern, label in FORBIDDEN:
            assert pattern.search(src) is None, f'{path} 命中禁区：{label}'


def test_剥离注释后仍能抓到真实的禁区调用() -> None:
    """TS: 剥离注释后仍能抓到真实的禁区调用（守护测试自身不得失效）。

    TS 的 sneaky 样本用 ``Date.now()``；Python 侧同一类禁区调用是 ``time.time()``。
    """
    sneaky = '\n'.join(['/** 这里可以讨论 Date.now 这个词 */', 't = time.time()'])
    cleaned = strip_block_comments(sneaky)
    assert _DATE_NOW.search(cleaned) is not None

    innocent = '\n'.join(
        ['/** spec 规定不得使用 random.random / Date.now */', 'x = 1'])
    assert _RANDOM_SOURCE.search(strip_block_comments(innocent)) is None
