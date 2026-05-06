"""Lambda-oriented tests for S3 JSON references and row-level transform comparisons."""

from __future__ import annotations

import json
from time import perf_counter
from typing import Any, cast

import pandas as pd

from jsonflat import aio, flatten


class _FakeBody:
    """Minimal async body object returned by fake S3 get_object."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    async def read(self) -> bytes:
        return self._payload


class _FakeS3Client:
    """In-memory async S3 client for Lambda-style tests."""

    def __init__(self, objects: dict[tuple[str, str], bytes]) -> None:
        self._objects = objects

    async def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        return {"Body": _FakeBody(self._objects[(Bucket, Key)])}


class _FakePool:
    """Async context manager used by the aio(pool=...) decorator path."""

    def __init__(self, client: _FakeS3Client) -> None:
        self._client = client

    async def __aenter__(self) -> _FakeS3Client:
        return self._client

    async def __aexit__(self, *_: object) -> None:
        return None


def test_lambda_style_s3_reference_enrichment_stays_under_256kb() -> None:
    """Selectively enriching from S3-linked JSON keeps payload below Step Functions limits."""
    event = {
        "execution_id": "exec-001",
        "record_id": "rec-001",
        "s3_refs": [
            {"bucket": "demo", "key": "risk/large.json"},
            {"bucket": "demo", "key": "risk/small.json"},
        ],
    }
    large_doc = {
        "risk": {"score": 612},
        "financials": {"income_monthly": 6200, "debt_monthly": 2100},
        "history": [{"ts": i, "blob": "x" * 512} for i in range(700)],
    }
    small_doc = {
        "risk": {"score": 701},
        "financials": {"income_monthly": 9100, "debt_monthly": 1200},
        "history": [{"ts": 1, "blob": "ok"}],
    }
    objects = {
        ("demo", "risk/large.json"): json.dumps(large_doc).encode("utf-8"),
        ("demo", "risk/small.json"): json.dumps(small_doc).encode("utf-8"),
    }
    client = _FakeS3Client(objects)

    @aio(workers=8, pool=lambda: _FakePool(client))
    async def fetch_ref(ref: dict[str, str], s3: _FakeS3Client) -> dict[str, Any]:
        response = await s3.get_object(Bucket=ref["bucket"], Key=ref["key"])
        return cast(dict[str, Any], json.loads(await response["Body"].read()))

    fetched_docs = fetch_ref(event["s3_refs"])

    selected_fields: dict[str, Any] = {}
    for idx, doc in enumerate(fetched_docs):
        flat = flatten(doc, max_nesting=None)
        income = float(flat["financials__income_monthly"])
        debt = float(flat["financials__debt_monthly"])
        selected_fields[f"s3_{idx}__risk_score"] = int(flat["risk__score"])
        selected_fields[f"s3_{idx}__income_monthly"] = income
        selected_fields[f"s3_{idx}__debt_to_income"] = round(debt / income, 6) if income else None

    enriched_event = {"execution_id": event["execution_id"], "record_id": event["record_id"], **selected_fields}
    enriched_size = len(json.dumps(enriched_event, separators=(",", ":")).encode("utf-8"))
    raw_size = len(json.dumps({**event, "documents": fetched_docs}, separators=(",", ":")).encode("utf-8"))

    assert raw_size > 256 * 1024
    assert enriched_size < 256 * 1024
    assert enriched_event["s3_0__risk_score"] == 612
    assert enriched_event["s3_1__risk_score"] == 701


def test_lambda_row_level_transform_matches_pandas_apply() -> None:
    """Row-level feature transforms match pandas apply output for Lambda-style processing."""
    records = [
        {
            "request_id": f"r-{i}",
            "risk": {"score": 560 + (i % 180)},
            "financials": {"income_monthly": 2500 + (i % 120) * 40, "debt_monthly": 150 + (i % 70) * 20},
        }
        for i in range(2000)
    ]

    jsonflat_start = perf_counter()
    jsonflat_rows: list[dict[str, Any]] = []
    for record in records:
        flat = flatten(record, max_nesting=None)
        income = float(flat["financials__income_monthly"])
        debt = float(flat["financials__debt_monthly"])
        score = int(flat["risk__score"])
        dti = round(debt / income, 6) if income else 0.0
        jsonflat_rows.append(
            {
                "request_id": flat["request_id"],
                "risk_score": score,
                "debt_to_income": dti,
                "risk_bucket": "high" if (score < 620 or dti > 0.4) else "low",
            }
        )
    jsonflat_seconds = perf_counter() - jsonflat_start

    pandas_start = perf_counter()
    frame = pd.json_normalize(records, sep="__")

    def pandas_row_transform(row: pd.Series) -> dict[str, Any]:
        income = float(row["financials__income_monthly"])
        debt = float(row["financials__debt_monthly"])
        score = int(row["risk__score"])
        dti = round(debt / income, 6) if income else 0.0
        return {
            "request_id": row["request_id"],
            "risk_score": score,
            "debt_to_income": dti,
            "risk_bucket": "high" if (score < 620 or dti > 0.4) else "low",
        }

    pandas_rows = frame.apply(pandas_row_transform, axis=1).tolist()
    pandas_seconds = perf_counter() - pandas_start

    assert pandas_rows == jsonflat_rows
    assert jsonflat_seconds > 0
    assert pandas_seconds > 0
