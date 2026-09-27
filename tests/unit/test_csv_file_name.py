import pytest

from app.core.csv_utils import csv_file_name


@pytest.mark.parametrize(
    ("batch_name", "expected"),
    [
        (None, "recipients.csv"),
        ("", "recipients.csv"),
        ("  ..  ", "recipients.csv"),
        ("Follow-up Sep 28", "Follow-up Sep 28.csv"),
        ('OPD/IPD: "day 1"?', "OPDIPD day 1.csv"),
        ("tab\there", "tabhere.csv"),
    ],
)
def test_csv_file_name(batch_name: str | None, expected: str) -> None:
    assert csv_file_name(batch_name) == expected


def test_csv_file_name_truncates_long_names() -> None:
    assert csv_file_name("x" * 300) == "x" * 150 + ".csv"


def test_csv_file_name_falls_back_to_the_uploaded_name() -> None:
    assert csv_file_name(None, fallback="feb_patients.csv") == "feb_patients.csv"
    assert (
        csv_file_name("Feb follow-ups", fallback="feb_patients.csv")
        == "Feb follow-ups.csv"
    )
