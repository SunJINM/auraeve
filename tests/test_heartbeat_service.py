from pathlib import Path

from auraeve.heartbeat.service import HeartbeatService


def test_heartbeat_file_reads_utf8_content(tmp_path: Path) -> None:
    heartbeat = tmp_path / "HEARTBEAT.md"
    heartbeat.write_text("# 心跳任务\n\n### Obsidian AI 知识体系长期管理\n", encoding="utf-8")
    service = HeartbeatService(workspace=tmp_path, enabled=True)

    assert service._read_heartbeat_file() == heartbeat.read_text(encoding="utf-8")


def test_template_heartbeat_file_reads_utf8_content(tmp_path: Path, monkeypatch) -> None:
    template = tmp_path / "workspace" / "HEARTBEAT.md"
    template.parent.mkdir()
    template.write_text("# 心跳任务\n\n<!-- 注释 -->\n", encoding="utf-8")
    service = HeartbeatService(workspace=tmp_path, enabled=True)

    monkeypatch.setattr(
        HeartbeatService,
        "template_heartbeat_file",
        property(lambda _self: template),
    )

    assert service._read_template_heartbeat_file() == template.read_text(encoding="utf-8")
