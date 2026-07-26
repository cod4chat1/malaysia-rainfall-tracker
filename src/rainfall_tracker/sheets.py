from __future__ import annotations

import calendar
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from .config import service_account_info_from_env, spreadsheet_id_from_env
from .constants import (
    CALENDAR_START,
    CONFIG_HEADERS,
    DAILY_HEADERS,
    MATRIX_HEADERS,
    MONTHLY_HEADERS,
    QUALITY_HEADERS,
    SCHEMA_VERSION,
    STATE_ORDER,
)
from .records import RainfallRecord, daily_row, matrix_row, monthly_row
from .summaries import summarize_month

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"


def column_letter(index: int) -> str:
    if index < 1:
        raise ValueError("Column index must be positive")
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


class SheetStore:
    def __init__(
        self,
        service: Any,
        spreadsheet_id: str,
        *,
        max_requests: int = 50,
    ) -> None:
        self.service = service
        self.spreadsheet_id = spreadsheet_id
        self.max_requests = max_requests
        self.request_count = 0

    @classmethod
    def from_env(cls, *, max_requests: int = 50) -> SheetStore:
        credentials = Credentials.from_service_account_info(
            service_account_info_from_env(),
            scopes=[SHEETS_SCOPE],
        )
        service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        return cls(service, spreadsheet_id_from_env(), max_requests=max_requests)

    def _execute(self, request: Any) -> Any:
        if self.request_count >= self.max_requests:
            raise RuntimeError("Google Sheets request ceiling reached")
        self.request_count += 1
        return request.execute(num_retries=3)

    def _values_update(self, range_name: str, values: list[list[object]]) -> None:
        self._execute(
            self.service.spreadsheets()
            .values()
            .update(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption="RAW",
                body={"values": values},
            )
        )

    def _metadata(self) -> dict[str, Any]:
        return self._execute(
            self.service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id,
                fields="sheets.properties",
            )
        )

    def init_sheet(self, *, through: date | None = None) -> None:
        through = through or date.today()
        if through < CALENDAR_START:
            raise ValueError("Sheet end date cannot predate 1981-01-01")
        days = (through - CALENDAR_START).days + 1
        months = (through.year - CALENDAR_START.year) * 12 + through.month
        required = {
            "Daily_State_Rainfall": (days * 16 + 1, len(DAILY_HEADERS)),
            "State_Daily_Matrix": (days + 1, len(MATRIX_HEADERS)),
            "Monthly_Summary": (months * 16 + 1, len(MONTHLY_HEADERS)),
            "Data_Quality": (5000, len(QUALITY_HEADERS)),
            "Configuration": (100, 2),
        }
        metadata = self._metadata()
        existing = {
            sheet["properties"]["title"]: sheet["properties"]
            for sheet in metadata.get("sheets", [])
        }
        requests: list[dict[str, Any]] = []
        for title, (rows, columns) in required.items():
            if title not in existing:
                requests.append(
                    {
                        "addSheet": {
                            "properties": {
                                "title": title,
                                "gridProperties": {
                                    "rowCount": rows,
                                    "columnCount": columns,
                                    "frozenRowCount": 1,
                                },
                            }
                        }
                    }
                )
            else:
                properties = existing[title]
                grid = properties["gridProperties"]
                if grid["rowCount"] < rows or grid["columnCount"] < columns:
                    requests.append(
                        {
                            "updateSheetProperties": {
                                "properties": {
                                    "sheetId": properties["sheetId"],
                                    "gridProperties": {
                                        "rowCount": max(rows, grid["rowCount"]),
                                        "columnCount": max(columns, grid["columnCount"]),
                                    },
                                },
                                "fields": (
                                    "gridProperties.rowCount,gridProperties.columnCount"
                                ),
                            }
                        }
                    )
        if requests:
            self._execute(
                self.service.spreadsheets().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body={"requests": requests},
                )
            )

        header_data = [
            {"range": "Daily_State_Rainfall!A1:O1", "values": [list(DAILY_HEADERS)]},
            {"range": "State_Daily_Matrix!A1:Q1", "values": [list(MATRIX_HEADERS)]},
            {"range": "Monthly_Summary!A1:J1", "values": [list(MONTHLY_HEADERS)]},
            {"range": "Data_Quality!A1:L1", "values": [list(QUALITY_HEADERS)]},
            {"range": "Configuration!A1:B1", "values": [list(CONFIG_HEADERS)]},
        ]
        self._execute(
            self.service.spreadsheets()
            .values()
            .batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"valueInputOption": "RAW", "data": header_data},
            )
        )

        chunk_days = 500
        for offset in range(0, days, chunk_days):
            count = min(chunk_days, days - offset)
            start_day = CALENDAR_START + timedelta(days=offset)
            daily_values: list[list[object]] = []
            matrix_values: list[list[object]] = []
            for day_offset in range(count):
                current = start_day + timedelta(days=day_offset)
                daily_values.extend([[current.isoformat(), state] for state in STATE_ORDER])
                matrix_values.append([current.isoformat()])
            start_daily_row = daily_row(start_day, STATE_ORDER[0])
            end_daily_row = start_daily_row + len(daily_values) - 1
            start_matrix_row = matrix_row(start_day)
            end_matrix_row = start_matrix_row + len(matrix_values) - 1
            self._execute(
                self.service.spreadsheets()
                .values()
                .batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body={
                        "valueInputOption": "RAW",
                        "data": [
                            {
                                "range": (
                                    f"Daily_State_Rainfall!A{start_daily_row}:"
                                    f"B{end_daily_row}"
                                ),
                                "values": daily_values,
                            },
                            {
                                "range": (
                                    f"State_Daily_Matrix!A{start_matrix_row}:"
                                    f"A{end_matrix_row}"
                                ),
                                "values": matrix_values,
                            },
                        ],
                    },
                )
            )

        configuration = [
            ["schema_version", SCHEMA_VERSION],
            ["calendar_start", CALENDAR_START.isoformat()],
            ["state_order", "|".join(STATE_ORDER)],
            ["dataset", "CHIRPS v3 daily Final rnl / Preliminary sat"],
            ["initialized_through", through.isoformat()],
        ]
        self._values_update("Configuration!A2:B6", configuration)

    def _read_config(self) -> dict[str, str]:
        response = self._execute(
            self.service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.spreadsheet_id,
                range="Configuration!A2:B100",
            )
        )
        return {
            row[0]: row[1]
            for row in response.get("values", [])
            if len(row) >= 2
        }

    def validate_schema(self) -> dict[str, str]:
        config = self._read_config()
        if config.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Sheet schema is missing or incompatible; run init-sheet")
        if config.get("state_order") != "|".join(STATE_ORDER):
            raise ValueError("Sheet state order is incompatible")
        return config

    def ensure_through(self, through: date) -> None:
        config = self.validate_schema()
        raw_initialized = config.get("initialized_through")
        if not raw_initialized:
            raise ValueError("Sheet has no initialized_through value; run init-sheet")
        initialized = date.fromisoformat(raw_initialized)
        if through <= initialized:
            return

        extend_to = through + timedelta(days=31)
        metadata = self._metadata()
        properties = {
            sheet["properties"]["title"]: sheet["properties"]
            for sheet in metadata.get("sheets", [])
        }
        days = (extend_to - CALENDAR_START).days + 1
        months = (extend_to.year - CALENDAR_START.year) * 12 + extend_to.month
        required = {
            "Daily_State_Rainfall": days * 16 + 1,
            "State_Daily_Matrix": days + 1,
            "Monthly_Summary": months * 16 + 1,
        }
        resize_requests: list[dict[str, Any]] = []
        for title, rows in required.items():
            sheet = properties.get(title)
            if sheet is None:
                raise ValueError(f"Required Sheet tab is missing: {title}")
            current_rows = sheet["gridProperties"]["rowCount"]
            if current_rows < rows:
                resize_requests.append(
                    {
                        "updateSheetProperties": {
                            "properties": {
                                "sheetId": sheet["sheetId"],
                                "gridProperties": {"rowCount": rows},
                            },
                            "fields": "gridProperties.rowCount",
                        }
                    }
                )
        if resize_requests:
            self._execute(
                self.service.spreadsheets().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body={"requests": resize_requests},
                )
            )

        start = initialized + timedelta(days=1)
        count = (extend_to - start).days + 1
        daily_values: list[list[object]] = []
        matrix_values: list[list[object]] = []
        for offset in range(count):
            current = start + timedelta(days=offset)
            daily_values.extend([[current.isoformat(), state] for state in STATE_ORDER])
            matrix_values.append([current.isoformat()])
        start_daily = daily_row(start, STATE_ORDER[0])
        end_daily = daily_row(extend_to, STATE_ORDER[-1])
        start_matrix = matrix_row(start)
        end_matrix = matrix_row(extend_to)
        self._execute(
            self.service.spreadsheets()
            .values()
            .batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={
                    "valueInputOption": "RAW",
                    "data": [
                        {
                            "range": (
                                f"Daily_State_Rainfall!A{start_daily}:B{end_daily}"
                            ),
                            "values": daily_values,
                        },
                        {
                            "range": (
                                f"State_Daily_Matrix!A{start_matrix}:A{end_matrix}"
                            ),
                            "values": matrix_values,
                        },
                        {
                            "range": "Configuration!B6",
                            "values": [[extend_to.isoformat()]],
                        },
                    ],
                },
            )
        )

    def get_statuses(self, days: list[date]) -> dict[date, str | None]:
        if not days:
            return {}
        start = min(days)
        end = max(days)
        start_row = daily_row(start, STATE_ORDER[0])
        end_row = daily_row(end, STATE_ORDER[-1])
        response = self._execute(
            self.service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.spreadsheet_id,
                range=f"Daily_State_Rainfall!M{start_row}:M{end_row}",
            )
        )
        raw = response.get("values", [])
        expected_rows = (end - start).days * 16 + 16
        padded = [row[0] if row else "" for row in raw]
        padded.extend([""] * (expected_rows - len(padded)))
        result: dict[date, str | None] = {}
        for day in days:
            offset = (day - start).days * 16
            statuses = {value for value in padded[offset : offset + 16] if value}
            result[day] = statuses.pop() if len(statuses) == 1 else None
        return result

    def write_records(self, records: Iterable[RainfallRecord]) -> None:
        grouped: dict[date, list[RainfallRecord]] = defaultdict(list)
        for record in records:
            grouped[record.day].append(record)
        if not grouped:
            return
        data: list[dict[str, object]] = []
        for day, daily in sorted(grouped.items()):
            ordered = sorted(daily, key=lambda record: STATE_ORDER.index(record.state))
            if tuple(record.state for record in ordered) != STATE_ORDER:
                raise ValueError(f"Expected exactly 16 ordered records for {day}")
            start_row = daily_row(day, STATE_ORDER[0])
            end_row = daily_row(day, STATE_ORDER[-1])
            data.append(
                {
                    "range": f"Daily_State_Rainfall!A{start_row}:O{end_row}",
                    "values": [record.sheet_values() for record in ordered],
                }
            )
            data.append(
                {
                    "range": f"State_Daily_Matrix!A{matrix_row(day)}:Q{matrix_row(day)}",
                    "values": [
                        [day.isoformat(), *[round(record.average_mm, 3) for record in ordered]]
                    ],
                }
            )
        self._execute(
            self.service.spreadsheets()
            .values()
            .batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"valueInputOption": "RAW", "data": data},
            )
        )

    def rebuild_months(self, months: set[date]) -> None:
        for month in sorted(months):
            last_day = calendar.monthrange(month.year, month.month)[1]
            start_row = daily_row(month, STATE_ORDER[0])
            end_row = daily_row(month.replace(day=last_day), STATE_ORDER[-1])
            response = self._execute(
                self.service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"Daily_State_Rainfall!A{start_row}:O{end_row}",
                )
            )
            records_by_state: dict[str, list[RainfallRecord]] = defaultdict(list)
            for row in response.get("values", []):
                if len(row) < 15 or not row[3] or not row[12]:
                    continue
                processed = datetime.fromisoformat(str(row[14]).replace("Z", "+00:00"))
                records_by_state[str(row[1])].append(
                    RainfallRecord(
                        day=date.fromisoformat(str(row[0])),
                        state=str(row[1]),
                        average_mm=float(row[3]),
                        median_mm=float(row[4]),
                        maximum_mm=float(row[5]),
                        area_above_1mm_pct=float(row[6]),
                        area_above_10mm_pct=float(row[7]),
                        area_above_20mm_pct=float(row[8]),
                        area_above_50mm_pct=float(row[9]),
                        valid_grid_cells=int(row[10]),
                        valid_area_pct=float(row[11]),
                        data_status=str(row[12]),
                        source_url=str(row[13]),
                        processed_at_utc=processed.astimezone(UTC),
                    )
                )
            values: list[list[object]] = []
            for state in STATE_ORDER:
                state_records = records_by_state.get(state, [])
                if state_records:
                    values.append(summarize_month(state_records).sheet_values())
                else:
                    area_type = (
                        "Federal Territory"
                        if state in {"Kuala Lumpur", "Putrajaya", "Labuan"}
                        else "State"
                    )
                    values.append([month.strftime("%Y-%m"), state, area_type])
            start = monthly_row(month, STATE_ORDER[0])
            end = monthly_row(month, STATE_ORDER[-1])
            self._values_update(f"Monthly_Summary!A{start}:J{end}", values)

    def append_quality(self, values: list[object]) -> None:
        self._execute(
            self.service.spreadsheets()
            .values()
            .append(
                spreadsheetId=self.spreadsheet_id,
                range="Data_Quality!A:L",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": [values]},
            )
        )
