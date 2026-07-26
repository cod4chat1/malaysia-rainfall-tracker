from datetime import date

import pytest

from rainfall_tracker.catalog import SourceAsset
from rainfall_tracker.pipeline import date_range, default_date_range, select_assets


class FakeCatalog:
    def __init__(self, assets):
        self.assets = assets

    def preferred_asset(self, day):
        return self.assets.get(day)


def test_date_range_is_inclusive_and_bounded():
    days = date_range(date(2025, 1, 1), date(2025, 1, 3))
    assert days == [date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 3)]
    with pytest.raises(ValueError):
        date_range(date(2025, 1, 2), date(2025, 1, 1))


def test_default_range_ends_yesterday():
    days = default_date_range(date(2025, 1, 10), 3)
    assert days == [date(2025, 1, 7), date(2025, 1, 8), date(2025, 1, 9)]


def test_asset_selection_respects_status_and_run_cap():
    days = [date(2025, 1, day) for day in range(1, 5)]
    assets = {
        days[0]: SourceAsset(days[0], "CHIRPS_V3_PRELIM_SAT", "https://data.chc.ucsb.edu/1.tif"),
        days[1]: SourceAsset(days[1], "CHIRPS_V3_FINAL_RNL", "https://data.chc.ucsb.edu/2.cog"),
        days[2]: SourceAsset(days[2], "CHIRPS_V3_FINAL_RNL", "https://data.chc.ucsb.edu/3.cog"),
    }
    selected, missing, skipped = select_assets(
        days,
        FakeCatalog(assets),
        {
            days[0]: "CHIRPS_V3_PRELIM_SAT",
            days[1]: "CHIRPS_V3_PRELIM_SAT",
            days[2]: None,
            days[3]: None,
        },
        max_dates=1,
    )
    assert [asset.day for asset in selected] == [days[1]]
    assert missing == [days[3]]
    assert set(skipped) == {days[0], days[2]}
