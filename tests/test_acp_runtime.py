from auraeve.runtimes.acp.runtime import ACPRuntime


def test_acp_runtime_exposes_runtime_name() -> None:
    runtime = ACPRuntime()

    assert runtime.name == "acp"
