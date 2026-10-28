# report_endpoint.py

import logging
import os
import io
from fastapi import BackgroundTasks
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.database.engine import get_db
from app.services.llm.llm_service import get_llm_service
from app.services.ppt.report_generator import generate_pptx



class _ListHandler(logging.Handler):
    """Temporary handler that collects log records into a list during a single request."""
    def __init__(self):
        super().__init__()
        self.records: list = []
        self.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

    def emit(self, record):
        self.records.append(self.format(record))
import base64
import copy
from sqlalchemy import text
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Path, Depends, Query, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any, List
from app.schemas.api import GraphApiResponse
from app.schemas.api import AccountAllocationRequest, SaveIntegrationCredentialsRequest
from app.core.database.engine import SessionLocal, get_db
from app.core.database.rpc import rpc_get_account_id_from_uid, rpc_create_account_and_platform_user
from app.models.users import PlatformUser, Account
from app.models.organizations import Organization, OrganizationIntegration
from app.models.integrations import Integration
from app.models.credentials import IntegrationCredential
from app.models.reports import GeneratedReport
from app.routes.reports.llm_report import get_previous_month_autotask_data, get_quarterly_monthly_breakdown
from dotenv import load_dotenv

from app.models.integrations import Integration, PlatformAvailableChart, AccountSelectedChart

load_dotenv()

# Import from the restructured app security reporting system
from app.services.integrations.orchestrator import SecurityAssessmentOrchestrator
from app.utils.frontend_transformer import FrontendTransformer

# Create router for report endpoints
router = APIRouter()
logger = logging.getLogger(__name__)


class OrgInsertRequest(BaseModel):
    account_id: int
    organization_name: str
    domain: Optional[str] = None
    industry: Optional[str] = None
    organization_size: Optional[str] = None
    status: str = "Active"


class OrgIntegrationInsertRequest(BaseModel):
    organization_id: int
    integration_id: int
    platform_organization_id: str
    is_active: bool = True
    last_synced: Optional[datetime] = None


