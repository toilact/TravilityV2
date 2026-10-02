from scripts.loadtest import percentile, row, summarize


def test_percentile_is_nearest_rank():
    xs = [0.4, 0.1, 0.3, 0.2]
    assert percentile(xs, 0.5) == 0.2
    assert percentile(xs, 0.95) == 0.4
    assert percentile([0.7], 0.95) == 0.7
    assert percentile([], 0.5) == 0.0


def test_summary_counts_errors_and_rate_of_successes():
    s = summarize([0.1, 0.2, 0.3, 0.4], errors=1, wall=2.0)
    assert s == {"n": 5, "errors": 1, "p50_ms": 200, "p95_ms": 400, "rps": 2.0}
    assert summarize([], errors=3, wall=0.0) == {"n": 3, "errors": 3, "p50_ms": 0, "p95_ms": 0, "rps": 0.0}


def test_row_is_a_markdown_table_line():
    s = summarize([0.1], errors=0, wall=1.0)
    assert row("2 api", "mở Trip", s) == "| 2 api | mở Trip | 1 | 0 | 100 | 100 | 1.0 |"
