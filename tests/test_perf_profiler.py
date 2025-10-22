from __future__ import annotations

from comfyvn.perf.profiler import PerfProfiler


def test_profiler_records_spans_and_dashboard():
    profiler = PerfProfiler(history_size=16)

    with profiler.profile("load_textures", category="render"):
        [bytes(range(64)) for _ in range(4)]

    profiler.mark("tick", category="loop", metadata={"frame": 1})

    aggregates = profiler.aggregates()
    assert any(entry["name"] == "load_textures" for entry in aggregates)

    dashboard = profiler.dashboard(limit=3)
    assert dashboard["top_time"]
    assert dashboard["top_memory"]
    assert dashboard["marks"]

    profiler.reset()
    assert profiler.aggregates() == []
