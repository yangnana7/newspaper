from mcp_news.logutil import log_kv


def test_log_kv_outputs_json_line(capsys):
    log_kv("unit_test_event", count=3, note={"x":1})
    captured = capsys.readouterr().out.strip()
    assert captured.startswith("{") and captured.endswith("}")
    assert '"event"' in captured and '"unit_test_event"' in captured

