"""
Send Report to POC Endpoint
Main endpoint for Phase 2: Sends report PDF to POC via email using Microsoft Graph API

NEW ARCHITECTURE (Single Sender):
- All MS Graph credentials loaded from .env file
- Single fixed sender mailbox (e.g., reports@company.com)
- No per-account SMTP credential storage
- No database lookups for SMTP credentials
"""

import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.core.database.engine import get_db
from app.models.organizations import Organization, OrganizationPoc
from app.models.reports import GeneratedReport
from app.services.email.outlook_sender import OutlookEmailSender
from app.schemas.api import GraphApiResponse

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================================================
# REQUEST SCHEMA
# ============================================================================

class SendReportToPOCRequest(BaseModel):
    """Request to send report to POC - Simplified: Only POC email required"""
    poc_email: EmailStr                 # ONLY REQUIRED FIELD
    report_month: Optional[str] = None
    report_year: Optional[int] = None

    class Config:
        json_schema_extra = {
            "example": {
                "poc_email": "john.doe@company.com",
                "report_month": "November",  # Optional
                "report_year": 2024          # Optional
            }
        }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_organization_from_poc_email(poc_email: str, db: Session):
    """
    Get organization ID and details from POC email.
    This replaces the need for manual org_id input - we lookup automatically!

    Args:
        poc_email: POC email address
        db: SQLAlchemy session

    Returns:
        Dict with organization_id and poc_name, or None if not found
    """
    poc = db.query(OrganizationPoc).filter(
        OrganizationPoc.poc_email == poc_email
    ).first()

    if poc:
        logger.info(f"Found POC: {poc.poc_name} → Org ID: {poc.organization_id}")
        return {'organization_id': poc.organization_id, 'poc_name': poc.poc_name}

    logger.warning(f"POC email not found: {poc_email}")
    return None


def get_latest_report(organization_id: int, db: Session):
    """
    Get the latest report for an organization.
    Logic: If today is December 3, 2025, returns November 2025 report.
    """
    report = db.query(GeneratedReport).filter(
        GeneratedReport.organization_id == organization_id,
        GeneratedReport.status == 'completed'
    ).order_by(
        GeneratedReport.report_year.desc(),
        GeneratedReport.created_at.desc()
    ).first()

    if report:
        return {
            'id': report.id,
            'report_month': report.report_month,
            'report_year': report.report_year,
            'pdf_file_path': report.pdf_file_path
        }
    return None


def get_specific_report(organization_id: int, report_month: str, report_year: int, db: Session):
    """Get a specific report by month and year"""
    report = db.query(GeneratedReport).filter(
        GeneratedReport.organization_id == organization_id,
        GeneratedReport.report_month == report_month,
        GeneratedReport.report_year == report_year,
        GeneratedReport.status == 'completed'
    ).first()

    if report:
        return {
            'id': report.id,
            'report_month': report.report_month,
            'report_year': report.report_year,
            'pdf_file_path': report.pdf_file_path
        }
    return None


def download_pdf_from_bucket(pdf_file_path: str) -> bytes:
    """Download PDF from Supabase private bucket"""
    import os
    from supabase import create_client

    logger.info(f"Downloading PDF: {pdf_file_path}")

    # Use service role key to bypass RLS for storage access
    service_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_KEY')
    storage_client = create_client(os.getenv('SUPABASE_URL'), service_key)

    pdf_bytes = storage_client.storage.from_("bucket").download(pdf_file_path)

    logger.info(f"Downloaded {len(pdf_bytes)} bytes")
    return pdf_bytes


# ============================================================================
# MAIN ENDPOINT
# ============================================================================

