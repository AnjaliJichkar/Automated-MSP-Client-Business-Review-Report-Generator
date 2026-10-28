import logging
from typing import Optional, Literal
import httpx
from fastapi import HTTPException
from app.core.auth.middleware import get_access_token
from app.schemas.api import GraphApiResponse
from app.core.config.settings import GRAPH_V1_URL, GRAPH_BETA_URL

logger = logging.getLogger(__name__)

# --- Generic Graph API Fetcher ---
async def fetch_from_graph(
    path: str,
    client_id: str,
    api_version: Literal['v1.0', 'beta'] = 'v1.0',
    params: Optional[dict] = None
) -> GraphApiResponse:
    """
    A generic function to make GET requests to the Microsoft Graph API.

    Args:
        path: The API path to request (e.g., "/users", "/groups").
        client_id: The client ID for tenant-specific authentication.
        api_version: The version of the API to use ('v1.0' or 'beta').
        params: Optional dictionary of query parameters.

    Returns:
        A GraphApiResponse object with the result of the call.
    """
    token = await get_access_token(client_id)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    base_url = GRAPH_V1_URL if api_version == 'v1.0' else GRAPH_BETA_URL
    url = f"{base_url}{path}"

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers, params=params, timeout=20.0)
            resp.raise_for_status()  # Raise an exception for 4xx or 5xx status codes
            return GraphApiResponse(status_code=resp.status_code, data=resp.json())
        except httpx.RequestError as exc:
            logger.error(f"Network error while calling Graph API: {exc}")
            raise HTTPException(status_code=502, detail=f"Bad Gateway: Cannot reach Graph API. Details: {exc}")
        except httpx.HTTPStatusError as exc:
            logger.error(f"Graph API returned an error: {exc.response.status_code} - {exc.response.text}")
            # Pass the error details from Graph API to the client
            raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)