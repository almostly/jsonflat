"""Tests for ``normalize_json.stream`` — record-by-record streaming."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterator

import pytest

from jsonflat import normalize_json


def _aggregate(stream: Iterator[tuple[str, dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """Collect a stream into the same shape as ``normalize_json(list)``."""
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for table_name, row in stream:
        out[table_name].append(row)
    return dict(out)


#-------------------------------------------------------------------------------
# Basic behaviour
#-------------------------------------------------------------------------------

def test_stream_yields_tuples() -> None:
    records = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
    result = list(normalize_json.stream(records))
    assert result == [
        ("main", {"id": 1, "name": "a"}),
        ("main", {"id": 2, "name": "b"}),
    ]


def test_stream_accepts_a_generator() -> None:
    def gen() -> Iterator[dict[str, Any]]:
        yield {"id": 1}
        yield {"id": 2}

    result = list(normalize_json.stream(gen()))
    assert [row for _, row in result] == [{"id": 1}, {"id": 2}]


def test_stream_empty_input_yields_nothing() -> None:
    assert list(normalize_json.stream([])) == []


def test_stream_is_lazy_until_consumed() -> None:
    consumed: list[int] = []

    def gen() -> Iterator[dict[str, Any]]:
        for i in range(5):
            consumed.append(i)
            yield {"id": i}

    iterator = normalize_json.stream(gen())
    assert consumed == []
    next(iterator)
    assert consumed == [0]
    next(iterator)
    assert consumed == [0, 1]


#-------------------------------------------------------------------------------
# Equivalence with batch normalize_json
#-------------------------------------------------------------------------------

def test_stream_aggregate_matches_batch_simple() -> None:
    records = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
    streamed = _aggregate(normalize_json.stream(records))
    batch = normalize_json(records)
    assert streamed == batch


def test_stream_aggregate_matches_batch_with_children() -> None:
    records = [
        {"id": 1, "items": [{"sku": "x"}, {"sku": "y"}]},
        {"id": 2, "items": [{"sku": "z"}]},
    ]
    streamed = _aggregate(normalize_json.stream(records, key="id"))
    batch = normalize_json(records, key="id")
    assert streamed == batch


def test_stream_aggregate_matches_batch_with_hoist() -> None:
    records = [
        {
            "loans": {
                "L1": {"amount": 100, "currency": "EUR"},
                "L2": {"amount": 200, "currency": "USD"},
            }
        }
    ]
    streamed = _aggregate(normalize_json.stream(records, hoist=["loans"]))
    batch = normalize_json(records, hoist=["loans"])
    assert streamed == batch


def test_stream_aggregate_matches_batch_with_propagate_keys() -> None:
    records = [
        {
            "request_id": "r1",
            "loan_id": "L1",
            "items": [{"sku": "x"}, {"sku": "y"}],
        },
        {
            "request_id": "r2",
            "loan_id": "L2",
            "items": [{"sku": "z"}],
        },
    ]
    streamed = _aggregate(
        normalize_json.stream(records, key="loan_id", propagate_keys=["request_id"])
    )
    batch = normalize_json(records, key="loan_id", propagate_keys=["request_id"])
    assert streamed == batch


def test_stream_aggregate_matches_batch_with_serialize_remaining() -> None:
    records = [
        {"id": 1, "meta": {"a": {"b": {"c": "deep"}}}},
        {"id": 2, "meta": {"a": {"b": {"c": "deeper"}}}},
    ]
    streamed = _aggregate(
        normalize_json.stream(records, max_nesting=2, serialize_remaining=True)
    )
    batch = normalize_json(records, max_nesting=2, serialize_remaining=True)
    assert streamed == batch


#-------------------------------------------------------------------------------
# kwarg forwarding
#-------------------------------------------------------------------------------

def test_stream_forwards_max_nesting() -> None:
    records = [{"id": 1, "deep": {"a": {"b": {"c": 1}}}}]
    streamed = _aggregate(normalize_json.stream(records, max_nesting=1))
    batch = normalize_json(records, max_nesting=1)
    assert streamed == batch


def test_stream_forwards_root_name() -> None:
    records = [{"id": 1}]
    result = list(normalize_json.stream(records, root_name="orders"))
    assert result == [("orders", {"id": 1})]


def test_stream_forwards_separator() -> None:
    records = [{"id": 1, "items": [{"sku": "x"}]}]
    table_names = {tn for tn, _ in normalize_json.stream(records, separator="/")}
    assert "items" in table_names


#-------------------------------------------------------------------------------
# Error propagation
#-------------------------------------------------------------------------------

def test_stream_raises_when_key_missing() -> None:
    records = [{"items": [{"sku": "x"}]}]
    with pytest.raises(KeyError, match="Key 'id' not found"):
        list(normalize_json.stream(records, key="id"))


def test_stream_partial_output_visible_before_error() -> None:
    """A failing record's predecessors should already be yielded."""
    records = [
        {"id": 1, "items": [{"sku": "x"}]},
        {"items": [{"sku": "y"}]},  # missing 'id', will raise
    ]
    consumed: list[tuple[str, dict[str, Any]]] = []
    iterator = normalize_json.stream(records, key="id")
    with pytest.raises(KeyError):
        for pair in iterator:
            consumed.append(pair)
    assert ("main", {"id": 1}) in consumed
