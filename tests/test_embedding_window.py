from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.indexer import session_in_embedding_window


def test_embedding_window_none_means_all() -> None:
    old = datetime(2020, 1, 1, tzinfo=UTC)
    assert session_in_embedding_window(old, None) is True


def test_embedding_window_respects_days() -> None:
    now = datetime.now(tz=UTC)
    fresh = now - timedelta(days=5)
    stale = now - timedelta(days=40)
    assert session_in_embedding_window(fresh, 30) is True
    assert session_in_embedding_window(stale, 30) is False


def test_embedding_window_naive_datetime_treated_as_utc() -> None:
    now = datetime.now(tz=UTC)
    naive_fresh = (now - timedelta(days=1)).replace(tzinfo=None)
    assert session_in_embedding_window(naive_fresh, 7) is True


@pytest.mark.parametrize("recent_days", [1, 30, 365])
def test_just_outside_window_excluded(recent_days: int) -> None:
    now = datetime.now(tz=UTC)
    too_old = now - timedelta(days=recent_days, seconds=30)
    assert session_in_embedding_window(too_old, recent_days) is False
