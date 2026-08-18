"""CSV processor — stdlib csv with delimiter sniffing."""
from __future__ import annotations

import csv
import io

from .base import make_result

_MAX_ROWS_READ = 5000
_MAX_TABLE_ROWS = 500
_MAX_PREVIEW_ROWS = 100


def process_csv(file_path: str, data: bytes) -> dict:
    warnings: list[str] = []
    errors: list[str] = []
    rows: list[list[str]] = []

    try:
        text = data.decode("utf-8-sig", errors="replace")
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample)
        except csv.Error:
            dialect = csv.excel

        reader = csv.reader(io.StringIO(text), dialect)
        for i, row in enumerate(reader):
            rows.append(row)
            if i + 1 >= _MAX_ROWS_READ:
                warnings.append(f"CSV truncated to the first {_MAX_ROWS_READ} rows for processing.")
                break
    except Exception as exc:
        errors.append(f"Failed to read CSV: {exc}")

    header = rows[0] if rows else []
    data_rows = rows[1:] if len(rows) > 1 else []
    text_preview = "\n".join(",".join(r) for r in rows[:_MAX_PREVIEW_ROWS])

    return make_result(
        file_path, "csv",
        text=text_preview,
        tables=[{"header": header, "rows": data_rows[:_MAX_TABLE_ROWS]}],
        metadata={"row_count": len(rows)},
        warnings=warnings, errors=errors,
    )
