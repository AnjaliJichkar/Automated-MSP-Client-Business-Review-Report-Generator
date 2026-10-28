import logging
from typing import Optional, Dict
from supabase import create_client, Client
from app.services.encryption.manager import decrypt_client_secret
from app.core.database.engine import SessionLocal
from app.models.credentials import M365Credential
import os

logger = logging.getLogger(__name__)

# Supabase client kept for legacy callers not yet migrated (e.g. licenses.py organization_mapping query)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


async def get_organization_credentials(org_id: int) -> Optional[Dict[str, str]]:
    """
    Retrieve and decrypt M365 credentials for an organization.

    Args:
        org_id: Organization ID (from organizations.id)

    Returns:
        Dictionary with decrypted tenant_id, client_id, and client_secret, or None if not found
    """
    db = SessionLocal()
    try:
        row = db.query(M365Credential).filter(
            M365Credential.organization_id == org_id
        ).first()

        if not row:
            logger.error(f"No M365 credentials found for org_id: {org_id}")
            return None

        if row.credential_status != 'Active':
            logger.error(f"M365 credentials inactive for org_id: {org_id}")
            return None

        try:
            decrypted_tenant_id = decrypt_client_secret(row.tenant_id)
            decrypted_client_id = decrypt_client_secret(row.client_id)
            decrypted_client_secret = decrypt_client_secret(row.client_secret)

            return {
                'tenant_id': decrypted_tenant_id,
                'client_id': decrypted_client_id,
                'client_secret': decrypted_client_secret
            }
        except ValueError as e:
            logger.error(f"Failed to decrypt credentials for org_id {org_id}: {str(e)}")
            return None

    except Exception as e:
        logger.error(f"Error retrieving credentials for org_id {org_id}: {e}")
        return None
    finally:
        db.close()


# Legacy function - DEPRECATED - Use get_organization_credentials instead
async def get_tenant_credentials(client_id: str) -> Optional[Dict[str, str]]:
    """
    DEPRECATED: Use get_organization_credentials(org_id) instead.
    """
    logger.warning("get_tenant_credentials() is DEPRECATED. Use get_organization_credentials(org_id) instead.")
    return None


async def get_credentials_by_ninjaone_id(ninjaone_org_id: str) -> Optional[Dict[str, str]]:
    """
    DEPRECATED: organizations table has no ninjaone_org_id column.
    NinjaOne org IDs live in organization_integrations.platform_organization_id.
    Returns None — use get_organization_credentials(org_id) instead.
    """
    logger.warning(
        "get_credentials_by_ninjaone_id() is DEPRECATED and non-functional. "
        "Use get_organization_credentials(org_id) instead."
    )
    return None


# Legacy function - DEPRECATED
async def get_tenant_credentials_by_ninjaone_id(ninjaone_org_id: str) -> Optional[Dict[str, str]]:
    """
    DEPRECATED: Use get_credentials_by_ninjaone_id instead.
    """
    logger.warning("get_tenant_credentials_by_ninjaone_id() is DEPRECATED.")
    return await get_credentials_by_ninjaone_id(ninjaone_org_id)


async def get_credentials_by_client_id(client_id: str) -> Optional[Dict[str, str]]:
    """
    Fetch M365 credentials from database by matching encrypted client_id.

    Args:
        client_id: The decrypted client_id to match (UUID format)

    Returns:
        Dictionary with decrypted tenant_id, client_id, and client_secret, or None if not found
    """
    db = SessionLocal()
    try:
        from app.services.encryption.manager import encrypt_client_secret

        encrypted_client_id = encrypt_client_secret(client_id)

        row = db.query(M365Credential).filter(
            M365Credential.client_id == encrypted_client_id
        ).first()

        if not row:
            logger.error(f"No M365 credentials found for client_id: {client_id}")
            return None

        if row.credential_status != 'Active':
            logger.error(f"M365 credentials inactive for client_id: {client_id}")
            return None

        try:
            decrypted_tenant_id = decrypt_client_secret(row.tenant_id)
            decrypted_client_id = decrypt_client_secret(row.client_id)
            decrypted_client_secret = decrypt_client_secret(row.client_secret)

            return {
                'tenant_id': decrypted_tenant_id,
                'client_id': decrypted_client_id,
                'client_secret': decrypted_client_secret
            }
        except ValueError as e:
            logger.error(f"Failed to decrypt credentials for client_id {client_id}: {str(e)}")
            return None

    except Exception as e:
        logger.error(f"Error retrieving credentials by client_id {client_id}: {e}")
        return None
    finally:
        db.close()


async def get_credentials_by_identifier(identifier: str, identifier_type: str) -> Optional[Dict[str, str]]:
    """
    Universal function to fetch M365 credentials by org_id, ninjaone_org_id, or client_id.

    Args:
        identifier: The identifier value
        identifier_type: Either "org_id", "ninjaone_org_id", or "client_id"

    Returns:
        Dictionary with decrypted tenant_id, client_id, and client_secret, or None if not found
    """
    if identifier_type == "org_id":
        return await get_organization_credentials(int(identifier))
    elif identifier_type == "ninjaone_org_id":
        return await get_credentials_by_ninjaone_id(identifier)
    elif identifier_type == "client_id":
        return await get_credentials_by_client_id(identifier)
    else:
        logger.error(f"Invalid identifier_type: {identifier_type}")
        return None
