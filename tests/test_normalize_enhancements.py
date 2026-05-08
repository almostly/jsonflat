"""Tests for the normalize_json / flatten enhancements added in 0.0.3:

1. separator param in flatten
2. on_collision in flatten ("warn" / "ignore")
3. serialize_remaining in normalize_json
4. propagate_keys in normalize_json
"""

from __future__ import annotations

import json
import warnings

import pytest

from jsonflat import flatten, normalize_json


# -------------------------------------------------------------------------------
# 1. separator
# -------------------------------------------------------------------------------
class TestSeparator:
    def test_dot_separator(self) -> None:
        data = {"user": {"id": 1, "name": "Alice"}, "score": 90}
        flat = flatten(data, separator=".")
        assert flat == {"user.id": 1, "user.name": "Alice", "score": 90}

    def test_dot_separator_deep(self) -> None:
        data = {"a": {"b": {"c": 1}}}
        flat = flatten(data, separator=".", max_nesting=None)
        assert flat == {"a.b.c": 1}

    def test_default_separator_unchanged(self) -> None:
        data = {"user": {"id": 1}}
        assert flatten(data) == {"user__id": 1}

    def test_dot_collision_raises(self) -> None:
        data = {"user.id": 1, "user": {"id": 2}}
        with pytest.raises(ValueError, match="Key collision"):
            flatten(data, separator=".", max_nesting=None)

    def test_dot_collision_warn_keeps_first(self) -> None:
        data = {"user.id": 1, "user": {"id": 2}}
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            flat = flatten(data, separator=".", max_nesting=None, on_collision="warn")
        assert flat["user.id"] == 1
        assert caught

    def test_normalize_json_unaffected_by_separator_param(self) -> None:
        # normalize_json always uses __ internally regardless of flatten's separator default
        data = {"id": "x1", "items": [{"v": 1}, {"v": 2}]}
        result = normalize_json(data, key="id")
        assert "items" in result
        assert result["items"][0]["id"] == "x1"


# -------------------------------------------------------------------------------
# 2. on_collision
# -------------------------------------------------------------------------------
class TestOnCollision:
    def test_warn_emits_warning_and_keeps_first(self) -> None:
        data = {"user__id": 1, "user": {"id": 2}}
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            flat = flatten(data, max_nesting=None, on_collision="warn")
        assert flat["user__id"] == 1
        assert any("user__id" in str(w.message) for w in caught)

    def test_ignore_keeps_first_silently(self) -> None:
        data = {"user__id": 1, "user": {"id": 2}}
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            flat = flatten(data, max_nesting=None, on_collision="ignore")
        assert flat["user__id"] == 1
        assert not caught

    def test_raise_still_raises_by_default(self) -> None:
        data = {"user__id": 1, "user": {"id": 2}}
        with pytest.raises(ValueError, match="Key collision"):
            flatten(data, max_nesting=None)

    def test_normalize_json_warns_on_collision(self) -> None:
        data = {"user__id": 1, "user": {"id": 2}}
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = normalize_json(data, max_nesting=None)
        assert "main" in result
        assert any("user__id" in str(w.message) for w in caught)


# -------------------------------------------------------------------------------
# 3. serialize_remaining
# -------------------------------------------------------------------------------
class TestSerializeRemaining:
    def test_nested_dict_serialized_to_string(self) -> None:
        # max_nesting=1 flattens one level; a dict at depth 1 is stored as-is.
        # "meta" → recurse; "meta.nested" → depth 1, stop → stored as dict.
        data = {"id": "x1", "meta": {"a": 1, "nested": {"deep": "value"}}}
        result = normalize_json(data, max_nesting=1, serialize_remaining=True)
        row = result["main"][0]
        assert isinstance(row["meta__nested"], str)
        assert json.loads(row["meta__nested"]) == {"deep": "value"}

    def test_scalars_untouched(self) -> None:
        data = {"id": "x1", "score": 42, "label": "ok"}
        result = normalize_json(data, max_nesting=1, serialize_remaining=True)
        row = result["main"][0]
        assert row["score"] == 42
        assert row["label"] == "ok"

    def test_serialize_false_keeps_objects(self) -> None:
        data = {"id": "x1", "meta": {"a": 1, "nested": {"deep": "value"}}}
        result = normalize_json(data, max_nesting=1, serialize_remaining=False)
        row = result["main"][0]
        assert isinstance(row["meta__nested"], dict)

    def test_child_rows_also_serialized(self) -> None:
        data = {
            "id": "x1",
            "items": [
                {"name": "a", "attrs": {"color": "red"}},
            ],
        }
        result = normalize_json(data, max_nesting=1, serialize_remaining=True)
        child_row = result["items"][0]
        assert isinstance(child_row["attrs"], str)
        assert json.loads(child_row["attrs"]) == {"color": "red"}


