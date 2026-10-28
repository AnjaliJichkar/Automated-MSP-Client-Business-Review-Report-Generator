import logging
from fastapi import APIRouter, Path, Depends
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.orm import Session
from app.core.database.engine import get_db
from app.models.users import PlatformUser
from app.models.organizations import Organization, OrganizationPoc
from app.models.credentials import M365Credential
from app.schemas.api import GraphApiResponse
from datetime import datetime
from app.services.encryption.manager import encrypt_client_secret


# Create router for client endpoints
router = APIRouter()
logger = logging.getLogger(__name__)


# POC model
class POCModel(BaseModel):
    poc_name: str
    poc_email: str
    poc_role: str

# Request model for the form data
class AddClientRequest(BaseModel):
    user_id: str  # UUID from auth table (auth_user_id)
    organization_name: str
    primary_domain: str
    tenant_id: Optional[str] = ""
    client_id: Optional[str] = ""
    client_secret: Optional[str] = ""
    industry: Optional[str] = None
    organization_size: Optional[str] = None
    pocs_list: Optional[List[POCModel]] = []

class EditClientRequest(BaseModel):
    organization_name: Optional[str] = None
    primary_domain: Optional[str] = None
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    industry: Optional[str] = None
    organization_size: Optional[str] = None
    pocs_list: Optional[List[POCModel]] = None


# ----------- Add Client Endpoint --------------
@router.post("/AddClient", response_model=GraphApiResponse, summary="Add New Client Organization")
async def add_client(request: AddClientRequest, db: Session = Depends(get_db)):
    """
    Adds a new client organization to the database with their Microsoft Graph API credentials and POCs.
    - Resolves user_id (UUID) to account_id and platform_user_id
    - Inserts into organizations table
    - Encrypts tenant_id, client_id, client_secret (all 3 fields) if provided and inserts into m365_credentials
    - Inserts POCs into organization_pocs table
    """
    try:
        logger.info(f"Adding new client organization: {request.organization_name}")

        # Step 1: Resolve user_id to account_id and platform_user_id
        platform_user = db.query(PlatformUser).filter(
            PlatformUser.auth_user_id == request.user_id
        ).first()

        if not platform_user:
            logger.error(f"No platform user found for user_id: {request.user_id}")
            return GraphApiResponse(
                status_code=404,
                data={"success": False},
                error=f"User not found. Invalid user_id: {request.user_id}"
            )

        platform_user_id = platform_user.id
        account_id = platform_user.account_id
        logger.info(f"Resolved user_id to platform_user_id: {platform_user_id}, account_id: {account_id}")

        # Step 2: Insert into organizations table
        org = Organization(
            account_id=account_id,
            organization_name=request.organization_name,
            domain=request.primary_domain,
            industry=request.industry,
            organization_size=request.organization_size,
            status="Active"
        )
        db.add(org)
        db.commit()
        db.refresh(org)

        org_id = org.id
        logger.info(f"Successfully added organization with org_id: {org_id}")

        # Step 3: Encrypt and insert credentials if provided trial
        credentials_saved = False
        if (request.tenant_id and request.tenant_id.strip() and
            request.client_id and request.client_id.strip() and
            request.client_secret and request.client_secret.strip()):
            try:
                # Encrypt all three credential fields
                encrypted_tenant_id = encrypt_client_secret(request.tenant_id)
                encrypted_client_id = encrypt_client_secret(request.client_id)
                encrypted_client_secret = encrypt_client_secret(request.client_secret)

                # Insert into m365_credentials table
                db.add(M365Credential(
                    organization_id=org_id,
                    account_id=account_id,
                    tenant_id=encrypted_tenant_id,
                    client_id=encrypted_client_id,
                    client_secret=encrypted_client_secret,
                    credential_status="Active"
                ))
                db.commit()

                credentials_saved = True
                logger.info(f"Successfully saved encrypted credentials for org_id: {org_id}")

            except ValueError as e:
                logger.error(f"Failed to encrypt credentials for {request.organization_name}: {str(e)}")
                # Don't fail the entire operation, just log the error
                credentials_saved = False
        else:
            logger.info("No credentials provided, skipping credential storage")

        # Step 4: Insert POCs if provided
        pocs_saved = 0
        if request.pocs_list and len(request.pocs_list) > 0:
            try:
                pocs = [
                    OrganizationPoc(
                        organization_id=org_id,
                        poc_name=poc.poc_name,
                        poc_email=poc.poc_email,
                        poc_role=poc.poc_role
                    )
                    for poc in request.pocs_list
                ]
                db.add_all(pocs)
                db.commit()
                pocs_saved = len(pocs)
                logger.info(f"Successfully saved {pocs_saved} POCs for org_id: {org_id}")

            except Exception as e:
                logger.error(f"Failed to save POCs for {request.organization_name}: {str(e)}")
                # Don't fail the entire operation, just log the error

        return GraphApiResponse(
            status_code=200,
            data={
                "success": True,
                "message": "Client organization added successfully",
                "org_id": org_id,
                "credentials_saved": credentials_saved,
                "pocs_saved": pocs_saved
            },
            error=None
        )

    except Exception as e:
        error_message = str(e).lower()
        logger.error(f"Error adding client organization {request.organization_name}: {str(e)}")

        # Handle duplicate organization name
        if "duplicate key" in error_message and "organization_name" in error_message:
            return GraphApiResponse(
                status_code=400,
                data={"success": False},
                error="An organization with this name already exists."
            )

        # Generic error response
        return GraphApiResponse(
            status_code=500,
            data={"success": False},
            error=f"Failed to add client: {str(e)}"
        )

