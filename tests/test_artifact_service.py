from auraeve.services.artifact_service import ArtifactService


def test_artifact_service_builds_record() -> None:
    service = ArtifactService()

    item = service.build_artifact(
        session_id="s1",
        run_id="r1",
        kind="diff",
        path="artifacts/diff.patch",
    )

    assert item.artifact_id
    assert item.session_id == "s1"
    assert item.run_id == "r1"
    assert item.kind == "diff"
    assert item.path == "artifacts/diff.patch"
    assert item.label == ""
    assert item.metadata == {}


def test_artifact_service_preserves_label_and_metadata() -> None:
    service = ArtifactService()

    item = service.build_artifact(
        session_id="s1",
        run_id="r1",
        kind="log",
        path="artifacts/log.txt",
        label="build log",
        metadata={"source": "acp"},
    )

    assert item.label == "build log"
    assert item.metadata == {"source": "acp"}
