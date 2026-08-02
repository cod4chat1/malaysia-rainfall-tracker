from datetime import UTC, date, datetime

from rainfall_tracker.constants import ANALYSIS_ORDER, STATE_ORDER
from rainfall_tracker.dashboard import DashboardSnapshot
from rainfall_tracker.records import RainfallRecord
from rainfall_tracker.sheets import (
    SheetStore,
    _dashboard_v2_control_requests,
    _quality_row_ranges_to_prune,
    column_letter,
)


def test_column_letters():
    assert column_letter(1) == "A"
    assert column_letter(26) == "Z"
    assert column_letter(27) == "AA"


def test_dashboard_validations_clear_stale_cells_and_restore_checkboxes():
    requests = _dashboard_v2_control_requests(123)
    clear_request = requests[0]["setDataValidation"]
    assert clear_request["range"] == {
        "sheetId": 123,
        "startRowIndex": 6,
        "endRowIndex": 9,
        "startColumnIndex": 1,
        "endColumnIndex": 2,
    }
    assert "rule" not in clear_request
    checkbox_requests = [
        request
        for request in requests
        if request.get("setDataValidation", {}).get("rule", {})
        .get("condition", {})
        .get("type")
        == "BOOLEAN"
    ]
    assert len(checkbox_requests) == len(ANALYSIS_ORDER)
    date_formats = [
        request["repeatCell"]["cell"]["userEnteredFormat"]["numberFormat"]
        for request in requests
        if "repeatCell" in request
    ]
    assert date_formats == [
        {"type": "DATE", "pattern": "yyyy-mm-dd"},
        {"type": "DATE", "pattern": "yyyy-mm-dd"},
    ]
    note_request = next(request for request in requests if "updateCells" in request)
    note = note_request["updateCells"]["rows"][0]["values"][0]["note"]
    assert "Future calendar rows without rainfall are excluded" in note


def test_quality_retention_preserves_cutoff_and_malformed_rows():
    cutoff = datetime(2026, 5, 4, tzinfo=UTC)
    started_rows = [
        ["2026-05-03T23:59:59+00:00"],
        ["2026-05-04T00:00:00+00:00"],
        ["not-a-timestamp"],
        ["2026-04-01T00:00:00Z"],
        ["2026-04-02T00:00:00"],
    ]

    assert _quality_row_ranges_to_prune(started_rows, cutoff) == [
        (1, 2),
        (4, 6),
    ]


class FakeRequest:
    def __init__(self, result=None):
        self.result = result or {}

    def execute(self, **_kwargs):
        return self.result


class FakeValues:
    def __init__(self):
        self.batch_bodies = []

    def get(self, **_kwargs):
        return FakeRequest(
            {
                "values": [
                    ["Pahang"],
                    ["Johor"],
                    ["Sabah"],
                    ["3 years"],
                    ["Monthly"],
                ]
            }
        )

    def batchUpdate(self, **kwargs):
        self.batch_bodies.append(kwargs["body"])
        return FakeRequest()


class FakeSpreadsheets:
    def __init__(self):
        self.values_api = FakeValues()

    def values(self):
        return self.values_api


class FakeService:
    def __init__(self):
        self.spreadsheets_api = FakeSpreadsheets()

    def spreadsheets(self):
        return self.spreadsheets_api


class MigrationValues:
    def get(self, **_kwargs):
        return FakeRequest(
            {
                "values": [
                    ["schema_version", "1"],
                    ["calendar_start", "2020-01-01"],
                    ["state_order", "|".join(STATE_ORDER)],
                    ["dataset", "CHIRPS"],
                    ["initialized_through", "2026-08-31"],
                ]
            }
        )


class MigrationSpreadsheets:
    def __init__(self):
        self.batch_bodies = []
        self.values_api = MigrationValues()

    def values(self):
        return self.values_api

    def get(self, **_kwargs):
        titles = [
            "Daily_State_Rainfall",
            "State_Daily_Matrix",
            "Monthly_Summary",
            "Configuration",
        ]
        return FakeRequest(
            {
                "sheets": [
                    {
                        "properties": {
                            "title": title,
                            "sheetId": index + 1,
                            "gridProperties": {
                                "rowCount": 100,
                                "columnCount": 20,
                            },
                        }
                    }
                    for index, title in enumerate(titles)
                ]
            }
        )

    def batchUpdate(self, **kwargs):
        self.batch_bodies.append(kwargs["body"])
        return FakeRequest()


class MigrationService:
    def __init__(self):
        self.spreadsheets_api = MigrationSpreadsheets()

    def spreadsheets(self):
        return self.spreadsheets_api


class RetentionValues:
    def get(self, **_kwargs):
        return FakeRequest(
            {
                "values": [
                    ["2026-05-03T23:59:59+00:00"],
                    ["2026-05-04T00:00:00+00:00"],
                    ["not-a-timestamp"],
                    ["2026-04-01T00:00:00Z"],
                    ["2026-04-02T00:00:00"],
                ]
            }
        )


class RetentionSpreadsheets:
    def __init__(self):
        self.values_api = RetentionValues()
        self.batch_bodies = []

    def values(self):
        return self.values_api

    def get(self, **_kwargs):
        return FakeRequest(
            {
                "sheets": [
                    {
                        "properties": {
                            "title": "Data_Quality",
                            "sheetId": 99,
                        }
                    }
                ]
            }
        )

    def batchUpdate(self, **kwargs):
        self.batch_bodies.append(kwargs["body"])
        return FakeRequest()


class RetentionService:
    def __init__(self):
        self.spreadsheets_api = RetentionSpreadsheets()

    def spreadsheets(self):
        return self.spreadsheets_api


