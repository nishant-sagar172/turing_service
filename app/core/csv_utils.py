"""Helpers for converting JSON recipient lists into the CSV format Bolna expects.

Bolna's ``POST /batches`` requires a CSV whose rows have a ``contact_number``
column (E.164) plus any number of extra columns; every extra column becomes a
dynamic prompt variable available to the agent.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any

CONTACT_COLUMN = "contact_number"
DEFAULT_CSV_NAME = "recipients.csv"
_UNSAFE_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def csv_file_name(batch_name: str | None, fallback: str = DEFAULT_CSV_NAME) -> str:
    """``<batch_name>.csv`` with filename-unsafe characters dropped; falls back
    to ``fallback`` when nothing usable is left."""
    stem = _UNSAFE_FILENAME_CHARS.sub("", batch_name or "").strip(" .")
    return f"{stem[:150]}.csv" if stem else fallback


def recipients_to_csv(recipients: list[dict[str, Any]]) -> bytes:
    """Serialize a list of recipient dicts into CSV bytes for Bolna.

    - ``contact_number`` is always the first column.
    - Remaining columns are the union of all other keys across recipients
      (sorted for stable output); missing values are written as empty cells.

    Raises:
        ValueError: if the list is empty or any recipient lacks a non-empty
            ``contact_number``.
    """
    if not recipients:
        raise ValueError("recipients must contain at least one entry")

    variable_columns: set[str] = set()
    for index, recipient in enumerate(recipients):
        number = str(recipient.get(CONTACT_COLUMN, "")).strip()
        if not number:
            raise ValueError(
                f"recipient at index {index} is missing '{CONTACT_COLUMN}'"
            )
        variable_columns.update(k for k in recipient if k != CONTACT_COLUMN)

    fieldnames = [CONTACT_COLUMN, *sorted(variable_columns)]

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for recipient in recipients:
        writer.writerow({key: recipient.get(key, "") for key in fieldnames})

    return buffer.getvalue().encode("utf-8")
