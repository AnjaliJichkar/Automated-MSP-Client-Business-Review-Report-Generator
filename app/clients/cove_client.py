"""
Cove Data Protection API Client
Handles authentication and API calls to Cove Backup Management platform
"""

import requests
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class CoveAPIClient:
    """Client for Cove Data Protection API."""

    def __init__(self, account_id: int = None, credential_id: str = None):
        """
        Initialize Cove API client.

        Args:
            account_id: Account ID for fetching credentials from integration_credentials table
            credential_id: DEPRECATED - Legacy UUID for old user_credentials table
        """
        self.visa = None

        # Load credentials from database
        if account_id is not None:
            try:
                from app.core.config.supabase import SupabaseCredentialManager
                from app.services.encryption.manager import EncryptionManager

                credential_manager = SupabaseCredentialManager()
                credentials = credential_manager.get_credentials_by_account_id(account_id)

                if not credentials:
                    raise ValueError(f"No credentials found for account_id: {account_id}")

                cove_creds = credentials.get('cove', {})

                self.username = cove_creds.get('cove_username')
                self.password = cove_creds.get('cove_password')
                self.api_url = cove_creds.get('cove_api_url', 'https://api.backup.management/jsonapi')

                if not self.username or not self.password:
                    raise ValueError("Cove credentials are incomplete")

                logger.info(f"Cove loaded credentials from account_id: {account_id}")

            except Exception as e:
                logger.error(f"Failed to load Cove credentials: {e}")
                raise
        else:
            raise ValueError("account_id is required")

        logger.info(f"Cove API Client initialized")

    def _get_token(self) -> str:
        """
        Authenticate with Cove API and get visa token.

        Returns:
            Visa token string

        Raises:
            Exception if authentication fails
        """
        payload = {
            "jsonrpc": "2.0",
            "method": "Login",
            "params": {
                "username": self.username,
                "password": self.password
            },
            "id": "1"
        }

        try:
            logger.info("Authenticating with Cove API...")
            response = requests.post(self.api_url, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()

            # Check for errors in response
            if "error" in result:
                error_msg = result.get("error", {}).get("message", "Unknown error")
                logger.error(f"Cove authentication failed: {error_msg}")
                raise Exception(f"Cove authentication error: {error_msg}")

            # Visa is at root level in response (as per test_cove_endpoints.py)
            self.visa = result.get('visa')

            if not self.visa:
                logger.error("No visa token in response")
                raise Exception("Visa token not found in authentication response")

            logger.info("Cove authentication successful")
            return self.visa

        except requests.RequestException as e:
            logger.error(f"Cove authentication request failed: {e}")
            raise Exception(f"Failed to connect to Cove API: {e}")
        except Exception as e:
            logger.error(f" Cove authentication failed: {e}")
            raise

    def _make_api_call(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make authenticated API call to Cove.

        Args:
            method: API method name (e.g., "EnumerateAccountStatistics")
            params: Method parameters

        Returns:
            API response as dictionary

        Raises:
            Exception if API call fails
        """
        # Get token if not already authenticated
        if not self.visa:
            self._get_token()

        # Visa goes at root level, not inside params (as per test_cove_endpoints.py)
        payload = {
            "jsonrpc": "2.0",
            "id": "jsonrpc",
            "visa": self.visa,
            "method": method,
            "params": params
        }

        try:
            logger.info(f"Calling Cove API: {method}")
            response = requests.post(self.api_url, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()

            # Check for API errors
            if "error" in result:
                error_msg = result.get("error", {}).get("message", "Unknown error")
                logger.error(f"Cove API error ({method}): {error_msg}")
                raise Exception(f"Cove API error: {error_msg}")

            logger.info(f"Cove API call successful: {method}")
            return result

        except requests.RequestException as e:
            logger.error(f"Cove API request failed ({method}): {e}")
            raise Exception(f"Cove API request error: {e}")
        except Exception as e:
            logger.error(f"Cove API call failed ({method}): {e}")
            raise

    def get_account_statistics(
        self,
        customer_id: str,
        columns: List[str],
        totals: Optional[List[str]] = None,
        start_record: int = 0,
        records_count: int = 100
    ) -> Dict[str, Any]:
        """
        Get account statistics for a specific customer.

        Column Codes Reference:
            I1  = Device Name
            I14 = Used Storage (bytes)
            I32 = OS Type (0=undefined, 1=workstation, 2=server)
            I81 = Device Physicality (Physical/Virtual/Undefined)
            PN  = Retention Policy
            GM  = Protected User Mailboxes
            G@  = Protected Shared Mailboxes
            JM  = OneDrive User Accounts

        Args:
            customer_id: Cove customer ID from organization_integrations table
            columns: List of column codes (e.g., ["I1", "I14", "I32", "I81", "PN", "GM", "G@", "JM"])
            totals: Optional list of aggregations (e.g., ["SUM(I14)", "SUM(GM)", "SUM(G@)", "SUM(JM)"])
            start_record: Start record number for pagination (default: 0)
            records_count: Number of records to retrieve (default: 100)

        Returns:
            API response with account statistics

        Example:
            >>> client.get_account_statistics(
            ...     customer_id="2641536",
            ...     columns=["I1", "I14", "I32", "I81", "PN", "GM", "G@", "JM"],
            ...     totals=["SUM(I14)", "SUM(GM)", "SUM(G@)", "SUM(JM)"],
            ...     start_record=0,
            ...     records_count=100
            ... )
        """
        # Build query params (matching test_cove_endpoints.py working structure)
        params = {
            "query": {
                "PartnerId": int(customer_id),
                "SelectionMode": "Merged",
                "StartRecordNumber": start_record,
                "RecordsCount": records_count,
                "Columns": columns
            }
        }

        if totals:
            params["query"]["Totals"] = totals

        logger.info(f"Fetching account statistics for customer: {customer_id}")
        logger.info(f"   Columns: {columns}")
        logger.info(f"   Pagination: start={start_record}, count={records_count}")
        if totals:
            logger.info(f"   Totals: {totals}")

        return self._make_api_call("EnumerateAccountStatistics", params)

    def get_storage_nodes(self, customer_id) -> Dict[str, Any]:
        """
        Fetch storage nodes for a customer.
        Tries partnerId first (more common), falls back to accountId.

        StorageNodeRole values:
            Home  = local storage only
            Cabs  = offsite / replicated
            Reserve = redundant
        """
        try:
            result = self._make_api_call(
                "EnumerateStorageNodesByAccountId",
                {"partnerId": int(customer_id)}
            )
            if result.get("result"):
                return result
        except Exception as e:
            logger.warning(f"Cove storage nodes (partnerId) failed: {e}, trying accountId")
        return self._make_api_call(
            "EnumerateStorageNodesByAccountId",
            {"accountId": int(customer_id)}
        )

    def get_customers(self) -> List[Dict[str, Any]]:
        """
        Get list of all customer accounts under this partner.

        Returns:
            List of customer dictionaries with details

        Example response item:
            {
                "Id": 111111,
                "Name": "Example Customer",
                "Level": 1,
                ...
            }
        """
        params = {
            "parentPartnerId": int(self.partner_id),
            "fetchRecursively": True
        }

        logger.info(f"Fetching customers for partner: {self.partner_id}")

        result = self._make_api_call("EnumeratePartners", params)
        customers = result.get('result', {}).get('result', [])

        logger.info(f"Found {len(customers)} customers")

        return customers

    def test_connection(self) -> bool:
        """
        Test connection to Cove API.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            self._get_token()
            logger.info("Cove connection test passed")
            return True
        except Exception as e:
            logger.error(f"Cove connection test failed: {e}")
            return False