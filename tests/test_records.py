from datetime import date

import pytest

from rainfall_tracker.constants import STATE_ORDER
from rainfall_tracker.records import daily_row, matrix_row, monthly_row


def test_deterministic_rows():
    assert daily_row(date(1981, 1, 1), STATE_ORDER[0]) == 2
    assert daily_row(date(1981, 1, 1), STATE_ORDER[-1]) == 17
    assert daily_row(date(1981, 1, 2), STATE_ORDER[0]) == 18
    assert matrix_row(date(1981, 1, 1)) == 2
    assert monthly_row(date(1981, 1, 1), STATE_ORDER[0]) == 2
    assert monthly_row(date(1981, 2, 1), STATE_ORDER[0]) == 18


def test_rows_reject_invalid_inputs():
    with pytest.raises(ValueError):
        daily_row(date(1980, 12, 31), "Johor")
    with pytest.raises(ValueError):
        monthly_row(date(1981, 1, 2), "Johor")