# -------------------------------------------------------------------------------
# 4. propagate_keys
# -------------------------------------------------------------------------------
class TestPropagateKeys:
    def test_extra_key_appears_in_child_rows(self) -> None:
        data = {
            "request_id": "req-1",
            "loan_id": "loan-A",
            "items": [{"amount": 100}, {"amount": 200}],
        }
        result = normalize_json(data, key="loan_id", propagate_keys=["request_id"])
        for row in result["items"]:
            assert row["request_id"] == "req-1"
            assert row["loan_id"] == "loan-A"

    def test_propagate_key_not_overwritten_when_present(self) -> None:
        data = {
            "request_id": "req-1",
            "loan_id": "loan-A",
            "items": [{"amount": 100, "request_id": "child-own"}],
        }
        result = normalize_json(data, key="loan_id", propagate_keys=["request_id"])
        assert result["items"][0]["request_id"] == "child-own"

    def test_propagate_missing_key_is_skipped(self) -> None:
        data = {"loan_id": "loan-A", "items": [{"amount": 100}]}
        result = normalize_json(data, key="loan_id", propagate_keys=["request_id"])
        assert "request_id" not in result["items"][0]

    def test_propagate_multiple_keys(self) -> None:
        data = {
            "request_id": "req-1",
            "batch_id": "batch-99",
            "loan_id": "loan-A",
            "items": [{"amount": 100}],
        }
        result = normalize_json(data, key="loan_id", propagate_keys=["request_id", "batch_id"])
        assert result["items"][0]["request_id"] == "req-1"
        assert result["items"][0]["batch_id"] == "batch-99"

    def test_propagate_keys_without_key_param(self) -> None:
        data = {
            "request_id": "req-1",
            "items": [{"amount": 100}],
        }
        result = normalize_json(data, propagate_keys=["request_id"])
        assert result["items"][0]["request_id"] == "req-1"

    def test_propagate_keys_not_applied_to_hoist_tables(self) -> None:
        # Hoisted child tables are built mid-loop before flat is complete,
        # so propagate_keys does not apply to them — document this boundary.
        data = {
            "request_id": "req-1",
            "loans": {"loan-A": {"amount": 500}, "loan-B": {"amount": 800}},
        }
        result = normalize_json(data, hoist=[("loans", "loan_id")], propagate_keys=["request_id"])
        for row in result["loans"]:
            assert "request_id" not in row
        # main table still gets request_id as a normal flat field
        assert result["main"][0]["request_id"] == "req-1"


# -------------------------------------------------------------------------------
# 5. serialize_remaining — hoist branch
# -------------------------------------------------------------------------------
class TestSerializeRemainingHoist:
    def test_hoist_child_rows_serialized(self) -> None:
        # outer flatten (max_nesting=1): loan-A list stored as blob → hoist picks it up
        # inner flatten (max_nesting=1): attrs__x = {"y": 1} (dict blob) → serialize_remaining dumps it
        data = {
            "id": "x1",
            "loans": {"loan-A": [{"amount": 500, "attrs": {"x": {"y": 1}}}]},
        }
        result = normalize_json(data, max_nesting=1, hoist=[("loans", "loan_id")], serialize_remaining=True)
        row = result["loans"][0]
        assert row["loan_id"] == "loan-A"
        assert isinstance(row["attrs__x"], str)
        assert json.loads(row["attrs__x"]) == {"y": 1}

    def test_hoist_child_rows_not_serialized_by_default(self) -> None:
        data = {
            "id": "x1",
            "loans": {"loan-A": [{"amount": 500, "attrs": {"x": {"y": 1}}}]},
        }
        result = normalize_json(data, max_nesting=1, hoist=[("loans", "loan_id")], serialize_remaining=False)
        row = result["loans"][0]
        assert isinstance(row["attrs__x"], dict)