# ----------- Get Clients Endpoint -------------


# @router.get("/GetClients", response_model=GraphApiResponse, summary="List All Active Client Organizations")
# async def get_clients():
#     """
#     Retrieves all active client organizations from the database.
#     Returns organization_name, domain (with link), client_id, created (created & updated date),
#     status, industry, and organization_size.
#     """
#     try:
#         logger.info("Fetching all active client organizations")
#
#         result = supabase.table("organization_mapping").select(
#             "ninjaone_org_id, client_id, organization_name, domain, status, created_at, updated_at, industry, organization_size"
#         ).eq("status", "Active").execute()
#
#         clients = []
#         for item in result.data:
#             # Use from isoformat() to parse ISO8601 string with timezone
#             created_at = datetime.fromisoformat(item["created_at"])
#             updated_at = datetime.fromisoformat(item["updated_at"])
#
#             clients.append({
#                 "ninjaone_org_id": item["ninjaone_org_id"],
#                 "organization_name": item["organization_name"],
#                 "domain": {
#                     "url": item["domain"],
#                     "text": "Visit Website"
#                 },
#                 "client_id": item["client_id"],
#                 "created": {
#                     "created_date": created_at.strftime("%m/%d/%Y"),
#                     "updated_date": updated_at.strftime("%m/%d/%Y")
#                 },
#                 "status": item["status"],
#                 "industry": item["industry"],
#                 "organization_size": item["organization_size"]
#             })
#
#         logger.info(f"Successfully retrieved {len(clients)} active client organizations")
#
#         return GraphApiResponse(
#             status_code=200,
#             data={
#                 "success": True,
#                 "clients": clients,
#                 "count": len(clients)
#             },
#             error=None
#         )
#
#     except Exception as e:
#         logger.error(f"Error fetching client organizations: {str(e)}")
#         return GraphApiResponse(
#             status_code=500,
#             data={
#                 "success": False,
#                 "clients": []
#             },
#             error=f"Failed to retrieve client organizations: {str(e)}"
#         )