def test_prune_quality_logs_deletes_old_ranges_from_bottom_up():
    service = RetentionService()
    store = SheetStore(service, "sheet-id")

    deleted = store.prune_quality_logs(
        now=datetime(2026, 8, 2, tzinfo=UTC),
        retention_days=90,
    )

    assert deleted == 3
    requests = service.spreadsheets_api.batch_bodies[0]["requests"]
    assert [request["deleteDimension"]["range"] for request in requests] == [
        {
            "sheetId": 99,
            "dimension": "ROWS",
            "startIndex": 4,
            "endIndex": 6,
        },
        {
            "sheetId": 99,
            "dimension": "ROWS",
            "startIndex": 1,
            "endIndex": 2,
        },
    ]


def test_write_records_builds_one_batched_daily_and_matrix_request():
    service = FakeService()
    store = SheetStore(service, "sheet-id")
    day = date(2025, 1, 1)
    records = [
        RainfallRecord(
            day=day,
            state=state,
            average_mm=float(index),
            median_mm=float(index),
            maximum_mm=float(index),
            area_above_1mm_pct=0.0,
            area_above_10mm_pct=0.0,
            area_above_20mm_pct=0.0,
            area_above_50mm_pct=0.0,
            valid_grid_cells=1,
            valid_area_pct=100.0,
            data_status="CHIRPS_V3_FINAL_RNL",
            source_url="https://data.chc.ucsb.edu/example.cog",
            processed_at_utc=datetime(2025, 1, 2, tzinfo=UTC),
        )
        for index, state in enumerate(STATE_ORDER)
    ]
    store.write_records(records)
    assert store.request_count == 1
    body = service.spreadsheets_api.values_api.batch_bodies[0]
    assert body["valueInputOption"] == "RAW"
    assert len(body["data"]) == 2
    assert body["data"][0]["range"].startswith("Daily_State_Rainfall!")
    assert body["data"][1]["range"].startswith("State_Daily_Matrix!")


def test_dashboard_controls_are_preserved_and_formulas_use_cutoff():
    store = SheetStore(FakeService(), "sheet-id")

    assert store._dashboard_control_values() == [
        "Pahang",
        "Johor",
        "Sabah",
        "3 years",
        "Monthly",
    ]
    formula_rows = store._dashboard_formula_rows()
    formulas = str(formula_rows)
    assert "Dashboard!$B$10" in formulas
    assert "7-day moving average" in formulas
    assert "30-day moving average" in formulas
    assert "=Dashboard!B4" in formulas
    assert '=Dashboard!B4&" normal"' in formulas

    snapshot = DashboardSnapshot(
        latest_date=date(2026, 7, 20),
        daily_headers=[],
        daily_rows=[],
        monthly_headers=[],
        monthly_rows=[],
        ranking_headers=[],
        ranking_rows=[],
        heatmap_headers=[],
        heatmap_rows=[],
    )
    dashboard = store._dashboard_main_values(snapshot, store._dashboard_control_values())
    latest_date_formula = dashboard[0]["values"][8][1]
    assert latest_date_formula == "=DATE(2026,7,20)"
    assert "Dashboard_Data" not in latest_date_formula


def test_dashboard_v2_supports_all_areas_and_separates_anomaly_from_trend():
    store = SheetStore(FakeService(), "sheet-id")
    focus, period, frequency, selected = store._dashboard_v2_control_values()
    assert (focus, period, frequency) == ("Malaysia", "1 year", "Daily")
    assert {"Johor", "Peninsular Malaysia", "East Malaysia", "Malaysia"} <= selected

    formulas = store._dashboard_v2_formula_rows()
    comparison_headers = formulas[1]["values"][0]
    assert len(comparison_headers) == 1 + len(ANALYSIS_ORDER)
    assert "Malaysia Rolling30" in str(formulas)
    assert "Dashboard!$B$9" in str(formulas)

    snapshot = DashboardSnapshot(
        latest_date=date(2026, 7, 20),
        baseline_start_year=2013,
        baseline_end_year=2025,
        daily_headers=[],
        daily_rows=[],
        monthly_headers=[],
        monthly_rows=[],
        ranking_headers=[],
        ranking_rows=[],
        heatmap_headers=[],
        heatmap_rows=[],
    )
    dashboard = store._dashboard_v2_main_values(
        snapshot,
        (focus, period, frequency, selected),
    )
    explanation = dashboard[2]["values"][0][0]
    assert "Anomaly compares month-to-date" in explanation
    assert "trend compares" in explanation


def test_calendar_migration_prepends_rows_and_updates_config_atomically():
    service = MigrationService()
    store = SheetStore(service, "sheet-id")
    initialized = []
    store.init_sheet = lambda *, through=None: initialized.append(through)

    assert store.migrate_calendar_start() is True

    body = service.spreadsheets_api.batch_bodies[0]
    requests = body["requests"]
    assert len(requests) == 4
    daily_insert = requests[0]["insertDimension"]["range"]
    matrix_insert = requests[1]["insertDimension"]["range"]
    monthly_insert = requests[2]["insertDimension"]["range"]
    assert daily_insert["endIndex"] - daily_insert["startIndex"] == 2556 * 16
    assert matrix_insert["endIndex"] - matrix_insert["startIndex"] == 2556
    assert monthly_insert["endIndex"] - monthly_insert["startIndex"] == 84 * 16
    config_update = requests[3]["updateCells"]
    assert (
        config_update["rows"][0]["values"][0]["userEnteredValue"]["stringValue"]
        == "2013-01-01"
    )
    assert initialized == [date(2026, 8, 31)]
