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
from .dashboard import DashboardSnapshot, build_dashboard_snapshot
from .records import RainfallRecord, daily_row, matrix_row, monthly_row
from .summaries import summarize_month

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
DASHBOARD_MAX_DAILY_ROWS = 6000
DASHBOARD_DAILY_COLUMNS = 65
DASHBOARD_MONTHLY_START = 65
DASHBOARD_FOCUS_START = 100
DASHBOARD_COMPARE_START = 105
DASHBOARD_MONTH_CHART_START = 110
DASHBOARD_RANKING_START = 116
DASHBOARD_HEATMAP_START = 124
DASHBOARD_DATA_COLUMNS = 140


def column_letter(index: int) -> str:
    if index < 1:
        raise ValueError("Column index must be positive")
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _a1_column(zero_based_index: int) -> str:
    return column_letter(zero_based_index + 1)


def _rgb(red: int, green: int, blue: int) -> dict[str, float]:
    return {"red": red / 255, "green": green / 255, "blue": blue / 255}


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

    def _values_clear(self, range_name: str) -> None:
        self._execute(
            self.service.spreadsheets()
            .values()
            .clear(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                body={},
            )
        )

    def _batch_update(self, requests: list[dict[str, Any]]) -> None:
        if not requests:
            return
        self._execute(
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"requests": requests},
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
            raise ValueError(
                f"Sheet end date cannot predate {CALENDAR_START.isoformat()}"
            )
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

    def calendar_start(self) -> date:
        raw = self._read_config().get("calendar_start")
        if not raw:
            raise ValueError("Sheet calendar start is missing")
        return date.fromisoformat(raw)

    def migrate_calendar_start(self) -> bool:
        response = self._execute(
            self.service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.spreadsheet_id,
                range="Configuration!A2:B100",
            )
        )
        config_rows = response.get("values", [])
        config = {
            row[0]: row[1]
            for row in config_rows
            if len(row) >= 2
        }
        raw_start = config.get("calendar_start")
        raw_through = config.get("initialized_through")
        if not raw_start or not raw_through:
            raise ValueError("Sheet calendar configuration is incomplete")
        previous_start = date.fromisoformat(raw_start)
        initialized_through = date.fromisoformat(raw_through)
        if previous_start == CALENDAR_START:
            self.init_sheet(through=initialized_through)
            return False
        if previous_start < CALENDAR_START:
            raise ValueError(
                "Calendar migration cannot remove existing history: found "
                f"{previous_start.isoformat()}, requested {CALENDAR_START.isoformat()}"
            )
        if (previous_start.month, previous_start.day) != (1, 1):
            raise ValueError("Existing calendar start must be January 1")

        day_count = (previous_start - CALENDAR_START).days
        month_count = (
            (previous_start.year - CALENDAR_START.year) * 12
            + previous_start.month
            - CALENDAR_START.month
        )
        metadata = self._metadata()
        properties = {
            sheet["properties"]["title"]: sheet["properties"]
            for sheet in metadata.get("sheets", [])
        }
        required_tabs = {
            "Daily_State_Rainfall",
            "State_Daily_Matrix",
            "Monthly_Summary",
            "Configuration",
        }
        missing_tabs = required_tabs - properties.keys()
        if missing_tabs:
            raise ValueError(
                "Required Sheet tabs are missing: " + ", ".join(sorted(missing_tabs))
            )

        calendar_row_offset = next(
            (
                index
                for index, row in enumerate(config_rows)
                if row and row[0] == "calendar_start"
            ),
            None,
        )
        if calendar_row_offset is None:
            raise ValueError("Calendar start configuration row is missing")
        calendar_grid_row = 1 + calendar_row_offset

        requests = []
        for title, inserted_rows in (
            ("Daily_State_Rainfall", day_count * len(STATE_ORDER)),
            ("State_Daily_Matrix", day_count),
            ("Monthly_Summary", month_count * len(STATE_ORDER)),
        ):
            requests.append(
                {
                    "insertDimension": {
                        "range": {
                            "sheetId": properties[title]["sheetId"],
                            "dimension": "ROWS",
                            "startIndex": 1,
                            "endIndex": 1 + inserted_rows,
                        },
                        "inheritFromBefore": False,
                    }
                }
            )
        requests.append(
            {
                "updateCells": {
                    "range": {
                        "sheetId": properties["Configuration"]["sheetId"],
                        "startRowIndex": calendar_grid_row,
                        "endRowIndex": calendar_grid_row + 1,
                        "startColumnIndex": 1,
                        "endColumnIndex": 2,
                    },
                    "rows": [
                        {
                            "values": [
                                {
                                    "userEnteredValue": {
                                        "stringValue": CALENDAR_START.isoformat()
                                    }
                                }
                            ]
                        }
                    ],
                    "fields": "userEnteredValue",
                }
            }
        )
        self._execute(
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"requests": requests},
            )
        )
        self.init_sheet(through=initialized_through)
        return True

    def validate_schema(self) -> dict[str, str]:
        config = self._read_config()
        if config.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Sheet schema is missing or incompatible; run init-sheet")
        if config.get("calendar_start") != CALENDAR_START.isoformat():
            raise ValueError(
                "Sheet calendar start is incompatible: expected "
                f"{CALENDAR_START.isoformat()}, found "
                f"{config.get('calendar_start') or 'missing'}"
            )
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

    def _dashboard_metadata(self) -> dict[str, Any]:
        return self._execute(
            self.service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id,
                fields="sheets(properties,charts)",
            )
        )

    def _ensure_dashboard_structure(self) -> dict[str, dict[str, Any]]:
        metadata = self._dashboard_metadata()
        sheets = {
            item["properties"]["title"]: item
            for item in metadata.get("sheets", [])
        }
        requests: list[dict[str, Any]] = []
        created_dashboard = "Dashboard" not in sheets
        if created_dashboard:
            requests.append(
                {
                    "addSheet": {
                        "properties": {
                            "title": "Dashboard",
                            "index": 0,
                            "gridProperties": {
                                "rowCount": 100,
                                "columnCount": 18,
                                "hideGridlines": True,
                            },
                        }
                    }
                }
            )
        if "Dashboard_Data" not in sheets:
            requests.append(
                {
                    "addSheet": {
                        "properties": {
                            "title": "Dashboard_Data",
                            "gridProperties": {
                                "rowCount": DASHBOARD_MAX_DAILY_ROWS + 1,
                                "columnCount": DASHBOARD_DATA_COLUMNS,
                                "hideGridlines": True,
                            },
                        }
                    }
                }
            )
        self._batch_update(requests)
        if requests:
            metadata = self._dashboard_metadata()
            sheets = {
                item["properties"]["title"]: item
                for item in metadata.get("sheets", [])
            }

        dashboard_id = sheets["Dashboard"]["properties"]["sheetId"]
        data_id = sheets["Dashboard_Data"]["properties"]["sheetId"]
        style_requests: list[dict[str, Any]] = [
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": dashboard_id,
                        "index": 0,
                        "gridProperties": {
                            "rowCount": max(
                                100,
                                sheets["Dashboard"]["properties"]["gridProperties"][
                                    "rowCount"
                                ],
                            ),
                            "columnCount": max(
                                18,
                                sheets["Dashboard"]["properties"]["gridProperties"][
                                    "columnCount"
                                ],
                            ),
                            "hideGridlines": True,
                            "frozenRowCount": 1,
                        },
                    },
                    "fields": (
                        "index,gridProperties.rowCount,"
                        "gridProperties.columnCount,gridProperties.hideGridlines,"
                        "gridProperties.frozenRowCount"
                    ),
                }
            },
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": data_id,
                        "gridProperties": {
                            "rowCount": max(
                                DASHBOARD_MAX_DAILY_ROWS + 1,
                                sheets["Dashboard_Data"]["properties"][
                                    "gridProperties"
                                ]["rowCount"],
                            ),
                            "columnCount": max(
                                DASHBOARD_DATA_COLUMNS,
                                sheets["Dashboard_Data"]["properties"][
                                    "gridProperties"
                                ]["columnCount"],
                            ),
                            "hideGridlines": True,
                            "frozenRowCount": 1,
                        },
                        "hidden": True,
                    },
                    "fields": (
                        "gridProperties.rowCount,"
                        "gridProperties.columnCount,gridProperties.hideGridlines,"
                        "gridProperties.frozenRowCount,hidden"
                    ),
                }
            },
        ]
        if created_dashboard:
            style_requests.append(
                {
                    "mergeCells": {
                        "range": {
                            "sheetId": dashboard_id,
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": 18,
                        },
                        "mergeType": "MERGE_ALL",
                    }
                }
            )

        state_values = [{"userEnteredValue": state} for state in STATE_ORDER]
        for start_row, values in (
            (3, state_values),
            (4, state_values),
            (5, state_values),
            (
                6,
                [
                    {"userEnteredValue": "90 days"},
                    {"userEnteredValue": "180 days"},
                    {"userEnteredValue": "1 year"},
                    {"userEnteredValue": "3 years"},
                    {"userEnteredValue": "All"},
                ],
            ),
            (
                7,
                [
                    {"userEnteredValue": "Daily"},
                    {"userEnteredValue": "Monthly"},
                ],
            ),
        ):
            style_requests.append(
                {
                    "setDataValidation": {
                        "range": {
                            "sheetId": dashboard_id,
                            "startRowIndex": start_row,
                            "endRowIndex": start_row + 1,
                            "startColumnIndex": 1,
                            "endColumnIndex": 2,
                        },
                        "rule": {
                            "condition": {
                                "type": "ONE_OF_LIST",
                                "values": values,
                            },
                            "strict": True,
                            "showCustomUi": True,
                        },
                    }
                }
            )

        style_requests.extend(
            [
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": dashboard_id,
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": 18,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColorStyle": {"rgbColor": _rgb(243, 244, 246)},
                                "textFormat": {
                                    "bold": True,
                                    "fontSize": 18,
                                    "foregroundColorStyle": {
                                        "rgbColor": _rgb(17, 24, 39)
                                    },
                                },
                                "verticalAlignment": "MIDDLE",
                            }
                        },
                        "fields": "userEnteredFormat",
                    }
                },
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": dashboard_id,
                            "startRowIndex": 2,
                            "endRowIndex": 9,
                            "startColumnIndex": 0,
                            "endColumnIndex": 1,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColorStyle": {"rgbColor": _rgb(229, 231, 235)},
                                "textFormat": {
                                    "bold": True,
                                    "foregroundColorStyle": {
                                        "rgbColor": _rgb(31, 41, 55)
                                    },
                                },
                            }
                        },
                        "fields": "userEnteredFormat",
                    }
                },
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": dashboard_id,
                            "startRowIndex": 2,
                            "endRowIndex": 9,
                            "startColumnIndex": 1,
                            "endColumnIndex": 2,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColorStyle": {"rgbColor": _rgb(239, 246, 255)},
                                "textFormat": {
                                    "bold": True,
                                    "foregroundColorStyle": {
                                        "rgbColor": _rgb(30, 64, 175)
                                    },
                                },
                            }
                        },
                        "fields": "userEnteredFormat",
                    }
                },
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": dashboard_id,
                            "startRowIndex": 10,
                            "endRowIndex": 11,
                            "startColumnIndex": 0,
                            "endColumnIndex": 12,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColorStyle": {"rgbColor": _rgb(229, 231, 235)},
                                "horizontalAlignment": "CENTER",
                                "textFormat": {
                                    "bold": True,
                                    "foregroundColorStyle": {
                                        "rgbColor": _rgb(55, 65, 81)
                                    },
                                },
                            }
                        },
                        "fields": "userEnteredFormat",
                    }
                },
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": dashboard_id,
                            "startRowIndex": 11,
                            "endRowIndex": 12,
                            "startColumnIndex": 0,
                            "endColumnIndex": 12,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColorStyle": {"rgbColor": _rgb(248, 250, 252)},
                                "horizontalAlignment": "CENTER",
                                "verticalAlignment": "MIDDLE",
                                "textFormat": {
                                    "bold": True,
                                    "fontSize": 15,
                                    "foregroundColorStyle": {
                                        "rgbColor": _rgb(15, 23, 42)
                                    },
                                },
                            }
                        },
                        "fields": "userEnteredFormat",
                    }
                },
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": dashboard_id,
                            "startRowIndex": 35,
                            "endRowIndex": 36,
                            "startColumnIndex": 9,
                            "endColumnIndex": 16,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColorStyle": {
                                    "rgbColor": _rgb(30, 64, 175)
                                },
                                "textFormat": {
                                    "bold": True,
                                    "foregroundColorStyle": {
                                        "rgbColor": _rgb(255, 255, 255)
                                    },
                                },
                            }
                        },
                        "fields": "userEnteredFormat",
                    }
                },
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": dashboard_id,
                            "startRowIndex": 57,
                            "endRowIndex": 58,
                            "startColumnIndex": 0,
                            "endColumnIndex": 13,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColorStyle": {
                                    "rgbColor": _rgb(30, 64, 175)
                                },
                                "textFormat": {
                                    "bold": True,
                                    "foregroundColorStyle": {
                                        "rgbColor": _rgb(255, 255, 255)
                                    },
                                },
                            }
                        },
                        "fields": "userEnteredFormat",
                    }
                },
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": dashboard_id,
                            "startRowIndex": 36,
                            "endRowIndex": 52,
                            "startColumnIndex": 11,
                            "endColumnIndex": 12,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "numberFormat": {
                                    "type": "PERCENT",
                                    "pattern": "0.0%",
                                }
                            }
                        },
                        "fields": "userEnteredFormat.numberFormat",
                    }
                },
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": dashboard_id,
                            "dimension": "COLUMNS",
                            "startIndex": 0,
                            "endIndex": 18,
                        },
                        "properties": {"pixelSize": 105},
                        "fields": "pixelSize",
                    }
                },
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": dashboard_id,
                            "dimension": "COLUMNS",
                            "startIndex": 0,
                            "endIndex": 2,
                        },
                        "properties": {"pixelSize": 150},
                        "fields": "pixelSize",
                    }
                },
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": dashboard_id,
                            "dimension": "COLUMNS",
                            "startIndex": 9,
                            "endIndex": 16,
                        },
                        "properties": {"pixelSize": 130},
                        "fields": "pixelSize",
                    }
                },
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [
                                {
                                    "sheetId": dashboard_id,
                                    "startRowIndex": 58,
                                    "endRowIndex": 74,
                                    "startColumnIndex": 1,
                                    "endColumnIndex": 13,
                                }
                            ],
                            "gradientRule": {
                                "minpoint": {
                                    "colorStyle": {"rgbColor": _rgb(255, 247, 188)},
                                    "type": "MIN",
                                },
                                "midpoint": {
                                    "colorStyle": {"rgbColor": _rgb(127, 205, 187)},
                                    "type": "PERCENTILE",
                                    "value": "50",
                                },
                                "maxpoint": {
                                    "colorStyle": {"rgbColor": _rgb(44, 127, 184)},
                                    "type": "MAX",
                                },
                            },
                        },
                        "index": 0,
                    }
                },
            ]
        )

        if not created_dashboard:
            style_requests = [
                request
                for request in style_requests
                if "addConditionalFormatRule" not in request
            ]

        existing_titles = {
            chart.get("spec", {}).get("title")
            for chart in sheets["Dashboard"].get("charts", [])
        }
        chart_specs = [
            (
                "Focus state: actual vs moving averages",
                DASHBOARD_FOCUS_START,
                3,
                13,
                0,
                ["Actual rainfall", "7-day moving average", "30-day moving average"],
            ),
            (
                "Selected states: rolling or monthly comparison",
                DASHBOARD_COMPARE_START,
                3,
                13,
                9,
                ["State 1", "State 2", "State 3"],
            ),
            (
                "Monthly totals vs seasonal normal",
                DASHBOARD_MONTH_CHART_START,
                4,
                35,
                0,
                ["State 1", "State 2", "State 3", "State 1 normal"],
            ),
        ]
        for title, start_column, _series_count, row_index, column_index, labels in chart_specs:
            if title in existing_titles:
                continue
            series = []
            for offset, _label in enumerate(labels, start=1):
                series.append(
                    {
                        "series": {
                            "sourceRange": {
                                "sources": [
                                    {
                                        "sheetId": data_id,
                                        "startRowIndex": 0,
                                        "endRowIndex": DASHBOARD_MAX_DAILY_ROWS + 1,
                                        "startColumnIndex": start_column + offset,
                                        "endColumnIndex": start_column + offset + 1,
                                    }
                                ]
                            }
                        },
                        "targetAxis": "LEFT_AXIS",
                        "colorStyle": {
                            "rgbColor": (
                                _rgb(37, 99, 235)
                                if offset == 1
                                else _rgb(100 + offset * 20, 116, 139)
                            )
                        },
                    }
                )
            style_requests.append(
                {
                    "addChart": {
                        "chart": {
                            "spec": {
                                "title": title,
                                "fontName": "Arial",
                                "basicChart": {
                                    "chartType": "LINE",
                                    "legendPosition": "BOTTOM_LEGEND",
                                    "axis": [
                                        {
                                            "position": "BOTTOM_AXIS",
                                            "title": "Date",
                                        },
                                        {
                                            "position": "LEFT_AXIS",
                                            "title": "Rainfall (mm)",
                                        },
                                    ],
                                    "domains": [
                                        {
                                            "domain": {
                                                "sourceRange": {
                                                    "sources": [
                                                        {
                                                            "sheetId": data_id,
                                                            "startRowIndex": 0,
                                                            "endRowIndex": (
                                                                DASHBOARD_MAX_DAILY_ROWS
                                                                + 1
                                                            ),
                                                            "startColumnIndex": start_column,
                                                            "endColumnIndex": (
                                                                start_column + 1
                                                            ),
                                                        }
                                                    ]
                                                }
                                            }
                                        }
                                    ],
                                    "series": series,
                                    "headerCount": 1,
                                },
                            },
                            "position": {
                                "overlayPosition": {
                                    "anchorCell": {
                                        "sheetId": dashboard_id,
                                        "rowIndex": row_index,
                                        "columnIndex": column_index,
                                    },
                                    "widthPixels": 760,
                                    "heightPixels": 360,
                                }
                            },
                        }
                    }
                }
            )
        self._batch_update(style_requests)
        return sheets

    def _dashboard_source_values(
        self,
    ) -> tuple[list[list[object]], list[list[object]], list[list[object]]]:
        config = self.validate_schema()
        initialized = date.fromisoformat(config["initialized_through"])
        matrix_end = matrix_row(initialized)
        matrix_response = self._execute(
            self.service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.spreadsheet_id,
                range=f"State_Daily_Matrix!A1:Q{matrix_end}",
            )
        )
        matrix_values = matrix_response.get("values", [])
        latest_date = next(
            (
                date.fromisoformat(str(row[0])[:10])
                for row in reversed(matrix_values[1:])
                if len(row) > 1 and any(value not in ("", None) for value in row[1:])
            ),
            None,
        )
        if latest_date is None:
            raise ValueError("Rainfall matrix has no observations for the dashboard")
        month_end = monthly_row(initialized.replace(day=1), STATE_ORDER[-1])
        monthly_response = self._execute(
            self.service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.spreadsheet_id,
                range=f"Monthly_Summary!A1:J{month_end}",
            )
        )
        detail_start = daily_row(latest_date, STATE_ORDER[0])
        detail_end = daily_row(latest_date, STATE_ORDER[-1])
        detail_response = self._execute(
            self.service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.spreadsheet_id,
                range=f"Daily_State_Rainfall!A{detail_start}:O{detail_end}",
            )
        )
        return (
            matrix_values,
            monthly_response.get("values", []),
            detail_response.get("values", []),
        )

    def _dashboard_formula_rows(self) -> list[dict[str, object]]:
        daily_end = DASHBOARD_MAX_DAILY_ROWS + 1
        actual_start = _a1_column(1)
        actual_end = _a1_column(16)
        ma7_start = _a1_column(17)
        ma7_end = _a1_column(32)
        ma30_start = _a1_column(33)
        ma30_end = _a1_column(48)
        roll_start = _a1_column(49)
        roll_end = _a1_column(64)
        monthly_date = _a1_column(DASHBOARD_MONTHLY_START)
        monthly_total_start = _a1_column(DASHBOARD_MONTHLY_START + 1)
        monthly_total_end = _a1_column(DASHBOARD_MONTHLY_START + 16)
        monthly_normal_start = _a1_column(DASHBOARD_MONTHLY_START + 17)
        monthly_normal_end = _a1_column(DASHBOARD_MONTHLY_START + 32)

        focus_formula = (
            f'=FILTER({{$A$2:$A${daily_end},'
            f'INDEX(${actual_start}$2:${actual_end}${daily_end},0,'
            f'MATCH(Dashboard!$B$4,${actual_start}$1:${actual_end}$1,0)),'
            f'INDEX(${ma7_start}$2:${ma7_end}${daily_end},0,'
            f'MATCH(Dashboard!$B$4&" MA7",${ma7_start}$1:${ma7_end}$1,0)),'
            f'INDEX(${ma30_start}$2:${ma30_end}${daily_end},0,'
            f'MATCH(Dashboard!$B$4&" MA30",${ma30_start}$1:${ma30_end}$1,0))}},'
            f'$A$2:$A${daily_end}<>"",$A$2:$A${daily_end}>=Dashboard!$B$10)'
        )
        daily_compare = (
            f'FILTER({{$A$2:$A${daily_end},'
            f'INDEX(${roll_start}$2:${roll_end}${daily_end},0,'
            f'MATCH(Dashboard!$B$4&" Rolling30",${roll_start}$1:${roll_end}$1,0)),'
            f'INDEX(${roll_start}$2:${roll_end}${daily_end},0,'
            f'MATCH(Dashboard!$B$5&" Rolling30",${roll_start}$1:${roll_end}$1,0)),'
            f'INDEX(${roll_start}$2:${roll_end}${daily_end},0,'
            f'MATCH(Dashboard!$B$6&" Rolling30",${roll_start}$1:${roll_end}$1,0))}},'
            f'$A$2:$A${daily_end}<>"",$A$2:$A${daily_end}>=Dashboard!$B$10)'
        )
        monthly_compare = (
            f'FILTER({{${monthly_date}$2:${monthly_date}$500,'
            f'INDEX(${monthly_total_start}$2:${monthly_total_end}$500,0,'
            f'MATCH(Dashboard!$B$4&" Total",'
            f'${monthly_total_start}$1:${monthly_total_end}$1,0)),'
            f'INDEX(${monthly_total_start}$2:${monthly_total_end}$500,0,'
            f'MATCH(Dashboard!$B$5&" Total",'
            f'${monthly_total_start}$1:${monthly_total_end}$1,0)),'
            f'INDEX(${monthly_total_start}$2:${monthly_total_end}$500,0,'
            f'MATCH(Dashboard!$B$6&" Total",'
            f'${monthly_total_start}$1:${monthly_total_end}$1,0))}},'
            f'${monthly_date}$2:${monthly_date}$500<>"",'
            f'${monthly_date}$2:${monthly_date}$500>=Dashboard!$B$10)'
        )
        comparison_formula = (
            f'=IF(Dashboard!$B$8="Daily",{daily_compare},{monthly_compare})'
        )
        monthly_chart_formula = (
            f'=FILTER({{${monthly_date}$2:${monthly_date}$500,'
            f'INDEX(${monthly_total_start}$2:${monthly_total_end}$500,0,'
            f'MATCH(Dashboard!$B$4&" Total",'
            f'${monthly_total_start}$1:${monthly_total_end}$1,0)),'
            f'INDEX(${monthly_total_start}$2:${monthly_total_end}$500,0,'
            f'MATCH(Dashboard!$B$5&" Total",'
            f'${monthly_total_start}$1:${monthly_total_end}$1,0)),'
            f'INDEX(${monthly_total_start}$2:${monthly_total_end}$500,0,'
            f'MATCH(Dashboard!$B$6&" Total",'
            f'${monthly_total_start}$1:${monthly_total_end}$1,0)),'
            f'INDEX(${monthly_normal_start}$2:${monthly_normal_end}$500,0,'
            f'MATCH(Dashboard!$B$4&" Normal",'
            f'${monthly_normal_start}$1:${monthly_normal_end}$1,0))}},'
            f'${monthly_date}$2:${monthly_date}$500<>"",'
            f'${monthly_date}$2:${monthly_date}$500>=Dashboard!$B$10)'
        )
        return [
            {
                "range": (
                    f"Dashboard_Data!{_a1_column(DASHBOARD_FOCUS_START)}1:"
                    f"{_a1_column(DASHBOARD_FOCUS_START + 3)}2"
                ),
                "values": [
                    ["Date", "Actual rainfall", "7-day moving average", "30-day moving average"],
                    [focus_formula],
                ],
            },
            {
                "range": (
                    f"Dashboard_Data!{_a1_column(DASHBOARD_COMPARE_START)}1:"
                    f"{_a1_column(DASHBOARD_COMPARE_START + 3)}2"
                ),
                "values": [
                    ["Date", "State 1", "State 2", "State 3"],
                    [comparison_formula],
                ],
            },
            {
                "range": (
                    f"Dashboard_Data!{_a1_column(DASHBOARD_MONTH_CHART_START)}1:"
                    f"{_a1_column(DASHBOARD_MONTH_CHART_START + 4)}2"
                ),
                "values": [
                    ["Month", "State 1", "State 2", "State 3", "State 1 normal"],
                    [monthly_chart_formula],
                ],
            },
        ]

    def _dashboard_control_values(self) -> list[str]:
        defaults = ["Johor", "Sabah", "Sarawak", "1 year", "Daily"]
        try:
            response = self._execute(
                self.service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=self.spreadsheet_id,
                    range="Dashboard!B4:B8",
                )
            )
        except Exception:
            return defaults
        rows = response.get("values", [])
        return [
            str(rows[index][0]).strip()
            if index < len(rows) and rows[index] and str(rows[index][0]).strip()
            else default
            for index, default in enumerate(defaults)
        ]

    def _dashboard_main_values(
        self,
        snapshot: DashboardSnapshot,
        controls: list[str],
    ) -> list[dict[str, object]]:
        focus_col = _a1_column(DASHBOARD_FOCUS_START)
        focus_actual = _a1_column(DASHBOARD_FOCUS_START + 1)
        focus_ma7 = _a1_column(DASHBOARD_FOCUS_START + 2)
        focus_ma30 = _a1_column(DASHBOARD_FOCUS_START + 3)
        month_actual = _a1_column(DASHBOARD_MONTH_CHART_START + 1)
        month_normal = _a1_column(DASHBOARD_MONTH_CHART_START + 4)
        last_daily = DASHBOARD_MAX_DAILY_ROWS + 1
        values = [
            ["Malaysia Rainfall Dashboard"],
            [],
            [],
            ["State 1 - focus", controls[0]],
            ["State 2 - compare", controls[1]],
            ["State 3 - compare", controls[2]],
            ["Period", controls[3]],
            ["Frequency", controls[4]],
            [
                "Latest valid date",
                f'=LOOKUP(2,1/(Dashboard_Data!{focus_col}2:{focus_col}{last_daily}<>""),'
                f'Dashboard_Data!{focus_col}2:{focus_col}{last_daily})',
            ],
            [
                "Cutoff date",
                '=IF(B7="90 days",B9-89,IF(B7="180 days",B9-179,'
                'IF(B7="1 year",EDATE(B9,-12),IF(B7="3 years",EDATE(B9,-36),'
                "DATE(2013,1,1)))))",
            ],
            [
                "Latest rainfall",
                "",
                "7-day average",
                "",
                "30-day average",
                "",
                "Current month",
                "",
                "Vs seasonal normal",
                "",
                "Source latency",
            ],
            [
                f'=LOOKUP(2,1/(Dashboard_Data!{focus_actual}2:{focus_actual}{last_daily}<>""),'
                f'Dashboard_Data!{focus_actual}2:{focus_actual}{last_daily})',
                "",
                f'=LOOKUP(2,1/(Dashboard_Data!{focus_ma7}2:{focus_ma7}{last_daily}<>""),'
                f'Dashboard_Data!{focus_ma7}2:{focus_ma7}{last_daily})',
                "",
                f'=LOOKUP(2,1/(Dashboard_Data!{focus_ma30}2:{focus_ma30}{last_daily}<>""),'
                f'Dashboard_Data!{focus_ma30}2:{focus_ma30}{last_daily})',
                "",
                f'=LOOKUP(2,1/(Dashboard_Data!{month_actual}2:{month_actual}500<>""),'
                f'Dashboard_Data!{month_actual}2:{month_actual}500)',
                "",
                (
                    f'=IFERROR(LOOKUP(2,1/(Dashboard_Data!{month_actual}2:'
                    f'{month_actual}500<>""),Dashboard_Data!{month_actual}2:'
                    f'{month_actual}500)/(LOOKUP(2,1/(Dashboard_Data!{month_normal}2:'
                    f'{month_normal}500<>""),Dashboard_Data!{month_normal}2:'
                    f'{month_normal}500)*DAY(B9)/DAY(EOMONTH(B9,0)))-1,"")'
                ),
                "",
                "=TODAY()-B9",
            ],
            [
                "mm/day",
                "",
                "mm/day",
                "",
                "mm/day",
                "",
                "mm month-to-date",
                "",
                "month-to-date vs prorated normal",
                "",
                "days",
            ],
        ]
        ranking_end = 36 + len(snapshot.ranking_rows)
        heatmap_end = 58 + len(snapshot.heatmap_rows)
        return [
            {"range": "Dashboard!A1:L13", "values": values},
            {
                "range": f"Dashboard!J36:P{ranking_end}",
                "values": [snapshot.ranking_headers, *snapshot.ranking_rows],
            },
            {
                "range": f"Dashboard!A58:M{heatmap_end}",
                "values": [snapshot.heatmap_headers, *snapshot.heatmap_rows],
            },
        ]

    def refresh_dashboard(self) -> DashboardSnapshot:
        self._ensure_dashboard_structure()
        controls = self._dashboard_control_values()
        matrix_values, monthly_values, detail_values = self._dashboard_source_values()
        snapshot = build_dashboard_snapshot(
            matrix_values,
            monthly_values,
            detail_values,
        )
        if len(snapshot.daily_rows) > DASHBOARD_MAX_DAILY_ROWS:
            raise ValueError("Dashboard daily history exceeds its configured helper range")
        self._values_clear(
            f"Dashboard_Data!A1:{_a1_column(DASHBOARD_DATA_COLUMNS - 1)}"
            f"{DASHBOARD_MAX_DAILY_ROWS + 1}"
        )
        self._values_clear("Dashboard!A1:R100")
        raw_data = [
            {
                "range": (
                    f"Dashboard_Data!A1:{_a1_column(DASHBOARD_DAILY_COLUMNS - 1)}"
                    f"{len(snapshot.daily_rows) + 1}"
                ),
                "values": [snapshot.daily_headers, *snapshot.daily_rows],
            },
            {
                "range": (
                    f"Dashboard_Data!{_a1_column(DASHBOARD_MONTHLY_START)}1:"
                    f"{_a1_column(DASHBOARD_MONTHLY_START + len(snapshot.monthly_headers) - 1)}"
                    f"{len(snapshot.monthly_rows) + 1}"
                ),
                "values": [snapshot.monthly_headers, *snapshot.monthly_rows],
            },
        ]
        self._execute(
            self.service.spreadsheets()
            .values()
            .batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"valueInputOption": "USER_ENTERED", "data": raw_data},
            )
        )
        formula_data = [
            *self._dashboard_formula_rows(),
            *self._dashboard_main_values(snapshot, controls),
        ]
        self._execute(
            self.service.spreadsheets()
            .values()
            .batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"valueInputOption": "USER_ENTERED", "data": formula_data},
            )
        )
        return snapshot

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
