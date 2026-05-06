from pydantic import BaseModel


class ReportRow(BaseModel):
    """Single row of report data."""
    id: int
    name: str
    email: str
