from datetime import date

import pytest

from rainfall_tracker.catalog import (
    SourceAsset,
    parse_directory_listing,
    should_process,
    validate_source_url,
)


def test_parse_directory_listing_accepts_tif_and_cog():
    base = "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/test/2025/"
    html = """
    <a href="chirps-v3.0.rnl.2025.01.02.cog">COG</a>
    <a href="chirps-v3.0.rnl.2025.01.03.tif">TIF</a>
    <a href="../">Parent</a>
    """
    result = parse_directory_listing(html, base)
    assert set(result) == {date(2025, 1, 2), date(2025, 1, 3)}
    assert result[date(2025, 1, 2)].endswith(".cog")


def test_unapproved_source_host_is_rejected():
    with pytest.raises(ValueError, match="Unapproved"):
        validate_source_url("https://example.com/rain.tif")


def test_replacement_rule_only_upgrades_preliminary_to_final():
    day = date(2025, 1, 1)
    prelim = SourceAsset(day, "CHIRPS_V3_PRELIM_SAT", "https://data.chc.ucsb.edu/x.tif")
    final = SourceAsset(day, "CHIRPS_V3_FINAL_RNL", "https://data.chc.ucsb.edu/x.cog")
    assert should_process(None, prelim)
    assert not should_process("CHIRPS_V3_PRELIM_SAT", prelim)
    assert should_process("CHIRPS_V3_PRELIM_SAT", final)
    assert not should_process("CHIRPS_V3_FINAL_RNL", final)

