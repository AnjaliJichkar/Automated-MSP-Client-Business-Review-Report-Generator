# organization_sync.py
import asyncio
import httpx
import logging
import base64
import requests
from typing import List, Dict

from app.services.organizations.service import OrganizationMappingService
from app.core.config.settings import config_manager

logger = logging.getLogger(__name__)


class OrganizationSyncService:
    def __init__(self, credential_id: str = None):
        self.mapping_service = OrganizationMappingService()
        self.credentials = config_manager.load_credentials(credential_id)

    async def get_autotask_zone_url(self) -> str:
        """Get Autotask zone URL - copied from your working client"""
        try:
            zone_info_url = f"https://webservices.autotask.net/atservicesrest/v1.0/zoneInformation?user={self.credentials['autotask_username']}"

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(zone_info_url)
                response.raise_for_status()
                zone_data = response.json()
                zone_url = zone_data.get('url').rstrip('/') + '/'
                logger.info(f"Retrieved Autotask zone URL: {zone_url}")
                return zone_url
        except Exception as e:
            logger.error(f"Could not get Autotask zone info: {e}")
            raise

    async def get_connectsecure_token(self) -> str:
        """Get ConnectSecure token - copied from your working client"""
        try:
            auth_url = f"{self.credentials['connectsecure_base_url']}/w/authorize"

            headers = {
                "Client-Auth-Token": base64.b64encode(
                    f"{self.credentials['connectsecure_tenant_name']}+{self.credentials['connectsecure_client_id']}:{self.credentials['connectsecure_client_secret_b64']}".encode()
                ).decode(),
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(auth_url, headers=headers, timeout=30.0)
                response.raise_for_status()
                token_data = response.json()

                access_token = token_data.get('access_token')
                user_id = token_data.get('user_id')

                if access_token and user_id:
                    logger.info(f"ConnectSecure token obtained successfully")
                    return access_token, str(user_id)
                else:
                    raise Exception("Missing access_token or user_id in response")

        except Exception as e:
            logger.error(f"Failed to get ConnectSecure token: {e}")
            raise

    async def fetch_ninjaone_organizations(self) -> List[Dict]:
        """Fetch organizations from NinjaOne API"""
        try:
            token_url = f"{self.credentials['ninjaone_instance_url']}/oauth/token"

            async with httpx.AsyncClient() as client:
                # Get token
                token_response = await client.post(token_url, data={
                    'grant_type': 'client_credentials',
                    'client_id': self.credentials['ninjaone_client_id'],
                    'client_secret': self.credentials['ninjaone_client_secret'],
                    'scope': 'monitoring management'
                })
                token_response.raise_for_status()
                token = token_response.json()['access_token']

                # Get organizations
                headers = {
                    'Authorization': f'Bearer {token}',
                    'Accept': 'application/json'
                }

                org_response = await client.get(
                    "https://teamlogicitneaustin.rmmservice.com/v2/organizations",
                    headers=headers,
                    timeout=30.0
                )
                org_response.raise_for_status()
                data = org_response.json()

                logger.info(f"Fetched {len(data)} organizations from NinjaOne")
                return data

        except Exception as e:
            logger.error(f"Error fetching NinjaOne organizations: {e}")
            return []

    async def fetch_autotask_companies(self) -> List[Dict]:
        """Fetch companies using the exact same method as your working client"""
        try:
            # Get zone URL first
            zone_url = await self.get_autotask_zone_url()

            headers = {
                "UserName": self.credentials['autotask_username'],
                "Secret": self.credentials['autotask_secret'],
                "APIIntegrationcode": self.credentials['autotask_integration_code'],
                "Content-Type": "application/json"
            }

            # Try with minimal filters first
            query_data = {
                "MaxRecords": 50,  # Start small
                "filter": [
                    {"field": "isActive", "op": "eq", "value": True}  # Only active companies
                ]
            }

            endpoint = f"{zone_url}v1.0/Companies/query"

            async with httpx.AsyncClient() as client:
                response = await client.post(endpoint, headers=headers, json=query_data, timeout=30.0)
                response.raise_for_status()
                data = response.json()

                print(f"DEBUG: Response status: {response.status_code}")
                print(f"DEBUG: Response data keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")

                if 'items' in data:
                    items = data['items']
                    print(f"DEBUG: Found {len(items)} companies")
                    if items:
                        print(
                            f"DEBUG: Sample company: {items[0].get('companyName', 'No name')} (ID: {items[0].get('id')})")
                    return items
                else:
                    print(f"DEBUG: No 'items' key found. Full response: {data}")
                    return []

        except Exception as e:
            logger.error(f"Error fetching Autotask companies: {e}")
            print(f"DEBUG: Exception details: {e}")
            return []

    async def fetch_connectsecure_companies(self) -> List[Dict]:
        """Fetch companies from ConnectSecure API using working authentication"""
        try:
            # Get token and user_id
            token, user_id = await self.get_connectsecure_token()

            headers = {
                'Authorization': f'Bearer {token}',
                'X-User-ID': user_id,
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://pod104.myconnectsecure.com/r/company/companies",
                    headers=headers,
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()

                # Handle different response formats
                if isinstance(data, list):
                    companies = data
                elif isinstance(data, dict) and 'data' in data:
                    companies = data['data']
                elif isinstance(data, dict) and 'companies' in data:
                    companies = data['companies']
                else:
                    logger.warning(f"Unexpected ConnectSecure response format: {type(data)}")
                    companies = []

                logger.info(f"Fetched {len(companies)} companies from ConnectSecure")
                return companies

        except Exception as e:
            logger.error(f"Error fetching ConnectSecure companies: {e}")
            return []

    async def sync_organizations(self) -> Dict:
        """Sync all organizations from all platforms"""
        try:
            logger.info("Starting organization sync...")

            # Fetch data from all platforms
            ninja_orgs, autotask_companies, connectsecure_companies = await asyncio.gather(
                self.fetch_ninjaone_organizations(),
                self.fetch_autotask_companies(),
                self.fetch_connectsecure_companies(),
                return_exceptions=True
            )

            # Handle any API failures gracefully
            ninja_orgs = ninja_orgs if not isinstance(ninja_orgs, Exception) else []
            autotask_companies = autotask_companies if not isinstance(autotask_companies, Exception) else []
            connectsecure_companies = connectsecure_companies if not isinstance(connectsecure_companies,
                                                                                Exception) else []

            logger.info(
                f"Fetched: {len(ninja_orgs)} NinjaOne, {len(autotask_companies)} Autotask, {len(connectsecure_companies)} ConnectSecure")

            # Create mappings using organization_service
            results = self.mapping_service.sync_all_organizations(
                ninja_orgs,
                autotask_companies,
                connectsecure_companies
            )

            return {
                "success": True,
                "results": results,
                "message": f"Processed {results['total_processed']} organizations",
                "summary": {
                    "source_id_matches": results.get('source_id_matches', 0),
                    "name_only_matches": results.get('name_only_matches', 0),
                    "ninjaone_only": results.get('ninjaone_only', 0)
                }
            }

        except Exception as e:
            logger.error(f"Sync failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "results": None
            }

    async def sync_single_organization(self, ninjaone_org_id: str) -> Dict:
        """Sync a single organization on demand"""
        try:
            logger.info(f"Syncing single organization: {ninjaone_org_id}")

            # Fetch data from all platforms
            ninja_orgs, autotask_companies, connectsecure_companies = await asyncio.gather(
                self.fetch_ninjaone_organizations(),
                self.fetch_autotask_companies(),
                self.fetch_connectsecure_companies(),
                return_exceptions=True
            )

            # Handle failures
            ninja_orgs = ninja_orgs if not isinstance(ninja_orgs, Exception) else []
            autotask_companies = autotask_companies if not isinstance(autotask_companies, Exception) else []
            connectsecure_companies = connectsecure_companies if not isinstance(connectsecure_companies,
                                                                                Exception) else []

            # Find the specific NinjaOne org
            ninja_org = next((org for org in ninja_orgs if str(org['id']) == ninjaone_org_id), None)

            if not ninja_org:
                return {"success": False, "error": f"Organization {ninjaone_org_id} not found in NinjaOne"}

            # Create mapping for this org
            mapping = self.mapping_service.create_mapping_for_org(
                ninja_org,
                autotask_companies,
                connectsecure_companies
            )

            # Save mapping
            if self.mapping_service.save_mapping(mapping):
                logger.info(f"Successfully synced organization: {ninja_org['name']}")
                return {"success": True, "mapping": mapping}
            else:
                return {"success": False, "error": "Failed to save mapping"}

        except Exception as e:
            logger.error(f"Single org sync failed: {e}")
            return {"success": False, "error": str(e)}