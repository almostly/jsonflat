"""CLI entry point for jsonflat."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, TextIO

from jsonflat.core import normalize_json


def _load_data(file: str | None) -> Any:
    """Load JSON from a file path or stdin."""
    if file:
        with open(file, encoding="utf-8") as f:
            return json.load(f)
    return json.load(sys.stdin)


def _resolve_tables(
    tables: dict[str, list[dict[str, Any]]],
    table: str | None,
    parser: argparse.ArgumentParser,
) -> dict[str, list[dict[str, Any]]]:
    """Optionally filter to a single table."""
    if table is None:
        return tables
    if table not in tables:
        parser.error(f"Table '{table}' not found. Available: {list(tables.keys())}")
    return {table: tables[table]}


def _open_text_output(path: str | None) -> TextIO:
    """Return stdout or an opened UTF-8 text file handle."""
    if path is None:
        return sys.stdout
    return Path(path).open("w", encoding="utf-8", newline="")


def _emit_summary(tables: dict[str, list[dict[str, Any]]]) -> None:
    """Print the human-readable table summary."""
    for name, rows in tables.items():
        cols = len(rows[0]) if rows else 0
        print(f"\n{name}: {len(rows)} rows, {cols} columns")
        if rows:
            for k in sorted(rows[0].keys()):
                v = rows[0][k]
                vstr = str(v)[:60]
                print(f"{k}: ({type(v).__name__}) {vstr}")


def _emit_machine_readable(
    tables: dict[str, list[dict[str, Any]]],
    output_path: str | None,
) -> None:
    """Emit JSON metadata for automation."""
    payload = {
        "tables": {
            name: {
                "rows": len(rows),
                "columns": sorted(rows[0].keys()) if rows else [],
                "column_count": len(rows[0]) if rows else 0,
            }
            for name, rows in tables.items()
        }
    }
    out = _open_text_output(output_path)
    try:
        json.dump(payload, out, ensure_ascii=False)
        out.write("\n")
    finally:
        if out is not sys.stdout:
            out.close()


def _emit_json(
    tables: dict[str, list[dict[str, Any]]],
    output_path: str | None,
    single_table: bool,
) -> None:
    """Emit table data as JSON."""
    out = _open_text_output(output_path)
    try:
        data: Any = next(iter(tables.values())) if single_table else tables
        json.dump(data, out, ensure_ascii=False)
        out.write("\n")
    finally:
        if out is not sys.stdout:
            out.close()


def _emit_csv(
    rows: list[dict[str, Any]],
    output_path: str | None,
) -> None:
    """Emit one table as CSV."""
    fieldnames = sorted({k for row in rows for k in row})
    out = _open_text_output(output_path)
    try:
        writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
        if fieldnames:
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
    finally:
        if out is not sys.stdout:
            out.close()


def _emit_parquet(rows: list[dict[str, Any]], output_path: str) -> None:
    """Emit one table as Parquet."""
    try:
        import pandas as pd
    except ImportError as e:
        raise RuntimeError("Parquet output requires pandas and a parquet engine (e.g. pyarrow).") from e
    try:
        pd.DataFrame(rows).to_parquet(output_path)
    except Exception as e:
        raise RuntimeError(f"Failed to write parquet to '{output_path}': {e}") from e


def main() -> None:
    """Flatten nested JSON from file or stdin and emit summaries or table data."""
    parser = argparse.ArgumentParser(description="Flatten nested JSON")
    parser.add_argument("file", nargs="?", help="JSON file (stdin if omitted)")
    parser.add_argument("--nesting", type=int, default=None, help="Max nesting depth (default: unlimited)")
    parser.add_argument("--table", help="Table name to select (default: all for summary/json, main for csv/parquet)")
    parser.add_argument(
        "--format",
        choices=["json", "csv", "parquet"],
        help="Output table data in the selected format",
    )
    parser.add_argument("--output", help="Write output to file path instead of stdout")
    parser.add_argument(
        "--machine-readable",
        action="store_true",
        help="Emit JSON summary metadata for automation",
    )
    args = parser.parse_args()

    if args.machine_readable and args.format is not None:
        parser.error("--machine-readable cannot be combined with --format")
    if args.output and args.format is None and not args.machine_readable:
        parser.error("--output requires --format or --machine-readable")
    if args.format == "parquet" and not args.output:
        parser.error("--format parquet requires --output")

    data = _load_data(args.file)
    records = data if isinstance(data, list) else [data]
    tables = normalize_json(records, max_nesting=args.nesting)
    selected_tables = _resolve_tables(tables, args.table, parser)

    if args.machine_readable:
        _emit_machine_readable(selected_tables, args.output)
        return

    if args.format == "json":
        _emit_json(selected_tables, args.output, single_table=args.table is not None)
        return

    if args.format in {"csv", "parquet"}:
        table_name = args.table or "main"
        if table_name not in tables:
            parser.error(f"Table '{table_name}' not found. Available: {list(tables.keys())}")
        rows = tables[table_name]
        if args.format == "csv":
            _emit_csv(rows, args.output)
            return
        _emit_parquet(rows, args.output)
        return

    _emit_summary(selected_tables)


if __name__ == "__main__":
    main()
