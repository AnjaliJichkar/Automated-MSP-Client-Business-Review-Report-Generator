"""
Axcient x360Cloud API Client
Handles authentication and API calls to the Axcient platform.
"""

import requests
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class AxcientClient:
    """Client for interacting with Axcient x360Cloud API."""

    def __init__(self, account_id: int):
        """
        Initialize Axcient API client.

        Args:
            account_id: Account ID for fetching credentials from integration_credentials table
        """
        self.api_key = None
        self.base_url = "https://axapi.axcient.com/x360cloud"
        
        if not account_id:
            raise ValueError("account_id is required to initialize AxcientClient")

        # Load credentials from database
        try:
            from app.core.config.supabase import SupabaseCredentialManager
            
            credential_manager = SupabaseCredentialManager()
            credentials = credential_manager.get_credentials_by_account_id(account_id)

            if not credentials:
                raise ValueError(f"No credentials found for account_id: {account_id}")

            axcient_creds = credentials.get('axcient', {})
            self.api_key = axcient_creds.get('axcient_api_key')

            if not self.api_key:
                raise ValueError("Axcient API key is missing from credentials")

            self.headers = {
                "x-api-key": self.api_key,
                "Accept": "application/json",
                "User-Agent": "MSP-Reporting-Platform/1.0"
            }

            logger.info(f"Axcient API Client initialized for account_id: {account_id}")

        except Exception as e:
            logger.error(f"Failed to load Axcient credentials: {e}")
            raise

    def _make_api_call(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make authenticated GET API call to Axcient.

        Args:
            endpoint: API endpoint path (e.g., "/client/my-client-id")
            params: Optional query parameters

        Returns:
            API response as dictionary
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            logger.info(f"Calling Axcient API: {endpoint}")
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            
            return response.json()

        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error {e.response.status_code}"
            try:
                error_details = e.response.json()
                if isinstance(error_details, dict):
                    error_msg += f": {error_details.get('error', '')} {error_details.get('infoMessage', '')}"
            except Exception:
                error_msg += f": {e.response.text}"
                
            logger.error(f"Axcient API HTTP error on {endpoint}: {error_msg}")
            raise RuntimeError(f"Axcient API request failed: {error_msg}") from e
            
        except requests.RequestException as e:
            logger.error(f"Axcient API request failed ({endpoint}): {e}")
            raise RuntimeError(f"Axcient API request error: {e}") from e

    def get_client_snapshot(self, client_id: str) -> Dict[str, Any]:
        """
        Fetch the current baseline snapshot for a specific client.
        Provides total users, protected users, services enabled, and latest backup health.
        
        Args:
            client_id: The specific Axcient client tenant ID
        """
        endpoint = f"/client/{client_id}"
        return self._make_api_call(endpoint)

    def get_backup_status_trend(self, client_id: str, from_date: str, to_date: str, page_size: int = 100) -> Dict[str, Any]:
        """
        Fetch the historical backup status over a date range.
        Used primarily to build the 30-day backup trend chart.
        
        Args:
            client_id: The specific Axcient client tenant ID
            from_date: Start date string (YYYY-MM-DD)
            to_date: End date string (YYYY-MM-DD)
            page_size: Pagination limit
        """
        endpoint = f"/client/{client_id}/backup_status"
        params = {
            "from": from_date,
            "to": to_date,
            "page": 0,          # Axcient uses 0-indexed pagination
            "page_size": page_size
        }
        return self._make_api_call(endpoint, params=params)