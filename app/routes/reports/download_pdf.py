"""
Download Report PDF Endpoint
Generates PDF from HTML content and returns as downloadable file
"""

import logging
import os
import subprocess
import tempfile
import re
from datetime import datetime
from fastapi import APIRouter, HTTPException, Path, Query, Depends
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel
from typing import Optional
from supabase import create_client
from app.services.ppt.report_generator import generate_pptx
from app.services.ppt.pdf_to_pptx import convert_pdf_to_pptx
from app.core.database.engine import SessionLocal
from app.models.reports import GeneratedReport
from app.models.organizations import Organization
import copy
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from datetime import datetime
from app.core.database.engine import get_db
from app.services.llm.llm_service import get_llm_service
from app.routes.reports.llm_report import get_previous_month_autotask_data, get_quarterly_monthly_breakdown
from app.routes.security.reports import _filter_charts_by_selection

router = APIRouter()
logger = logging.getLogger(__name__)

# Path to Node.js PDF generator script
PDF_GENERATOR_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "services",
    "pdf",
    "generate_pdf.js"
)


# ============================================================================
# REQUEST SCHEMA
# ============================================================================

class DownloadReportPDFRequest(BaseModel):
    """Request to generate and download PDF from HTML"""
    html_content: str                   # Full HTML content
    organization_name: str              # Organization name
    month_display_name: str             # Format: "December 2025"
    org_id: Optional[int] = None        # Organization ID (optional)
    uuid: Optional[str] = None          # Report UUID (optional)


class DownloadNativePPTRequest(BaseModel):
    """Request to generate and download native python-pptx report."""
    json_content: dict                  # Full report JSON from GenerateSecurityReportJSON
    organization_name: str              # Organization name (for filename)
    month_display_name: str             # Format: "February 2026" (for filename)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def sanitize_filename(name: str) -> str:
    """
    Sanitize organization name for filename
    - Replace spaces with underscores
    - Remove special characters except underscores and hyphens

    Example: "TeamLogic IT - Burlington" → "TeamLogic_IT_Burlington"
    """
    # Replace spaces with underscores
    name = name.replace(" ", "_")
    # Remove special characters except underscores and hyphens
    name = re.sub(r'[^a-zA-Z0-9_-]', '', name)
    return name


def generate_pdf_filename(org_name: str, month_display_name: str) -> str:
    """
    Generate PDF filename in format: {org_name}_{MonthYear}_report.pdf

    Example: "Terra-Vaults_December2025_report.pdf"

    Args:
        org_name: Organization name (will be sanitized)
        month_display_name: Already formatted date like "December 2025"
    """
    sanitized_org = sanitize_filename(org_name)
    # Remove space from month_display_name: "December 2025" → "December2025"
    month_year_no_space = month_display_name.replace(" ", "")
    return f"{sanitized_org}_{month_year_no_space}_report.pdf"


def generate_pptx_filename(org_name: str, month_display_name: str) -> str:
    """
    Generate PPTX filename in format: {org_name}_{MonthYear}_report.pptx

    Example: "Terra-Vaults_December2025_report.pptx"

    Args:
        org_name: Organization name (will be sanitized)
        month_display_name: Already formatted date like "December 2025"
    """
    sanitized_org = sanitize_filename(org_name)
    # Remove space from month_display_name: "December 2025" → "December2025"
    month_year_no_space = month_display_name.replace(" ", "")
    return f"{sanitized_org}_{month_year_no_space}_report.pptx"


