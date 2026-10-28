"""
API client module for NinjaOne API only.

This module contains client class for fetching data from NinjaOne API
with proper authentication and error handling.
"""

import requests
from typing import Dict, List, Optional
import logging
from datetime import datetime

# Add path resolution for local running
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
security_system_root = os.path.join(current_dir, '..', '..')
if security_system_root not in sys.path:
    sys.path.insert(0, security_system_root)

# Updated imports for new app/ structure
from app.core.config.settings import DEFAULT_TIMEOUT, DEFAULT_PAGE_SIZE, MAX_PAGES
from app.core.auth.utils import OAuth2ClientCredentialsClient

logger = logging.getLogger(__name__)


class NinjaOneAPIClient:
    """Enhanced NinjaOne API client with proper data parsing and server-side filtering."""

    def _filter_by_timestamp(self, data: List[Dict], start_timestamp: float, end_timestamp: float) -> List[Dict]:
        """Client-side filtering fallback for endpoints that don't support server-side filtering."""
        filtered_data = []
        for item in data:
            timestamp = item.get('timestamp')
            if timestamp and start_timestamp <= timestamp <= end_timestamp:
                filtered_data.append(item)
        return filtered_data

    def _timestamp_to_date_string(self, timestamp: float) -> str:
        """Convert timestamp to YYYY-MM-DD format for API parameters."""
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')

    def __init__(self, client_id: str, client_secret: str, instance_url: str, org_id: str, scopes: str = None) -> None:

        self.instance_url = instance_url.rstrip('/')
        self.org_id = org_id

        token_url = f"{self.instance_url}/ws/oauth/token"
        self.oauth_client = OAuth2ClientCredentialsClient(
            client_id=client_id,
            client_secret=client_secret,
            token_url=token_url,
            base_url=self.instance_url,
            scopes=scopes
        )

        # Organization-specific endpoints - only what we need
        self.endpoints = {
            "devices": f"/v2/devices?df=org={org_id}",
            "devices_detailed": f"/v2/devices-detailed?df=org={org_id}&expand=warranty",
            "os_patches": f"/v2/queries/os-patches?df=org={org_id}",
            "os_patch_installs": f"/v2/queries/os-patch-installs?df=org={org_id}",
            "software_patch_installs": f"/v2/queries/software-patch-installs?df=org={org_id}",
            "software_patches": f"/v2/queries/software-patches?df=org={org_id}",
            "organization": f"/v2/organization/{org_id}",
            "locations": "/v2/locations",
        }

    def _make_request(self, endpoint: str, use_pagination: bool = True, params: Optional[Dict] = None) -> List[Dict]:

        url = f"{self.instance_url}{endpoint}"
        headers = self.oauth_client.get_authenticated_headers()

        # Initialize request parameters
        request_params = params.copy() if params else {}

        logger.debug(f"Making NinjaOne request to: {endpoint}")
        if request_params:
            logger.debug(f"   → With parameters: {request_params}")

        try:
            # Try simple request first for better performance
            logger.debug(f"   → Making simple request...")
            response = requests.get(url, headers=headers, params=request_params, timeout=15)
            logger.debug(f"   → Response status: {response.status_code}")
            response.raise_for_status()
            data = response.json()

            if isinstance(data, list):
                logger.debug(f"Simple request successful: {len(data)} items")
                return data
            elif isinstance(data, dict):
                items = (data.get('results', []) or
                        data.get('data', []) or
                        data.get('items', []) or
                        data.get('agents', []))

                # If it's a single record response, wrap in list
                if not items and any(key in data for key in ['deviceId', 'id', 'name']):
                    items = [data]

                logger.debug(f"Simple request successful: {len(items)} items from data structure")
                return items

            # If simple request doesn't work, try pagination
            if use_pagination:
                logger.debug(f"   → Simple request returned no recognizable data, trying pagination...")
                all_items = []
                page_size = DEFAULT_PAGE_SIZE
                page = 0

                logger.debug(f"   → Using pagination (page size: {page_size})")
                while page < MAX_PAGES:
                    # Add pagination parameters to existing params
                    paginated_params = request_params.copy()
                    paginated_params.update({'pageSize': page_size, 'page': page})

                    logger.debug(f"   → Requesting page {page}...")
                    response = requests.get(url, headers=headers, params=paginated_params, timeout=15)
                    logger.debug(f"   → Response status: {response.status_code}")
                    response.raise_for_status()
                    data = response.json()

                    # Extract items from response properly handling cursor-based results
                    if isinstance(data, list):
                        current_batch = data
                    elif isinstance(data, dict):
                        current_batch = (data.get('results', []) or
                                       data.get('data', []) or
                                       data.get('items', []) or
                                       data.get('agents', []))

                        # If it's a single record response, wrap in list
                        if not current_batch and any(key in data for key in ['deviceId', 'id', 'name']):
                            current_batch = [data]
                    else:
                        current_batch = []

                    logger.debug(f"   → Retrieved {len(current_batch)} items on page {page}")

                    if not current_batch:
                        logger.debug(f"   → No more data, stopping pagination")
                        break

                    all_items.extend(current_batch)
                    logger.debug(f"   → Total items so far: {len(all_items)}")

                    if len(current_batch) < page_size:
                        logger.debug(f"   → Last page reached (items < page_size)")
                        break

                    page += 1

                if all_items:
                    logger.debug(f" Paginated request successful: {len(all_items)} total items")
                    return all_items

            logger.debug(f"  No recognizable data structure returned")
            return []

        except requests.exceptions.Timeout:
            logger.error(f"Timeout error for {endpoint}")
            return []
        except requests.exceptions.ConnectionError:
            logger.error(f"Connection error for {endpoint}")
            return []
        except Exception as e:
            logger.error(f"Error fetching {endpoint}: {e}")
            return []

    def get_organization_info(self) -> Dict:
        """Get comprehensive organization information."""
        try:
            data = self._make_request(self.endpoints["organization"], use_pagination=False)
            return data[0] if data else {"id": self.org_id, "name": f"Organization {self.org_id}"}
        except:
            return {"id": self.org_id, "name": f"Organization {self.org_id}"}

    def get_software_patch_installs(self, start_timestamp: Optional[float] = None,
                                    end_timestamp: Optional[float] = None) -> List[Dict]:
        """Get software patch install data with SERVER-SIDE filtering by timestamp."""
        params = {}

        # Add server-side date filtering if timestamps provided
        if start_timestamp and end_timestamp:
            start_date = self._timestamp_to_date_string(start_timestamp)
            end_date = self._timestamp_to_date_string(end_timestamp)

            params['installedAfter'] = start_date
            params['installedBefore'] = end_date

            logger.debug(f"  Using SERVER-SIDE filtering: installedAfter={start_date}, installedBefore={end_date}")

        data = self._make_request(self.endpoints["software_patch_installs"], params=params)
        logger.debug(f"  Retrieved {len(data)} software patch installs (server-side filtered)")
        return data

    def get_devices(self) -> List[Dict]:
        """Get devices for the organization."""
        return self._make_request(self.endpoints["devices"])

    def get_devices_detailed(self) -> List[Dict]:
        """Get detailed device information."""
        return self._make_request(self.endpoints["devices_detailed"])

    def get_os_patches(self, start_timestamp: Optional[float] = None, end_timestamp: Optional[float] = None) -> List[Dict]:
        """Get OS patch data, optionally filtered by timestamp (client-side)."""
        data = self._make_request(self.endpoints["os_patches"])
        if start_timestamp and end_timestamp:
            data = self._filter_by_timestamp(data, start_timestamp, end_timestamp)
            logger.debug(f"   → Filtered OS patches to {len(data)} items within timestamp range")
        return data

    def get_os_patch_installs(self, start_timestamp: Optional[float] = None,
                              end_timestamp: Optional[float] = None) -> List[Dict]:
        """Get OS patch install data with SERVER-SIDE filtering by timestamp."""
        params = {}

        # Add server-side date filtering if timestamps provided
        if start_timestamp and end_timestamp:
            start_date = self._timestamp_to_date_string(start_timestamp)
            end_date = self._timestamp_to_date_string(end_timestamp)

            params['installedAfter'] = start_date
            params['installedBefore'] = end_date

            logger.debug(f"Using SERVER-SIDE filtering: installedAfter={start_date}, installedBefore={end_date}")

        data = self._make_request(self.endpoints["os_patch_installs"], params=params)
        logger.debug(f"   → Retrieved {len(data)} OS patch installs (server-side filtered)")
        return data

    def get_software_patches(self, start_timestamp: Optional[float] = None, end_timestamp: Optional[float] = None) -> List[Dict]:
        """Get software patch data, optionally filtered by timestamp (client-side)."""
        data = self._make_request(self.endpoints["software_patches"])
        if start_timestamp and end_timestamp:
            data = self._filter_by_timestamp(data, start_timestamp, end_timestamp)
            logger.debug(f"   → Filtered software patches to {len(data)} items within timestamp range")
        return data

    def get_locations(self) -> List[Dict]:
        """Get all locations across all organizations."""
        data = self._make_request(self.endpoints["locations"])
        logger.debug(f"   → Retrieved {len(data)} locations")
        return data
    