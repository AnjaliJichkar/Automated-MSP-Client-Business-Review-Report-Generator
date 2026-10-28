"""
Infima Security Awareness Training API Client
Handles authentication and API interactions with the Infima platform
"""

import requests
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

BASE_URL = "https://app.infimasecapis.com/v1"


class DarkWebMonitoringNotEnabled(Exception):
    """
    Raised when GET /v1/clients/{client_id}/darkweb/exposures returns 403.

    Dark Web Monitoring is a per-client feature -- a 403 here means the
    client hasn't enabled it, not that the request failed. Callers should
    treat this as an expected state to handle gracefully, not an error to
    log/alert on the same way as a real API failure.
    """
    pass


class InfimaClient:
    """Client for interacting with the Infima Security Awareness Training API"""

    def __init__(self, api_key: str):
        """
        Initialize Infima API client

        Args:
            api_key: Infima API key (sent as X-API-KEY header)
        """
        self.api_key = api_key
        self.base_url = BASE_URL

        self.headers = {
            "X-API-KEY": api_key,
            "Accept": "application/json"
        }

        logger.info("InfimaClient initialized")

    @staticmethod
    def _extract_list(data: Any, context: str) -> List[Dict[str, Any]]:
        """
        Normalize an Infima list-endpoint response into a plain list, since the
        exact envelope (bare list vs. {"data": [...]} vs. some other wrapper
        key) isn't confirmed against a real response yet.

        Tries a bare list first, then a handful of common wrapper key names.
        If none match, logs the actual top-level shape and raises loudly --
        silently falling through to items[0] on a dict caused the original
        bug here (a bare dict has integer-keyed access fail with a bare
        KeyError(0), which is nearly impossible to debug from the log alone).

        Args:
            data: Parsed JSON response body
            context: Short description of the call site, for the error message

        Returns:
            The list of records found in the response

        Raises:
            Exception if the response shape doesn't match any known pattern
        """
        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            for key in ("data", "clients", "items", "results", "records"):
                value = data.get(key)
                if isinstance(value, list):
                    return value
            logger.error(f"Unexpected Infima response shape for {context} -- top-level keys: {list(data.keys())}")
            raise Exception(
                f"Unexpected Infima API response shape for {context}: "
                f"got a dict with keys {list(data.keys())}, none of which contain a list. "
                f"Update InfimaClient._extract_list() once the real wrapper key is confirmed."
            )

        logger.error(f"Unexpected Infima response type for {context}: {type(data)}")
        raise Exception(f"Unexpected Infima API response type for {context}: {type(data)}")

    def get_client_details(self, client_id: int) -> Dict[str, Any]:
        """
        Fetch a single client's rollup data (phishing_click_rate_total,
        training_on_track_rate, etc.) via GET /v1/clients.

        There is no single-client-by-id endpoint -- /v1/clients always returns
        a list, so this filters to one client using the `ids` query param and
        takes the first (only) match.

        Args:
            client_id: Infima client id to fetch

        Returns:
            Dict of client fields, or {} if no matching client was returned
        """
        endpoint = f"{self.base_url}/clients"
        params = {"ids": client_id, "limit": 1}

        try:
            logger.info(f"Fetching Infima client details for client_id={client_id}")
            response = requests.get(endpoint, headers=self.headers, params=params, timeout=30)

            if response.status_code >= 400:
                logger.error(f"Infima API error response: {response.text}")
                response.raise_for_status()

            data = response.json()
            items = self._extract_list(data, context=f"GET /clients (client_id={client_id})")

            if not items:
                logger.warning(f"No Infima client found for client_id={client_id}")
                return {}

            return items[0]

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch Infima client details: {e}")
            raise Exception(f"Infima API error: {str(e)}")

    def get_dark_web_exposures(self, client_id: int, start: Optional[str] = None,
                                end: Optional[str] = None, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Fetch ALL per-user dark web exposure records for a client by paginating
        via offset until a short page confirms the last page.

        Every active user is returned by this endpoint, including users with
        zero exposures -- resolved/unresolved counts always reflect status as
        of today; start/end only bound which exposures (by discovery date)
        are counted.

        Args:
            client_id: Infima client id
            start: ISO date/timestamp lower bound on exposure discovery date
            end: ISO date/timestamp upper bound on exposure discovery date
            limit: Page size (API max is 1000)

        Returns:
            List of per-user exposure records
        """
        endpoint = f"{self.base_url}/clients/{client_id}/darkweb/exposures"
        all_items: List[Dict[str, Any]] = []
        offset = 0

        while True:
            params: Dict[str, Any] = {"limit": limit, "offset": offset}
            if start:
                params["start"] = start
            if end:
                params["end"] = end

            try:
                logger.info(f"Fetching Infima dark web exposures (client_id={client_id}, offset={offset})...")
                response = requests.get(endpoint, headers=self.headers, params=params, timeout=30)

                if response.status_code == 403:
                    # Not a failure -- this client simply hasn't enabled Dark Web
                    # Monitoring. Raising a distinct exception here (rather than
                    # returning silently) forces every caller to make an explicit
                    # choice about how to represent "disabled" vs "zero exposures",
                    # instead of the two states quietly collapsing into each other.
                    logger.info(f"Dark Web Monitoring is not enabled for client_id={client_id} (403)")
                    raise DarkWebMonitoringNotEnabled(
                        f"Dark Web Monitoring is not enabled for this client (client_id={client_id})"
                    )

                if response.status_code >= 400:
                    logger.error(f"Infima API error response: {response.text}")
                    response.raise_for_status()

                data = response.json()
                items = self._extract_list(data, context=f"GET /darkweb/exposures (client_id={client_id})")

            except DarkWebMonitoringNotEnabled:
                raise
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to fetch Infima dark web exposures: {e}")
                raise Exception(f"Infima API error: {str(e)}")

            all_items.extend(items)

            # No pagination metadata confirmed in the API response -- a page
            # shorter than the requested limit is the signal we've reached
            # the last page.
            if len(items) < limit:
                break
            offset += limit

        logger.info(f"Retrieved {len(all_items)} dark web exposure records for client_id={client_id}")
        return all_items