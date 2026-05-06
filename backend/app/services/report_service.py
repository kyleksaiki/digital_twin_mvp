import csv
import io
import re
from datetime import datetime, timezone
from typing import Iterable, Iterator

from app.schemas.report import ReportRow


class ReportService:
    """Builds and streams exportable report data."""

    def generate_rows(self, total_rows: int = 5000) -> Iterable[ReportRow]:
        for i in range(1, total_rows + 1):
            yield ReportRow(
                id=i,
                name=f"User {i}",
                email=f"user{i}@example.com",
            )

    def stream_csv(self, rows: Iterable[ReportRow]) -> Iterator[bytes]:
        buffer = io.StringIO()
        writer = csv.writer(buffer)

        writer.writerow(["id", "name", "email"])
        yield buffer.getvalue().encode("utf-8")
        buffer.seek(0)
        buffer.truncate(0)

        for row in rows:
            writer.writerow([row.id, row.name, row.email])
            yield buffer.getvalue().encode("utf-8")
            buffer.seek(0)
            buffer.truncate(0)

    def build_filename(self, base: str, extension: str) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        raw_name = f"{base}_{timestamp}.{extension}"
        return re.sub(r"[^A-Za-z0-9._-]", "_", raw_name)
