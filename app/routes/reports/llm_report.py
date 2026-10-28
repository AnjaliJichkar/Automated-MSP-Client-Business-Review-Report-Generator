"""
LLM Report Endpoints
=====================
POST /api/GenerateLLMData      — generate and save llm_data for a report
GET  /api/GetLLMData           — retrieve stored llm_data for a report
POST /api/TestGenerateLLMData  — test LLM generation using realjson.json (no DB needed)

Lookup: either report_id OR (org_id + month) can be used.
month format: "march_2026" | "last_3_months"
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database.engine import get_db
from app.models.reports import GeneratedReport
from app.schemas.api import GraphApiResponse
from app.services.llm.llm_service import get_llm_service

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_month(month: str):
    """
    Parse month string → (report_month, report_year, report_type)

    "march_2026"     → ("March", 2026, "monthly")
    "last_3_months"  → ("January-March", 2026, "quarterly")  ← dates auto-calculated
    """
    if month.strip().lower() == "last_3_months":
        from app.utils.month_selector import MonthSelector
        ms = MonthSelector()
        start_ts, end_ts = ms.get_quarterly_date_range()
        start_dt = datetime.fromtimestamp(start_ts)
        end_dt   = datetime.fromtimestamp(end_ts)
        report_month = f"{start_dt.strftime('%B')}-{end_dt.strftime('%B')}"
        report_year  = end_dt.year
        report_type  = "quarterly"
    elif "_" in month:
        parts = month.split("_")
        report_month = parts[0].capitalize()
        report_year  = int(parts[1])
        report_type  = "monthly"
    else:
        raise ValueError("Invalid month format. Use 'march_2026' or 'last_3_months'")

    return report_month, report_year, report_type


def _fetch_report(db: Session, report_id: Optional[int], org_id: Optional[int], month: Optional[str]) -> Optional[GeneratedReport]:
    """
    Fetch active report using either report_id OR (org_id + month).
    """
    if report_id is not None:
        return db.query(GeneratedReport).filter(
            GeneratedReport.id == report_id
        ).first()

    if org_id is not None and month is not None:
        report_month, report_year, report_type = _parse_month(month)
        return db.query(GeneratedReport).filter(
            GeneratedReport.organization_id == org_id,
            GeneratedReport.report_month    == report_month,
            GeneratedReport.report_year     == report_year,
            GeneratedReport.report_type     == report_type,
            GeneratedReport.status          == "Active"
        ).first()

    return None


# ---------------------------------------------------------------------------
# Month-over-month helpers
# ---------------------------------------------------------------------------

_MONTH_TO_NUM = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12
}
_NUM_TO_MONTH = {v: k for k, v in _MONTH_TO_NUM.items()}


def _previous_month_label(report_month: str, report_year: int):
    n = _MONTH_TO_NUM.get(report_month)
    if not n:
        return None, None
    if n == 1:
        return "December", report_year - 1
    return _NUM_TO_MONTH[n - 1], report_year


def get_previous_month_autotask_data(db, organization_id: int, report_month: str, report_year: int):
    """
    Look up the previous month's GeneratedReport for the same org and
    extract only the Autotask charts subset. Returns None if not found.
    Skips quarterly reports (report_month contains '-').
    """
    if "-" in report_month:
        return None
    prev_month, prev_year = _previous_month_label(report_month, report_year)
    if not prev_month:
        return None
    prev_report = db.query(GeneratedReport).filter(
        GeneratedReport.organization_id == organization_id,
        GeneratedReport.report_month    == prev_month,
        GeneratedReport.report_year     == prev_year,
        GeneratedReport.status          == "Active"
    ).first()
    if not prev_report or not prev_report.organization_data:
        return None
    autotask_charts = prev_report.organization_data.get("Autotask", {}).get("charts", {})
    if not autotask_charts:
        return None
    return {
        "month": f"{prev_month} {prev_year}",
        "daily_tickets_trend": autotask_charts.get("daily_tickets_trend", {}),
        "monthly_tickets_by_type": autotask_charts.get("monthly_tickets_by_type", {}),
        "sla_performance": autotask_charts.get("sla_performance", {}),
    }


# ---------------------------------------------------------------------------
# Quarterly helpers
# ---------------------------------------------------------------------------

def _quarterly_months_with_years(report_month: str, report_year: int):
    """
    Given "February-April" and 2026 → [("February",2026),("March",2026),("April",2026)]
    Handles year-boundary: "November-January" and 2026 →
      [("November",2025),("December",2025),("January",2026)]
    Rule: if a month number > end_month_number it belongs to report_year - 1.
    """
    parts = report_month.split("-")
    if len(parts) != 2:
        return []
    start_name, end_name = parts[0].strip(), parts[1].strip()
    start_num = _MONTH_TO_NUM.get(start_name)
    end_num   = _MONTH_TO_NUM.get(end_name)
    if not start_num or not end_num:
        return []
    mid_num = (start_num % 12) + 1  # month after start, wrapping Dec→Jan
    result = []
    for m_num in [start_num, mid_num, end_num]:
        m_name = _NUM_TO_MONTH[m_num]
        m_year = report_year - 1 if m_num > end_num else report_year
        result.append((m_name, m_year))
    return result


def get_quarterly_monthly_breakdown(db, organization_id: int, report_month: str, report_year: int):
    """
    For a quarterly report (report_month e.g. "February-April"), look up the 3 individual
    monthly reports that make up this quarter and return their Autotask data separately
    so the LLM can compare within-quarter trends on Slide 8.
    Returns None if not a quarterly report or none of the monthly reports are found.
    """
    if "-" not in report_month:
        return None

    months_with_years = _quarterly_months_with_years(report_month, report_year)
    if not months_with_years:
        return None

    monthly_data = []
    for month_name, month_year in months_with_years:
        month_report = db.query(GeneratedReport).filter(
            GeneratedReport.organization_id == organization_id,
            GeneratedReport.report_month    == month_name,
            GeneratedReport.report_year     == month_year,
            GeneratedReport.report_type     == "monthly",
            GeneratedReport.status          == "Active"
        ).first()

        if not month_report or not month_report.organization_data:
            continue

        charts = month_report.organization_data.get("Autotask", {}).get("charts", {})
        if not charts:
            continue

        daily_completed = charts.get("daily_tickets_trend", {}).get("completed", [])
        completed_tickets = sum(daily_completed) if daily_completed else 0

        sla = charts.get("sla_performance", {})
        monthly_data.append({
            "month":                   f"{month_name} {month_year}",
            "completed_tickets":       completed_tickets,
            "monthly_tickets_by_type": charts.get("monthly_tickets_by_type", {}),
            "sla_performance": {
                "resolution_percentage":     sla.get("resolution_percentage"),
                "first_response_percentage": sla.get("first_response_percentage"),
            },
        })

    if not monthly_data:
        return None

    return {
        "quarter_label": report_month,
        "report_year":   report_year,
        "months":        monthly_data,
    }


# ---------------------------------------------------------------------------
# POST /api/GenerateLLMData
# ---------------------------------------------------------------------------

class GenerateLLMDataRequest(BaseModel):
    report_id:  Optional[int] = None
    org_id:     Optional[int] = None
    month:      Optional[str] = None   # "march_2026" | "last_3_months"


@router.post("/GenerateLLMData", response_model=GraphApiResponse, summary="Generate LLM slide data for a report")
async def generate_llm_data(
    request: GenerateLLMDataRequest,
    db: Session = Depends(get_db)
):
    """
    Reads organization_data from the report, sends it to OpenAI,
    and saves the filled-in slide JSON to the llm_data column.

    Lookup priority:
      1. report_id (if provided)
      2. org_id + month (if report_id not provided)
    """
    try:
        if not request.report_id and not (request.org_id and request.month):
            return GraphApiResponse(
                status_code=400,
                data={},
                error="Provide either 'report_id' or both 'org_id' and 'month'."
            )

        report = _fetch_report(db, request.report_id, request.org_id, request.month)

        if not report:
            return GraphApiResponse(
                status_code=404,
                data={},
                error="No active report found for the given parameters."
            )

        if not report.organization_data:
            return GraphApiResponse(
                status_code=400,
                data={},
                error=f"Report {report.id} has no organization_data to process."
            )

        prev_month_data = get_previous_month_autotask_data(
            db, report.organization_id, report.report_month, report.report_year
        )
        service = get_llm_service()
        llm_data = await service.generate_llm_data(report.organization_data, previous_month_data=prev_month_data)

        report.llm_data = llm_data
        db.commit()
        db.refresh(report)

        logger.info(f"LLM data generated and saved for report_id: {report.id}")

        return GraphApiResponse(
            status_code=200,
            data={"report_id": report.id, "llm_data": llm_data}
        )

    except ValueError as e:
        logger.error(f"LLM generation error: {e}")
        return GraphApiResponse(status_code=400, data={}, error=str(e))
    except Exception as e:
        logger.error(f"Unexpected error generating LLM data: {e}")
        return GraphApiResponse(status_code=500, data={}, error=f"Failed to generate LLM data: {str(e)}")


# ---------------------------------------------------------------------------
# GET /api/GetLLMData
# ---------------------------------------------------------------------------

@router.get("/GetLLMData", response_model=GraphApiResponse, summary="Get stored LLM slide data for a report")
async def get_llm_data(
    report_id:  Optional[int] = Query(None, description="Report ID"),
    org_id:     Optional[int] = Query(None, description="Organization ID"),
    month:      Optional[str] = Query(None, description="Month string: 'march_2026' or 'last_3_months'"),
    db: Session = Depends(get_db)
):
    """
    Returns the llm_data JSON stored on a report.

    Lookup priority:
      1. report_id (if provided)
      2. org_id + month (if report_id not provided)
    """
    try:
        if not report_id and not (org_id and month):
            return GraphApiResponse(
                status_code=400,
                data={},
                error="Provide either 'report_id' or both 'org_id' and 'month'."
            )

        report = _fetch_report(db, report_id, org_id, month)

        if not report:
            return GraphApiResponse(
                status_code=404,
                data={},
                error="No active report found for the given parameters."
            )

        if not report.llm_data:
            return GraphApiResponse(
                status_code=404,
                data={},
                error=f"LLM data has not been generated yet for report {report.id}. Call POST /GenerateLLMData first."
            )

        return GraphApiResponse(
            status_code=200,
            data={"report_id": report.id, "llm_data": report.llm_data}
        )

    except ValueError as e:
        logger.error(f"LLM fetch error: {e}")
        return GraphApiResponse(status_code=400, data={}, error=str(e))
    except Exception as e:
        logger.error(f"Error fetching LLM data: {e}")
        return GraphApiResponse(status_code=500, data={}, error=f"Failed to fetch LLM data: {str(e)}")


# ---------------------------------------------------------------------------
# POST /api/TestGenerateLLMData  (test only — uses realjson.json, no DB)
# ---------------------------------------------------------------------------

@router.post("/TestGenerateLLMData", response_model=GraphApiResponse, summary="Test LLM generation using realjson.json")
async def test_generate_llm_data():
    """
    Test endpoint — loads realjson.json as input and calls OpenAI.
    No database required. Use this to verify the LLM service is working.
    """
    try:
        realjson_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "..", "realjson.json"
        )
        realjson_path = os.path.abspath(realjson_path)

        if not os.path.exists(realjson_path):
            return GraphApiResponse(
                status_code=404,
                data={},
                error=f"realjson.json not found at: {realjson_path}"
            )

        with open(realjson_path, "r", encoding="utf-8") as f:
            organization_data = json.load(f)

        service = get_llm_service()
        llm_data = await service.generate_llm_data(organization_data)

        return GraphApiResponse(
            status_code=200,
            data={"llm_data": llm_data}
        )

    except ValueError as e:
        logger.error(f"LLM test generation error: {e}")
        return GraphApiResponse(status_code=500, data={}, error=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in test LLM generation: {e}")
        return GraphApiResponse(status_code=500, data={}, error=f"Test failed: {str(e)}")
