"""Регрессии K1-1..K1-3, R2.1..R2.3, R8."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from collector import ids, normalize
from collector.collectors import github as gh


def test_r1_created_id_preserves_timestamp_case():
    assert (
        ids.created_id("Legacy-Lib", "2023-09-12T06:00:00Z")
        == "pypi:legacy-lib:2023-09-12T06:00:00Z"
    )  # регистр T/Z сохранён


def test_r1_normalize_ts_variants():
    assert ids.normalize_ts("2023-09-12t06:00:00z") == "2023-09-12T06:00:00Z"
    assert ids.normalize_ts("2023-09-12 06:00:00+00:00") == "2023-09-12T06:00:00Z"
    with pytest.raises(ValueError):
        ids.normalize_ts("not-a-time")


def test_r8_membership_id():
    assert (
        ids.membership_id(
            "Old-Dev/Legacy-Lib", "Right9Ctrl", "2023-09-11T10:00:00Z", "added"
        )
        == "gh:old-dev/legacy-lib:member:right9ctrl:20230911:added"
    )


def test_r2_user_profile_snapshot_normalizer_full_envelope():
    doc = normalize.normalize_user_profile_snapshot(
        {
            "login": "Right9Ctrl",
            "date": "2023-09-12",
            "account_created_at": "2018-08-15T14:22:00Z",
            "followers": 2,
            "public_repos": 1,
        },
        watchlist="ground_truth",
        ingested_at="2026-10-19T10:00:00Z",
    )
    assert doc["event"]["id"] == "github-api:right9ctrl:metric:2023-09-12"
    assert doc["event"]["kind"] == "metric"
    assert doc["user"]["name"] == "right9ctrl"
    assert doc["sscs"]["user"]["followers"] == 2
    assert doc["sscs"]["user"]["account_created_at"] == "2018-08-15T14:22:00Z"
    assert doc["sscs"]["user"]["public_repos"] == 1


def test_r2_membership_normalizer_type_mapping():
    doc = normalize.normalize_membership_change(
        {
            "repo": "old-dev/legacy-lib",
            "login": "right9ctrl",
            "role": "maintainer",
            "change_type": "added",
            "event_at": "2023-09-11T10:00:00Z",
        },
        watchlist="ground_truth",
        ingested_at="2026-10-19T10:00:00Z",
    )
    assert doc["event"]["type"] == "creation"
    assert doc["event"]["category"] == "iam"
    removed = normalize.normalize_membership_change(
        {
            "repo": "old-dev/legacy-lib",
            "login": "right9ctrl",
            "role": "maintainer",
            "change_type": "removed",
            "event_at": "2023-09-11T10:00:00Z",
        },
        watchlist="ground_truth",
        ingested_at="2026-10-19T10:00:00Z",
    )
    assert removed["event"]["type"] == "deletion"


def test_r2_invalid_change_type_raises():
    import pytest as _pt

    with _pt.raises(ValueError):
        normalize.normalize_membership_change(
            {
                "repo": "r",
                "login": "u",
                "change_type": "banned",
                "event_at": "2023-09-11T10:00:00Z",
            },
            watchlist="monitored",
            ingested_at="2026-10-19T10:00:00Z",
        )


def test_determinism_same_fixture_same_sha256():
    root = Path(__file__).resolve().parent.parent.parent / "demo_fixtures"
    if not (root / "fixtures").exists():
        pytest.skip("demo fixtures not materialized")
    from collector import runner

    out_a = root / "out" / "a.jsonl"
    out_b = root / "out" / "b.jsonl"
    ref = json.loads((root / "reference.json").read_text())
    runner.run_backfill(root / "fixtures", ref, out_a, "2026-10-19T10:00:00Z")
    runner.run_backfill(root / "fixtures", ref, out_b, "2026-10-19T10:00:00Z")
    assert out_a.read_bytes() == out_b.read_bytes()


def test_ratelimit_handle_status_pauses_only_via_state():
    from collector import ratelimit

    st = ratelimit.RateLimitState(simulated=True)
    cont, slept = ratelimit.handle_status(429, {"Retry-After": "120"}, st)
    assert cont is False and slept == 120.0 and st._now == 120.0
    cont, _ = ratelimit.handle_status(200, {}, st)
    assert cont is True
    cont, _ = ratelimit.handle_status(404, {}, st)
    assert cont is False
