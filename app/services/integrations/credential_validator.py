# app/services/integrations/credential_validator.py
import httpx
import json
import uuid
import base64
import logging

logger = logging.getLogger(__name__)


def _clean_creds(creds: dict) -> dict:
    """
    Strip leading/trailing whitespace from every string credential value.

    Fixes cases like a pasted Autotask secret with a leading space, which
    httpx/h11 reject outright as an "Illegal header value" before any
    network call is even made.
    """
    return {
        key: (value.strip() if isinstance(value, str) else value)
        for key, value in (creds or {}).items()
    }


# ==============================
# INDIVIDUAL PLATFORM VALIDATORS
# ==============================

async def _validate_autotask(creds: dict, client: httpx.AsyncClient) -> tuple[bool, str]:
    username = creds.get('autotask_username', '')
    zone_info_url = f"https://webservices.autotask.net/atservicesrest/v1.0/zoneInformation?user={username}"
    headers = {
        'UserName': username,
        'Secret': creds.get('autotask_secret', ''),
        'ApiIntegrationcode': creds.get('autotask_integration_code', ''),
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    res = await client.get(zone_info_url, headers=headers)
    res.raise_for_status()
    data = res.json()
    if not data.get('url'):
        return False, "Authentication failed: no zone URL returned"
    return True, ""


async def _validate_ninjaone(creds: dict, client: httpx.AsyncClient) -> tuple[bool, str]:
    base_url = creds.get('ninjaone_instance_url', '')
    client_id = creds.get('ninjaone_client_id', '')
    client_secret = creds.get('ninjaone_client_secret', '')
    scopes = creds.get('ninjaone_scopes') or 'monitoring'

    clean_host = base_url.replace("https://", "").replace("http://", "").rstrip('/')
    auth_url = f"https://{clean_host}/ws/oauth/token"

    encoded_credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    headers = {
        'Authorization': f'Basic {encoded_credentials}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    res = await client.post(auth_url, data={'grant_type': 'client_credentials', 'scope': scopes}, headers=headers)
    res.raise_for_status()
    return True, ""


async def _validate_connectsecure(creds: dict, client: httpx.AsyncClient) -> tuple[bool, str]:
    host_url = creds.get('connectsecure_base_url', '')
    client_id = creds.get('connectsecure_client_id', '')
    client_secret = creds.get('connectsecure_client_secret_b64', '')
    tenant_name = creds.get('connectsecure_tenant_name', '')

    raw_auth_string = f"{tenant_name}+{client_id}:{client_secret}"
    encoded_auth_string = base64.b64encode(raw_auth_string.encode('utf-8')).decode('utf-8')

    clean_host = host_url.replace('https://', '').replace('http://', '').rstrip('/')
    url = f"https://{clean_host}/w/authorize"
    headers = {'Client-Auth-Token': encoded_auth_string, 'Content-Type': 'application/json', 'Accept': 'application/json'}

    res = await client.post(url, headers=headers)
    res.raise_for_status()
    data = res.json()
    if "access_token" not in data:
        return False, data.get("message", "No access token returned")
    return True, ""


async def _validate_bitdefender(creds: dict, client: httpx.AsyncClient) -> tuple[bool, str]:
    api_key = creds.get('bitdefender_api_key', '')
    url = "https://cloud.gravityzone.bitdefender.com/api/v1.0/jsonrpc/accounts"
    payload = {"jsonrpc": "2.0", "method": "getAccountDetails", "params": {}, "id": str(uuid.uuid4())}

    res = await client.post(url, auth=(api_key, ''), headers={'Content-Type': 'application/json'}, json=payload)
    res.raise_for_status()
    data = res.json()
    if "error" in data and data["error"]:
        return False, f"Bitdefender Error: {data['error']}"
    if not data.get('result'):
        return False, "Bitdefender authentication failed: invalid API key"
    return True, ""


async def _validate_cove(creds: dict, client: httpx.AsyncClient) -> tuple[bool, str]:
    base_url = creds.get('cove_api_url', '')
    payload = {
        "jsonrpc": "2.0",
        "method": "Login",
        "id": str(uuid.uuid4()),
        "params": {
            "username": creds.get('cove_username', ''),
            "password": creds.get('cove_password', '')
        }
    }
    res = await client.post(base_url, headers={'Content-Type': 'application/json'}, json=payload)
    res.raise_for_status()
    data = res.json()
    if "error" in data and data["error"]:
        return False, f"Cove Login failed: {data['error']}"
    return True, ""


async def _validate_sentinelone(creds: dict, client: httpx.AsyncClient) -> tuple[bool, str]:
    base_url = creds.get('sentinelone_base_url', '')
    api_token = creds.get('sentinelone_api_token', '')

    clean_host = base_url.replace("https://", "").replace("http://", "").rstrip('/')
    api_url = f"https://{clean_host}/web/api/v2.1/agents"

    res = await client.get(api_url, headers={'Authorization': f'ApiToken {api_token}'}, params={"limit": 1})
    res.raise_for_status()
    return True, ""


async def _validate_nodeware(creds: dict, client: httpx.AsyncClient) -> tuple[bool, str]:
    api_key = creds.get('nodeware_api_token', '')
    res = await client.get(
        "https://api.nodeware.com/api/v4/customers/",
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    )
    res.raise_for_status()
    return True, ""


async def _validate_dnsfilter(creds: dict, client: httpx.AsyncClient) -> tuple[bool, str]:
    api_key = creds.get('dnsfilter_api_key', '')
    if not api_key:
        return False, "dnsfilter_api_key is missing"
    res = await client.get(
        "https://api.dnsfilter.com/v1/organizations/all",
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        timeout=15.0
    )
    res.raise_for_status()
    return True, ""


async def _validate_dropsuite(creds: dict, client: httpx.AsyncClient) -> tuple[bool, str]:
    reseller_token = creds.get("dropsuite_reseller_token", "")
    if not reseller_token:
        return False, "dropsuite_reseller_token is missing"
    return True, ""

async def _validate_axcient(creds: dict, client: httpx.AsyncClient) -> tuple[bool, str]:
    api_key = creds.get('axcient_api_key', '')
    if not api_key:
        return False, "axcient_api_key is missing"
        
    url = "https://axapi.axcient.com/x360cloud/client"
    headers = {
        "x-api-key": api_key,
        "Accept": "application/json",
        "User-Agent": "MSP-Reporting-Platform/1.0"
    }
    params = {"page": 0, "page_size": 1}
    
    res = await client.get(url, headers=headers, params=params, timeout=15.0)
    res.raise_for_status()
    return True, ""


async def _validate_loyaltyloop(creds: dict, client: httpx.AsyncClient) -> tuple[bool, str]:
    api_token = creds.get('loyaltyloop_api_token', '')
    if not api_token:
        return False, "loyaltyloop_api_token is missing"

    base_url = (creds.get('loyaltyloop_base_url') or 'https://app.loyaltyloop.com/api/v1').rstrip('/')
    url = f"{base_url}/testimonials/stats"
    headers = {
        'Authorization': f'Bearer {api_token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }

    res = await client.get(url, headers=headers)
    res.raise_for_status()
    data = res.json()
    if not isinstance(data, dict):
        return False, "LoyaltyLoop authentication failed: unexpected response shape"
    return True, ""


async def _validate_infima(creds: dict, client: httpx.AsyncClient) -> tuple[bool, str]:
    api_key = creds.get('infima_api_key', '')
    if not api_key:
        return False, "infima_api_key is missing"

    url = "https://app.infimasecapis.com/v1/clients"
    headers = {'X-API-KEY': api_key, 'Accept': 'application/json'}

    res = await client.get(url, headers=headers, params={"limit": 1})
    res.raise_for_status()
    return True, ""


# ==============================
# DISPATCH MAP
# ==============================

VALIDATORS = {
    "autotask":      _validate_autotask,
    "ninjaone":      _validate_ninjaone,
    "connectsecure": _validate_connectsecure,
    "bitdefender":   _validate_bitdefender,
    "cove":          _validate_cove,
    "sentinelone":   _validate_sentinelone,
    "nodeware":      _validate_nodeware,
    "dnsfilter":     _validate_dnsfilter,
    "dropsuite":     _validate_dropsuite,
    "axcient":       _validate_axcient,
    "loyaltyloop":   _validate_loyaltyloop,
    "infima":        _validate_infima,
}


# ==============================
# MAIN ENTRY POINT
# ==============================

async def health_check_credentials(creds: dict, integration_key: str) -> tuple[bool, str]:
    """
    Same auth call as validate_credentials_from_payload but surfaces raw 3rd party errors.
    Returns: (is_healthy: bool, raw_error_message: str)
    """
    handler = VALIDATORS.get(integration_key)
    if not handler:
        return False, f"No health check configured for integration: '{integration_key}'"

    creds = _clean_creds(creds)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            return await handler(creds, client)

    except httpx.HTTPStatusError as e:
        try:
            raw = e.response.json()
            raw_error = json.dumps(raw)
        except Exception:
            raw_error = e.response.text
        return False, f"HTTP {e.response.status_code}: {raw_error}"

    except httpx.ConnectTimeout:
        return False, "Connection timed out — API host unreachable"

    except httpx.ConnectError as e:
        return False, f"Connection error: {str(e)}"

    except httpx.LocalProtocolError as e:
        # Malformed header value (e.g. invalid characters) slipped through cleaning
        return False, f"Malformed credential field: {str(e)}"

    except Exception as e:
        return False, f"Unexpected error: {str(e)}"


async def validate_credentials_from_payload(creds: dict, integration_key: str) -> tuple[bool, str]:
    """
    Validates platform credentials using integration_key (stable string from DB).
    Returns: (is_valid: bool, error_message: str)
    """
    handler = VALIDATORS.get(integration_key)

    if not handler:
        logger.info(f"No validation mapped for '{integration_key}'. Passing through.")
        return True, ""

    creds = _clean_creds(creds)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            return await handler(creds, client)

    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        logger.warning(f"Validation failed for '{integration_key}': {e.response.text}")

        if status in (401, 403):
            # Credentials reached the API and were rejected -> this is specifically
            # a wrong-password/secret case, not a network or config problem.
            return False,"Invalid credentials. Please verify your secrets, URLs, usernames and IDs."

        # Any other HTTP status (400, 404, 429, 500...) is NOT a credential problem
        # (e.g. bad request shape, rate limiting, API downtime) -- don't mislabel it.
        return False, f"The {integration_key} API rejected the request (HTTP {status})."

    except httpx.LocalProtocolError as e:
        # Malformed header value slipped through cleaning (invalid characters, not just
        # whitespace) -- distinct from "wrong password" since it never reached the API.
        logger.error(f"Malformed credential field for '{integration_key}': {str(e)}")
        return False, "One of your credential fields contains invalid characters. Please check and re-enter them."

    except (httpx.ConnectTimeout, httpx.ConnectError) as e:
        logger.error(f"Connection failure validating '{integration_key}': {str(e)}")
        return False, f"Could not reach the {integration_key} API. Please check the URL/host and try again."

    except Exception as e:
        logger.error(f"Validation exception for '{integration_key}': {str(e)}")
        return False, f"Unexpected error while validating {integration_key} credentials: {str(e)}"