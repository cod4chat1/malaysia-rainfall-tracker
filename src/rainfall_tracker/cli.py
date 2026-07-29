from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

from .catalog import CatalogClient
from .config import Settings
from .constants import STATE_ORDER
from .pipeline import date_range, default_date_range, process_assets, select_assets
from .sheets import SheetStore
from .weights import build_weights, load_weights


def _day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rainfall-tracker",
        description="Aggregate CHIRPS v3 rainfall for Malaysian states.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    weights = sub.add_parser("build-weights", help="Build spatial weights")
    weights.add_argument("--boundaries", type=Path)
    weights.add_argument("--output", type=Path)

    init = sub.add_parser("init-sheet", help="Initialize Google Sheet tabs")
    init.add_argument("--through", type=_day)

    sub.add_parser(
        "migrate-calendar-start",
        help="Safely prepend calendar rows when moving the configured start earlier",
    )
    sub.add_parser(
        "refresh-dashboard",
        help="Create or refresh the Google Sheets rainfall dashboard",
    )

    run = sub.add_parser("run", help="Process recent or explicit dates")
    run.add_argument("--start-date", type=_day)
    run.add_argument("--end-date", type=_day)
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--max-dates", type=int)

    backfill = sub.add_parser("backfill", help="Process a bounded historical range")
    backfill.add_argument("--start-date", required=True, type=_day)
    backfill.add_argument("--end-date", required=True, type=_day)
    backfill.add_argument("--dry-run", action="store_true")
    backfill.add_argument("--max-dates", type=int, default=366)

    smoke = sub.add_parser("smoke", help="No-write live-source smoke test")
    smoke.add_argument("--date", required=True, type=_day)

    return parser


def _resolve_days(args: argparse.Namespace, settings: Settings) -> list[date]:
    if args.command == "smoke":
        return [args.date]
    if args.command == "backfill":
        days = date_range(args.start_date, args.end_date)
        if len(days) > 366:
            raise ValueError("Backfill range is limited to 366 days per invocation")
        return days
    if bool(args.start_date) != bool(args.end_date):
        raise ValueError("--start-date and --end-date must be supplied together")
    if args.start_date:
        return date_range(args.start_date, args.end_date)
    return default_date_range(date.today(), settings.lookback_days)


def _records_json(records) -> str:
    values = []
    for record in records:
        values.append(
            {
                "date": record.day.isoformat(),
                "state": record.state,
                "average_mm": round(record.average_mm, 3),
                "median_mm": round(record.median_mm, 3),
                "maximum_mm": round(record.maximum_mm, 3),
                "valid_area_pct": round(record.valid_area_pct, 3),
                "status": record.data_status,
            }
        )
    return json.dumps(values, indent=2)


def _run(args: argparse.Namespace, settings: Settings) -> int:
    started = datetime.now(UTC)
    run_id = str(uuid.uuid4())
    days = _resolve_days(args, settings)
    max_dates = getattr(args, "max_dates", None) or settings.max_dates_per_run
    if max_dates <= 0:
        raise ValueError("--max-dates must be positive")
    dry_run = args.command == "smoke" or bool(args.dry_run)
    store = None if dry_run else SheetStore.from_env(max_requests=settings.max_sheets_requests)
    if store:
        store.ensure_through(max(days))
        statuses = store.get_statuses(days)
    else:
        statuses = {day: None for day in days}
    catalog = CatalogClient(timeout_seconds=settings.request_timeout_seconds)
    selected, missing, skipped = select_assets(
        days,
        catalog,
        statuses,
        max_dates=max_dates,
    )
    weights = load_weights(settings.weights_path, boundary_path=settings.boundary_path)
    records = process_assets(selected, weights, settings)
    if dry_run:
        print(_records_json(records))
    elif store:
        store.write_records(records)
        store.rebuild_months({record.day.replace(day=1) for record in records})
        if records:
            store.refresh_dashboard(settings.weights_path)
        finished = datetime.now(UTC)
        records_by_day = {
            record.day: record.data_status
            for record in records
        }
        result = "success" if records else "no_new_data"
        store.append_quality(
            [
                run_id,
                started.isoformat(),
                finished.isoformat(),
                min(days).isoformat(),
                max(days).isoformat(),
                len({record.day for record in records}),
                sum(
                    status == "CHIRPS_V3_PRELIM_SAT"
                    for status in records_by_day.values()
                ),
                sum(
                    status == "CHIRPS_V3_FINAL_RNL"
                    for status in records_by_day.values()
                ),
                len(missing),
                0,
                store.request_count + 1,
                result,
            ]
        )
    print(
        json.dumps(
            {
                "requested_dates": len(days),
                "processed_dates": len({record.day for record in records}),
                "records": len(records),
                "missing_dates": len(missing),
                "skipped_dates": len(skipped),
                "dry_run": dry_run,
            },
            sort_keys=True,
        ),
        file=sys.stderr,
    )
    if records and len(records) % len(STATE_ORDER) != 0:
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = Settings.from_env()
    try:
        if args.command == "build-weights":
            result = build_weights(
                args.boundaries or settings.boundary_path,
                args.output or settings.weights_path,
            )
            print(
                json.dumps(
                    {
                        "states": len(result.states),
                        "window": [
                            int(result.window.row_off),
                            int(result.window.col_off),
                            int(result.window.height),
                            int(result.window.width),
                        ],
                        "boundary_sha256": result.boundary_sha256,
                    }
                )
            )
            return 0
        if args.command == "init-sheet":
            store = SheetStore.from_env(max_requests=settings.max_sheets_requests)
            store.init_sheet(through=args.through)
            print(f"Sheet initialized using {store.request_count} API requests")
            return 0
        if args.command == "migrate-calendar-start":
            store = SheetStore.from_env(max_requests=settings.max_sheets_requests)
            changed = store.migrate_calendar_start()
            action = "migrated" if changed else "already current"
            print(
                f"Sheet calendar is {action} at "
                f"{store.calendar_start().isoformat()} using "
                f"{store.request_count} API requests"
            )
            return 0
        if args.command == "refresh-dashboard":
            store = SheetStore.from_env(max_requests=settings.max_sheets_requests)
            snapshot = store.refresh_dashboard(settings.weights_path)
            print(
                "Dashboard refreshed through "
                f"{snapshot.latest_date.isoformat()} using "
                f"{store.request_count} API requests"
            )
            return 0
        return _run(args, settings)
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
