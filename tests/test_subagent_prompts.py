from auraeve.agent.agents.definitions import (
    COORDINATOR_AGENT,
    EXPLORE_AGENT,
    PLAN_AGENT,
    VERIFIER_AGENT,
    WORKER_AGENT,
)


def test_explore_prompt_mentions_parallel_read_only_search():
    assert "并发" in EXPLORE_AGENT.system_prompt
    assert "只读" in EXPLORE_AGENT.system_prompt


def test_plan_prompt_mentions_critical_files_output():
    assert "关键文件" in PLAN_AGENT.system_prompt
    assert "只读" in PLAN_AGENT.system_prompt


def test_worker_prompt_mentions_not_talking_to_user():
    assert "不要直接与用户对话" in WORKER_AGENT.system_prompt


def test_verifier_prompt_mentions_independent_verification():
    assert "独立验证" in VERIFIER_AGENT.system_prompt
    assert "不要替实现背书" in VERIFIER_AGENT.system_prompt


def test_coordinator_prompt_mentions_worker_and_notification():
    assert "worker" in COORDINATOR_AGENT.system_prompt
    assert "task-notification" in COORDINATOR_AGENT.system_prompt
