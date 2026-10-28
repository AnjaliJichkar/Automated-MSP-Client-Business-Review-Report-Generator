# dependencies.py - Support both client_id, ninjaone_org_id, and org_id
from fastapi import Query, HTTPException
from typing import Optional, Tuple


async def get_client_id(
    clientId: Optional[str] = Query(None),
    org_id: Optional[int] = Query(None)
) -> str:
    """
    Get client_id from either clientId parameter (old) or org_id parameter (new).
    For backward compatibility, accepts both parameters.
    Returns the decrypted client_id.
    """
    if not clientId and not org_id:
        raise HTTPException(
            status_code=400,
            detail="Either clientId or org_id query parameter is required"
        )

    # If clientId provided directly (old method), return it
    if clientId:
        return clientId.strip()

    # If org_id provided (new method), look up credentials and return client_id
    if org_id:
        from app.core.database.supabase_services import get_organization_credentials
        creds = await get_organization_credentials(org_id)
        if not creds:
            raise HTTPException(
                status_code=404,
                detail=f"No credentials found for org_id: {org_id}"
            )
        return creds['client_id']


async def get_client_credentials(
    clientId: Optional[str] = Query(None),
    ninjaone_org_id: Optional[str] = Query(None),
    org_id: Optional[int] = Query(None)
) -> Tuple[str, str]:
    """
    Get client credentials identifier with support for client_id, ninjaone_org_id, and org_id.
    Returns (identifier, identifier_type) tuple.

    Priority order (for backward compatibility):
    1. clientId (old method)
    2. org_id (new method)
    3. ninjaone_org_id (legacy method)
    """
    # Trim whitespace from parameters
    clientId = clientId.strip() if clientId else None
    ninjaone_org_id = ninjaone_org_id.strip() if ninjaone_org_id else None

    if not clientId and not ninjaone_org_id and not org_id:
        raise HTTPException(
            status_code=400,
            detail="Either clientId, org_id, or ninjaone_org_id query parameter is required"
        )

    # Priority 1: clientId (backward compatibility)
    if clientId:
        return clientId, "client_id"

    # Priority 2: org_id (new method)
    elif org_id:
        return str(org_id), "org_id"

    # Priority 3: ninjaone_org_id (legacy)
    else:
        return ninjaone_org_id, "ninjaone_org_id"