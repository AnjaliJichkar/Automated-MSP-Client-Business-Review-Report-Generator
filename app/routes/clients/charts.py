"""
Integration Platform Charts Endpoints
======================================
Endpoints for managing integration platforms and their available charts
"""

import logging
from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse
from typing import List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from app.core.database.engine import get_db
from app.core.database.rpc import rpc_get_account_id_from_uid
from app.models.credentials import IntegrationCredential
from app.models.integrations import Integration, PlatformAvailableChart, AccountSelectedChart
from app.schemas.api import GraphApiResponse
from app.schemas.api import SavePlatformCredentialsRequest, DeleteIntegrationCredentialsRequest
from app.services.integrations.credential_validator import validate_credentials_from_payload

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/PlatformList", response_model=GraphApiResponse, summary="Get All Integration Platforms with User Credentials")
async def get_platform_list(u_id: str, db: Session = Depends(get_db)):
    """
    Get list of all integration platforms with their available charts and pre-filled credential values for a specific user.

    Query Parameters:
    - u_id: User UUID from auth.users

    Returns a list of platforms with their details including:
    - platform_id: Unique identifier
    - name: Display name of the platform
    - description: Platform description
    - enabled: Whether the platform is active
    - integrationFields: Required fields for integration WITH pre-filled values
    - chartlist: List of available charts for this platform


    """
    try:
        logger.info(f"Fetching integration platforms with credentials for u_id: {u_id}")

        # ================================================================
        # Step 1: Get account_id from u_id
        # ================================================================
        try:
            account_id = rpc_get_account_id_from_uid(db, u_id)

            if not account_id:
                logger.warning(f"User not found for u_id: {u_id}")
                return GraphApiResponse(
                    status_code=404,
                    data=[],
                    error="User not found"
                )

            logger.info(f"Found account_id: {account_id} for u_id: {u_id}")

        except Exception as e:
            logger.error(f"Error fetching account_id from u_id: {str(e)}")
            return GraphApiResponse(
                status_code=500,
                data=[],
                error=f"Failed to retrieve account information: {str(e)}"
            )

        # ================================================================
        # Step 2: Fetch and decrypt credentials for this account
        # ================================================================
        decrypted_credentials = {}
        try:
            creds_row = db.query(IntegrationCredential).filter(
                IntegrationCredential.account_id == account_id,
                IntegrationCredential.is_active == True
            ).first()

            if creds_row:
                from app.services.encryption.manager import EncryptionManager
                encryption_manager = EncryptionManager()
                decrypted_credentials = encryption_manager.decrypt_integration_credentials(creds_row.credentials)
                logger.info(f"Successfully decrypted credentials for account {account_id}")
                logger.info(f"Found credentials for platforms: {list(decrypted_credentials.keys())}")
            else:
                logger.info(f"No credentials found for account {account_id}, will return empty values")

        except Exception as e:
            logger.warning(f"Error fetching/decrypting credentials: {str(e)}, will return empty values")
            decrypted_credentials = {}

        # ================================================================
        # Step 3: Query integrations table - get all platforms
        # ================================================================
        integrations = db.query(Integration).filter(
            Integration.is_active == True
        ).order_by(Integration.id).all()

        if not integrations:
            logger.warning("No integration platforms found in database")
            return GraphApiResponse(
                status_code=200,
                data=[],
                error=None
            )

        # ================================================================
        # Step 4: Fetch all available charts for all platforms
        # ================================================================
        all_charts = db.query(PlatformAvailableChart).order_by(
            PlatformAvailableChart.integration_id, PlatformAvailableChart.id
        ).all()

        # Group charts by integration_id for efficient lookup
        charts_by_platform = {}
        for chart in all_charts:
            if chart.integration_id not in charts_by_platform:
                charts_by_platform[chart.integration_id] = []
            charts_by_platform[chart.integration_id].append({
                "chart_id": chart.id,
                "chart_key": chart.chart_key,
                "chart_display_name": chart.chart_display_name,
                "chart_description": chart.chart_description or ''
            })

        # ================================================================
        # Step 5: Fetch user's selected charts for this account
        # ================================================================
        selected_charts_by_platform = {}
        try:
            selected_rows = db.query(AccountSelectedChart).filter(
                AccountSelectedChart.account_id == account_id,
                AccountSelectedChart.is_active == True
            ).all()

            if selected_rows:
                selected_chart_ids = [row.chart_id for row in selected_rows]

                selected_chart_details = db.query(PlatformAvailableChart).filter(
                    PlatformAvailableChart.id.in_(selected_chart_ids)
                ).all()

                for chart in selected_chart_details:
                    if chart.integration_id not in selected_charts_by_platform:
                        selected_charts_by_platform[chart.integration_id] = []
                    selected_charts_by_platform[chart.integration_id].append({
                        "chart_id": chart.id,
                        "chart_key": chart.chart_key,
                        "chart_display_name": chart.chart_display_name,
                        "chart_description": chart.chart_description or ''
                    })

                logger.info(f"Found {len(selected_chart_ids)} selected charts for account {account_id}")
            else:
                logger.info(f"No selected charts found for account {account_id}")

        except Exception as e:
            logger.warning(f"Error fetching selected charts: {str(e)}, will return empty arrays")
            selected_charts_by_platform = {}

        # ================================================================
        # Step 6: Transform records and add credential values + selected charts
        # ================================================================
        platforms = []
        for record in integrations:
            platform_id = record.id
            integration_key = record.integration_key
            integration_fields = record.integration_fields or []

            # Get credentials for this platform (if they exist)
            platform_credentials = decrypted_credentials.get(integration_key, {})

            # Add "value" field to each integration field
            fields_with_values = []
            for field in integration_fields:
                field_name = field.get('name')
                field_value = platform_credentials.get(field_name, "")  # Empty string if not found

                field_with_value = {
                    "name": field.get('name'),
                    "type": field.get('type'),
                    "label": field.get('label'),
                    "required": field.get('required', False),
                    "field_info": field.get('field_info', ''),
                    "value": field_value
                }
                fields_with_values.append(field_with_value)

            platform = {
                "platform_id": platform_id,
                "integration_key": integration_key,
                "name": record.integration_display_name,
                "description": record.description or '',
                "enabled": bool(platform_credentials and any(v for v in platform_credentials.values())),
                "integrationFields": fields_with_values,
                "chartlist": charts_by_platform.get(platform_id, []),
                "account_selected_charts": selected_charts_by_platform.get(platform_id, [])
            }
            platforms.append(platform)

        logger.info(f"Successfully retrieved {len(platforms)} integration platforms with credentials for account {account_id}")

        return GraphApiResponse(
            status_code=200,
            data=platforms,
            error=None
        )

    except Exception as e:
        logger.error(f"Error fetching integration platforms: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return GraphApiResponse(
            status_code=500,
            data=[],
            error=f"Failed to fetch integration platforms: {str(e)}"
        )


