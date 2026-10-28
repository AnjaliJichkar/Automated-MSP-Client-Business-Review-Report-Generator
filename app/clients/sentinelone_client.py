"""
SentinelOne API Client
Handles all API interactions with SentinelOne platform
"""

import requests
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class SentinelOneClient:
    """Client for interacting with SentinelOne API"""

    def __init__(self, api_token: str, base_url: str):
        self.api_token = api_token
        self.base_url = base_url.rstrip('/')
        self.agents_url = f"{self.base_url}/web/api/v2.1/agents"
        self.threats_url = f"{self.base_url}/web/api/v2.1/threats"
        self.headers = {
            "Authorization": f"ApiToken {api_token}"
        }
        logger.info("SentinelOneClient initialized")

    def get_all_agents(self, site_id: str) -> List[Dict[str, Any]]:
        """
        Fetch ALL agents for a site with cursor-based pagination.
        Agents are always live data (no date filter).
        """
        all_agents = []
        cursor = None
        page_count = 0

        logger.info(f"Fetching agents for site_id: {site_id}")

        while True:
            page_count += 1
            params = {
                "siteIds": site_id,
                "limit": 1000
            }
            if cursor:
                params["cursor"] = cursor

            try:
                response = requests.get(
                    self.agents_url,
                    headers=self.headers,
                    params=params,
                    timeout=60
                )

                if response.status_code != 200:
                    logger.error(f"SentinelOne Agents API Error: Status {response.status_code}, Response: {response.text}")
                    raise RuntimeError(f"SentinelOne Agents API Error: Status {response.status_code}, Response: {response.text}")

                data = response.json()
                agents = data.get("data", [])

                logger.info(f"Agents page {page_count}: Retrieved {len(agents)} agents")

                if agents:
                    all_agents.extend(agents)

                pagination = data.get("pagination", {})
                next_cursor = pagination.get("nextCursor")

                if not next_cursor:
                    break

                cursor = next_cursor

            except requests.exceptions.RequestException as e:
                logger.error(f"SentinelOne agents request error: {e}")
                raise RuntimeError(f"SentinelOne agents request error: {e}")

        logger.info(f"Successfully fetched {len(all_agents)} total agents across {page_count} pages")
        return all_agents

    def get_all_threats(self, site_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch ALL threats for a site with cursor-based pagination.
        Threats are filtered by createdAt date range.
        """
        all_threats = []
        cursor = None
        page_count = 0

        logger.info(f"Fetching threats for site_id: {site_id}")
        if start_date and end_date:
            logger.info(f"Date filter: {start_date} to {end_date}")

        while True:
            page_count += 1
            params = {
                "siteIds": site_id,
                "limit": 1000
            }

            if start_date:
                params["createdAt__gte"] = start_date
            if end_date:
                params["createdAt__lt"] = end_date
            if cursor:
                params["cursor"] = cursor

            try:
                response = requests.get(
                    self.threats_url,
                    headers=self.headers,
                    params=params,
                    timeout=60
                )

                if response.status_code != 200:
                    logger.error(f"SentinelOne Threats API Error: Status {response.status_code}, Response: {response.text}")
                    raise RuntimeError(f"SentinelOne Threats API Error: Status {response.status_code}, Response: {response.text}")

                data = response.json()
                threats = data.get("data", [])

                logger.info(f"Threats page {page_count}: Retrieved {len(threats)} threats")

                if threats:
                    all_threats.extend(threats)

                pagination = data.get("pagination", {})
                next_cursor = pagination.get("nextCursor")

                if not next_cursor:
                    break

                cursor = next_cursor

            except requests.exceptions.RequestException as e:
                logger.error(f"SentinelOne threats request error: {e}")
                raise RuntimeError(f"SentinelOne threats request error: {e}")

        logger.info(f"Successfully fetched {len(all_threats)} total threats across {page_count} pages")
        return all_threats
