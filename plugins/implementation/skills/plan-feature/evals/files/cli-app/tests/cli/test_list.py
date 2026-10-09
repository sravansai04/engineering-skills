import json

from cli.main import main


def test_list_shows_table(tmp_path, monkeypatch, capsys):
    data = tmp_path / "tasks.json"
    data.write_text(json.dumps([{"id": 1, "title": "Write docs", "status": "open", "due": "2026-05-01"}]))
    monkeypatch.setenv("TASKTRACK_FILE", str(data))

    main(["list"])

    out = capsys.readouterr().out
    assert "TITLE" in out
    assert "Write docs" in out