@router.delete("/DeleteClient/{org_id}", response_model=GraphApiResponse, summary="Delete Client Organization")
async def delete_client(org_id: int = Path(..., description="The organization ID to delete"), db: Session = Depends(get_db)):
    """
    Permanently deletes a client organization and all related data from the database.
    This is a hard delete operation and cannot be undone.

    Deletes from:
    - organization_pocs table
    - m365_credentials table
    - organizations table
    """
    try:
        logger.info(f"Attempting to delete client organization with org_id: {org_id}")

        # Step 1: Check if organization exists
        existing_org = db.query(Organization).filter(Organization.id == org_id).first()

        if not existing_org:
            logger.warning(f"Organization with org_id {org_id} not found")
            return GraphApiResponse(
                status_code=404,
                data={"success": False},
                error="Organization not found"
            )

        org_name = existing_org.organization_name
        logger.info(f"Found organization to delete: {org_name}")

        # Step 2: Delete related POCs first
        try:
            db.query(OrganizationPoc).filter(
                OrganizationPoc.organization_id == org_id
            ).delete(synchronize_session=False)
            db.commit()
            logger.info(f"Deleted POCs for org_id: {org_id}")
        except Exception as e:
            logger.warning(f"Error deleting POCs (may not exist): {str(e)}")

        # Step 3: Delete credentials
        try:
            db.query(M365Credential).filter(
                M365Credential.organization_id == org_id
            ).delete(synchronize_session=False)
            db.commit()
            logger.info(f"Deleted credentials for org_id: {org_id}")
        except Exception as e:
            logger.warning(f"Error deleting credentials (may not exist): {str(e)}")

        # Step 4: Delete the organization itself
        db.query(Organization).filter(Organization.id == org_id).delete(synchronize_session=False)
        db.commit()

        logger.info(f"Successfully deleted client organization: {org_name} (org_id: {org_id})")

        return GraphApiResponse(
            status_code=200,
            data={
                "success": True,
                "message": f"Client organization '{org_name}' and all related data deleted successfully",
                "deleted_org_id": org_id
            },
            error=None
        )

    except Exception as e:
        logger.error(f"Error deleting client organization with org_id {org_id}: {str(e)}")
        return GraphApiResponse(
            status_code=500,
            data={"success": False},
            error=f"Failed to delete client: {str(e)}"
        )


