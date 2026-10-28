"""
ConnectSecure API Client - Simplified to use only the working endpoint
"""

import base64
import time
import requests
import backoff
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

import os

logger = logging.getLogger(__name__)

class ConnectSecureConfig:
    """Configuration for ConnectSecure API connection."""

    def __init__(self, tenant_name: str, base_url: str, client_id: str, client_secret_b64: str):
        self.tenant_name = tenant_name
        self.base_url = base_url.rstrip('/')
        self.auth_url = f"{self.base_url}/w/authorize"
        self.client_id = client_id
        self.client_secret_b64 = client_secret_b64


class ConnectSecureClient:
    """ConnectSecure API client using ONLY the working endpoint."""

    def __init__(self, config: ConnectSecureConfig = None, account_id: int = None, credential_id: str = None):
        """
        Initialize ConnectSecure client.

        Args:
            config: ConnectSecureConfig object (if provided, account_id and credential_id are ignored)
            account_id: Account ID for fetching credentials from integration_credentials table (NEW)
            credential_id: DEPRECATED - Legacy UUID for old user_credentials table
        """
        if config is None:
            # Load credentials dynamically for default config
            # Add path resolution for local running
            import sys
            current_dir = os.path.dirname(os.path.abspath(__file__))
            security_system_root = os.path.join(current_dir, '..', '..')
            if security_system_root not in sys.path:
                sys.path.insert(0, security_system_root)

            # NEW: Load credentials from account_id
            if account_id is not None:
                from app.core.config.supabase import SupabaseCredentialManager

                credential_manager = SupabaseCredentialManager()
                credentials = credential_manager.get_credentials_by_account_id(account_id)

                if not credentials:
                    raise ValueError(f"No credentials found for account_id: {account_id}")

                connectsecure_creds = credentials.get('connectsecure', {})
                creds = {
                    'connectsecure_tenant_name': connectsecure_creds.get('connectsecure_tenant_name'),
                    'connectsecure_base_url': connectsecure_creds.get('connectsecure_base_url'),
                    'connectsecure_client_id': connectsecure_creds.get('connectsecure_client_id'),
                    'connectsecure_client_secret_b64': connectsecure_creds.get('connectsecure_client_secret_b64')
                }
                logger.info(f" ConnectSecure loaded credentials from account_id: {account_id}")

            # OLD: Fallback to legacy credential_id method
            else:
                from app.core.config.settings import config_manager

                if credential_id:
                    logger.warning("ConnectSecure: Using DEPRECATED credential_id method. Please migrate to account_id.")

                creds = config_manager.load_credentials(credential_id)

            config = ConnectSecureConfig(
                tenant_name=creds['connectsecure_tenant_name'],
                base_url=creds['connectsecure_base_url'],
                client_id=creds['connectsecure_client_id'],
                client_secret_b64=creds['connectsecure_client_secret_b64']
            )

        self.config = config
        self.token = None
        self.user_id = None
        self.headers = None
        self.token_expiry: float = 0.0
        self.timeout = int(os.getenv('DEFAULT_TIMEOUT', '30'))
        self.token_buffer_seconds = int(os.getenv('TOKEN_BUFFER_SECONDS', '300'))

    def _is_token_valid(self) -> bool:
        """Check if current instance token is valid and not expired."""
        return (self.token is not None and
                time.time() < self.token_expiry - self.token_buffer_seconds)

    @backoff.on_exception(backoff.expo, requests.RequestException, max_tries=3)
    def get_token(self) -> str:
        """Get ConnectSecure API token using the WORKING authentication method."""
        if self._is_token_valid():
            return self.token

        logger.info("Getting new ConnectSecure token...")

        try:
            # Use the WORKING authentication method from your successful files
            headers = {
                "Client-Auth-Token": base64.b64encode(
                    f"{self.config.tenant_name}+{self.config.client_id}:{self.config.client_secret_b64}".encode()
                ).decode(),
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            # POST to /w/authorize with headers only (no body data)
            response = requests.post(
                self.config.auth_url,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()

            token_data = response.json()

            # Extract token information
            access_token = token_data.get('access_token')
            user_id = token_data.get('user_id')
            expires_in = token_data.get('expires_in', 3600)
            status = token_data.get('status')

            if access_token and user_id:
                self.token = access_token
                self.user_id = str(user_id)
                self.token_expiry = time.time() + expires_in - 300  # 5 min buffer
                self._update_headers()

                logger.info(f"ConnectSecure token obtained successfully (expires in {expires_in}s)")
                logger.info(f"    User ID: {self.user_id}")
                logger.info(f"    Token: {self.token[:20]}...")
                return self.token
            elif status is False:
                error_msg = token_data.get("message", "Authentication failed")
                raise RuntimeError(f"ConnectSecure authentication failed: {error_msg}")
            else:
                raise RuntimeError("ConnectSecure token response missing required fields")

        except requests.HTTPError as e:
            if e.response.status_code == 401:
                raise RuntimeError(f"ConnectSecure authentication failed: Invalid credentials (401)")
            else:
                raise RuntimeError(
                    f"ConnectSecure authentication failed: HTTP {e.response.status_code} - {e.response.text}")
        except requests.RequestException as e:
            raise RuntimeError(f"ConnectSecure authentication request failed: {e}")
        except Exception as e:
            raise RuntimeError(f"ConnectSecure authentication failed: {e}")

    def _update_headers(self):
        """Update request headers with current token and user ID."""
        if self.token and self.user_id:
            self.headers = {
                'Authorization': f'Bearer {self.token}',
                'X-User-ID': self.user_id,
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }

    @backoff.on_exception(backoff.expo, requests.RequestException, max_tries=2)
    def _make_api_call(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make authenticated API call to ConnectSecure using working method."""
        if not self.token or not self.user_id:
            self.get_token()

        url = f"{self.config.base_url}{endpoint}"

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

        except requests.HTTPError as e:
            if e.response.status_code == 401:
                # Token might be expired, force re-auth once
                logger.info("Got 401, forcing token refresh...")
                self.token = None
                self.token_expiry = 0.0
                self.get_token()

                # Retry with new token
                response = requests.get(url, headers=self.headers, params=params, timeout=self.timeout)
                response.raise_for_status()
                return response.json()
            else:
                logger.error(
                    f"ConnectSecure API HTTP error for {endpoint}: {e.response.status_code} - {e.response.text}")
                raise
        except requests.RequestException as e:
            logger.error(f"ConnectSecure API request error for {endpoint}: {e}")
            raise
        except Exception as e:
            logger.error(f"ConnectSecure API error for {endpoint}: {e}")
            raise

    def _paginate_get_request(self, url: str, limit: int = 100) -> List[Dict]:
        """ConnectSecure specific pagination function from your working files."""
        if not self.token or not self.user_id:
            self.get_token()

        all_items = []
        skip = 0
        max_iterations = 50  # Safety limit

        logger.debug(f"Starting ConnectSecure pagination for {url}")

        for iteration in range(max_iterations):
            params = {'skip': skip, 'limit': limit}

            try:
                response = requests.get(url, headers=self.headers, params=params, timeout=self.timeout)
                response.raise_for_status()
                data = response.json()

                # Extract items using the working method from your files
                current_batch = []
                if isinstance(data, list):
                    current_batch = data
                elif isinstance(data, dict):
                    # Check all possible data keys
                    for key in ['data', 'items', 'agents', 'assets', 'results', 'records']:
                        if key in data and isinstance(data[key], list):
                            current_batch = data[key]
                            break

                    # If it's a single record response, wrap in list
                    if not current_batch and any(k in data for k in ['id', 'name', 'host_name', 'hostname']):
                        current_batch = [data]

                if not current_batch:
                    break

                all_items.extend(current_batch)
                logger.debug(f"Batch {iteration + 1}: {len(current_batch)} items, total: {len(all_items)}")

                # Check if we got fewer items than requested (last page)
                if len(current_batch) < limit:
                    break

                skip += limit

            except Exception as e:
                logger.error(f"Error during ConnectSecure pagination at skip={skip}: {e}")
                break

        logger.info(f"ConnectSecure pagination complete: {len(all_items)} total items")
        return all_items

    def get_total_asset_count(self, company_id: str) -> Dict[str, Any]:

        logger.info(f"Fetching total asset count for company {company_id}...")

        if not self.token:
            self.get_token()

        endpoint = f"/r/report_queries/total_asset_count?condition=company_id={company_id}"

        try:
            response_data = self._make_api_call(endpoint)

            if isinstance(response_data, list) and len(response_data) > 0:
                asset_count_data = response_data[0]
                logger.info(f" Retrieved asset count data: {asset_count_data.get('total_assets', 0)} total assets")
                return asset_count_data
            else:
                logger.warning("No asset count data returned")
                return {}

        except Exception as e:
            logger.error(f"Failed to fetch total asset count: {e}")
            return {}

    def get_asset_view_data(self, company_id: str, month_name: str = None) -> List[Dict]:

        logger.info(f"Fetching asset view data for company {company_id}, month: {month_name}...")

        if not self.token:
            self.get_token()

        # Build condition with optional month filtering using 'created' field
        if month_name:
            # Calculate date range using MonthSelector (same as AutoTask/NinjaOne)
            try:
                from app.utils.month_selector import MonthSelector
                month_selector = MonthSelector()
                start_timestamp, end_timestamp = month_selector.get_month_timestamps(month_name)

                from datetime import datetime
                start_of_month = datetime.fromtimestamp(start_timestamp)
                end_of_month = datetime.fromtimestamp(end_timestamp)

                start_date = start_of_month.strftime('%Y-%m-%d')
                end_date = end_of_month.strftime('%Y-%m-%d')

                # URL encode the condition: created BETWEEN '2025-08-01' AND '2025-08-31' AND company_id = 6376
                import urllib.parse
                condition = f"created BETWEEN '{start_date}' AND '{end_date}' AND company_id = {company_id}"
                encoded_condition = urllib.parse.quote(condition)

                logger.info(f"ConnectSecure filtering for month: {month_name}")
                logger.info(f"Date range: {start_date} to {end_date}")
            except Exception as e:
                logger.error(f"Failed to calculate month timestamps for {month_name}: {e}")
                # Fallback to no month filtering
                encoded_condition = urllib.parse.quote(f"company_id={company_id}")
                logger.info(f"ConnectSecure falling back to no month filtering for company {company_id}")
        else:
            # No month filtering
            import urllib.parse
            encoded_condition = urllib.parse.quote(f"company_id={company_id}")

        endpoint = f"/r/asset/asset_view?condition={encoded_condition}"
        url = f"{self.config.base_url}{endpoint}"

        try:
            # Use existing pagination method
            all_assets = self._paginate_get_request(url, limit=100)

            logger.info(f"Retrieved {len(all_assets)} assets from asset_view endpoint")

            # Log month filtering results for debugging
            if month_name:
                if len(all_assets) == 0:
                    logger.info(f"Month filtering for '{month_name}' returned 0 assets - this may indicate no activity in that month or restrictive date filtering")
                else:
                    logger.info(f"Month filtering for '{month_name}' successfully returned {len(all_assets)} assets")

            return all_assets

        except Exception as e:
            logger.error(f"Failed to fetch asset view data: {e}")
            return []
    def get_asset_view(self, company_id: str) -> List[Dict]:
        """Get asset view data with detailed online status information."""
        logger.info(f"Fetching asset view for company {company_id}...")

        endpoint = f"/r/asset/asset_view?condition=company_id={company_id}"
        url = f"{self.config.base_url}{endpoint}"

        try:
            # Use pagination method for large datasets
            assets = self._paginate_get_request(url, limit=100)

            logger.info(f"Retrieved {len(assets)} assets from asset view")
            return assets

        except Exception as e:
            logger.error(f"Failed to fetch asset view: {e}")
            return []
    def get_assets_by_company(self, company_id: str) -> List[Dict]:
        """
        Get assets for specific company using ONLY the working endpoint.
        This uses the pagination method from your working files.
        """
        logger.info(f"Fetching ConnectSecure assets for company {company_id}...")

        if not self.token:
            self.get_token()

        endpoint = f"/r/asset/assets?condition=company_id={company_id}"
        url = f"{self.config.base_url}{endpoint}"

        try:
            # Use pagination method from your working files
            assets = self._paginate_get_request(url, limit=100)

            logger.info(f"Retrieved {len(assets)} assets from ConnectSecure")
            return assets

        except Exception as e:
            logger.error(f"Failed to fetch ConnectSecure assets: {e}")
            return []

    def get_risk_score(self, company_id: str, month_name: str = None) -> List[Dict[str, Any]]:
        """Get asset stats data for risk score calculation with optional monthly filtering."""
        logger.info(f"Fetching asset stats for risk score calculation (company {company_id}, month: {month_name})...")

        if not self.token:
            self.get_token()

        # Build condition with optional month filtering
        if month_name:
            # Calculate date range using MonthSelector
            try:
                from app.utils.month_selector import MonthSelector
                month_selector = MonthSelector()
                start_timestamp, end_timestamp = month_selector.get_month_timestamps(month_name)

                from datetime import datetime
                start_of_month = datetime.fromtimestamp(start_timestamp)
                end_of_month = datetime.fromtimestamp(end_timestamp)

                start_date = start_of_month.strftime('%Y-%m-%d')
                end_date = end_of_month.strftime('%Y-%m-%d')

                # URL encode the condition: created >= '2025-08-01' AND created <= '2025-08-31' AND company_id = 6376
                import urllib.parse
                condition = f"created >= '{start_date}' AND created <= '{end_date}' AND company_id = {company_id}"
                encoded_condition = urllib.parse.quote(condition)

                logger.info(f"ConnectSecure asset stats filtering for month: {month_name}")
                logger.info(f"Date range: {start_date} to {end_date}")
            except Exception as e:
                logger.warning(f"Failed to calculate month timestamps for {month_name}: {e}")
                # Fallback to no month filtering
                import urllib.parse
                encoded_condition = urllib.parse.quote(f"company_id={company_id}")
        else:
            # No month filtering
            import urllib.parse
            encoded_condition = urllib.parse.quote(f"company_id={company_id}")

        endpoint = f"/r/asset/asset_stats?condition={encoded_condition}"
        url = f"{self.config.base_url}{endpoint}"

        try:
            # Use pagination method to handle large datasets
            all_asset_stats = self._paginate_get_request(url, limit=100)

            print(f" DEBUG: Retrieved {len(all_asset_stats)} asset stats records")

            # Filter only records that have vul_stats with avg_risk_score
            valid_assets = []
            for asset_stat in all_asset_stats:
                vul_stats = asset_stat.get('vul_stats', {})
                if vul_stats and 'avg_risk_score' in vul_stats:
                    avg_score = vul_stats['avg_risk_score']
                    if avg_score is not None:  # Allow 0 scores but exclude None
                        valid_assets.append(asset_stat)

            print(f"DEBUG: Found {len(valid_assets)} assets with valid avg_risk_score")
            logger.info(f"Retrieved asset stats from {len(valid_assets)} assets with risk scores")

            # Log month filtering results for debugging
            if month_name:
                if len(valid_assets) == 0:
                    logger.info(f"Month filtering for '{month_name}' returned 0 risk score assets - this may indicate no risk data for that month")
                else:
                    logger.info(f"Month filtering for '{month_name}' successfully returned {len(valid_assets)} risk score assets")

            return valid_assets

        except Exception as e:
            print(f" DEBUG: Exception in get_risk_score: {e}")
            logger.error(f"Failed to fetch asset stats for risk score: {e}")
            return []

    def get_agents(self, company_id: str) -> List[Dict[str, Any]]:
        """Get active agents data for specific company (no monthly filtering)."""
        logger.info(f"Fetching active agents for company {company_id}...")

        if not self.token:
            self.get_token()

        # Build condition with is_deprecated=false filter only
        import urllib.parse
        condition = f"is_deprecated=false AND company_id = {company_id}"
        encoded_condition = urllib.parse.quote(condition)

        endpoint = f"/r/company/agents?condition={encoded_condition}"

        try:
            response_data = self._make_api_call(endpoint)

            print(f" DEBUG: Raw agents response type: {type(response_data)}")

            if response_data:
                if isinstance(response_data, dict) and 'data' in response_data:
                    agents_data = response_data['data']
                    print(f"DEBUG: Retrieved {len(agents_data)} active agents from API")
                    logger.info(f"Retrieved {len(agents_data)} active agents")
                    return agents_data
                elif isinstance(response_data, list):
                    print(f" DEBUG: Retrieved {len(response_data)} active agents directly")
                    logger.info(f"Retrieved {len(response_data)} active agents")
                    return response_data
                else:
                    print(f" DEBUG: Unexpected response format: {response_data}")

            logger.warning(" No agents data returned")
            return []

        except Exception as e:
            print(f" DEBUG: Exception in get_agents: {e}")
            logger.error(f"Failed to fetch agents: {e}")
            return []

    def get_company_stats(self, company_id: str, month_name: str = None) -> Dict[str, Any]:
        """Get company statistics including vulnerability counts with optional monthly filtering."""
        logger.info(f"Fetching company stats for company {company_id}, month: {month_name}...")

        if not self.token:
            self.get_token()

        # Build condition with optional month filtering
        if month_name:
            # Calculate date range using MonthSelector
            try:
                from app.utils.month_selector import MonthSelector
                month_selector = MonthSelector()
                start_timestamp, end_timestamp = month_selector.get_month_timestamps(month_name)

                from datetime import datetime
                start_of_month = datetime.fromtimestamp(start_timestamp)
                end_of_month = datetime.fromtimestamp(end_timestamp)

                start_date = start_of_month.strftime('%Y-%m-%d')
                end_date = end_of_month.strftime('%Y-%m-%d')

                # URL encode the condition with date filtering
                import urllib.parse
                condition = f"created >= '{start_date}' AND created <= '{end_date}' AND company_id = {company_id}"
                encoded_condition = urllib.parse.quote(condition)

                logger.info(f"ConnectSecure company stats filtering for month: {month_name}")
                logger.info(f"Date range: {start_date} to {end_date}")
            except Exception as e:
                logger.warning(f"Failed to calculate month timestamps for {month_name}: {e}")
                # Fallback to no month filtering
                import urllib.parse
                condition = f"company_id = {company_id}"
                encoded_condition = urllib.parse.quote(condition)
        else:
            # No monthly filtering
            import urllib.parse
            condition = f"company_id = {company_id}"
            encoded_condition = urllib.parse.quote(condition)

        endpoint = f"/r/company/company_stats?condition={encoded_condition}"

        try:
            response_data = self._make_api_call(endpoint)

            print(f" DEBUG: Raw company_stats response: {response_data}")

            if response_data and 'data' in response_data and response_data['data']:
                company_stats = response_data['data'][0]  # Get first item from data array
                print(f" DEBUG: Retrieved company stats data: {company_stats.get('company_id', 'unknown')}")
                logger.info(f" Retrieved company stats data")

                # Log month filtering results
                if month_name:
                    logger.info(f"Month filtering for '{month_name}' returned company stats")

                return company_stats
            else:
                logger.warning(" No company stats data returned")
                return {}

        except Exception as e:
            print(f"DEBUG: Exception in get_company_stats: {e}")
            logger.error(f"Failed to fetch company stats: {e}")
            return {}

    def test_connection(self) -> bool:
        """Test ConnectSecure API connectivity using the working endpoint."""
        try:
            # Test authentication first
            token = self.get_token()
            if not token:
                logger.error("ConnectSecure: Failed to obtain authentication token")
                return False

            # Test the working endpoint
            assets = self.get_assets_by_company()
            if assets is not None:  # Even empty list is successful
                logger.info(f"ConnectSecure: Successfully connected ({len(assets)} assets found)")
                return True
            else:
                logger.error("ConnectSecure: Assets endpoint returned None")
                return False

        except Exception as e:
            logger.error(f"ConnectSecure connection test failed: {e}")
            return False


def create_connectsecure_client(user_id: str = None):
    """Create ConnectSecure client with dynamic configuration."""
    from app.core.config.settings import config_manager
    config = config_manager.load_credentials(credential_id)

    cs_config = ConnectSecureConfig(
        tenant_name=config['connectsecure_tenant_name'],
        base_url=config['connectsecure_base_url'],
        client_id=config['connectsecure_client_id'],
        client_secret_b64=config['connectsecure_client_secret_b64']
    )

    return ConnectSecureClient(cs_config)
