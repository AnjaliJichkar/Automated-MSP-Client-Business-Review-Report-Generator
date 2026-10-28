# app/routes/health_check.py
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.core.database.engine import get_db
from app.core.database.rpc import rpc_get_account_id_from_uid
from app.models.credentials import IntegrationCredential
from app.services.encryption.manager import encryption_manager
from app.services.integrations.credential_validator import health_check_credentials
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health-check")
async def integration_health_check(uuid: str, integration_key: str, db: Session = Depends(get_db)):
    """
    Backend diagnostic endpoint.
    Decrypts stored credentials for the given uuid + integration_key,
    fires the real auth call against the 3rd party API, and returns
    the exact error if the integration is down or misconfigured.
    """
    try:
        # Resolve uuid → account_id
        account_id = rpc_get_account_id_from_uid(db, uuid)
        if not account_id:
            return JSONResponse(status_code=404, content={
                "status": "error",
                "integration_key": integration_key,
                "message": "User not found"
            })

        # Fetch encrypted credentials blob
        creds_row = db.query(IntegrationCredential).filter(
            IntegrationCredential.account_id == account_id,
            IntegrationCredential.is_active == True
        ).first()

        if not creds_row:
            return JSONResponse(status_code=404, content={
                "status": "not_configured",
                "integration_key": integration_key,
                "message": "No credentials found for this account"
            })

        # Decrypt blob
        all_creds = encryption_manager.decrypt_integration_credentials(creds_row.credentials)

        # Check if this specific integration is saved
        platform_creds = all_creds.get(integration_key)
        if not platform_creds:
            return JSONResponse(status_code=404, content={
                "status": "not_configured",
                "integration_key": integration_key,
                "message": f"No credentials saved for '{integration_key}'"
            })

        # Run health check — same auth call as credential validator but with raw error passthrough
        is_healthy, error = await health_check_credentials(platform_creds, integration_key)

        if is_healthy:
            return JSONResponse(status_code=200, content={
                "status": "healthy",
                "integration_key": integration_key,
                "message": "Authentication successful"
            })
        else:
            return JSONResponse(status_code=200, content={
                "status": "unhealthy",
                "integration_key": integration_key,
                "error": error
            })

    except Exception as e:
        logger.error(f"Health check failed for '{integration_key}': {str(e)}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "integration_key": integration_key,
            "message": f"Internal error: {str(e)}"
        })
