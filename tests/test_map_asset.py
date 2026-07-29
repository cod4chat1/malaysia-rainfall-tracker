from pathlib import Path

from rainfall_tracker.constants import STATE_ORDER


def test_generated_map_contains_every_state_once():
    content = Path("apps_script/MapPaths.html").read_text(encoding="utf-8")
    for state in STATE_ORDER:
        assert content.count(f'data-state="{state}"') == 1
    assert content.count('class="state"') == len(STATE_ORDER)
    assert 'data-state="Malacca"' not in content


def test_map_dialog_exposes_all_tooltip_metrics():
    content = Path("apps_script/MapDialog.html").read_text(encoding="utf-8")
    for label in (
        "MTD rainfall mm",
        "Expected MTD mm",
        "MTD anomaly",
        "7-day average mm",
        "30-day average mm",
        "Recent trend",
        "Trend %",
    ):
        assert label in content
