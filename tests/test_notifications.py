import json
from pathlib import Path

from rainfall_tracker.notifications import (
    RunSummary,
    build_message,
    load_summary,
    should_send,
)


def test_load_summary_uses_last_json_summary(tmp_path: Path):
    path = tmp_path / "run.log"
    path.write_text(
        "downloaded source\n"
        + json.dumps(
            {
                "requested_dates": 10,
                "processed_dates": 2,
                "records": 32,
                "missing_dates": 1,
                "skipped_dates": 7,
                "dry_run": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert load_summary(path) == RunSummary(
        requested_dates=10,
        processed_dates=2,
        records=32,
        missing_dates=1,
        skipped_dates=7,
        dry_run=False,
    )


def test_success_email_skips_no_new_data_by_default():
    summary = RunSummary(processed_dates=0)

    assert should_send("success", summary, notify_no_data=False) is False
    assert should_send("success", summary, notify_no_data=True) is True
    assert should_send("failure", summary, notify_no_data=False) is True


def test_success_message_contains_update_counts():
    message = build_message(
        sender="sender@example.com",
        recipient="recipient@example.com",
        status="success",
        summary=RunSummary(
            requested_dates=10,
            processed_dates=2,
            records=32,
            missing_dates=1,
            skipped_dates=7,
        ),
        repository="owner/repository",
        run_url="https://github.com/owner/repository/actions/runs/123",
        spreadsheet_url="https://docs.google.com/spreadsheets/d/example/edit",
    )

    assert "Updated 2 date(s)" in str(message["Subject"])
    body = message.get_content()
    assert "Rows written: 32" in body
    assert "Source dates not yet available: 1" in body
    assert "Workflow details:" in body
