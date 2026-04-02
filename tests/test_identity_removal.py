import inspect
import subprocess

from auraeve.agent_runtime.kernel import RuntimeKernel


def test_kernel_has_no_identity_resolver_parameter() -> None:
    signature = inspect.signature(RuntimeKernel)

    assert "identity_resolver" not in signature.parameters


def test_no_identity_imports_left_in_production_code() -> None:
    result = subprocess.run(
        ["rg", "-n", r"auraeve\.identity|IdentityResolver|IdentityService|IdentityStore", "auraeve", "main.py"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 1


def test_no_identity_metadata_fields_left_in_production_code() -> None:
    result = subprocess.run(
        [
            "rg",
            "-n",
            r"canonical_user_id|relationship_to_assistant|identity_confidence|identity_source|webui_display_name|is_owner",
            "auraeve",
            "main.py",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 1
