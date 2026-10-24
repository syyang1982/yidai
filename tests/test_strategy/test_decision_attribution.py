"""归属分离回归测试（2026-10-14 D4 复核后加）。

背景：agent 曾把复盘文本写进 review_notes/lessons，与用户真实决策矛盾，
而 W9.4 认知偏差检测读的正是这些字段 —— 检测的是 agent 的话，不是用户的决策。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.strategy.decision import DecisionLog, DecisionRecord


@pytest.fixture
def log(tmp_path):
    dl = DecisionLog(str(tmp_path / "d.duckdb"))
    yield dl
    dl.conn.close()


def _rec(**kw):
    base = dict(ticker="LX", company_name="乐信", market="US",
                action="HOLD", price=0.69, decision_date="2026-10-14")
    base.update(kw)
    return DecisionRecord(**base)


def test_user_decision_persists_author(log):
    log.record(_rec(author="user", counter_argument="地板价，风险已暴露"),
               enforce_constraints=False)
    got = log.list_decisions(ticker="LX")[0]
    assert got.author == "user"
    assert got.counter_argument == "地板价，风险已暴露"


def test_agent_review_is_separate_from_review_notes(log):
    """agent 的分析只能进 agent_review，不得占用用户的 review_notes。"""
    log.record(_rec(author="user", review_notes="用户自己写的一句话",
                    agent_review="[agent] 我的分析"),
               enforce_constraints=False)
    got = log.list_decisions(ticker="LX")[0]
    assert got.review_notes == "用户自己写的一句话"
    assert got.agent_review == "[agent] 我的分析"
    assert got.author == "user"


def test_agent_authored_decision_is_markable(log):
    """agent 代录/建议的决策必须能标出来，不能冒充用户决策。"""
    log.record(_rec(author="agent"), enforce_constraints=False)
    assert log.list_decisions(ticker="LX")[0].author == "agent"


def test_default_author_is_user_not_blank(log):
    """不指定时默认 user（符合 DecisionRecord 默认值），但不写空串。"""
    log.record(_rec(), enforce_constraints=False)
    got = log.list_decisions(ticker="LX")[0]
    assert got.author == "user"


def test_roundtrip_preserves_author_across_get(log):
    did = log.record(_rec(author="user", agent_review="分析"), enforce_constraints=False)["decision_id"]
    got = log.get(did)
    assert got is not None
    assert got.author == "user"
    assert got.agent_review == "分析"


def test_legacy_db_without_columns_gets_them_added(tmp_path):
    """旧库（无 author 列）打开时应自动补列，不报错。"""
    import duckdb
    p = str(tmp_path / "legacy.duckdb")
    con = duckdb.connect(p)
    con.execute("""CREATE TABLE decision_log (
        decision_id VARCHAR PRIMARY KEY, ticker VARCHAR, action VARCHAR,
        price DOUBLE, decision_date DATE, status VARCHAR
    )""")
    con.execute("INSERT INTO decision_log VALUES ('t1','LX','HOLD',0.69,'2026-10-14','active')")
    con.close()

    dl = DecisionLog(p)   # 打开旧库应触发 ALTER 补列
    cols = {r[3] for r in dl.conn.execute(
        "SELECT * FROM information_schema.columns WHERE table_name='decision_log'").fetchall()}
    assert        "author" in cols
    assert "agent_review" in cols
    dl.conn.close()