@router.post("/SavePlatformCredentials", response_model=GraphApiResponse, summary="Save Platform Credentials and Chart Selections")
async def save_platform_credentials(request: SavePlatformCredentialsRequest, db: Session = Depends(get_db)):
    """
    Save credentials and selected charts for a single platform.

    This endpoint:
    1. Validates user UUID and gets account_id
    2. Validates platform_id exists
    3. Validates charts belong to the platform
    4. Merges credentials with existing ones
    5. Encrypts and saves to integration_credentials table
    6. Inserts chart selections into account_selected_charts table

    """
    try:
        logger.info(f"SavePlatformCredentials called for platform_id: {request.platform_id}")

        # ================================================================
        # Step 1: Get account_id from UUID
        # ================================================================
        try:
            account_id = rpc_get_account_id_from_uid(db, request.uuid)

            if not account_id:
                logger.warning(f"User not found for UUID: {request.uuid}")
                return GraphApiResponse(
                    status_code=404,
                    data={"success": False},
                    error="User not found"
                )

            logger.info(f"Found account_id: {account_id} for UUID: {request.uuid}")

        except Exception as e:
            logger.error(f"Error fetching account_id from UUID: {str(e)}")
            return GraphApiResponse(
                status_code=500,
                data={"success": False},
                error=f"Failed to retrieve account information: {str(e)}"
            )

        # ================================================================
        # Step 2: Get integration details
        # ================================================================
        try:
            integration = db.query(Integration).filter(
                Integration.id == request.platform_id,
                Integration.is_active == True
            ).first()

            if not integration:
                logger.warning(f"Platform not found for platform_id: {request.platform_id}")
                return GraphApiResponse(
                    status_code=404,
                    data={"success": False},
                    error=f"Platform not found: platform_id {request.platform_id}"
                )

            integration_key = integration.integration_key
            integration_display_name = integration.integration_display_name

            logger.info(f"Processing platform: {integration_key} ({integration_display_name})")

        except Exception as e:
            logger.error(f"Error fetching platform details: {str(e)}")
            return GraphApiResponse(
                status_code=500,
                data={"success": False},
                error=f"Failed to fetch platform details: {str(e)}"
            )

        # ================================================================
        # Step 2.5: VALIDATE CREDENTIALS BEFORE SAVING
        # ================================================================
        # Strip whitespace once here, then use `cleaned_credentials` everywhere below
        # (both for validation and for storage) so a stray leading/trailing space in a
        # pasted secret never gets persisted, even if the frontend forgot to trim it.
        cleaned_credentials = {
            key: (value.strip() if isinstance(value, str) else value)
            for key, value in request.credentials.items()
        }

        logger.info(f"Validating {integration_key} credentials before saving to database...")

        is_valid, error_msg = await validate_credentials_from_payload(cleaned_credentials, integration_key)

        if not is_valid:
            logger.warning(f"Blocking save operation: {integration_key} authentication failed.")
            return JSONResponse(
                status_code=400,
                content={"success": False, "is_authenticated": False, "error": f"Authentication Failed: {error_msg}"}
            )

        logger.info(f"✓ {integration_key} credentials successfully authenticated!")

        # ================================================================
        # Step 3: Validate charts belong to this platform
        # ================================================================
        chart_ids = [chart['chart_id'] for chart in request.chartlist_selected_by_user]

        if chart_ids:
            try:
                charts_validation = db.query(PlatformAvailableChart).filter(
                    PlatformAvailableChart.id.in_(chart_ids)
                ).all()

                wrong_platform_charts = [
                    chart.id for chart in charts_validation
                    if chart.integration_id != request.platform_id
                ]

                if wrong_platform_charts:
                    logger.warning(f"Charts belong to different platform: {wrong_platform_charts}")
                    return GraphApiResponse(
                        status_code=400,
                        data={"success": False},
                        error=f"Charts {', '.join(map(str, wrong_platform_charts))} do not belong to this platform"
                    )

                logger.info(f"✓ Chart validation passed for {integration_key}")

            except Exception as e:
                logger.error(f"Error validating charts: {str(e)}")
                return GraphApiResponse(
                    status_code=500,
                    data={"success": False},
                    error=f"Failed to validate charts: {str(e)}"
                )

        # ================================================================
        # Step 4: Merge with existing credentials and save
        # ================================================================
        credential_id = None
        try:
            from app.services.encryption.manager import EncryptionManager
            encryption_manager = EncryptionManager()

            existing_creds_row = db.query(IntegrationCredential).filter(
                IntegrationCredential.account_id == account_id,
                IntegrationCredential.is_active == True
            ).first()

            if existing_creds_row:
                credential_id = existing_creds_row.id

                existing_credentials = encryption_manager.decrypt_integration_credentials(existing_creds_row.credentials)
                logger.info(f"Found existing credentials for account {account_id}, merging...")

                existing_credentials[integration_key] = cleaned_credentials
                new_encrypted_blob = encryption_manager.encrypt_integration_credentials(existing_credentials)

                existing_creds_row.credentials = new_encrypted_blob
                existing_creds_row.is_active = True
                existing_creds_row.updated_at = datetime.utcnow()
                db.commit()

                logger.info(f"Updated credentials for account {account_id}, credential_id: {credential_id}")

            else:
                # No active row — check for an inactive row to reactivate
                inactive_creds_row = db.query(IntegrationCredential).filter(
                    IntegrationCredential.account_id == account_id,
                    IntegrationCredential.is_active == False
                ).first()

                if inactive_creds_row:
                    credential_id = inactive_creds_row.id

                    existing_credentials = encryption_manager.decrypt_integration_credentials(inactive_creds_row.credentials)
                    existing_credentials[integration_key] = cleaned_credentials
                    new_encrypted_blob = encryption_manager.encrypt_integration_credentials(existing_credentials)

                    inactive_creds_row.credentials = new_encrypted_blob
                    inactive_creds_row.is_active = True
                    inactive_creds_row.updated_at = datetime.utcnow()
                    db.commit()

                    logger.info(f"Reactivated credentials row for account {account_id}, credential_id: {credential_id}")

                else:
                    # Truly no row exists — insert fresh
                    new_credentials = {integration_key: cleaned_credentials}
                    encrypted_blob = encryption_manager.encrypt_integration_credentials(new_credentials)

                    new_row = IntegrationCredential(
                        account_id=account_id,
                        credentials=encrypted_blob,
                        is_active=True,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    db.add(new_row)
                    db.commit()
                    db.refresh(new_row)
                    credential_id = new_row.id

                    logger.info(f"Created new credentials for account {account_id}, credential_id: {credential_id}")

        except Exception as e:
            logger.error(f"Error saving credentials: {str(e)}")
            return GraphApiResponse(
                status_code=500,
                data={"success": False},
                error=f"Failed to save credentials: {str(e)}"
            )

        # ================================================================
        # Step 5: Update chart selections (Handle both select AND deselect)
        # ================================================================
        charts_saved = 0
        try:
            # STEP 5A: Get ALL available charts for this platform
            all_platform_charts = db.query(PlatformAvailableChart).filter(
                PlatformAvailableChart.integration_id == request.platform_id
            ).all()

            all_platform_chart_ids = {chart.id for chart in all_platform_charts}
            logger.info(f"Platform {request.platform_id} has {len(all_platform_chart_ids)} available charts")

            # STEP 5B: Get currently selected charts for this account AND platform
            existing_platform_charts = db.query(AccountSelectedChart).filter(
                AccountSelectedChart.account_id == account_id,
                AccountSelectedChart.chart_id.in_(list(all_platform_chart_ids)),
                AccountSelectedChart.is_active == True
            ).all()

            existing_chart_ids = {row.chart_id for row in existing_platform_charts}
            logger.info(f"Account {account_id} currently has {len(existing_chart_ids)} selected charts for this platform")

            # STEP 5C: Determine which charts to ADD and which to REMOVE
            new_chart_ids = set(chart_ids) if chart_ids else set()

            charts_to_add = new_chart_ids - existing_chart_ids
            charts_to_remove = existing_chart_ids - new_chart_ids

            logger.info(f"Charts to ADD: {charts_to_add}")
            logger.info(f"Charts to REMOVE: {charts_to_remove}")

            # STEP 5D: Soft-deactivate deselected charts
            if charts_to_remove:
                db.query(AccountSelectedChart).filter(
                    AccountSelectedChart.account_id == account_id,
                    AccountSelectedChart.chart_id.in_(list(charts_to_remove))
                ).update({'is_active': False, 'updated_at': datetime.utcnow()}, synchronize_session=False)
                db.commit()
                logger.info(f"✓ Deactivated {len(charts_to_remove)} deselected charts for account {account_id}")

            # STEP 5E: Reactivate previously deactivated charts OR insert truly new ones
            if charts_to_add:
                existing_inactive = db.query(AccountSelectedChart).filter(
                    AccountSelectedChart.account_id == account_id,
                    AccountSelectedChart.is_active == False,
                    AccountSelectedChart.chart_id.in_(list(charts_to_add))
                ).all()

                inactive_chart_ids = {row.chart_id for row in existing_inactive}

                # Reactivate existing inactive rows
                if inactive_chart_ids:
                    db.query(AccountSelectedChart).filter(
                        AccountSelectedChart.account_id == account_id,
                        AccountSelectedChart.chart_id.in_(list(inactive_chart_ids))
                    ).update({'is_active': True, 'updated_at': datetime.utcnow()}, synchronize_session=False)
                    db.commit()
                    logger.info(f"✓ Reactivated {len(inactive_chart_ids)} previously deselected charts for account {account_id}")

                # Insert only charts that have never existed
                truly_new = charts_to_add - inactive_chart_ids
                if truly_new:
                    new_chart_rows = [
                        AccountSelectedChart(
                            account_id=account_id,
                            chart_id=chart_id,
                            is_active=True,
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow()
                        )
                        for chart_id in truly_new
                    ]
                    db.add_all(new_chart_rows)
                    db.commit()
                    logger.info(f"✓ Inserted {len(truly_new)} new chart selections for account {account_id}")

            charts_saved = len(new_chart_ids)
            logger.info(f"Chart selections updated: {charts_saved} total charts now selected for platform {request.platform_id}")

        except Exception as e:
            logger.error(f"Error updating chart selections: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return GraphApiResponse(
                status_code=500,
                data={"success": False},
                error=f"Failed to save chart selections: {str(e)}"
            )

        logger.info(f"✓ SavePlatformCredentials completed successfully for account {account_id}")

        return GraphApiResponse(
            status_code=200,
            data={
                "success": True,
                "is_authenticated": True,
                "platform_name": integration_display_name,
                "charts_saved": charts_saved,
                "credential_id": credential_id
            },
            error=None
        )

    except Exception as e:
        logger.error(f"Unexpected error in SavePlatformCredentials: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return GraphApiResponse(
            status_code=500,
            data={"success": False},
            error=f"Internal server error: {str(e)}"
        )


# ============================================================================
# DELETE INTEGRATION CREDENTIALS
# ============================================================================

@router.post("/DeleteIntegrationCredentials", summary="Delete credentials for a specific integration")
async def delete_integration_credentials(request: DeleteIntegrationCredentialsRequest, db: Session = Depends(get_db)):
    """
    Deletes credentials and chart selections for a specific integration.

    Query Parameters:
    - uuid: User UUID from auth.users
    - integration_key: e.g. "ninjaone", "autotask", "bitdefender"

    Steps:
    1. Resolve account_id from uuid
    2. Validate integration_key exists
    3. Remove integration key from encrypted credentials blob
    4. Delete chart selections for that integration
    """
    try:
        uuid = request.uuid
        integration_key = request.integration_key
        logger.info(f"DeleteIntegrationCredentials called for integration_key: {integration_key}")

        # ================================================================
        # Step 1: Get account_id from UUID
        # ================================================================
        try:
            account_id = rpc_get_account_id_from_uid(db, uuid)

            if not account_id:
                return JSONResponse(status_code=404, content={"success": False, "error": "User not found"})

            logger.info(f"Found account_id: {account_id} for UUID: {uuid}")

        except Exception as e:
            logger.error(f"Error fetching account_id: {str(e)}")
            return JSONResponse(status_code=500, content={"success": False, "error": f"Failed to retrieve account: {str(e)}"})

        # ================================================================
        # Step 2: Validate integration_key and get integration id
        # ================================================================
        try:
            integration = db.query(Integration).filter(
                Integration.integration_key == integration_key,
                Integration.is_active == True
            ).first()

            if not integration:
                return JSONResponse(status_code=404, content={"success": False, "error": f"Integration '{integration_key}' not found"})

            integration_id = integration.id
            integration_display_name = integration.integration_display_name

        except Exception as e:
            logger.error(f"Error fetching integration: {str(e)}")
            return JSONResponse(status_code=500, content={"success": False, "error": f"Failed to retrieve integration: {str(e)}"})

        # ================================================================
        # Step 3: Remove integration key from credentials blob
        # ================================================================
        try:
            creds_row = db.query(IntegrationCredential).filter(
                IntegrationCredential.account_id == account_id,
                IntegrationCredential.is_active == True
            ).first()

            if not creds_row:
                return JSONResponse(status_code=404, content={"success": False, "error": "No credentials found for this account"})

            from app.services.encryption.manager import EncryptionManager
            encryption_manager = EncryptionManager()
            existing_credentials = encryption_manager.decrypt_integration_credentials(creds_row.credentials)

            if integration_key not in existing_credentials:
                return JSONResponse(status_code=404, content={"success": False, "error": f"No credentials found for '{integration_key}'"})

            del existing_credentials[integration_key]

            new_encrypted_blob = encryption_manager.encrypt_integration_credentials(existing_credentials)

            if not existing_credentials:
                # Blob is now empty — deactivate the row
                creds_row.credentials = new_encrypted_blob
                creds_row.is_active = False
                creds_row.updated_at = datetime.utcnow()
                db.commit()
                logger.info(f"✓ Removed '{integration_key}' — blob now empty, row deactivated for account {account_id}")
            else:
                creds_row.credentials = new_encrypted_blob
                creds_row.updated_at = datetime.utcnow()
                db.commit()
                logger.info(f"✓ Removed '{integration_key}' credentials for account {account_id}")

        except Exception as e:
            logger.error(f"Error removing credentials: {str(e)}")
            return JSONResponse(status_code=500, content={"success": False, "error": f"Failed to delete credentials: {str(e)}"})

        # ================================================================
        # Step 4: Delete chart selections for this integration
        # ================================================================
        try:
            platform_charts = db.query(PlatformAvailableChart).filter(
                PlatformAvailableChart.integration_id == integration_id
            ).all()

            if platform_charts:
                chart_ids = [row.id for row in platform_charts]

                db.query(AccountSelectedChart).filter(
                    AccountSelectedChart.account_id == account_id,
                    AccountSelectedChart.chart_id.in_(chart_ids)
                ).update({'is_active': False, 'updated_at': datetime.utcnow()}, synchronize_session=False)
                db.commit()

                logger.info(f"✓ Deactivated chart selections for '{integration_key}' (account {account_id})")

        except Exception as e:
            logger.error(f"Error deleting chart selections: {str(e)}")
            return JSONResponse(status_code=500, content={"success": False, "error": f"Credentials deleted but failed to remove chart selections: {str(e)}"})

        return JSONResponse(
            status_code=200,
            content={"success": True, "integration_key": integration_key, "platform_name": integration_display_name}
        )

    except Exception as e:
        logger.error(f"Unexpected error in DeleteIntegrationCredentials: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return JSONResponse(status_code=500, content={"success": False, "error": f"Internal server error: {str(e)}"})


# ============================================================================
# SMTP CREDENTIALS ENDPOINTS
# ============================================================================

# @router.get("/GetSMTPCredentials", response_model=GraphApiResponse, summary="Get SMTP Credentials for User")
# async def get_smtp_credentials(u_id: str):
#     """
#     Get SMTP credentials for a user with password masked for security.
#
#     Query Parameters:
#     - u_id: User UUID from auth.users
#
#     Returns credentials in frontend format:
#
#     ```
#     """
#     try:
#         logger.info(f"GetSMTPCredentials called for u_id: {u_id}")
#
#         # ================================================================
#         # Step 1: Get account_id from u_id
#         # ================================================================
#         try:
#             account_response = supabase.rpc('get_account_id_from_uid', {'user_uid': u_id}).execute()
#
#             if not account_response.data:
#                 logger.warning(f"User not found for u_id: {u_id}")
#                 return GraphApiResponse(
#                     status_code=404,
#                     data=None,
#                     error="User not found"
#                 )
#
#             account_id = account_response.data
#             logger.info(f"Found account_id: {account_id} for u_id: {u_id}")
#
#         except Exception as e:
#             logger.error(f"Error fetching account_id from u_id: {str(e)}")
#             return GraphApiResponse(
#                 status_code=500,
#                 data=None,
#                 error=f"Failed to retrieve account information: {str(e)}"
#             )
#
#         # ================================================================
#         # Step 2: Fetch SMTP credentials for this account
#         # ================================================================
#         try:
#             creds_response = supabase.table('account_smtp_credentials')\
#                 .select('smtp_email, app_password, smtp_server, is_active, last_used, created_at, updated_at')\
#                 .eq('account_id', account_id)\
#                 .eq('is_active', True)\
#                 .execute()
#
#             if not creds_response.data or len(creds_response.data) == 0:
#                 logger.info(f"No SMTP credentials found for account {account_id}")
#                 return GraphApiResponse(
#                     status_code=404,
#                     data=None,
#                     error="No SMTP credentials found for this account"
#                 )
#
#             creds = creds_response.data[0]
#             logger.info(f"Found SMTP credentials for account {account_id}")
#
#             # ================================================================
#             # Step 3: Decrypt app_password and return actual values
#             # ================================================================
#             from app.services.encryption.smtp_encryption import SMTPEncryptionService
#
#             encryption_service = SMTPEncryptionService()
#
#             try:
#                 # Decrypt the app_password from database
#                 decrypted_password = encryption_service.decrypt_app_password(creds['app_password'])
#                 logger.info(f"✓ Successfully decrypted app_password for account {account_id}")
#             except Exception as e:
#                 logger.error(f"Failed to decrypt app_password: {e}")
#                 return GraphApiResponse(
#                     status_code=500,
#                     data=None,
#                     error=f"Failed to decrypt credentials: {str(e)}"
#                 )
#
#             return GraphApiResponse(
#                 status_code=200,
#                 data={
#                     "senderEmail": creds['smtp_email'],
#                     "smtpServer": creds['smtp_server'],
#                     "appPassword": decrypted_password,  # ← ACTUAL DECRYPTED VALUE
#                     "isActive": creds['is_active'],
#                     "lastUsed": creds.get('last_used'),
#                     "createdAt": creds['created_at'],
#                     "updatedAt": creds['updated_at']
#                 },
#                 error=None
#             )
#
#         except Exception as e:
#             logger.error(f"Error fetching SMTP credentials: {str(e)}")
#             import traceback
#             logger.error(f"Traceback: {traceback.format_exc()}")
#             return GraphApiResponse(
#                 status_code=500,
#                 data=None,
#                 error=f"Failed to fetch SMTP credentials: {str(e)}"
#             )
#
#     except Exception as e:
#         logger.error(f"Unexpected error in GetSMTPCredentials: {str(e)}")
#         import traceback
#         logger.error(f"Traceback: {traceback.format_exc()}")
#         return GraphApiResponse(
#             status_code=500,
#             data=None,
#             error=f"Internal server error: {str(e)}"
#         )
#
#
# @router.post("/SaveSMTPCredentials", response_model=GraphApiResponse, summary="Save SMTP Credentials")
# async def save_smtp_credentials(
#     uuid: str,
#     senderEmail: str,
#     appPassword: str,
#     smtpServer: str
# ):
#     """
#     Save or update SMTP credentials for an account.
#
#     Query Parameters (from frontend):
#     - uuid: User UUID from auth.users
#     - senderEmail: SMTP sender email address (e.g., "pratik@inputiv.com")
#     - appPassword: App password for SMTP (will be encrypted)
#     - smtpServer: SMTP server hostname (e.g., "smtp-mail.outlook.com")
#
#
#     Response:
#
#     """
#     try:
#         logger.info(f"SaveSMTPCredentials called for user: {uuid}")
#
#         # ================================================================
#         # Step 1: Get account_id from UUID
#         # ================================================================
#         try:
#             account_response = supabase.rpc('get_account_id_from_uid', {'user_uid': uuid}).execute()
#
#             if not account_response.data:
#                 logger.warning(f"User not found for UUID: {uuid}")
#                 return GraphApiResponse(
#                     status_code=404,
#                     data={"success": False},
#                     error="User not found"
#                 )
#
#             account_id = account_response.data
#             logger.info(f"Found account_id: {account_id} for UUID: {uuid}")
#
#         except Exception as e:
#             logger.error(f"Error fetching account_id from UUID: {str(e)}")
#             return GraphApiResponse(
#                 status_code=500,
#                 data={"success": False},
#                 error=f"Failed to retrieve account information: {str(e)}"
#             )
#
#         # ================================================================
#         # Step 2: Validate SMTP data
#         # ================================================================
#         from app.services.encryption.smtp_encryption import SMTPEncryptionService
#
#         encryption_service = SMTPEncryptionService()
#
#         smtp_data = {
#             "smtp_email": senderEmail,
#             "app_password": appPassword,
#             "smtp_server": smtpServer
#         }
#
#         try:
#             encryption_service.validate_smtp_data(smtp_data)
#             logger.info(f"✓ SMTP data validation passed")
#         except ValueError as e:
#             logger.warning(f"SMTP data validation failed: {e}")
#             return GraphApiResponse(
#                 status_code=400,
#                 data={"success": False},
#                 error=f"Validation failed: {str(e)}"
#             )
#
#         # ================================================================
#         # Step 3: Encrypt app_password
#         # ================================================================
#         try:
#             encrypted_password = encryption_service.encrypt_app_password(appPassword)
#             logger.info(f"✓ Encrypted app_password (length: {len(encrypted_password)} chars)")
#         except Exception as e:
#             logger.error(f"Failed to encrypt app_password: {e}")
#             return GraphApiResponse(
#                 status_code=500,
#                 data={"success": False},
#                 error=f"Failed to encrypt credentials: {str(e)}"
#             )
#
#         # ================================================================
#         # Step 4: Check if credentials already exist (UPSERT logic)
#         # ================================================================
#         try:
#             existing_response = supabase.table('account_smtp_credentials')\
#                 .select('id')\
#                 .eq('account_id', account_id)\
#                 .execute()
#
#             if existing_response.data and len(existing_response.data) > 0:
#                 # UPDATE existing credentials
#                 credential_id = existing_response.data[0]['id']
#
#                 supabase.table('account_smtp_credentials')\
#                     .update({
#                         'smtp_email': senderEmail,
#                         'app_password': encrypted_password,
#                         'smtp_server': smtpServer,
#                         'is_active': True,
#                         'updated_at': datetime.now().isoformat()
#                     })\
#                     .eq('id', credential_id)\
#                     .execute()
#
#                 logger.info(f"✓ Updated SMTP credentials for account {account_id}, credential_id: {credential_id}")
#                 action = "updated"
#
#             else:
#                 # INSERT new credentials
#                 insert_result = supabase.table('account_smtp_credentials')\
#                     .insert({
#                         'account_id': account_id,
#                         'smtp_email': senderEmail,
#                         'app_password': encrypted_password,
#                         'smtp_server': smtpServer,
#                         'is_active': True,
#                         'created_at': datetime.now().isoformat(),
#                         'updated_at': datetime.now().isoformat()
#                     })\
#                     .execute()
#
#                 credential_id = insert_result.data[0]['id']
#                 logger.info(f"✓ Created new SMTP credentials for account {account_id}, credential_id: {credential_id}")
#                 action = "created"
#
#         except Exception as e:
#             logger.error(f"Error saving SMTP credentials: {str(e)}")
#             import traceback
#             logger.error(f"Traceback: {traceback.format_exc()}")
#             return GraphApiResponse(
#                 status_code=500,
#                 data={"success": False},
#                 error=f"Failed to save SMTP credentials: {str(e)}"
#             )
#
#         # ================================================================
#         # Step 5: Return success response (camelCase)
#         # ================================================================
#         logger.info(f"✓ SaveSMTPCredentials completed successfully for account {account_id}")
#
#         return GraphApiResponse(
#             status_code=200,
#             data={
#                 "success": True,
#                 "action": action,
#                 "senderEmail": senderEmail,
#                 "credentialId": credential_id
#             },
#             error=None
#         )
#
#     except Exception as e:
#         logger.error(f"Unexpected error in SaveSMTPCredentials: {str(e)}")
#         import traceback
#         logger.error(f"Traceback: {traceback.format_exc()}")
#         return GraphApiResponse(
#             status_code=500,
#             data={"success": False},
#             error=f"Internal server error: {str(e)}"
#         )