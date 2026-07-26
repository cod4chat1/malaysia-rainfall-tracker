import pytest

from rainfall_tracker.boundaries import normalize_state_name


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("Malacca", "Melaka"),
        ("Pulau Pinang", "Penang"),
        ("Wilayah Persekutuan Kuala Lumpur", "Kuala Lumpur"),
        ("Negeri-Sembilan", "Negeri Sembilan"),
    ],
)
def test_normalize_state_name(source, expected):
    assert normalize_state_name(source) == expected


def test_unknown_state_is_rejected():
    with pytest.raises(ValueError, match="Unknown"):
        normalize_state_name("Atlantis")

