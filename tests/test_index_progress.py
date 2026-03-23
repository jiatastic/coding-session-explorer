from core import index_progress


def test_index_progress_lifecycle() -> None:
    index_progress.reset_running()
    s = index_progress.snapshot()
    assert s["running"] is True
    assert s["phase"] == "running"

    index_progress.update(crawler="Claude", current=2, total=10, detail="/tmp/x.jsonl")
    s = index_progress.snapshot()
    assert s["crawler"] == "Claude"
    assert s["current"] == 2
    assert s["total"] == 10
    assert s["detail"] == "/tmp/x.jsonl"

    index_progress.finish({"new_sessions": 1, "new_messages": 3, "skipped": 0})
    s = index_progress.snapshot()
    assert s["running"] is False
    assert s["phase"] == "done"
    assert s["stats"] == {"new_sessions": 1, "new_messages": 3, "skipped": 0}


def test_index_progress_fail() -> None:
    index_progress.reset_running()
    index_progress.fail("disk full")
    s = index_progress.snapshot()
    assert s["running"] is False
    assert s["phase"] == "error"
    assert s["error"] == "disk full"
