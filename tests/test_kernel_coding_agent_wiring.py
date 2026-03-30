from auraeve.agent.tools.assembler import build_tool_registry


class DummyProvider:
    def get_default_model(self):
        return "test-model"


def test_build_tool_registry_registers_coding_agent(tmp_path):
    registry = build_tool_registry(
        profile="main",
        workspace=tmp_path,
        restrict_to_workspace=False,
        exec_timeout=60,
        brave_api_key=None,
        bus_publish_outbound=None,
        provider=DummyProvider(),
        model="test-model",
        plan_manager=None,
        channel_users={},
        notify_channel="",
        task_orchestrator=None,
        cron_service=None,
        engine=None,
        execution_workspace=str(tmp_path),
        media_runtime=None,
        external_agent_service=object(),
        origin_session_key_getter=lambda: "terminal:chat",
    )
    assert registry.has("coding_agent")