async def call_node_pdf_generator(html_content: str, output_pdf_path: str) -> bool:
    """
    Call Node.js PDF generator script with retry logic handled by the script

    Args:
        html_content: Full HTML content string
        output_pdf_path: Where to save the generated PDF

    Returns:
        True if successful, False otherwise
    """
    temp_html_file = None

    try:
        # Create temp HTML file
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.html', delete=False) as f:
            temp_html_file = f.name
            f.write(html_content)

        logger.info(f"Created temp HTML file: {temp_html_file}")

        # Call Node.js script
        # Script handles retry logic internally (3 attempts)
        logger.info("Calling Node.js PDF generator...")
        result = subprocess.run(
            ['node', PDF_GENERATOR_SCRIPT, temp_html_file, output_pdf_path],
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes timeout for large reports
        )

        # Log Node.js script output
        if result.stdout:
            logger.info(f"Node.js output: {result.stdout}")
        if result.stderr:
            logger.warning(f"Node.js stderr: {result.stderr}")

        if result.returncode != 0:
            logger.error(f"PDF generation failed with return code {result.returncode}")
            return False

        # Verify PDF was created
        if not os.path.exists(output_pdf_path):
            logger.error(f"PDF file not found at: {output_pdf_path}")
            return False

        file_size = os.path.getsize(output_pdf_path)
        logger.info(f"PDF generated successfully: {file_size} bytes")

        return True

    except subprocess.TimeoutExpired:
        logger.error("PDF generation timed out after 180 seconds")
        return False
    except Exception as e:
        logger.error(f"Error calling Node.js PDF generator: {e}")
        return False
    finally:
        # Clean up temp HTML file
        if temp_html_file and os.path.exists(temp_html_file):
            try:
                os.remove(temp_html_file)
                logger.info(f"Cleaned up temp HTML file: {temp_html_file}")
            except Exception as e:
                logger.warning(f"Failed to remove temp HTML file: {e}")


# ============================================================================
# MAIN ENDPOINT
# ============================================================================

@router.post("/DownloadReportPDF")
async def download_report_pdf(request: DownloadReportPDFRequest):
    """
    Generate PDF from HTML content and return as downloadable file.

    Workflow:
    1. Receive HTML content and metadata from frontend
    2. Write HTML to temporary file
    3. Call Node.js Puppeteer script to generate PDF (with retry logic)
    4. Return PDF as file download
    5. Clean up temporary files

    Filename format: {org_name}_{Month Year}_report.pdf
    Example: "Terra-Vaults_December 2025_report.pdf"

    Returns:
        FileResponse with PDF file for download
    """
    temp_pdf_file = None

    try:
        logger.info(f"DownloadReportPDF called for org: {request.organization_name}, month: {request.month_display_name}")
        logger.info(f"HTML content length: {len(request.html_content)} characters")

        # Generate filename
        pdf_filename = generate_pdf_filename(request.organization_name, request.month_display_name)
        logger.info(f"Generated filename: {pdf_filename}")

        # Create temp PDF file path
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            temp_pdf_file = f.name

        logger.info(f"Temp PDF path: {temp_pdf_file}")

        # Generate PDF using Node.js script
        success = await call_node_pdf_generator(request.html_content, temp_pdf_file)

        if not success:
            raise HTTPException(
                status_code=500,
                detail="PDF generation failed after all retry attempts. Please try again."
            )

        # Return PDF as download
        logger.info(f"Returning PDF file: {pdf_filename}")
        return FileResponse(
            path=temp_pdf_file,
            filename=pdf_filename,
            media_type='application/pdf',
            background=None  # File will be kept until response is sent
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error in DownloadReportPDF: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")

        # Clean up temp PDF file on error
        if temp_pdf_file and os.path.exists(temp_pdf_file):
            try:
                os.remove(temp_pdf_file)
            except:
                pass

        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate PDF: {str(e)}"
        )


# ============================================================================
# PPTX DOWNLOAD ENDPOINT
# ============================================================================

