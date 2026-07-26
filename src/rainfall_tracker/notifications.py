from __future__ import annotations

import argparse
import json
import os
import smtplib
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class RunSummary:
    requested_dates: int = 0
    processed_dates: int = 0
    records: int = 0
    missing_dates: int = 0
    skipped_dates: int = 0
    dry_run: bool = False

    @classmethod
    def from_mapping(cls, value: dict[str, object]) -> RunSummary:
        return cls(
            requested_dates=int(value.get("requested_dates", 0)),
            processed_dates=int(value.get("processed_dates", 0)),
            records=int(value.get("records", 0)),
            missing_dates=int(value.get("missing_dates", 0)),
            skipped_dates=int(value.get("skipped_dates", 0)),
            dry_run=bool(value.get("dry_run", False)),
        )


def load_summary(path: Path | None) -> RunSummary | None:
    if path is None or not path.exists():
        return None
    for line in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "processed_dates" in value:
            return RunSummary.from_mapping(value)
    return None


def should_send(status: str, summary: RunSummary | None, notify_no_data: bool) -> bool:
    if status != "success":
        return True
    if summary is None:
        return True
    return summary.processed_dates > 0 or notify_no_data


def build_message(
    *,
    sender: str,
    recipient: str,
    status: str,
    summary: RunSummary | None,
    repository: str,
    run_url: str,
    spreadsheet_url: str,
) -> EmailMessage:
    now = datetime.now(UTC).astimezone(ZoneInfo("Asia/Kuala_Lumpur"))
    if status == "success" and summary and summary.processed_dates:
        subject = (
            f"[Malaysia Rainfall Tracker] Updated "
            f"{summary.processed_dates} date(s)"
        )
        headline = "The daily rainfall update completed successfully."
    elif status == "success":
        subject = "[Malaysia Rainfall Tracker] No new source data"
        headline = "The daily workflow completed, but no new rainfall data was added."
    else:
        subject = "[Malaysia Rainfall Tracker] Daily update failed"
        headline = "The daily rainfall workflow did not complete successfully."

    lines = [
        headline,
        "",
        f"Completed: {now:%Y-%m-%d %H:%M} Malaysia time",
        f"Repository: {repository or 'unknown'}",
    ]
    if summary is not None:
        lines.extend(
            [
                f"Requested dates: {summary.requested_dates}",
                f"Processed dates: {summary.processed_dates}",
                f"Rows written: {summary.records}",
                f"Source dates not yet available: {summary.missing_dates}",
                f"Dates already current/skipped: {summary.skipped_dates}",
            ]
        )
    if spreadsheet_url:
        lines.extend(["", f"Rainfall sheet: {spreadsheet_url}"])
    if run_url:
        lines.append(f"Workflow details: {run_url}")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content("\n".join(lines))
    return message


def send_notification(
    *,
    status: str,
    summary_path: Path | None,
    repository: str,
    run_url: str,
) -> bool:
    sender = os.environ.get("RAINFALL_EMAIL_FROM", "").strip()
    password = os.environ.get("RAINFALL_EMAIL_APP_PASSWORD", "").strip()
    recipient = os.environ.get("RAINFALL_EMAIL_TO", "").strip() or sender
    notify_no_data = (
        os.environ.get("RAINFALL_NOTIFY_NO_DATA", "false").strip().lower()
        in {"1", "true", "yes"}
    )
    if not sender or not password or not recipient:
        print("Email notification is disabled because its GitHub secrets are unset.")
        return False

    summary = load_summary(summary_path)
    if not should_send(status, summary, notify_no_data):
        print("No new rainfall data; success email skipped.")
        return False

    spreadsheet_id = os.environ.get("GOOGLE_SPREADSHEET_ID", "").strip()
    spreadsheet_url = (
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
        if spreadsheet_id
        else ""
    )
    message = build_message(
        sender=sender,
        recipient=recipient,
        status=status,
        summary=summary,
        repository=repository,
        run_url=run_url,
        spreadsheet_url=spreadsheet_url,
    )
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(sender, password)
        smtp.send_message(message)
    print(f"Email notification sent to {recipient}.")
    return True


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send a rainfall workflow email.")
    parser.add_argument("--status", required=True, choices=["success", "failure"])
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--repository", default="")
    parser.add_argument("--run-url", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        send_notification(
            status=args.status,
            summary_path=args.summary,
            repository=args.repository,
            run_url=args.run_url,
        )
    except (OSError, smtplib.SMTPException) as exc:
        print(f"Email notification failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
