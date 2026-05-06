"""Tests for the ``jsonflat`` CLI."""

from __future__ import annotations
import io

import json
import subprocess
import sys
from pathlib import Path
import pytest

import jsonflat.__main__ as cli_main


def _run(args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    """Invoke the jsonflat CLI as a subprocess and return the completed process."""
    return subprocess.run(
        [sys.executable, "-m", "jsonflat", *args],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_from_file(tmp_path: Path) -> None:
    """Reading JSON from a file path prints a main-table summary with flattened keys."""
    data = {"user": {"name": "Alice", "address": {"city": "NYC"}}, "score": 90}
    path = tmp_path / "data.json"
    path.write_text(json.dumps(data))

    result = _run([str(path), "--nesting", "3"])
    assert result.returncode == 0, result.stderr
    assert "main: 1 rows" in result.stdout
    assert "user__name" in result.stdout
    assert "user__address__city" in result.stdout


def test_cli_from_stdin() -> None:
    """Reading JSON from stdin produces a main row plus one child table per list."""
    data = {"order_id": "A1", "items": [{"sku": "W1"}, {"sku": "G1"}]}
    result = _run(["--nesting", "3"], stdin=json.dumps(data))
    assert result.returncode == 0, result.stderr
    assert "main: 1 rows" in result.stdout
    assert "items: 2 rows" in result.stdout


def test_cli_list_input(tmp_path: Path) -> None:
    """A top-level JSON array produces one main-table row per record."""
    records = [{"id": 1, "city": "NYC"}, {"id": 2, "city": "SF"}]
    path = tmp_path / "list.json"
    path.write_text(json.dumps(records))

    result = _run([str(path)])
    assert result.returncode == 0, result.stderr
    assert "main: 2 rows" in result.stdout


def test_cli_missing_file() -> None:
    """A non-existent file path exits with a non-zero status."""
    result = _run(["/no/such/file.json"])
    assert result.returncode != 0


def test_cli_table_selection_summary() -> None:
    """--table limits summary output to a single selected table."""
    data = {"order_id": "A1", "items": [{"sku": "W1"}, {"sku": "G1"}]}
    result = _run(["--table", "items", "--nesting", "3"], stdin=json.dumps(data))
    assert result.returncode == 0, result.stderr
    assert "items: 2 rows" in result.stdout
    assert "main: 1 rows" not in result.stdout


def test_cli_format_json_all_tables() -> None:
    """--format json outputs all tables as a JSON object by default."""
    data = {"order_id": "A1", "items": [{"sku": "W1"}, {"sku": "G1"}]}
    result = _run(["--format", "json", "--nesting", "3"], stdin=json.dumps(data))
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert "main" in out
    assert "items" in out
    assert out["main"][0]["order_id"] == "A1"
    assert len(out["items"]) == 2


def test_cli_format_json_single_table() -> None:
    """--format json with --table outputs only that table as a JSON array."""
    data = {"order_id": "A1", "items": [{"sku": "W1"}, {"sku": "G1"}]}
    result = _run(["--format", "json", "--table", "items", "--nesting", "3"], stdin=json.dumps(data))
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert isinstance(out, list)
    assert out[0]["sku"] == "W1"
    assert len(out) == 2


def test_cli_format_csv_main_default() -> None:
    """--format csv defaults to the main table."""
    data = {"order_id": "A1", "items": [{"sku": "W1"}]}
    result = _run(["--format", "csv", "--nesting", "3"], stdin=json.dumps(data))
    assert result.returncode == 0, result.stderr
    lines = [line for line in result.stdout.strip().splitlines() if line]
    assert lines[0] == "order_id"
    assert lines[1] == "A1"


def test_cli_format_csv_selected_table() -> None:
    """--format csv with --table emits that child table."""
    data = {"order_id": "A1", "items": [{"sku": "W1"}, {"sku": "G1"}]}
    result = _run(["--format", "csv", "--table", "items", "--nesting", "3"], stdin=json.dumps(data))
    assert result.returncode == 0, result.stderr
    lines = [line for line in result.stdout.strip().splitlines() if line]
    assert lines[0] == "sku"
    assert lines[1] == "W1"
    assert lines[2] == "G1"


def test_cli_machine_readable() -> None:
    """--machine-readable emits JSON table metadata for automation."""
    data = {"order_id": "A1", "items": [{"sku": "W1"}, {"sku": "G1"}]}
    result = _run(["--machine-readable", "--nesting", "3"], stdin=json.dumps(data))
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["tables"]["main"]["rows"] == 1
    assert out["tables"]["items"]["rows"] == 2


def test_cli_json_output_to_file(tmp_path: Path) -> None:
    """--output writes JSON data to a file path."""
    data = {"order_id": "A1"}
    out_path = tmp_path / "out.json"
    result = _run(["--format", "json", "--output", str(out_path)], stdin=json.dumps(data))
    assert result.returncode == 0, result.stderr
    saved = json.loads(out_path.read_text())
    assert saved["main"][0]["order_id"] == "A1"


def test_cli_parquet_requires_output() -> None:
    """Parquet format requires an explicit output file."""
    result = _run(["--format", "parquet"], stdin=json.dumps({"x": 1}))
    assert result.returncode != 0
    assert "--format parquet requires --output" in result.stderr


def test_cli_machine_readable_conflicts_with_format() -> None:
    """--machine-readable and --format are mutually exclusive."""
    result = _run(["--machine-readable", "--format", "json"], stdin=json.dumps({"x": 1}))
    assert result.returncode != 0
    assert "--machine-readable cannot be combined with --format" in result.stderr


def test_module_main_summary_mode(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Running main() without --format prints a human-readable summary."""
    monkeypatch.setattr(sys, "argv", ["jsonflat"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"order_id": "A1"})))
    cli_main.main()
    out = capsys.readouterr().out
    assert "main: 1 rows" in out


def test_module_main_machine_readable_to_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """main() writes machine-readable metadata JSON when requested."""
    out_path = tmp_path / "meta.json"
    monkeypatch.setattr(sys, "argv", ["jsonflat", "--machine-readable", "--output", str(out_path)])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"order_id": "A1"})))
    cli_main.main()
    payload = json.loads(out_path.read_text())
    assert payload["tables"]["main"]["rows"] == 1


def test_module_main_json_single_table(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """main() emits a JSON array when --format json and --table are used."""
    data = {"order_id": "A1", "items": [{"sku": "W1"}, {"sku": "G1"}]}
    monkeypatch.setattr(sys, "argv", ["jsonflat", "--format", "json", "--table", "items"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(data)))
    cli_main.main()
    out = json.loads(capsys.readouterr().out)
    assert isinstance(out, list)
    assert len(out) == 2
    assert out[0]["sku"] == "W1"


def test_module_main_csv_selected_table(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """main() emits CSV for the selected table."""
    data = {"order_id": "A1", "items": [{"sku": "W1"}, {"sku": "G1"}]}
    monkeypatch.setattr(sys, "argv", ["jsonflat", "--format", "csv", "--table", "items"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(data)))
    cli_main.main()
    lines = [line for line in capsys.readouterr().out.strip().splitlines() if line]
    assert lines[0] == "sku"
    assert lines[1:] == ["W1", "G1"]


def test_module_main_parquet_path_invokes_emitter(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """main() dispatches to parquet emitter with selected rows and output path."""
    called: dict[str, object] = {}

    def fake_emit_parquet(rows: list[dict[str, object]], output_path: str) -> None:
        called["rows"] = rows
        called["output_path"] = output_path

    out_path = tmp_path / "items.parquet"
    data = {"order_id": "A1", "items": [{"sku": "W1"}]}
    monkeypatch.setattr(cli_main, "_emit_parquet", fake_emit_parquet)
    monkeypatch.setattr(
        sys,
        "argv",
        ["jsonflat", "--format", "parquet", "--table", "items", "--output", str(out_path)],
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(data)))
    cli_main.main()
    assert called["output_path"] == str(out_path)
    assert called["rows"] == [{"sku": "W1"}]


def test_module_main_validation_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid argument combinations fail with SystemExit."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"x": 1})))

    monkeypatch.setattr(sys, "argv", ["jsonflat", "--machine-readable", "--format", "json"])
    with pytest.raises(SystemExit):
        cli_main.main()

    monkeypatch.setattr(sys, "argv", ["jsonflat", "--output", "out.json"])
    with pytest.raises(SystemExit):
        cli_main.main()

    monkeypatch.setattr(sys, "argv", ["jsonflat", "--format", "parquet"])
    with pytest.raises(SystemExit):
        cli_main.main()
