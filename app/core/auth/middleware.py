import time
import logging
from fastapi import HTTPException
from msal import ConfidentialClientApplication
from typing import Dict
from app.core.database.supabase_services import get_tenant_credentials, get_credentials_by_identifier

# Configure logging
logger = logging.getLogger(__name__)

# --- MSAL and Token Management ---
# In-memory cache for access tokens per tenant
token_cache: Dict[str, Dict] = {}


async def get_access_token(client_id: str) -> str:
    """
    Legacy function for backward compatibility.
    Gets an access token from cache (must be pre-cached by get_access_token_from_credentials).
    Does NOT do database lookup by client_id (encryption mismatch issue).

    Args:
        client_id: The client ID to get token for

    Returns:
        Access token string

    Raises:
        HTTPException: If token not in cache
    """
    global token_cache
    now = int(time.time())

    # Check if token exists in cache from get_access_token_from_credentials
    cache_key = f"creds:{client_id}"

    if cache_key in token_cache:
        cached_token = token_cache[cache_key]
        expires_at = cached_token.get("expires_in", 0)

        # Log detailed info
        logger.info(f"Token found in cache for {cache_key}")
        logger.info(f"Current time: {now}, Token expires_in: {expires_at}")
        logger.info(f"Token valid: {expires_at > now}")

        if expires_at > now:
            logger.info(f"✅ Using cached token for client_id {client_id}")
            return cached_token["access_token"]
        else:
            logger.warning(f"Token expired! expires_in={expires_at}, now={now}")

    # Token not in cache - this means get_access_token_from_credentials was not called first
    # We cannot look up by client_id because encrypted values won't match
    logger.error(f"❌ Token not found in cache for client_id {client_id}. Must call get_access_token_from_credentials first.")
    logger.error(f"Cache key searched: {cache_key}")
    logger.error(f"Available keys: {list(token_cache.keys())}")
    raise HTTPException(
        status_code=500,
        detail=f"Token not cached. Internal error: credentials must be pre-fetched by org_id."
    )


async def get_access_token_from_credentials(tenant_id: str, client_id: str, client_secret: str) -> str:
    """
    Acquires an access token directly from credentials without database lookup.
    Use this for internal calls where credentials are already known.

    Args:
        tenant_id: The Azure AD tenant ID
        client_id: The application client ID
        client_secret: The application client secret

    Returns:
        Access token string

    Raises:
        HTTPException: If token acquisition fails
    """
    global token_cache
    now = int(time.time())

    cache_key = f"creds:{client_id}"

    # Check if a valid, non-expired token is in our cache
    if cache_key in token_cache and token_cache[cache_key].get("expires_in", 0) > now:
        return token_cache[cache_key]["access_token"]

    # Create MSAL app for this specific tenant
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    scope = ["https://graph.microsoft.com/.default"]

    msal_app = ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=authority,
    )

    # Try to get a token from MSAL's silent cache first
    result = msal_app.acquire_token_silent(scopes=scope, account=None)

    # If silent acquisition fails, get a new token from AAD
    if not result:
        logger.info(f"No token in silent cache for client_id {client_id}, acquiring a new one...")
        result = msal_app.acquire_token_for_client(scopes=scope)

    # Handle token acquisition failure
    if not result or 'access_token' not in result:
        error = result.get('error_description', result.get('error', 'Unknown error'))
        logger.error(f"Token acquisition failed for client_id {client_id}: {error}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to acquire token: {error}"
        )

    # Cache the new token and its expiration time
    # Convert expires_in (duration in seconds) to absolute timestamp
    if 'expires_in' in result:
        result['expires_in'] = now + result['expires_in']

    token_cache[cache_key] = result
    logger.info(f"Successfully acquired and cached a new access token for client_id {client_id}.")
    return result['access_token']


async def get_access_token_by_identifier(identifier: str, identifier_type: str) -> str:
    """
    Acquires an access token for Microsoft Graph for a specific tenant,
    using a simple in-memory cache per identifier. Supports both client_id and ninjaone_org_id.

    Args:
        identifier: The identifier (client_id or ninjaone_org_id) to get token for
        identifier_type: Either "client_id" or "ninjaone_org_id"

    Returns:
        Access token string

    Raises:
        HTTPException: If token acquisition fails
    """
    global token_cache
    now = int(time.time())

    # Use identifier as cache key regardless of type
    cache_key = f"{identifier_type}:{identifier}"

    # Check if a valid, non-expired token is in our cache for this identifier
    if cache_key in token_cache and token_cache[cache_key].get("expires_in", 0) > now:
        return token_cache[cache_key]["access_token"]

    # Get tenant credentials from Supabase using the universal function
    credentials = await get_credentials_by_identifier(identifier, identifier_type)
    if not credentials:
        raise HTTPException(
            status_code=404,
            detail=f"No tenant credentials found for {identifier_type}: {identifier}"
        )

    tenant_id = credentials['tenant_id']
    client_id = credentials['client_id']
    client_secret = credentials['client_secret']

    # Use the new function to get token from credentials
    return await get_access_token_from_credentials(tenant_id, client_id, client_secret)