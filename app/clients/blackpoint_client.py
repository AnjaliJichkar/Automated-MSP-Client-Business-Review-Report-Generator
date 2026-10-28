"""
Blackpoint Cyber API Client.

Handles direct synchronous communication with the Blackpoint Cyber API,
implementing standard header mapping, request routing, error containment,
and linear skip/take loop pagination.
"""

import os
import sys
import logging
import requests
from typing import Dict, List, Optional

# Standard path resolution used across your platform's integration clients
current_dir = os.path.dirname(os.path.abspath(__file__))
security_system_root = os.path.join(current_dir, '..', '..')
if security_system_root not in sys.path:
    sys.path.insert(0, security_system_root)

from app.core.config.settings import DEFAULT_TIMEOUT

logger = logging.getLogger(__name__)

class BlackpointClient:
    """Synchronous API client matching msp_platform's core communication patterns."""

    def __init__(self, api_key: str, tenant_id: str) -> None:
        """
        Initialize Blackpoint Client with secure credential tokens.

        Args:
            api_key: Decrypted static Bearer token string
            tenant_id: Target x-tenant-id GUID mapping to the client
        """
        self.api_key = api_key
        self.tenant_id = tenant_id
        self.base_url = "https://api.blackpointcyber.com/v1"
        self.endpoint = "/alert-groups"

    def _get_headers(self) -> Dict[str, str]:
        """Generate mandatory security routing headers for Blackpoint requests."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "x-tenant-id": self.tenant_id,
            "Accept": "application/json"
        }

    def _make_request(self, params: Optional[Dict[str, any]] = None) -> List[Dict]:
        """
        Executes outbound requests to the Blackpoint endpoint and natively handles
        the skip/take loop pagination matrix directly inside the network tier.
        """
        url = f"{self.base_url}{self.endpoint}"
        headers = self._get_headers()
        base_params = params.copy() if params else {}

        all_items = []
        skip = 0
        take = 100  # Default batch window size configuration

        try:
            while True:
                # Merge current pagination states into parameters copy
                current_params = base_params.copy()
                current_params.update({"skip": skip, "take": take})

                logger.debug(f"Querying Blackpoint window: skip={skip}, take={take}")

                response = requests.get(
                    url,
                    headers=headers,
                    params=current_params,
                    timeout=DEFAULT_TIMEOUT
                )

                # Raise exceptions directly to catch downstream errors safely
                response.raise_for_status()
                payload = response.json()

                batch_items = payload.get("items", [])
                total_records = payload.get("total", 0)

                # Edge Case Safety: Break immediately if page content yields an empty dataset
                if not batch_items:
                    break

                all_items.extend(batch_items)
                skip += take

                # Stop execution if pagination window eclipses the server-side total ceiling
                if skip >= total_records:
                    break

            logger.info(f"Blackpoint request successful: aggregated {len(all_items)} total alert groups.")
            return all_items

        except requests.exceptions.Timeout:
            logger.error(f"Blackpoint API Timeout encountered on query parameters: {base_params}")
            return []
        except requests.exceptions.ConnectionError:
            logger.error("Blackpoint API Connection failure - host unreachable.")
            return []
        except Exception as exc:
            logger.error(f"Unexpected exception caught during Blackpoint pagination processing: {exc}")
            return []

    def get_alert_groups(self, since: str, type_filter: Optional[str] = None) -> List[Dict]:
        """
        Fetch alert groups with custom scoping modifiers.

        Args:
            since: ISO-8601 string baseline timestamp boundary (e.g., '2026-05-01T00:00:00Z')
            type_filter: Optional endpoint filter string parameter ('MDR' or 'CR')
        """
        query_params = {"since": since}
        if type_filter:
            query_params["type"] = type_filter

        logger.info(f"Dispatching Blackpoint query wrapper: since={since}, type={type_filter}")
        return self._make_request(params=query_params)