# ----------- Edit Client Endpoint -------------
@router.put("/EditClient/{org_id}", response_model=GraphApiResponse, summary="Edit Client Organization")
async def edit_client(
        org_id: int = Path(..., description="The organization ID to edit"),
        request: EditClientRequest = None,
        db: Session = Depends(get_db)
):
    """
    Updates client organization information with credentials and POCs.
    - Updates organizations table
    - Encrypts and updates/inserts credentials in m365_credentials if provided
    - Replaces POCs in organization_pocs table if provided

    This is a partial update - only provided fields will be updated.
    """
    try:
        logger.info(f"Attempting to edit client organization with org_id: {org_id}")

        # First check if organization exists
        existing_org = db.query(Organization).filter(Organization.id == org_id).first()

        if not existing_org:
            logger.warning(f"Organization with org_id {org_id} not found")
            return GraphApiResponse(
                status_code=404,
                data={"success": False},
                error="Organization not found"
            )

        # Step 1: Update organizations table with provided fields
        update_data = {}
        if request.organization_name is not None:
            existing_org.organization_name = request.organization_name
            update_data["organization_name"] = request.organization_name
        if request.primary_domain is not None:
            existing_org.domain = request.primary_domain
            update_data["domain"] = request.primary_domain
        if request.industry is not None:
            existing_org.industry = request.industry
            update_data["industry"] = request.industry
        if request.organization_size is not None:
            existing_org.organization_size = request.organization_size
            update_data["organization_size"] = request.organization_size

        if update_data:
            existing_org.updated_at = datetime.utcnow()
            db.commit()
            logger.info(f"Updated organization fields: {list(update_data.keys())}")

        # Step 2: Update credentials if provided
        credentials_updated = False
        has_tenant = request.tenant_id and request.tenant_id.strip()
        has_client = request.client_id and request.client_id.strip()
        has_secret = request.client_secret and request.client_secret.strip()

        if has_tenant or has_client or has_secret:
            try:
                # Check if credentials already exist for this organization
                existing_creds = db.query(M365Credential).filter(
                    M365Credential.organization_id == org_id
                ).first()

                # Prepare credential update data (only encrypt fields that are provided)
                if has_tenant:
                    encrypted_tenant = encrypt_client_secret(request.tenant_id)
                if has_client:
                    encrypted_client = encrypt_client_secret(request.client_id)
                if has_secret:
                    encrypted_secret = encrypt_client_secret(request.client_secret)

                if existing_creds:
                    # Update existing credentials
                    if has_tenant:
                        existing_creds.tenant_id = encrypted_tenant
                    if has_client:
                        existing_creds.client_id = encrypted_client
                    if has_secret:
                        existing_creds.client_secret = encrypted_secret
                    existing_creds.updated_at = datetime.utcnow()
                    db.commit()
                    credentials_updated = True
                    logger.info(f"Updated credentials for org_id: {org_id}")
                else:
                    # Insert new credentials (need all three fields)
                    if has_tenant and has_client and has_secret:
                        db.add(M365Credential(
                            organization_id=org_id,
                            tenant_id=encrypted_tenant,
                            client_id=encrypted_client,
                            client_secret=encrypted_secret,
                            credential_status="Active"
                        ))
                        db.commit()
                        credentials_updated = True
                        logger.info(f"Inserted new credentials for org_id: {org_id}")
                    else:
                        logger.warning("Cannot insert partial credentials - all three fields required")

            except Exception as e:
                logger.error(f"Failed to update credentials for org_id {org_id}: {str(e)}")
                # Don't fail the entire operation

        # Step 3: Update POCs if provided (soft-deactivate old ones, insert new ones)
        pocs_updated = 0
        if request.pocs_list is not None and len(request.pocs_list) > 0:
            try:
                # Soft-deactivate existing POCs
                db.query(OrganizationPoc).filter(
                    OrganizationPoc.organization_id == org_id
                ).update({'is_active': False, 'updated_at': datetime.utcnow()}, synchronize_session=False)
                db.commit()
                logger.info(f"Deactivated existing POCs for org_id: {org_id}")

                # Insert new POCs
                pocs = [
                    OrganizationPoc(
                        organization_id=org_id,
                        poc_name=poc.poc_name,
                        poc_email=poc.poc_email,
                        poc_role=poc.poc_role,
                        is_active=True
                    )
                    for poc in request.pocs_list
                ]
                db.add_all(pocs)
                db.commit()
                pocs_updated = len(pocs)
                logger.info(f"Updated {pocs_updated} POCs for org_id: {org_id}")

            except Exception as e:
                logger.error(f"Failed to update POCs for org_id {org_id}: {str(e)}")
                # Don't fail the entire operation

        return GraphApiResponse(
            status_code=200,
            data={
                "success": True,
                "message": "Client organization updated successfully",
                "org_id": org_id,
                "updated_fields": list(update_data.keys()) if update_data else [],
                "credentials_updated": credentials_updated,
                "pocs_updated": pocs_updated
            },
            error=None
        )

    except Exception as e:
        logger.error(f"Error updating client organization with org_id {org_id}: {str(e)}")
        return GraphApiResponse(
            status_code=500,
            data={"success": False},
            error=f"Failed to update client: {str(e)}"
        )


# @router.get("/GetClientOrganizations", response_model=GraphApiResponse, summary="List All Client Organizations from Mapping Table")
# async def get_client_organizations():
#     """
#     Retrieves all organization mappings from the 'organization_mapping' table.
#     Returns ninjaone_org_id and organization_name.
#     """
#     try:
#         logger.info("Fetching all organization mappings")
#
#         result = supabase.table("organization_mapping").select(
#             "ninjaone_org_id, organization_name"
#         ).execute()
#
#         organizations = result.data if result.data else []
#
#         logger.info(f"Successfully retrieved {len(organizations)} organization mappings")
#
#         return GraphApiResponse(
#             status_code=200,
#             data={
#                 "success": True,
#                 "organizations": organizations,
#                 "count": len(organizations)
#             },
#             error=None
#         )
#
#     except Exception as e:
#         logger.error(f"Error fetching organization mappings: {str(e)}")
#         return GraphApiResponse(
#             status_code=500,
#             data={
#                 "success": False,
#                 "organizations": []
#             },
#             error=f"Failed to retrieve organization mappings: {str(e)}"
#         )