@router.post("/DownloadPPT")
async def download_report_ppt(request: DownloadNativePPTRequest):
    """
    Generate PPTX using native python-pptx engine and return as downloadable file.

    Workflow:
    1. Receive report JSON and metadata from frontend
    2. Call generate_pptx() directly — no Node.js, no external API
    3. Write BytesIO to temp file
    4. Return PPTX as file download (temp file auto-deleted after send)

    Filename format: {org_name}_{MonthYear}_report.pptx
    Example: "Terra-Vaults_December2025_report.pptx"

    Returns:
        FileResponse with PPTX file for download
    """
    # ================================================================
    # OLD APPROACH — commented out (HTML → Puppeteer → PDF → ConvertHub → PPTX)
    # Restore this block if native engine needs to be rolled back.
    # ================================================================
    # temp_pdf_file = None
    # temp_pptx_file = None
    # try:
    #     logger.info(f"DownloadPPT called for org: {request.organization_name}, month: {request.month_display_name}")
    #     logger.info(f"HTML content length: {len(request.html_content)} characters")
    #     with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
    #         temp_pdf_file = f.name
    #     pdf_success = await call_node_pdf_generator(request.html_content, temp_pdf_file)
    #     if not pdf_success:
    #         raise HTTPException(status_code=500, detail="PDF generation failed.")
    #     with tempfile.NamedTemporaryFile(suffix='.pptx', delete=False) as f:
    #         temp_pptx_file = f.name
    #     pptx_success = convert_pdf_to_pptx(temp_pdf_file, temp_pptx_file)
    #     if not pptx_success:
    #         raise HTTPException(status_code=500, detail="PPTX conversion failed. Check CONVERTHUB_API_KEY.")
    #     pptx_filename = generate_pptx_filename(request.organization_name, request.month_display_name)
    #     return FileResponse(path=temp_pptx_file, filename=pptx_filename,
    #         media_type='application/vnd.openxmlformats-officedocument.presentationml.presentation',
    #         background=None)
    # except HTTPException:
    #     raise
    # except Exception as e:
    #     logger.error(f"Error in DownloadPPT: {e}")
    #     raise HTTPException(status_code=500, detail=f"Failed to generate PPTX: {str(e)}")
    # finally:
    #     if temp_pdf_file and os.path.exists(temp_pdf_file):
    #         os.remove(temp_pdf_file)
    #     if temp_pptx_file and os.path.exists(temp_pptx_file):
    #         import sys
    #         if sys.exc_info()[0] is not None:
    #             os.remove(temp_pptx_file)

    # ================================================================
    # NEW APPROACH — Native python-pptx engine
    # ================================================================
    tmp_path = None
    try:
        logger.info(f"DownloadPPT (native) called for org: {request.organization_name}, month: {request.month_display_name}")

        # Step 1: Generate filename
        pptx_filename = generate_pptx_filename(request.organization_name, request.month_display_name)
        logger.info(f"Generated filename: {pptx_filename}")

        # Step 2: Call native engine — returns BytesIO
        pptx_buf = generate_pptx(request.json_content)

        # Step 3: Write BytesIO to temp file (FileResponse needs a file path)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pptx")
        tmp.write(pptx_buf.read())
        tmp.close()
        tmp_path = tmp.name
        logger.info(f"Written to temp file: {tmp_path}")

        # Step 4: Stream file to client, auto-delete after send
        return FileResponse(
            path=tmp_path,
            filename=pptx_filename,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            background=BackgroundTask(os.remove, tmp_path)
        )

    except Exception as e:
        logger.error(f"Error in DownloadPPT (native): {e}")
        import traceback
        logger.error(traceback.format_exc())
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise HTTPException(status_code=500, detail=f"Failed to generate PPTX: {str(e)}")


# ============================================================================
# FETCH STORED PPTX FROM SUPABASE BUCKET
# ============================================================================