@router.post("/SendReportToPOC", response_model=GraphApiResponse)
async def send_report_to_poc(request: SendReportToPOCRequest, db: Session = Depends(get_db)):
    """
    Send monthly security report PDF to Point of Contact via email.

    SIMPLIFIED WORKFLOW (Single Sender Architecture):
    1. Get organization_id from POC email (automatic lookup)
    2. Get report (latest or specific month/year)
    3. Get org_name from organization
    4. Download PDF from Supabase bucket
    5. Send email with PDF attached (credentials from .env)

    Note: All MS Graph credentials are loaded from environment variables.
    Single fixed sender mailbox is used for all emails.

    Returns:
        Success message with email details
    """
    try:
        logger.info(f"SendReportToPOC called for POC: {request.poc_email}")

        # ================================================================
        # Step 1: Get organization from POC email (AUTO-LOOKUP!)
        # ================================================================
        poc_data = get_organization_from_poc_email(request.poc_email, db)

        if not poc_data:
            logger.warning(f"POC email not found: {request.poc_email}")
            return GraphApiResponse(
                status_code=404,
                data={"success": False},
                error=f"POC email '{request.poc_email}' not found in system. Please check the email address."
            )

        organization_id = poc_data['organization_id']
        poc_name = poc_data['poc_name']

        logger.info(f"✓ Found POC: {poc_name} → Org ID: {organization_id}")

        # ================================================================
        # Step 2: Get report (latest or specific)
        # ================================================================
        if request.report_month and request.report_year:
            # Get specific report
            report = get_specific_report(
                organization_id,
                request.report_month,
                request.report_year,
                db
            )
            report_description = f"{request.report_month} {request.report_year}"
        else:
            # Get latest report
            report = get_latest_report(organization_id, db)
            report_description = "latest available"

        if not report:
            logger.warning(f"No report found for org {organization_id}")
            return GraphApiResponse(
                status_code=404,
                data={"success": False},
                error=f"No report found for organization {organization_id}"
            )

        pdf_file_path = report['pdf_file_path']
        report_month = report['report_month']
        report_year = report['report_year']

        logger.info(f"✓ Found report: {report_month} {report_year}")

        # ================================================================
        # Step 3: Get org_name from organization
        # ================================================================
        org = db.query(Organization).filter(Organization.id == organization_id).first()

        if not org:
            logger.error(f"Organization {organization_id} not found")
            return GraphApiResponse(
                status_code=404,
                data={"success": False},
                error=f"Organization {organization_id} not found"
            )

        org_name = org.organization_name
        logger.info(f"Found org_name: {org_name}")

        # ================================================================
        # Step 4: Download PDF from bucket
        # ================================================================
        try:
            pdf_bytes = download_pdf_from_bucket(pdf_file_path)
            logger.info(f"✓ Downloaded PDF: {len(pdf_bytes)} bytes")
        except Exception as e:
            logger.error(f"Failed to download PDF: {e}")
            return GraphApiResponse(
                status_code=500,
                data={"success": False},
                error=f"Failed to download PDF from storage: {str(e)}"
            )

        # ================================================================
        # Step 5: Send email with PDF attached (Graph API)
        # Credentials loaded from .env (single sender architecture)
        # ================================================================
        email_sender = OutlookEmailSender()  # No params - loads from .env

        success = await email_sender.send_report_email(
            recipient_email=request.poc_email,
            organization_name=org_name,
            report_month=report_month,
            report_year=report_year,
            pdf_bytes=pdf_bytes
        )

        if not success:
            logger.error(f"Failed to send email to {request.poc_email}")
            return GraphApiResponse(
                status_code=500,
                data={"success": False},
                error="Failed to send email via Graph API. Please check MS_* environment variables."
            )

        logger.info(f"Email sent successfully to {request.poc_email}")

        return GraphApiResponse(
            status_code=200,
            data={
                "success": True,
                "recipient_email": request.poc_email,
                "organization_name": org_name,
                "report_month": report_month,
                "report_year": report_year,
                "pdf_file_path": pdf_file_path,
                "pdf_size_kb": len(pdf_bytes) // 1024,
                "sent_at": datetime.now().isoformat()
            },
            error=None
        )

    except Exception as e:
        logger.error(f"Error sending report to POC: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return GraphApiResponse(
            status_code=500,
            data={"success": False},
            error=f"Internal server error: {str(e)}"
        )