@router.post("/InsertOrganizations", response_model=GraphApiResponse, summary="Insert multiple organizations for an account")
async def insert_organizations(
    payload: List[OrgInsertRequest] = Body(..., description="List of organizations to insert into the organizations table"),
    db: Session = Depends(get_db)
):
    """
    Insert multiple organization rows into the organizations table.

    This endpoint is intended for bulk load of organizations under a specific account_id.
    It does not insert credentials or POCs.
    """
    try:
        if not payload:
            return GraphApiResponse(
                status_code=400,
                data={"success": False, "inserted_count": 0},
                error="Payload cannot be empty. Send a list of organizations."
            )

        inserted_rows = []
        skipped_rows = []

        for item in payload:
            if not item.organization_name or not item.organization_name.strip():
                skipped_rows.append({
                    "account_id": item.account_id,
                    "reason": "organization_name is required"
                })
                continue

            normalized_domain = item.domain.strip() if isinstance(item.domain, str) and item.domain.strip() else None
            normalized_industry = item.industry.strip() if isinstance(item.industry, str) and item.industry.strip() else None
            normalized_size = item.organization_size.strip() if isinstance(item.organization_size, str) and item.organization_size.strip() else None
            normalized_status = (item.status or "Active").strip() if isinstance(item.status, str) else "Active"
            if not normalized_status:
                normalized_status = "Active"

            existing = db.query(Organization).filter(
                Organization.account_id == item.account_id,
                Organization.organization_name == item.organization_name.strip()
            ).first()

            if existing:
                skipped_rows.append({
                    "account_id": item.account_id,
                    "organization_name": item.organization_name.strip(),
                    "reason": "organization already exists for this account"
                })
                continue

            now = datetime.utcnow()
            org = Organization(
                account_id=item.account_id,
                organization_name=item.organization_name.strip(),
                domain=normalized_domain,
                industry=normalized_industry,
                organization_size=normalized_size,
                status=normalized_status,
                created_at=now,
                updated_at=now,
            )
            db.add(org)
            db.flush()
            inserted_rows.append({
                "id": org.id,
                "account_id": org.account_id,
                "organization_name": org.organization_name,
                "domain": org.domain,
                "industry": org.industry,
                "organization_size": org.organization_size,
                "status": org.status,
            })

        db.commit()

        return GraphApiResponse(
            status_code=200,
            data={
                "success": True,
                "inserted_count": len(inserted_rows),
                "inserted_rows": inserted_rows,
                "skipped_count": len(skipped_rows),
                "skipped_rows": skipped_rows,
            },
            error=None,
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Error inserting organizations: {str(e)}")
        return GraphApiResponse(
            status_code=500,
            data={"success": False, "inserted_count": 0},
            error=f"Failed to insert organizations: {str(e)}"
        )


@router.post("/InsertOrganizationIntegrations", response_model=GraphApiResponse, summary="Insert multiple organization integration mappings")
async def insert_organization_integrations(
    payload: List[OrgIntegrationInsertRequest] = Body(..., description="List of organization integration mappings to insert into organization_integrations table"),
    db: Session = Depends(get_db)
):
    """
    Bulk insert rows into organization_integrations.

    Required fields:
      - organization_id
      - integration_id
      - platform_organization_id

    Optional fields:
      - is_active (defaults to True)
      - last_synced
      - created_at and updated_at are auto-filled
    """
    try:
        if not payload:
            return GraphApiResponse(
                status_code=400,
                data={"success": False, "inserted_count": 0},
                error="Payload cannot be empty. Send a list of organization integrations."
            )

        inserted_rows = []
        skipped_rows = []

        for item in payload:
            if item.organization_id is None:
                skipped_rows.append({"reason": "organization_id is required"})
                continue
            if item.integration_id is None:
                skipped_rows.append({"organization_id": item.organization_id, "reason": "integration_id is required"})
                continue
            if not item.platform_organization_id or not item.platform_organization_id.strip():
                skipped_rows.append({"organization_id": item.organization_id, "integration_id": item.integration_id, "reason": "platform_organization_id is required"})
                continue

            existing = db.query(OrganizationIntegration).filter(
                OrganizationIntegration.organization_id == item.organization_id,
                OrganizationIntegration.integration_id == item.integration_id,
            ).first()

            if existing:
                skipped_rows.append({
                    "organization_id": item.organization_id,
                    "integration_id": item.integration_id,
                    "reason": "organization-integration mapping already exists"
                })
                continue

            now = datetime.utcnow()
            mapping = OrganizationIntegration(
                organization_id=item.organization_id,
                integration_id=item.integration_id,
                platform_organization_id=item.platform_organization_id.strip(),
                is_active=item.is_active if item.is_active is not None else True,
                last_synced=item.last_synced,
                created_at=now,
                updated_at=now,
            )
            db.add(mapping)
            db.flush()
            inserted_rows.append({
                "id": mapping.id,
                "organization_id": mapping.organization_id,
                "integration_id": mapping.integration_id,
                "platform_organization_id": mapping.platform_organization_id,
                "is_active": mapping.is_active,
                "last_synced": mapping.last_synced,
            })

        db.commit()

        return GraphApiResponse(
            status_code=200,
            data={
                "success": True,
                "inserted_count": len(inserted_rows),
                "inserted_rows": inserted_rows,
                "skipped_count": len(skipped_rows),
                "skipped_rows": skipped_rows,
            },
            error=None,
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Error inserting organization integrations: {str(e)}")
        return GraphApiResponse(
            status_code=500,
            data={"success": False, "inserted_count": 0},
            error=f"Failed to insert organization integrations: {str(e)}"
        )


@router.get("/GetAvailableReportMonths", response_model=GraphApiResponse,
            summary="Get Available Report Months")
async def get_available_report_months():
    """
    Returns a list of the last 3 months available for report generation.
    Each month includes the key needed for API calls and human-readable information.

    Returns:
        GraphApiResponse: Contains list of available months with keys and date ranges
    """
    try:
        from app.utils.month_selector import MonthSelector

        month_selector = MonthSelector()
        available_months = month_selector.list_available_months()

        # Format response for API consumption
        months_list = [
            {
                "month_key":    "last_3_months",
                "display_name": "Last 3 Months",
                "month_name":   "Last 3 Months",
                "year":         None,
                "month_number": None
            }
        ]
        for month in available_months:
            month_key = f"{month['name'].lower()}_{month['year']}"  # "august_2025"
            months_list.append({
                "month_key":    month_key,
                "display_name": month['display_name'],     # "August 2025"
                "month_name":   month['name'],             # "August"
                "year":         month['year'],             # "2025"
                "month_number": month['month_number']      # "8"
            })

        logger.info(f"Retrieved {len(months_list)} available report months")

        return GraphApiResponse(
            status_code=200,
            data={
                "success": True,
                "available_months": months_list,
                "count": len(months_list),
                "usage_instructions": {
                    "description": "Use the 'month_key' field when calling the report generation endpoint",
                    "example": "GET /api/GenerateSecurityReportJSON/{user_id}/{org_id}?month=november_2024"
                }
            },
            error=None
        )

    except Exception as e:
        logger.error(f"Error retrieving available report months: {e}")
        return GraphApiResponse(
            status_code=500,
            data={
                "success": False,
                "available_months": []
            },
            error=f"Failed to retrieve available months: {str(e)}"
        )

# Add this new endpoint after the existing GenerateSecurityReport endpoint

def get_organization_name(org_id: int) -> str:
    """
    Helper function to fetch organization name from Supabase.

    Args:
        org_id: Organization ID from organizations table

    Returns:
        Organization name string, or "Unknown Organization" if not found
    """
    try:
        db = SessionLocal()
        try:
            org = db.query(Organization).filter(Organization.id == org_id).first()
            if org:
                return org.organization_name
            else:
                logger.warning(f"No organization found for org_id: {org_id}")
                return "Unknown Organization"
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error fetching organization name for org_id {org_id}: {e}")
        return "Unknown Organization"


@router.get("/GenerateSecurityReportJSON/{user_id}/{org_id}", response_model=GraphApiResponse,
            summary="Generate Security Assessment Report JSON")
async def generate_security_report_json_endpoint(
        user_id: str = Path(..., description="User UUID (auth_user_id) from frontend"),
        org_id: int = Path(..., description="Organization ID"),
        month: Optional[str] = Query(None,
                                     description="Report month in 'month_year' format (e.g., 'november_2024', 'december_2024'). If not provided, defaults to previous month.")
):
    """
    Generates a comprehensive security assessment report in JSON format for the specified organization and month.

    NEW STRUCTURE:
    - Uses user_id (UUID) to fetch account_id via Supabase function
    - Uses org_id to identify the organization
    - Supports month selection for historical reports

    Args:
        user_id: User UUID (auth_user_id) from platform_users table
        org_id: Organization ID (organizations.id)
        month: Optional month in 'month_year' format (e.g., 'november_2024'). Defaults to previous month.

    Returns:
        GraphApiResponse: Contains JSON data from frontend transformer

    Example Usage:
        - GET /api/GenerateSecurityReportJSON/{uuid}/{org_id} (previous month - default)
        - GET /api/GenerateSecurityReportJSON/{uuid}/{org_id}?month=november_2024
        - GET /api/GenerateSecurityReportJSON/{uuid}/{org_id}?month=december_2024
    """
    try:
        logger.info(
            f"Generating security report JSON for user_id: {user_id}, org_id: {org_id}, month: {month or 'previous_month'}")

        # DEMO DATA FOR SPECIFIC USER
        demo_user_id = os.getenv("DEMO_USER_ID", "")
        if demo_user_id and user_id == demo_user_id:
            logger.info(f"Returning demo data from dummy.json for user_id: {user_id}")

            # Load demo data from dummy.json file
            dummy_json_path = os.path.join(os.path.dirname(__file__), 'dummy.json')

            try:
                import json
                with open(dummy_json_path, 'r', encoding='utf-8') as f:
                    demo_data = json.load(f)

                # Fetch organization name dynamically based on org_id
                organization_name = get_organization_name(org_id)
                logger.info(f"Fetched organization name: {organization_name} for org_id: {org_id}")

                # Replace placeholders in organization data with actual values
                if "organization" in demo_data:
                    demo_data["organization"]["id"] = str(org_id)
                    demo_data["organization"]["name"] = organization_name

                logger.info(f"Successfully loaded and customized demo data from {dummy_json_path}")

            except FileNotFoundError:
                logger.error(f"dummy.json file not found at {dummy_json_path}")
                return GraphApiResponse(
                    status_code=500,
                    data=None,
                    error="Demo data file not found"
                )
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in dummy.json: {e}")
                return GraphApiResponse(
                    status_code=500,
                    data=None,
                    error=f"Invalid demo data format: {str(e)}"
                )

            # Return the demo data loaded from dummy.json
            return GraphApiResponse(
                status_code=200,
                data=demo_data,
                error=None
            )



        # Step 1: Get account_id from user_id using RPC function
        try:
            db = SessionLocal()
            try:
                account_id = rpc_get_account_id_from_uid(db, user_id)
            finally:
                db.close()

            if not account_id:
                logger.error(f"No account found for user_id: {user_id}")
                return GraphApiResponse(
                    status_code=404,
                    data=None,
                    error=f"User not found or inactive: {user_id}"
                )

            logger.info(f"Resolved user_id {user_id} to account_id: {account_id}")

        except Exception as e:
            logger.error(f"Error fetching account_id for user_id {user_id}: {e}")
            return GraphApiResponse(
                status_code=500,
                data=None,
                error=f"Failed to resolve user credentials: {str(e)}"
            )

        # Step 2: Get organization details and validate it belongs to the account
        try:
            db = SessionLocal()
            try:
                org = db.query(Organization).filter(
                    Organization.id == org_id,
                    Organization.account_id == account_id,
                    Organization.status == 'Active'
                ).first()

                if not org:
                    logger.error(f"Organization {org_id} not found or doesn't belong to account {account_id}")
                    return GraphApiResponse(
                        status_code=403,
                        data=None,
                        error=f"Organization {org_id} not found or access denied"
                    )

                org_name = org.organization_name

                # Get platform IDs from organization_integrations with integration join
                integration_rows = db.query(
                    OrganizationIntegration,
                    Integration.integration_key
                ).join(
                    Integration, Integration.id == OrganizationIntegration.integration_id
                ).filter(
                    OrganizationIntegration.organization_id == org_id
                ).all()

                # Extract ninjaone_org_id from integrations
                ninjaone_org_id = None
                for org_int, integration_key in integration_rows:
                    if integration_key == 'ninjaone':
                        ninjaone_org_id = org_int.platform_organization_id
                        break

                logger.info(f"Validated organization: {org_name} (ninjaone_org_id: {ninjaone_org_id})")
            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error fetching organization {org_id}: {e}")
            return GraphApiResponse(
                status_code=500,
                data=None,
                error=f"Failed to fetch organization details: {str(e)}"
            )

        # Validate month format if provided (should be "november_2024" format or "last_3_months")
        if month and month.strip().lower() != "last_3_months":
            try:
                from app.utils.month_selector import MonthSelector

                month_selector = MonthSelector()
                # This will validate the format and raise ValueError if invalid
                month_info = month_selector.get_month_by_name(month)
                logger.info(f"Using month: {month} -> {month_info.display_name}")

            except ValueError as e:
                # get_month_by_name raises ValueError with clear error message
                return GraphApiResponse(
                    status_code=400,
                    data=None,
                    error=str(e)
                )
            except Exception as e:
                logger.error(f"Error validating month: {e}")
                return GraphApiResponse(
                    status_code=500,
                    data=None,
                    error=f"Error validating month parameter: {str(e)}"
                )

        # Initialize security assessment orchestrator with NEW credential system (account_id + org_id)
        # No organization sync needed - we already validated org exists and belongs to account
        try:
            logger.info(f"Initializing SecurityAssessmentOrchestrator with account_id={account_id}, org_id={org_id}")
            orchestrator = SecurityAssessmentOrchestrator(account_id=account_id, org_id=org_id)
            logger.info("SecurityAssessmentOrchestrator initialized successfully")
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"Failed to initialize SecurityAssessmentOrchestrator: {e}")
            logger.error(f"Full traceback: {error_details}")
            return GraphApiResponse(
                status_code=500,
                data=None,
                error=f"Failed to initialize security assessment system: {str(e)} | Details: {error_details[:500]}"
            )

        # Generate the security assessment data
        try:
            logger.info("Attempting to generate security assessment data...")

            # Use the NEW method: collect_all_data_with_org_id() with account_id and org_id
            security_data = await orchestrator.collect_all_data_with_org_id(
                month_name=month  # Pass selected month to orchestrator
            )

            if not security_data:
                logger.error("Security data generation returned empty result")
                return GraphApiResponse(
                    status_code=500,
                    data=None,
                    error="Security data generation failed - empty result"
                )

            logger.info(f"Security data generation completed successfully")

        except Exception as e:
            logger.error(f"Security data generation failed: {e}")
            return GraphApiResponse(
                status_code=500,
                data=None,
                error=f"Security data generation failed: {str(e)}"
            )

        try:
            logger.info("Transforming data using FrontendTransformer...")

            # Convert month parameter to "November 2024" format for reporting_period
            reporting_period = None
            if month:
                try:
                    parts = month.split('_')
                    if len(parts) == 3 and parts[0].lower() == 'last' and parts[2].lower() == 'months':
                        reporting_period = f"Last {parts[1]} Months"  # "Last 3 Months"
                    else:
                        month_name = parts[0].capitalize()  # "november" -> "November"
                        year = parts[1]  # "2024"
                        reporting_period = f"{month_name} {year}"  # "November 2024"
                except:
                    pass  # If parsing fails, reporting_period will be None and use current month

            transformer = FrontendTransformer()
            frontend_json = transformer.transform_to_frontend_json(
                security_data,
                account_id=account_id,
                reporting_period=reporting_period
            )

            if not frontend_json:
                logger.error("Frontend transformation returned empty result")
                return GraphApiResponse(
                    status_code=500,
                    data=None,
                    error="Frontend transformation failed - empty result"
                )

            logger.info("Frontend transformation completed successfully")

        except Exception as e:
            logger.error(f"Frontend transformation failed: {e}")
            return GraphApiResponse(
                status_code=500,
                data=None,
                error=f"Frontend transformation failed: {str(e)}"
            )
        # Get organization info for response
        logger.info(f"Successfully generated security report JSON for {org_name}")

        # Return the transformed JSON data
        return GraphApiResponse(
            status_code=200,
            data=frontend_json,  # Return the frontend JSON data directly
            error=None
        )

    except Exception as e:
        logger.error(f"Unexpected error generating security report JSON for user_id={user_id}, org_id={org_id}: {e}")
        return GraphApiResponse(
            status_code=500,
            data=None,
            error=f"Internal server error: {str(e)}"
        )


@router.get("/GenerateSecurityReportJSONStream/{user_id}/{org_id}",
            summary="Generate Security Report JSON (Streaming)",
            description="Streams report data platform-by-platform as NDJSON to avoid 504 timeouts.")
async def generate_security_report_json_stream(
        user_id: str = Path(..., description="User UUID (auth_user_id) from frontend"),
        org_id: int = Path(..., description="Organization ID"),
        month: Optional[str] = Query(None,
                                     description="Report month in 'month_year' format (e.g., 'november_2024')")
):
    """
    Streaming version of GenerateSecurityReportJSON.
    Returns NDJSON (newline-delimited JSON) with each platform's data sent as it completes.
    Sends heartbeats every 10 seconds to keep the connection alive and prevent 504 timeouts.

    Each line is a JSON object with a 'type' field:
    - type: "organization"    → organization info (sent first)
    - type: "platform_data"   → a single platform's transformed data
    - type: "heartbeat"       → keep-alive signal (ignore for data)
    - type: "error"           → error for a specific platform
    - type: "complete"        → final signal with execution_info
    """
    import json

    async def stream_generator():
        try:
            # --- Step 1: Validate user_id → get account_id ---
            try:
                db = SessionLocal()
                try:
                    account_id = rpc_get_account_id_from_uid(db, user_id)
                finally:
                    db.close()

                if not account_id:
                    yield json.dumps({"type": "error", "message": f"User not found: {user_id}", "progress": 0}) + "\n"
                    return

                logger.info(f"[Stream] Resolved user_id {user_id} to account_id: {account_id}")

            except Exception as e:
                yield json.dumps({"type": "error", "message": f"Failed to resolve user: {str(e)}", "progress": 0}) + "\n"
                return

            # --- Step 2: Validate org_id belongs to account ---
            try:
                db = SessionLocal()
                try:
                    org = db.query(Organization).filter(
                        Organization.id == org_id,
                        Organization.account_id == account_id,
                        Organization.status == 'Active'
                    ).first()
                finally:
                    db.close()

                if not org:
                    yield json.dumps({"type": "error", "message": f"Organization {org_id} not found or access denied", "progress": 0}) + "\n"
                    return

                org_name = org.organization_name

            except Exception as e:
                yield json.dumps({"type": "error", "message": f"Failed to validate organization: {str(e)}", "progress": 0}) + "\n"
                return

            # --- Step 3: Validate month format ---
            if month and month.strip().lower() != "last_3_months":
                try:
                    from app.utils.month_selector import MonthSelector
                    month_selector = MonthSelector()
                    month_info = month_selector.get_month_by_name(month)
                except ValueError as e:
                    yield json.dumps({"type": "error", "message": str(e), "progress": 0}) + "\n"
                    return
                except Exception as e:
                    yield json.dumps({"type": "error", "message": f"Invalid month: {str(e)}", "progress": 0}) + "\n"
                    return

            # --- Step 4: Initialize orchestrator ---
            try:
                orchestrator = SecurityAssessmentOrchestrator(account_id=account_id, org_id=org_id)
                org_info = orchestrator._initialize_processors_with_org_id()
            except Exception as e:
                yield json.dumps({"type": "error", "message": f"Failed to initialize: {str(e)}", "progress": 0}) + "\n"
                return

            # --- Step 5: Send organization info immediately ---
            reporting_period = None
            if month:
                try:
                    parts = month.split('_')
                    if len(parts) == 3 and parts[0].lower() == 'last' and parts[2].lower() == 'months':
                        reporting_period = f"Last {parts[1]} Months"  # "Last 3 Months"
                    else:
                        month_name_str = parts[0].capitalize()
                        year_str = parts[1]
                        reporting_period = f"{month_name_str} {year_str}"
                except:
                    pass

            transformer = FrontendTransformer()
            execution_info_data = {
                "execution_info": {
                    "organization_id": str(org_id),
                    "organization_name": org_info['organization_name'],
                    "timestamp": datetime.now().isoformat(),
                    "data_sources": []
                }
            }

            org_data = transformer._extract_organization_info(execution_info_data, reporting_period, account_id)

            yield json.dumps({
                "type": "organization",
                "data": {"organization": org_data},
                "progress": 5
            }, default=str) + "\n"

            logger.info(f"[Stream] Sent organization info for {org_name}")

            # --- Step 6: Stream each platform's data ---
            autotask_company_id = org_info.get('autotask_company_id')
            start_time = datetime.now()
            data_sources = []

            async for chunk in orchestrator.stream_data_per_platform(
                company_id=autotask_company_id,
                month_name=month
            ):
                if chunk["type"] == "platform_data":
                    # Transform the raw platform data to frontend format
                    platform_name = chunk["platform"]
                    raw_data = chunk["data"]

                    try:
                        transformed = transformer.transform_single_platform(
                            platform_name, raw_data, account_id
                        )

                        if transformed:
                            yield json.dumps({
                                "type": "platform_data",
                                "platform": platform_name,
                                "data": transformed,
                                "progress": chunk["progress"]
                            }, default=str) + "\n"
                            logger.info(f"[Stream] Sent {platform_name} data")
                        else:
                            yield json.dumps({
                                "type": "error",
                                "platform": platform_name,
                                "message": f"{platform_name}: transformation returned empty data",
                                "progress": chunk["progress"]
                            }, default=str) + "\n"
                            logger.warning(f"[Stream] {platform_name} transform returned empty")

                    except Exception as e:
                        yield json.dumps({
                            "type": "error",
                            "platform": platform_name,
                            "message": f"{platform_name} transform failed: {str(e)}",
                            "progress": chunk["progress"]
                        }, default=str) + "\n"
                        logger.error(f"[Stream] {platform_name} transform error: {e}")

                elif chunk["type"] == "heartbeat":
                    yield json.dumps(chunk, default=str) + "\n"

                elif chunk["type"] == "error":
                    yield json.dumps(chunk, default=str) + "\n"

                elif chunk["type"] == "stream_done":
                    data_sources = chunk.get("data_sources", [])

            # --- Step 7: Send complete signal with execution_info ---
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            yield json.dumps({
                "type": "complete",
                "data": {
                    "execution_info": {
                        "generated_at": start_time.isoformat(),
                        "data_sources_processed": data_sources,
                        "report_type": "Monthly Customer Report",
                        "processing_time_seconds": round(duration, 2),
                        "next_update": (datetime.now() + timedelta(days=30)).isoformat()
                    }
                },
                "progress": 100
            }, default=str) + "\n"

            logger.info(f"[Stream] Report complete in {duration:.1f}s, platforms: {data_sources}")

        except Exception as e:
            logger.error(f"[Stream] Unexpected error: {e}")
            yield json.dumps({"type": "error", "message": f"Unexpected error: {str(e)}", "progress": 0}) + "\n"

    return StreamingResponse(
        stream_generator(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"  # Disable Nginx/proxy buffering
        }
    )


def filter_platform_data(frontend_json: Dict[str, Any], platform_name: str) -> Dict[str, Any]:
    """
    Filter frontend JSON to return only specific platform data.

    Args:
        frontend_json: Full frontend JSON with all platforms
        platform_name: Platform to extract (NinjaOne, Autotask, ConnectSecure)

    Returns:
        Filtered JSON with organization + single platform + execution_info
    """
    filtered = {
        "organization": frontend_json.get("organization", {}),
        "execution_info": frontend_json.get("execution_info", {})
    }

    if platform_name in frontend_json:
        filtered[platform_name] = frontend_json[platform_name]

    return filtered


@router.get("/GenerateNinjaOneReportJSON/{user_id}/{org_id}", response_model=GraphApiResponse,
            summary="Generate NinjaOne-Only Security Report JSON")
async def generate_ninjaone_report_json_endpoint(
        user_id: str = Path(..., description="User UUID (auth_user_id) from frontend"),
        org_id: int = Path(..., description="Organization ID"),
        month: Optional[str] = Query(None, description="Report month name")
):
    """
    Generate security report JSON containing ONLY NinjaOne platform data.

    Returns structure: {"organization": {...}, "NinjaOne": {...}, "execution_info": {...}}
    Respects account_selected_charts filtering.
    """
    try:
        full_response = await generate_security_report_json_endpoint(user_id, org_id, month)

        if full_response.status_code != 200 or not full_response.data:
            return full_response

        filtered_data = filter_platform_data(full_response.data, "NinjaOne")

        return GraphApiResponse(
            status_code=200,
            data=filtered_data,
            error=None
        )
    except Exception as e:
        logger.error(f"Failed to generate NinjaOne report: {e}")
        return GraphApiResponse(
            status_code=500,
            data=None,
            error=f"Failed to generate NinjaOne report: {str(e)}"
        )


@router.get("/GenerateAutotaskReportJSON/{user_id}/{org_id}", response_model=GraphApiResponse,
            summary="Generate Autotask-Only Security Report JSON")
async def generate_autotask_report_json_endpoint(
        user_id: str = Path(..., description="User UUID (auth_user_id) from frontend"),
        org_id: int = Path(..., description="Organization ID"),
        month: Optional[str] = Query(None, description="Report month name")
):
    """
    Generate security report JSON containing ONLY Autotask platform data.

    Returns structure: {"organization": {...}, "Autotask": {...}, "execution_info": {...}}
    Respects account_selected_charts filtering.
    """
    try:
        full_response = await generate_security_report_json_endpoint(user_id, org_id, month)

        if full_response.status_code != 200 or not full_response.data:
            return full_response

        filtered_data = filter_platform_data(full_response.data, "Autotask")

        return GraphApiResponse(
            status_code=200,
            data=filtered_data,
            error=None
        )
    except Exception as e:
        logger.error(f"Failed to generate Autotask report: {e}")
        return GraphApiResponse(
            status_code=500,
            data=None,
            error=f"Failed to generate Autotask report: {str(e)}"
        )


@router.get("/GenerateConnectSecureReportJSON/{user_id}/{org_id}", response_model=GraphApiResponse,
            summary="Generate ConnectSecure-Only Security Report JSON")
async def generate_connectsecure_report_json_endpoint(
        user_id: str = Path(..., description="User UUID (auth_user_id) from frontend"),
        org_id: int = Path(..., description="Organization ID"),
        month: Optional[str] = Query(None, description="Report month name")
):
    """
    Generate security report JSON containing ONLY ConnectSecure platform data.

    Returns structure: {"organization": {...}, "ConnectSecure": {...}, "execution_info": {...}}
    Respects account_selected_charts filtering.
    """
    try:
        full_response = await generate_security_report_json_endpoint(user_id, org_id, month)

        if full_response.status_code != 200 or not full_response.data:
            return full_response

        filtered_data = filter_platform_data(full_response.data, "ConnectSecure")

        return GraphApiResponse(
            status_code=200,
            data=filtered_data,
            error=None
        )
    except Exception as e:
        logger.error(f"Failed to generate ConnectSecure report: {e}")
        return GraphApiResponse(
            status_code=500,
            data=None,
            error=f"Failed to generate ConnectSecure report: {str(e)}"
        )


@router.get("/GenerateBitdefenderReportJSON/{user_id}/{org_id}", response_model=GraphApiResponse,
            summary="Generate Bitdefender-Only Security Report JSON")
async def generate_bitdefender_report_json_endpoint(
        user_id: str = Path(..., description="User UUID (auth_user_id) from frontend"),
        org_id: int = Path(..., description="Organization ID"),
        month: Optional[str] = Query(None, description="Report month name")
):
    """
    Generate security report JSON containing ONLY Bitdefender platform data.

    Returns structure: {"organization": {...}, "Bitdefender": {...}, "execution_info": {...}}
    Respects account_selected_charts filtering.
    """
    try:
        full_response = await generate_security_report_json_endpoint(user_id, org_id, month)

        if full_response.status_code != 200 or not full_response.data:
            return full_response

        filtered_data = filter_platform_data(full_response.data, "Bitdefender")

        return GraphApiResponse(
            status_code=200,
            data=filtered_data,
            error=None
        )
    except Exception as e:
        logger.error(f"Failed to generate Bitdefender report: {e}")
        return GraphApiResponse(
            status_code=500,
            data=None,
            error=f"Failed to generate Bitdefender report: {str(e)}"
        )


@router.post("/AccountAllocation", response_model=GraphApiResponse,
             summary="Allocate New Account and Platform User")
async def account_allocation_endpoint(request: AccountAllocationRequest):
    """
    Creates a new account and platform user in the system.

    This endpoint calls the Supabase function `create_account_and_platform_user` to:
    1. Create a new account with the provided company name
    2. Create a platform user linked to the account and auth user
    3. Return the newly created account_id and platform_user_id

    Args:
        request: AccountAllocationRequest containing:
            - companyName: Company name for the new account (2-255 characters)
            - userId: User UUID (auth_user_id) from Supabase Auth
            - userEmail: User email address

    Returns:
        GraphApiResponse containing:
            - success: Boolean indicating success
            - account_id: Newly created account ID
            - platform_user_id: Newly created platform user ID
            - message: Success message

    Error Handling:
        - 400: Invalid request data (validation errors)
        - 409: User already exists (duplicate userId)
        - 500: Server error or database operation failed

    Example Request:
        POST /api/AccountAllocation
        {
            "companyName": "Acme Corp",
            "userId": "670fef07-80ea-45be-b1ab-5c51461218d2",
            "userEmail": "admin@acmecorp.com"
        }

    Example Response:
        {
            "status_code": 200,
            "data": {
                "success": true,
                "account_id": 123,
                "platform_user_id": 456,
                "message": "Account allocated successfully"
            },
            "error": null
        }
    """
    try:
        logger.info(f"Account allocation request received for company: {request.companyName}, user: {request.userId}")

        # Check if user already exists in platform_users table
        try:
            db = SessionLocal()
            try:
                existing_user = db.query(PlatformUser).filter(
                    PlatformUser.auth_user_id == request.userId
                ).first()
            finally:
                db.close()

            if existing_user:
                logger.warning(f"User already exists: {request.userId}")
                return GraphApiResponse(
                    status_code=409,
                    data={
                        "success": False,
                        "message": "This user already exists",
                        "existing_platform_user_id": existing_user.id,
                        "existing_account_id": existing_user.account_id
                    },
                    error="User with this userId already exists in the system"
                )
        except Exception as e:
            logger.error(f"Error checking existing user: {e}")
            # Continue with creation attempt even if check fails

        # Call the RPC function to create account and platform user
        try:
            db = SessionLocal()
            try:
                result = rpc_create_account_and_platform_user(
                    db, request.companyName, request.userId, request.userEmail
                )
                db.commit() 
            
            except Exception:
                db.rollback()       
                raise
            finally:
                db.close()

            if not result:
                logger.error("RPC function returned empty result")
                return GraphApiResponse(
                    status_code=500,
                    data=None,
                    error="Failed to create account: Database function returned empty result"
                )

            # Extract the returned IDs
            account_id = result.get('account_id')
            platform_user_id = result.get('platform_user_id')

            if not account_id or not platform_user_id:
                logger.error(f"Invalid response from database function: {result}")
                return GraphApiResponse(
                    status_code=500,
                    data=None,
                    error="Failed to create account: Invalid response from database"
                )

            logger.info(f"Account created successfully - account_id: {account_id}, platform_user_id: {platform_user_id}")

            return GraphApiResponse(
                status_code=200,
                data={
                    "success": True,
                    "account_id": account_id,
                    "platform_user_id": platform_user_id,
                    "message": "Account allocated successfully",
                    "company_name": request.companyName,
                    "user_email": request.userEmail
                },
                error=None
            )

        except Exception as e:
            error_message = str(e)
            logger.error(f"Error calling Supabase function: {error_message}")

            # Check for specific database errors
            if "duplicate key" in error_message.lower() or "already exists" in error_message.lower():
                return GraphApiResponse(
                    status_code=409,
                    data=None,
                    error="This user already exists in the system"
                )
            elif "foreign key" in error_message.lower():
                return GraphApiResponse(
                    status_code=400,
                    data=None,
                    error="Invalid user ID: User must exist in Supabase Auth"
                )
            else:
                return GraphApiResponse(
                    status_code=500,
                    data=None,
                    error=f"Database operation failed: {error_message}"
                )

    except ValueError as ve:
        # Validation errors from Pydantic
        logger.error(f"Validation error: {ve}")
        return GraphApiResponse(
            status_code=400,
            data=None,
            error=f"Invalid request data: {str(ve)}"
        )

    except Exception as e:
        logger.error(f"Unexpected error in account allocation: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return GraphApiResponse(
            status_code=500,
            data=None,
            error=f"Internal server error: {str(e)}"
        )


@router.post("/SaveIntegrationCredentials", response_model=GraphApiResponse,
             summary="Save Integration Credentials and Sync Organizations")
async def save_integration_credentials_endpoint(request: SaveIntegrationCredentialsRequest):
    """
    Save encrypted integration credentials for NinjaOne, Autotask, and/or ConnectSecure platforms,
    test the credentials, fetch organizations, perform fuzzy matching, and save organization mappings.

    Workflow:
    1. Validate request and extract platform credentials
    2. Transform to encryption format and encrypt using EncryptionManager
    3. Save to integration_credentials table (or update if exists)
    4. Test each platform's credentials by attempting API calls
    5. Fetch organization lists from each platform
    6. Perform fuzzy matching to map organizations across platforms
    7. Save/update organization mappings to organizations table
    8. Return detailed response with mappings and confidence scores

    Args:
        request: SaveIntegrationCredentialsRequest containing:
            - companyId: Account ID (account_id in database)
            - companyName: Company name
            - userId: User UUID (auth_user_id)
            - platforms: List of platform configurations (at least one)

    Returns:
        GraphApiResponse containing:
            - success: Boolean indicating success
            - message: Success/error message
            - credential_id: ID of saved integration_credentials record
            - platforms_tested: List of successfully tested platforms
            - organizations_synced: Count of synced organizations
            - organization_mappings: List of mapped organizations with confidence scores

    Error Handling:
        - 400: Invalid request data
        - 403: Account access denied
        - 500: Encryption, database, or API errors

    Example Request:
        POST /api/SaveIntegrationCredentials
        {
            "companyId": 41,
            "companyName": "Crimson Retail",
            "userId": "201d1004-4d25-4466-9d10-1936afd62a78",
            "platforms": [
                {
                    "platform": "ninjaone",
                    "configuration": {
                        "ninjaone_client_id": "xxxx",
                        "ninjaone_client_secret": "yyyy",
                        "ninjaone_instance_url": "https://app.ninjarmm.com"
                    }
                },
                {
                    "platform": "autotask",
                    "configuration": {
                        "autotask_username": "user@example.com",
                        "autotask_secret": "secret",
                        "autotask_integration_code": "code"
                    }
                }
            ]
        }
    """
    try:
        logger.info(f"SaveIntegrationCredentials request received for account_id: {request.companyId}, "
                   f"platforms: {[p.platform for p in request.platforms]}")

        # Step 1: Validate account exists (simple validation)
        try:
            db = SessionLocal()
            try:
                account = db.query(Account).filter(Account.id == request.companyId).first()
            finally:
                db.close()

            if not account:
                logger.error(f"Account {request.companyId} not found")
                return GraphApiResponse(
                    status_code=403,
                    data=None,
                    error=f"Account {request.companyId} not found"
                )

            logger.info(f"Validated account ID: {request.companyId}")

        except Exception as e:
            logger.error(f"Error validating account: {e}")
            return GraphApiResponse(
                status_code=500,
                data=None,
                error=f"Failed to validate account: {str(e)}"
            )

        # Step 2: Transform payload to encryption format
        # Combine all platform configurations into single credentials dict
        combined_credentials = {}

        for platform_item in request.platforms:
            platform_name = platform_item.platform.lower()
            config = platform_item.configuration

            # Convert Pydantic model to dict if needed
            if hasattr(config, 'dict'):
                config_dict = config.dict(exclude_unset=True, exclude_none=True)
            else:
                config_dict = dict(config)

            # Merge into combined credentials
            combined_credentials.update(config_dict)

        logger.info(f"Combined credentials keys: {list(combined_credentials.keys())}")

        # Step 3: Encrypt credentials using EncryptionManager
        try:
            from app.services.encryption.manager import EncryptionManager

            encryption_manager = EncryptionManager()
            encrypted_blob = encryption_manager.encrypt_integration_credentials(combined_credentials)

            logger.info("Credentials encrypted successfully")

        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            return GraphApiResponse(
                status_code=500,
                data=None,
                error=f"Failed to encrypt credentials: {str(e)}"
            )

        # Step 4: Save or update integration_credentials record
        try:
            db = SessionLocal()
            try:
                cred_row = db.query(IntegrationCredential).filter(
                    IntegrationCredential.account_id == request.companyId,
                    IntegrationCredential.is_active == True
                ).first()

                if cred_row:
                    credential_id = cred_row.id
                    cred_row.credentials = encrypted_blob
                    cred_row.is_active = True
                    cred_row.updated_at = datetime.now()
                    db.commit()
                    logger.info(f"Updated existing credentials (ID: {credential_id})")
                else:
                    new_cred = IntegrationCredential(
                        account_id=request.companyId,
                        credentials=encrypted_blob,
                        is_active=True,
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                    db.add(new_cred)
                    db.commit()
                    db.refresh(new_cred)
                    credential_id = new_cred.id
                    logger.info(f"Inserted new credentials (ID: {credential_id})")
            finally:
                db.close()

        except Exception as e:
            logger.error(f"Failed to save credentials: {e}")
            return GraphApiResponse(
                status_code=500,
                data=None,
                error=f"Failed to save credentials to database: {str(e)}"
            )

        # Step 5: Test credentials and fetch organizations from each platform
        import asyncio
        import httpx

        platforms_tested = []
        platforms_failed = []
        ninjaone_orgs = []
        autotask_companies = []
        connectsecure_companies = []

        # Test each platform
        for platform_item in request.platforms:
            platform_name = platform_item.platform.lower()

            try:
                if platform_name == 'ninjaone':
                    # Test NinjaOne credentials
                    config = platform_item.configuration
                    if hasattr(config, 'dict'):
                        config_dict = config.dict(exclude_unset=True, exclude_none=True)
                    else:
                        config_dict = dict(config)

                    token_url = f"{config_dict.get('ninjaone_instance_url')}/oauth/token"

                    async with httpx.AsyncClient() as client:
                        token_response = await client.post(token_url, data={
                            'grant_type': 'client_credentials',
                            'client_id': config_dict.get('ninjaone_client_id'),
                            'client_secret': config_dict.get('ninjaone_client_secret'),
                            'scope': config_dict.get('ninjaone_scopes', 'monitoring management')
                        }, timeout=30.0)
                        token_response.raise_for_status()
                        token = token_response.json()['access_token']

                        # Fetch organizations
                        headers = {
                            'Authorization': f'Bearer {token}',
                            'Accept': 'application/json'
                        }
                        org_response = await client.get(
                            f"{config_dict.get('ninjaone_instance_url')}/v2/organizations",
                            headers=headers,
                            timeout=30.0
                        )
                        org_response.raise_for_status()
                        ninjaone_orgs = org_response.json()

                        platforms_tested.append('ninjaone')
                        logger.info(f"✓ NinjaOne tested successfully - {len(ninjaone_orgs)} organizations fetched")

                elif platform_name == 'autotask':
                    # Test Autotask credentials
                    config = platform_item.configuration
                    if hasattr(config, 'dict'):
                        config_dict = config.dict(exclude_unset=True, exclude_none=True)
                    else:
                        config_dict = dict(config)

                    # Get zone URL first
                    zone_info_url = f"https://webservices.autotask.net/atservicesrest/v1.0/zoneInformation?user={config_dict.get('autotask_username')}"

                    async with httpx.AsyncClient(timeout=30.0) as client:
                        zone_response = await client.get(zone_info_url)
                        zone_response.raise_for_status()
                        zone_data = zone_response.json()
                        zone_url = zone_data.get('url').rstrip('/') + '/'

                        # Fetch companies
                        headers = {
                            "UserName": config_dict.get('autotask_username'),
                            "Secret": config_dict.get('autotask_secret'),
                            "APIIntegrationcode": config_dict.get('autotask_integration_code'),
                            "Content-Type": "application/json"
                        }

                        query_data = {
                            "MaxRecords": 500,
                            "filter": [{"field": "isActive", "op": "eq", "value": True}]
                        }

                        company_response = await client.post(
                            f"{zone_url}v1.0/Companies/query",
                            headers=headers,
                            json=query_data,
                            timeout=30.0
                        )
                        company_response.raise_for_status()
                        company_data = company_response.json()
                        autotask_companies = company_data.get('items', [])

                        platforms_tested.append('autotask')
                        logger.info(f"✓ Autotask tested successfully - {len(autotask_companies)} companies fetched")

                elif platform_name == 'connectsecure':
                    # Test ConnectSecure credentials
                    config = platform_item.configuration
                    if hasattr(config, 'dict'):
                        config_dict = config.dict(exclude_unset=True, exclude_none=True)
                    else:
                        config_dict = dict(config)

                    auth_url = f"{config_dict.get('connectsecure_base_url')}/w/authorize"

                    headers = {
                        "Client-Auth-Token": base64.b64encode(
                            f"{config_dict.get('connectsecure_tenant_name')}+{config_dict.get('connectsecure_client_id')}:{config_dict.get('connectsecure_client_secret_b64')}".encode()
                        ).decode(),
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    }

                    async with httpx.AsyncClient() as client:
                        auth_response = await client.post(auth_url, headers=headers, timeout=30.0)
                        auth_response.raise_for_status()
                        token_data = auth_response.json()

                        access_token = token_data.get('access_token')
                        user_id = str(token_data.get('user_id'))

                        # Fetch companies
                        company_headers = {
                            'Authorization': f'Bearer {access_token}',
                            'X-User-ID': user_id,
                            'Accept': 'application/json',
                            'Content-Type': 'application/json'
                        }

                        company_response = await client.get(
                            f"{config_dict.get('connectsecure_base_url')}/r/company/companies",
                            headers=company_headers,
                            timeout=30.0
                        )
                        company_response.raise_for_status()
                        company_data = company_response.json()

                        # Handle different response formats
                        if isinstance(company_data, list):
                            connectsecure_companies = company_data
                        elif isinstance(company_data, dict) and 'data' in company_data:
                            connectsecure_companies = company_data['data']
                        elif isinstance(company_data, dict) and 'companies' in company_data:
                            connectsecure_companies = company_data['companies']
                        else:
                            connectsecure_companies = []

                        platforms_tested.append('connectsecure')
                        logger.info(f"✓ ConnectSecure tested successfully - {len(connectsecure_companies)} companies fetched")

                elif platform_name == 'dnsfilter':
                    config = platform_item.configuration
                    if hasattr(config, 'dict'):
                        config_dict = config.dict(exclude_unset=True, exclude_none=True)
                    else:
                        config_dict = dict(config)

                    api_key = config_dict.get('dnsfilter_api_key', '')
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        test_response = await client.get(
                            "https://api.dnsfilter.com/v1/organizations/all",
                            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
                        )
                        test_response.raise_for_status()

                    platforms_tested.append('dnsfilter')
                    logger.info(f"✓ DNSFilter tested successfully")

            except Exception as e:
                logger.warning(f"⚠ {platform_name.title()} test failed: {e}")
                platforms_failed.append({
                    'platform': platform_name,
                    'error': str(e)
                })

        # Step 6: Perform fuzzy matching using OrganizationMatcher
        try:
            from app.services.organizations.matcher import OrganizationMatcher

            matcher = OrganizationMatcher()
            organization_mappings = matcher.match_organizations(
                ninjaone_orgs,
                autotask_companies,
                connectsecure_companies
            )

            logger.info(f"Created {len(organization_mappings)} organization mappings")

        except Exception as e:
            logger.error(f"Organization matching failed: {e}")
            return GraphApiResponse(
                status_code=500,
                data=None,
                error=f"Organization matching failed: {str(e)}"
            )

        # Step 7: Save organization mappings to organizations table
        organizations_created = 0
        organizations_updated = 0
        organizations_failed = 0

        try:
            # Get integration IDs for mapping
            integrations_map = {}
            try:
                db = SessionLocal()
                try:
                    int_rows = db.query(Integration).filter(Integration.is_active == True).all()
                    for row in int_rows:
                        integrations_map[row.integration_key] = row.id
                finally:
                    db.close()

                logger.info(f"Loaded integrations map: {integrations_map}")
            except Exception as e:
                logger.error(f"Failed to load integrations: {e}")
                return GraphApiResponse(
                    status_code=500,
                    data=None,
                    error=f"Failed to load platform integrations: {str(e)}"
                )

            for mapping in organization_mappings:
                try:
                    db = SessionLocal()
                    try:
                        # Check if organization already exists by organization_name and account_id
                        existing_org = db.query(Organization).filter(
                            Organization.account_id == request.companyId,
                            Organization.organization_name == mapping['organization_name']
                        ).first()

                        org_id = None
                        if existing_org:
                            org_id = existing_org.id
                            existing_org.status = 'Active'
                            existing_org.updated_at = datetime.now()
                            db.commit()
                            organizations_updated += 1
                            logger.info(f"Updated organization: {mapping['organization_name']} (ID: {org_id})")
                        else:
                            new_org = Organization(
                                account_id=request.companyId,
                                organization_name=mapping['organization_name'],
                                status='Active',
                                created_at=datetime.now(),
                                updated_at=datetime.now()
                            )
                            db.add(new_org)
                            db.commit()
                            db.refresh(new_org)
                            org_id = new_org.id
                            organizations_created += 1
                            logger.info(f"Created new organization: {mapping['organization_name']} (ID: {org_id})")

                        # Now insert/update organization_integrations for each platform
                        platform_mappings = {
                            'ninjaone': mapping.get('ninjaone_org_id'),
                            'autotask': mapping.get('autotask_id'),
                            'connectsecure': mapping.get('connect_secure_id')
                        }

                        for platform_key, platform_org_id in platform_mappings.items():
                            if platform_org_id and platform_key in integrations_map:
                                integration_id = integrations_map[platform_key]

                                existing_int = db.query(OrganizationIntegration).filter(
                                    OrganizationIntegration.organization_id == org_id,
                                    OrganizationIntegration.integration_id == integration_id
                                ).first()

                                if existing_int:
                                    existing_int.platform_organization_id = str(platform_org_id)
                                    existing_int.is_active = True
                                    existing_int.last_synced = datetime.now()
                                    existing_int.updated_at = datetime.now()
                                    logger.debug(f"  Updated {platform_key} integration mapping")
                                else:
                                    db.add(OrganizationIntegration(
                                        organization_id=org_id,
                                        integration_id=integration_id,
                                        platform_organization_id=str(platform_org_id),
                                        is_active=True,
                                        last_synced=datetime.now(),
                                        created_at=datetime.now(),
                                        updated_at=datetime.now()
                                    ))
                                    logger.debug(f"  Created {platform_key} integration mapping")

                        db.commit()
                    finally:
                        db.close()

                except Exception as e:
                    logger.error(f"Failed to save organization {mapping.get('organization_name')}: {e}")
                    logger.error(f"Error details: {str(e)}")
                    organizations_failed += 1

            logger.info(f"Organizations saved: {organizations_created} created, {organizations_updated} updated, {organizations_failed} failed")

        except Exception as e:
            logger.error(f"Failed to save organizations: {e}")
            return GraphApiResponse(
                status_code=500,
                data=None,
                error=f"Failed to save organization mappings: {str(e)}"
            )

        # Step 8: Build response
        response_data = {
            "success": True,
            "message": f"Integration credentials saved and {len(organization_mappings)} organizations synced",
            "credential_id": credential_id,
            "platforms_tested": platforms_tested,
            "platforms_failed": platforms_failed if platforms_failed else None,
            "organizations_summary": {
                "total_synced": len(organization_mappings),
                "created": organizations_created,
                "updated": organizations_updated,
                "failed": organizations_failed
            },
            "organization_mappings": [
                {
                    "organization_name": m['organization_name'],
                    "ninjaone_org_id": m['ninjaone_org_id'],
                    "autotask_id": m.get('autotask_id'),
                    "connect_secure_id": m.get('connect_secure_id'),
                    "match_confidence": m.get('match_confidence', 0.0),
                    "match_method": m.get('match_method', 'unknown')
                }
                for m in organization_mappings[:50]  # Limit to first 50 for response size
            ]
        }

        logger.info(f"✓ SaveIntegrationCredentials completed successfully for account {request.companyId}")

        return GraphApiResponse(
            status_code=200,
            data=response_data,
            error=None
        )

    except Exception as e:
        logger.error(f"Unexpected error in SaveIntegrationCredentials: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return GraphApiResponse(
            status_code=500,
            data=None,
            error=f"Internal server error: {str(e)}"
        )


@router.post("/SaveSecurityReport", response_model=GraphApiResponse, summary="Generate and Save Security Report")
async def save_security_report_endpoint(
        user_id: str,
        org_id: int,
        month: Optional[str] = None,
        generate_llm: bool = Query(False, description="If true, call OpenAI and save llm_data to the report row"),
        generate_ppt: bool = Query(False, description="If true, generate PPTX and upload to Supabase bucket, updating file_path/file_url on the row"),
        return_data: bool = Query(False, description="If true, returns the raw organization_data and llm_data in the response payload")
):
    """
    Generate a security report and save it to the database.

    Args:
        user_id: User UUID (auth_user_id) from platform_users table
        org_id: Organization ID
        month: Month in 'month_year' format (e.g., 'march_2026') or 'last_3_months' for quarterly.
               Defaults to previous month if not provided.
        generate_llm: Call OpenAI and save llm_data to the report row (default: False)
        generate_ppt: Generate PPTX, upload to Supabase bucket, update file_path/file_url (default: False)

    Returns:
        GraphApiResponse with report_id, report_type, and platforms list
    """
    _log_collector = _ListHandler()
    logging.getLogger().addHandler(_log_collector)
    try:
        logger.info(f"SaveSecurityReport called for user_id: {user_id}, org_id: {org_id}, month: {month or 'previous_month'}, generate_llm: {generate_llm}, generate_ppt: {generate_ppt}")

        # Step 1: Call the existing GenerateSecurityReportJSON endpoint to get report data
        logger.info("Calling GenerateSecurityReportJSON endpoint to fetch report data")
        report_response = await generate_security_report_json_endpoint(
            user_id=user_id,
            org_id=org_id,
            month=month
        )

        # Check if report generation was successful
        if report_response.status_code != 200 or not report_response.data:
            logger.error(f"Failed to generate report: status={report_response.status_code}, error={report_response.error}")
            return GraphApiResponse(
                status_code=report_response.status_code,
                data=None,
                error=f"Failed to generate report: {report_response.error}"
            )

        json_response = report_response.data
        logger.info("Successfully fetched report JSON from GenerateSecurityReportJSON")

        # Step 2: Parse month parameter → report_month, report_year, report_type (moved before LLM call)
        organization_data = json_response

        if month and month.strip().lower() == "last_3_months":
            from app.utils.month_selector import MonthSelector
            ms = MonthSelector()
            start_ts, end_ts = ms.get_quarterly_date_range()
            start_dt = datetime.fromtimestamp(start_ts)
            end_dt   = datetime.fromtimestamp(end_ts)
            report_month = f"{start_dt.strftime('%B')}-{end_dt.strftime('%B')}"
            report_year  = end_dt.year
            report_type  = "quarterly"
            logger.info(f"Parsed 'last_3_months' -> report_month={report_month}, report_year={report_year}, report_type=quarterly")

        elif month and '_' in month:
            parts = month.split('_')
            report_month = parts[0].capitalize()
            report_year  = int(parts[1])
            report_type  = "monthly"
            logger.info(f"Parsed '{month}' -> report_month={report_month}, report_year={report_year}, report_type=monthly")

        else:
            # Fallback: extract from reporting_period in organization data
            reporting_period = organization_data.get("reporting_period", "")
            if reporting_period:
                parts = reporting_period.split()
                report_month = parts[0] if len(parts) > 0 else "Unknown"
                report_year  = int(parts[1]) if len(parts) > 1 else datetime.now().year
            else:
                report_month = "Unknown"
                report_year  = datetime.now().year
            report_type = "monthly"
            logger.info(f"Fallback from reporting_period: report_month={report_month}, report_year={report_year}")

        # Step 3: Generate LLM slide data (only if generate_llm=True)
        llm_data = None
        if generate_llm:
            try:
                from app.services.llm.llm_service import get_llm_service
                logger.info("Calling OpenAI to generate LLM slide data...")
                db_prev = SessionLocal()
                try:
                    prev_month_data = get_previous_month_autotask_data(db_prev, org_id, report_month, report_year)
                finally:
                    db_prev.close()
                if prev_month_data:
                    logger.info(f"Previous month data found: {prev_month_data.get('month')} — comparison will be included in Slide 8")
                else:
                    logger.info("No previous month data found in DB — Slide 8 will use current values only")
                db_prev2 = SessionLocal()
                try:
                    quarterly_breakdown = get_quarterly_monthly_breakdown(db_prev2, org_id, report_month, report_year)
                finally:
                    db_prev2.close()
                if quarterly_breakdown:
                    found = len(quarterly_breakdown.get("months", []))
                    logger.info(f"Quarterly breakdown found: {found}/3 monthly reports for {report_month} — within-quarter trend enabled on Slide 8")
                else:
                    logger.info("No quarterly monthly breakdown — Slide 8 will use current values only")
                service = get_llm_service()
                llm_data = await service.generate_llm_data(json_response, previous_month_data=prev_month_data, quarterly_breakdown=quarterly_breakdown)
                logger.info("LLM slide data generated successfully")
            except Exception as llm_err:
                logger.error(f"LLM generation failed (non-fatal) — llm_data will be null: {llm_err}")
        else:
            logger.info("generate_llm=False — skipping LLM generation")

        # Step 4: Upsert — overwrite existing active row or insert new
        logger.info(f"Checking for existing active report: org_id={org_id}, month={report_month}, year={report_year}, type={report_type}")

        db = SessionLocal()
        try:
            existing_report = db.query(GeneratedReport).filter(
                GeneratedReport.organization_id == org_id,
                GeneratedReport.report_month    == report_month,
                GeneratedReport.report_year     == report_year,
                GeneratedReport.report_type     == report_type,
                GeneratedReport.status          == "Active"
            ).first()

            if existing_report:
                logger.info(f"Found existing active report ID={existing_report.id} — overwriting in place")
                existing_report.organization_data = organization_data
                existing_report.llm_data          = llm_data
                existing_report.generated_at      = datetime.now()
                existing_report.updated_at        = datetime.now()
                existing_report.file_path         = None
                existing_report.file_url          = None
                existing_report.pdf_generated_at  = None
                db.commit()
                db.refresh(existing_report)
                report_id = existing_report.id
                logger.info(f"Overwrote existing report ID={report_id}")
            else:
                logger.info("No existing report found — inserting new active report row")
                new_report = GeneratedReport(
                    organization_id   = org_id,
                    report_month      = report_month,
                    report_year       = report_year,
                    report_type       = report_type,
                    organization_data = organization_data,
                    llm_data          = llm_data,
                    status            = "Active",
                    generated_at      = datetime.now(),
                    created_at        = datetime.now(),
                    updated_at        = datetime.now(),
                )
                db.add(new_report)
                db.commit()
                db.refresh(new_report)
                report_id = new_report.id
                logger.info(f"Inserted new report ID={report_id}")

            platforms_saved = [k for k in json_response if k not in ("organization", "execution_info")]
            platforms_skipped = []

        finally:
            db.close()

        # Step 5: Generate PPTX and upload to Supabase bucket (only if generate_ppt=True)
        file_url = None
        if generate_ppt:
            try:
                from app.services.ppt.report_generator import generate_pptx
                from supabase import create_client as supabase_create_client

                logger.info(f"generate_ppt=True — generating PPTX for report_id={report_id}")
                pptx_input = dict(organization_data)
                if llm_data:
                    pptx_input['llm_data'] = llm_data
                pptx_buf = generate_pptx(pptx_input)
                pptx_bytes = pptx_buf.read()
                logger.info(f"PPTX generated: {len(pptx_bytes)} bytes")

                # Fetch account_id for storage path
                db2 = SessionLocal()
                try:
                    account_id = rpc_get_account_id_from_uid(db2, user_id)
                finally:
                    db2.close()

                storage_path = f"reports/{account_id}/{org_id}/{report_year}/{report_month}.pptx"
                logger.info(f"Uploading PPTX to bucket path: {storage_path}")

                service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
                storage_client = supabase_create_client(os.getenv("SUPABASE_URL"), service_key)
                storage_client.storage.from_("bucket").upload(
                    path=storage_path,
                    file=pptx_bytes,
                    file_options={
                        "content-type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                        "upsert": "true"
                    }
                )
                file_url = storage_client.storage.from_("bucket").get_public_url(storage_path)
                logger.info(f"PPTX uploaded. URL: {file_url}")

                # Update the newly inserted report row with file info
                db3 = SessionLocal()
                try:
                    saved_report = db3.query(GeneratedReport).filter(GeneratedReport.id == report_id).first()
                    if saved_report:
                        saved_report.file_path        = storage_path
                        saved_report.file_url         = file_url
                        saved_report.pdf_generated_at = datetime.now()
                        saved_report.updated_at       = datetime.now()
                        db3.commit()
                        logger.info(f"Updated report_id={report_id} with file_path and file_url")
                finally:
                    db3.close()

            except Exception as ppt_err:
                logger.error(f"PPTX generation/upload failed (non-fatal): {ppt_err}")
        else:
            logger.info("generate_ppt=False — skipping PPTX generation")

        # Step 6: Return success response
        logger.info(f"SaveSecurityReport completed. Report ID={report_id}, type={report_type}, month={report_month} {report_year}")
        response_data = {
            "success": True,
            "report_id": report_id,
            "organization_id": org_id,
            "report_month": report_month,
            "report_year": report_year,
            "report_type": report_type,
            "llm_data_saved": llm_data is not None,
            "pptx_uploaded": file_url is not None,
            "file_url": file_url,
            "platforms_saved": platforms_saved,
            "platforms_skipped": platforms_skipped,
            "execution_logs": _log_collector.records,
        }

        if return_data:
            # .update() unpacks all top-level keys (Cove, NinjaOne, organization, etc.) directly into response_data
            response_data.update(organization_data)

            # Explicitly append the llm_data (which could be None or a populated dict)
            response_data["llm_data"] = llm_data

        return GraphApiResponse(
            status_code=200,
            data=response_data,
            error=None
        )

    except Exception as e:
        logger.error(f"Unexpected error in SaveSecurityReport: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return GraphApiResponse(
            status_code=500,
            data=None,
            error=f"Internal server error: {str(e)}"
        )
    finally:
        logging.getLogger().removeHandler(_log_collector)


@router.get("/GenerateLLMSecurityReportJSON/{user_id}/{org_id}", response_model=GraphApiResponse,
            summary="Generate Security Report JSON with LLM slide data")
async def generate_llm_security_report_json_endpoint(
        user_id: str = Path(..., description="User UUID (auth_user_id) from frontend"),
        org_id: int = Path(..., description="Organization ID"),
        month: Optional[str] = Query(None,
                                     description="Report month: 'march_2026' or 'last_3_months'. Defaults to previous month.")
):
    """
    Same as GenerateSecurityReportJSON but also appends freshly generated LLM slide data.
    llm_data is null if OpenAI generation fails.
    """
    try:
        logger.info(f"GenerateLLMSecurityReportJSON called for user_id={user_id}, org_id={org_id}, month={month or 'previous_month'}")

        # Step 1: Generate full security report JSON (same as existing endpoint)
        report_response = await generate_security_report_json_endpoint(
            user_id=user_id,
            org_id=org_id,
            month=month
        )

        if report_response.status_code != 200 or not report_response.data:
            logger.error(f"Failed to generate security report: {report_response.error}")
            return GraphApiResponse(
                status_code=report_response.status_code,
                data=None,
                error=f"Failed to generate security report: {report_response.error}"
            )

        organization_data = report_response.data
        logger.info("Security report JSON generated successfully — calling OpenAI for LLM data...")

        # Step 2: Generate LLM slide data from the report JSON
        llm_data = None
        try:
            from app.services.llm.llm_service import get_llm_service
            _rm, _ry = None, None
            if month and month.strip().lower() != "last_3_months" and '_' in month:
                _parts = month.split('_')
                _rm, _ry = _parts[0].capitalize(), int(_parts[1])
            prev_month_data = None
            if _rm and _ry:
                db_prev = SessionLocal()
                try:
                    prev_month_data = get_previous_month_autotask_data(db_prev, org_id, _rm, _ry)
                finally:
                    db_prev.close()
            quarterly_breakdown = None
            if _rm and _ry:
                db_prev2 = SessionLocal()
                try:
                    quarterly_breakdown = get_quarterly_monthly_breakdown(db_prev2, org_id, _rm, _ry)
                finally:
                    db_prev2.close()
            if quarterly_breakdown:
                found = len(quarterly_breakdown.get("months", []))
                logger.info(f"Quarterly breakdown found: {found}/3 monthly reports for {_rm} — within-quarter trend enabled on Slide 8")
            service = get_llm_service()
            llm_data = await service.generate_llm_data(organization_data, previous_month_data=prev_month_data, quarterly_breakdown=quarterly_breakdown)
            logger.info("LLM slide data generated successfully")
        except Exception as llm_err:
            logger.error(f"LLM generation failed (non-fatal) — returning llm_data=null: {llm_err}")

        # Step 3: Append llm_data to response
        logger.info("Building response dict...")
        response_data = dict(organization_data)
        response_data["llm_data"] = llm_data
        logger.info(f"Response dict built — keys: {list(response_data.keys())}")

        logger.info("Serializing response via FastAPI...")
        result = GraphApiResponse(
            status_code=200,
            data=response_data,
            error=None
        )
        logger.info("Response serialized — returning to client")
        return result

    except Exception as e:
        logger.error(f"Unexpected error in GenerateLLMSecurityReportJSON: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return GraphApiResponse(
            status_code=500,
            data=None,
            error=f"Internal server error: {str(e)}"
        )

def _filter_charts_by_selection(organization_data: Dict[str, Any], account_id: int) -> Dict[str, Any]:
    """
    Remove deselected charts from a saved report's organization_data before it's sent
    to the frontend. Safely traverses infinitely deep JSON paths and ignores nulls.
    """
    db = SessionLocal()
    try:
        rows = db.query(
            PlatformAvailableChart.json_path,
            AccountSelectedChart.is_active
        ).join(
            AccountSelectedChart, AccountSelectedChart.chart_id == PlatformAvailableChart.id
        ).filter(
            AccountSelectedChart.account_id == account_id
        ).all()
    finally:
        db.close()

    if not rows:
        logger.info(f"No account_selected_charts rows for account {account_id} — returning report unfiltered")
        return organization_data

    # FIX 1: Safely ignore NULL values and strip trailing spaces from the database
    inactive_paths = [
        json_path.strip()
        for json_path, is_active in rows
        if not is_active and json_path
    ]

    if not inactive_paths:
        logger.info(f"Account {account_id} has no deselected charts — returning report unfiltered")
        return organization_data

    filtered_data = copy.deepcopy(organization_data)

    for json_path in inactive_paths:
        # FIX 2: Split entirely, without the limit of 2
        keys = json_path.split(".")
        if len(keys) < 2:
            logger.warning(f"account {account_id}: unexpected json_path format '{json_path}' — skipping")
            continue

        # Dynamic Traversal: Walk down the dictionary to the second-to-last key
        current_level = filtered_data
        valid_path = True
        
        for key in keys[:-1]:
            if isinstance(current_level, dict) and key in current_level:
                current_level = current_level[key]
            else:
                logger.warning(f"account {account_id}: path '{json_path}' broken at '{key}' — skipping")
                valid_path = False
                break
        
        # If we successfully reached the final parent dict, delete the target key
        if valid_path and isinstance(current_level, dict):
            target_key = keys[-1]
            if target_key in current_level:
                del current_level[target_key]
                logger.info(f"account {account_id}: filtered out deselected {json_path}")
            else:
                logger.warning(f"account {account_id}: target key '{target_key}' not found for '{json_path}'")

    return filtered_data


# ==========================================
# 1. NEW BACKGROUND TASK (Non-blocking DB Save)
# ==========================================
async def _background_save_raw_data(
    org_id: int, 
    report_month: str, 
    report_year: int, 
    report_type: str, 
    organization_data: dict
):
    """Background task to save raw integration data to the DB to avoid Render timeouts."""
    db = SessionLocal()
    try:
        existing_report = db.query(GeneratedReport).filter(
            GeneratedReport.organization_id == org_id,
            GeneratedReport.report_month == report_month,
            GeneratedReport.report_year == report_year,
            GeneratedReport.report_type == report_type,
            GeneratedReport.status == "Active"
        ).first()

        if existing_report:
            existing_report.organization_data = organization_data
            existing_report.updated_at = datetime.now()
            db.commit()
            logger.info(f"[Background] Updated raw data for active report ID={existing_report.id}")
        else:
            new_report = GeneratedReport(
                organization_id=org_id,
                report_month=report_month,
                report_year=report_year,
                report_type=report_type,
                organization_data=organization_data,
                status="Active",
                generated_at=datetime.now(),
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            db.add(new_report)
            db.commit()
            logger.info(f"[Background] Inserted new raw data report ID={new_report.id}")
    except Exception as e:
        logger.error(f"[Background] Failed to save raw data: {e}")
    finally:
        db.close()


# ==========================================
# 2. NEW LIGHTWEIGHT ENDPOINT
# ==========================================
@router.get("/FetchAndCacheIntegrationData/{user_id}/{org_id}", response_model=GraphApiResponse, summary="Fetch Live Data and Cache in DB")
async def fetch_and_cache_integration_data_endpoint(
        user_id: str = Path(..., description="User UUID"),
        org_id: int = Path(..., description="Organization ID"),
        background_tasks: BackgroundTasks = BackgroundTasks(),
        month: Optional[str] = Query(None, description="Report month")
):
    """
    Fetches live integration data, immediately returns only the report data to the frontend,
    and saves it to the PostgreSQL database in the background.
    """
    try:
        logger.info(f"Fetching live integration data for org_id: {org_id}")

        # 1. Fetch live data from integrations
        report_response = await generate_security_report_json_endpoint(user_id=user_id, org_id=org_id, month=month)
        if report_response.status_code != 200 or not report_response.data:
            return report_response

        organization_data = report_response.data

        # 2. Parse month and year for DB storage
        if month and month.strip().lower() == "last_3_months":
            from app.utils.month_selector import MonthSelector
            ms = MonthSelector()
            start_ts, end_ts = ms.get_quarterly_date_range()
            start_dt = datetime.fromtimestamp(start_ts)
            end_dt   = datetime.fromtimestamp(end_ts)
            report_month = f"{start_dt.strftime('%B')}-{end_dt.strftime('%B')}"
            report_year  = end_dt.year
            report_type  = "quarterly"
        elif month and '_' in month:
            parts = month.split('_')
            report_month = parts[0].capitalize()
            report_year  = int(parts[1])
            report_type  = "monthly"
        else:
            reporting_period = organization_data.get("reporting_period", "")
            if reporting_period:
                parts = reporting_period.split()
                report_month = parts[0] if len(parts) > 0 else "Unknown"
                report_year  = int(parts[1]) if len(parts) > 1 else datetime.now().year
            else:
                report_month = "Unknown"
                report_year  = datetime.now().year
            report_type = "monthly"

        # 3. Dispatch DB save to a Background Task (Non-blocking)
        background_tasks.add_task(
            _background_save_raw_data,
            org_id=org_id,
            report_month=report_month,
            report_year=report_year,
            report_type=report_type,
            organization_data=organization_data
        )

        # 4. Immediately return ONLY the raw organization data payload
        return GraphApiResponse(
            status_code=200,
            data=organization_data,
            error=None
        )

    except Exception as e:
        logger.error(f"Unexpected error in FetchAndCacheIntegrationData: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return GraphApiResponse(status_code=500, data=None, error=f"Internal server error: {str(e)}")


@router.get("/GetSavedLLMReportfromDB/{user_id}/{org_id}", response_model=GraphApiResponse, summary="Get Saved LLM Security Report")
async def get_saved_llm_report_endpoint(
        user_id: str = Path(..., description="User UUID (auth_user_id) from frontend"),
        org_id: int = Path(..., description="Organization ID"),
        background_tasks: BackgroundTasks = BackgroundTasks(),
        month: Optional[str] = Query(None, description="Report month: 'march_2026' or 'last_3_months'. Defaults to latest active report.")
):
    """
    Returns the saved organization_data for the latest active report of this org.
    Strictly serves data from the database. Live API calls are only made on the initial request 
    if no saved report exists yet.
    """
    try:
        # Step 1: Validate user_id → account_id
        db = SessionLocal()
        try:
            account_id = rpc_get_account_id_from_uid(db, user_id)
        finally:
            db.close()

        if not account_id:
            return GraphApiResponse(status_code=404, data=None, error=f"User not found: {user_id}")

        # Step 2: Validate org belongs to account
        db = SessionLocal()
        try:
            org = db.query(Organization).filter(
                Organization.id == org_id,
                Organization.account_id == account_id,
                Organization.status == 'Active'
            ).first()
        finally:
            db.close()

        if not org:
            return GraphApiResponse(status_code=403, data=None, error=f"Organization {org_id} not found or access denied")

        # Step 3: Fetch report from DB
        db = SessionLocal()
        try:
            query = db.query(GeneratedReport).filter(
                GeneratedReport.organization_id == org_id,
                GeneratedReport.status == "Active"
            )
            if month:
                if month.strip().lower() == "last_3_months":
                    query = query.filter(GeneratedReport.report_type == "quarterly")
                elif '_' in month:
                    _parts = month.split('_')
                    query = query.filter(
                        GeneratedReport.report_month == _parts[0].capitalize(),
                        GeneratedReport.report_year  == int(_parts[1])
                    )
            report = query.order_by(GeneratedReport.created_at.desc()).first()
        finally:
            db.close()

        response_data = None

        # Step 4: Evaluate DB result (Only trigger live calls on first run when missing data)
        is_missing_data = not report or not report.organization_data or not report.llm_data

        if is_missing_data:
            logger.info(f"First call for org {org_id} (no report data in DB). Fetching fresh integration data...")
            
            # Call the fetch_and_cache_integration_data_endpoint endpoint to populate the DB for the first time
            fallback_response = await fetch_and_cache_integration_data_endpoint(
                user_id=user_id,
                org_id=org_id,
                background_tasks=background_tasks,
                month=month
            )
            
            # If the generation fails, return the error directly
            if fallback_response.status_code != 200 or not fallback_response.data:
                return fallback_response
                
            response_data = fallback_response.data
            logger.info("Successfully fetched and saved fresh integration data on initial call.")
            
        else:
            logger.info(f" Found existing saved report ID={report.id} in DB. Serving strictly from database.")
            
            # Reconstruct the response dict directly from stored DB JSON
            response_data = dict(report.organization_data)
            response_data["llm_data"] = report.llm_data

        # Step 5: Strip out any charts the account has since deselected
        try:
            response_data = _filter_charts_by_selection(response_data, account_id)
        except NameError:
            pass # Failsafe if _filter_charts_by_selection is missing in scope

        return GraphApiResponse(status_code=200, data=response_data, error=None)

    except Exception as e:
        logger.error(f"Unexpected error in GetSavedLLMReportfromDB: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return GraphApiResponse(status_code=500, data=None, error=f"Internal server error: {str(e)}")


@router.get("/GetSavedSecurityReport", response_model=GraphApiResponse, summary="Get Saved Security Report")
async def get_saved_security_report_endpoint(
        org_id: int = Query(..., description="Organization ID"),
        month: str = Query(..., description="Report month in 'month_year' format (e.g., 'november_2024')")
):
    """
    Retrieve a previously saved security report from the database.

    This endpoint:
    1. Parses the month_year parameter into month and year
    2. Queries generated_reports table by org_id, month, and year
    3. Fetches all platform data from report_platform_data table
    4. Reconstructs the JSON response in the same format as /GenerateSecurityReportJSON

    Args:
        org_id: Organization ID
        month: Month in 'month_year' format (e.g., 'november_2024', 'december_2024')

    Returns:
        GraphApiResponse with the same JSON structure as GenerateSecurityReportJSON

    Example Usage:
        GET /api/GetSavedSecurityReport?org_id=41&month=november_2024
    """
    try:
        logger.info(f"GetSavedSecurityReport called for org_id: {org_id}, month: {month}")

        # Step 1: Parse month_year format
        if '_' not in month:
            return GraphApiResponse(
                status_code=400,
                data=None,
                error=f"Invalid month format: '{month}'. Expected format: 'monthlowercase_year' (e.g., 'november_2024')"
            )

        parts = month.split('_')
        if len(parts) != 2:
            return GraphApiResponse(
                status_code=400,
                data=None,
                error=f"Invalid month format: '{month}'. Expected format: 'monthlowercase_year'"
            )

        month_name_lowercase = parts[0].lower()
        year_str = parts[1]

        # Validate year
        if not year_str.isdigit() or len(year_str) != 4:
            return GraphApiResponse(
                status_code=400,
                data=None,
                error=f"Invalid year: '{year_str}'. Year must be a 4-digit number."
            )

        report_year = int(year_str)
        # Capitalize month for database query
        report_month = month_name_lowercase.capitalize()

        logger.info(f"Parsed month: {report_month}, year: {report_year}")

        # Step 3: Query generated_reports table
        logger.info(f"Querying generated_reports for org_id={org_id}, month={report_month}, year={report_year}")
        db = SessionLocal()
        try:
            report = db.query(GeneratedReport).filter(
               GeneratedReport.organization_id == org_id,
               GeneratedReport.report_month == report_month,
               GeneratedReport.report_year == report_year
              ).order_by(GeneratedReport.generated_at.desc()).first()

            if not report:
                logger.warning(
                    f"No saved report found for org_id={org_id}, month={report_month}, year={report_year}"
        )
                return GraphApiResponse(
                     status_code=404,
                     data=None,
                     error=f"No saved report found for organization {org_id} in {report_month} {report_year}"
        )

            logger.info(f"Found report with ID: {report.id}")

            if not report.organization_data:
               return GraphApiResponse(
                  status_code=404,
                  data=None,
                  error=f"Report {report.id} contains no saved data"
        )

            return GraphApiResponse(
               status_code=200,
               data=report.organization_data,
               error=None
    )

        finally:
           db.close()

        
    except Exception as e:
        logger.error(f"Unexpected error in GetSavedSecurityReport: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return GraphApiResponse(
            status_code=500,
            data=None,
            error=f"Internal server error: {str(e)}"
        )