@router.get("/DownloadSecurityReportPPT/{org_id}", summary="Download PPT strictly using DB Data")
async def download_security_report_ppt(
        org_id: int = Path(..., description="Organization ID"),
        month: str = Query(..., description="Report month (e.g., 'june_2026' or 'last_3_months')"),
        db: Session = Depends(get_db)
):
    """
    Generates a PPTX purely from the database cache. 
    Does NOT require the frontend to pass the massive JSON payload.
    """
    tmp_path = None
    try:
        logger.info(f"Download PPT requested for org_id: {org_id}, month: {month}")

        # Step 1: Parse the month string
        if month.strip().lower() == "last_3_months":
            from app.utils.month_selector import MonthSelector
            ms = MonthSelector()
            start_ts, end_ts = ms.get_quarterly_date_range()
            start_dt = datetime.fromtimestamp(start_ts)
            end_dt = datetime.fromtimestamp(end_ts)
            report_month = f"{start_dt.strftime('%B')}-{end_dt.strftime('%B')}"
            report_year = end_dt.year
            report_type = "quarterly"
        elif '_' in month:
            parts = month.split('_')
            report_month = parts[0].capitalize()
            report_year = int(parts[1])
            report_type = "monthly"
        else:
            raise HTTPException(status_code=400, detail="Invalid month format.")

        # Step 2: Fetch the report directly from the database (No frontend JSON needed)
        report = db.query(GeneratedReport).filter(
            GeneratedReport.organization_id == org_id,
            GeneratedReport.report_month == report_month,
            GeneratedReport.report_year == report_year,
            GeneratedReport.report_type == report_type,
            GeneratedReport.status == "Active"
        ).first()

        if not report or not report.organization_data:
            raise HTTPException(
                status_code=404, 
                detail="Report data not found in database. Please view the report first to generate data."
            )

        # Step 3: Fast Path vs Slow Path for LLM Data
        if report.llm_data:
            logger.info("llm_data found in DB! Skipping OpenAI.")
            llm_data = report.llm_data
        else:
            logger.info("LLM data missing. Calling OpenAI to generate it...")
            prev_month_data = get_previous_month_autotask_data(db, org_id, report_month, report_year)
            quarterly_breakdown = get_quarterly_monthly_breakdown(db, org_id, report_month, report_year)

            service = get_llm_service()
            llm_data = await service.generate_llm_data(
                report.organization_data, 
                previous_month_data=prev_month_data, 
                quarterly_breakdown=quarterly_breakdown
            )
            
            # Save the generated JSON to the DB for next time
            report.llm_data = llm_data
            report.updated_at = datetime.now()
            db.commit()

        # Step 4: Look up account_id for this org (needed to check account_selected_charts)
        org = db.query(Organization).filter(Organization.id == org_id).first()
        account_id = org.account_id if org else None

        # Step 5: Strip out any charts the account has since deselected
        filtered_org_data = _filter_charts_by_selection(report.organization_data, account_id)

        # Step 6: Generate PPTX using Native Engine
        logger.info("Compiling PPTX file in memory...")
        pptx_input = copy.deepcopy(filtered_org_data)
        pptx_input['llm_data'] = llm_data
        
        # Run in threadpool to prevent blocking the FastAPI event loop
        pptx_buf = await run_in_threadpool(generate_pptx, pptx_input)
        
        # Step 7: Write BytesIO to temp file for FileResponse
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pptx")
        tmp.write(pptx_buf.read())
        tmp.close()
        tmp_path = tmp.name
        
        # Extract Organization Name for the file download title
        org_name = pptx_input.get("organization", {}).get("name", f"Org_{org_id}")
        clean_org_name = org_name.replace(" ", "_").replace("/", "-")
        clean_month = str(report_month).replace("-", "_")
        pptx_filename = f"{clean_org_name}_{clean_month}_{report_year}_Report.pptx"

        logger.info(f"Streaming {pptx_filename} to the client...")

        # Send file and auto-delete temp file in the background
        return FileResponse(
            path=tmp_path,
            filename=pptx_filename,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            background=BackgroundTask(os.remove, tmp_path),
            headers={"Access-Control-Expose-Headers": "Content-Disposition"}
        )

    except HTTPException:
        raise
    except Exception as e:
        # Cleanup temp file on failure
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
            
        logger.error(f"Error generating PPT: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")