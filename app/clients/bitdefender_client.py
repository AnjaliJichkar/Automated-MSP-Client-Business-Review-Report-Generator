"""
Bitdefender GravityZone API Client
Handles all API interactions with Bitdefender GravityZone platform
"""

import base64
import requests
import uuid
import math
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class BitdefenderClient:
    """Client for interacting with Bitdefender GravityZone API"""

    def __init__(self, api_key: str):
        """
        Initialize Bitdefender API client

        Args:
            api_key: Bitdefender GravityZone API key
        """
        self.api_key = api_key

        encoded_auth = base64.b64encode(f"{api_key}:".encode()).decode()
        self.auth_header = f"Basic {encoded_auth}"

        self.network_api_url = "https://throbbing-cherry-7759.somesh-nagar.workers.dev/api/v1.0/jsonrpc/network"
        self.network_api_url_v1_1 = "https://throbbing-cherry-7759.somesh-nagar.workers.dev/api/v1.1/jsonrpc/network"
        self.companies_api_url = "https://throbbing-cherry-7759.somesh-nagar.workers.dev/api/v1.0/jsonrpc/companies"

        self.headers = {
            "Content-Type": "application/json",
            "Authorization": self.auth_header
        }

        logger.info("BitdefenderClient initialized")

    def get_company_details(self, company_id: str) -> Dict[str, Any]:
        """
        Get company details including risk score and 2FA status

        Args:
            company_id: Bitdefender company ID

        Returns:
            Company details dict
        """
        payload = {
            "id": str(uuid.uuid4()),
            "jsonrpc": "2.0",
            "method": "getCompanyDetails",
            "params": {"companyId": company_id} if company_id else {}
        }

        try:
            response = requests.post(
                self.companies_api_url,
                headers=self.headers,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            if "error" in data:
                logger.error(f"Bitdefender API error in getCompanyDetails: {data['error']}")
                return {}

            return data.get("result", {})

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get company details: {e}")
            return {}

    def get_endpoints_list(self, company_id: str, page: int = 1, per_page: int = 10) -> Dict[str, Any]:
        """
        Get endpoints list (paginated)

        Args:
            company_id: Bitdefender company ID (parentId)
            page: Page number
            per_page: Items per page

        Returns:
            Endpoints list response with items and pagination info
        """
        payload = {
            "jsonrpc": "2.0",
            "method": "getEndpointsList",
            "id": str(uuid.uuid4()),
            "params": {
                "page": page,
                "perPage": per_page,
                "isManaged": True,
                "filters": {"depth": {"allItemsRecursively": True}},
                "options": {
                    "returnProductOutdated": True,
                    "includeScanLogs": True
                }
            }
        }

        if company_id:
            payload["params"]["parentId"] = company_id

        try:
            response = requests.post(
                self.network_api_url,
                headers=self.headers,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            if "error" in data and data["error"]:
                logger.error(f"Bitdefender API error in getEndpointsList: {data['error']}")
                return {"items": [], "pagesCount": 0, "total": 0}

            return data.get("result", {"items": [], "pagesCount": 0, "total": 0})

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get endpoints list: {e}")
            return {"items": [], "pagesCount": 0, "total": 0}

    def get_network_inventory_items(self, company_id: str, page: int = 1, per_page: int = 1000) -> Dict[str, Any]:
        """
        Get network inventory items (paginated)

        Args:
            company_id: Bitdefender company ID (parentId)
            page: Page number
            per_page: Items per page

        Returns:
            Network inventory response with items and pagination info
        """
        payload = {
            "jsonrpc": "2.0",
            "method": "getNetworkInventoryItems",
            "id": str(uuid.uuid4()),
            "params": {
                "parentId": company_id,
                "page": page,
                "perPage": per_page,
                "filters": {
                    "type": {
                        "computers": True,
                        "virtualMachines": True,
                        "ec2Instances": True
                    },
                    "depth": {"allItemsRecursively": True}
                },
                "options": {
                    "companies": {"returnAllProducts": True},
                    "endpoints": {
                        "includeScanLogs": True,
                        "returnProductOutdated": True
                    }
                }
            }
        }

        try:
            response = requests.post(
                self.network_api_url_v1_1,
                headers=self.headers,
                json=payload,
                verify=False,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            result = data.get("result", {})
            if result is None:
                result = {}

            return {
                "items": result.get("items", []),
                "pagesCount": result.get("pagesCount", 1),
                "total": result.get("total", 0)
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get network inventory items: {e}")
            return {"items": [], "pagesCount": 1, "total": 0}


    def get_all_endpoints_paginated(self, company_id: str, per_page: int = 10) -> List[Dict[str, Any]]:
        """
        Get ALL endpoints by iterating through all pages

        Args:
            company_id: Bitdefender company ID
            per_page: Items per page

        Returns:
            List of all endpoint items
        """
        all_items = []
        current_page = 1

        while True:
            result = self.get_endpoints_list(company_id, page=current_page, per_page=per_page)

            items = result.get("items", [])
            all_items.extend(items)

            pages_count = result.get("pagesCount")
            if pages_count is None:
                total = result.get("total")
                if total is not None and per_page:
                    pages_count = math.ceil(int(total) / int(per_page))
                else:
                    break

            if current_page >= pages_count:
                break

            current_page += 1

        logger.info(f"Retrieved {len(all_items)} total endpoints across {current_page} pages")
        return all_items

    def get_all_network_inventory_paginated(self, company_id: str, per_page: int = 1000) -> List[Dict[str, Any]]:
        """
        Get ALL network inventory items by iterating through all pages

        Args:
            company_id: Bitdefender company ID
            per_page: Items per page

        Returns:
            List of all inventory items
        """
        all_items = []
        current_page = 1

        while True:
            result = self.get_network_inventory_items(company_id, page=current_page, per_page=per_page)

            items = result.get("items", [])
            all_items.extend(items)

            pages_count = result.get("pagesCount", 1)
            if current_page >= pages_count:
                break

            current_page += 1

        logger.info(f"Retrieved {len(all_items)} total inventory items across {current_page} pages")
        return all_items
