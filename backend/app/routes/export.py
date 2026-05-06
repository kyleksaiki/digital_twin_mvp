"""Report export endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.services.report_service import ReportService

router = APIRouter(prefix="/api/export", tags=["export"])

SUPPORTED_FORMATS = {"csv": "text/csv", "pdf": "application/pdf", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


def get_report_service() -> ReportService:
    return ReportService()


@router.get("/report")
def export_report(
    format: str = Query("csv", description="Report format: csv | pdf | xlsx"),
    report_service: ReportService = Depends(get_report_service),
):
    format_key = format.lower().strip()
    if format_key not in SUPPORTED_FORMATS:
        raise HTTPException(status_code=400, detail="Unsupported format")

    if format_key != "csv":
        raise HTTPException(
            status_code=501,
            detail="Format not implemented yet. Supported today: csv",
        )

    rows = report_service.generate_rows()
    filename = report_service.build_filename("report", format_key)

    headers = {
        "Content-Disposition": f"attachment; filename=\"{filename}\"",
    }

    return StreamingResponse(
        report_service.stream_csv(rows),
        media_type=SUPPORTED_FORMATS[format_key],
        headers=headers,
    )
