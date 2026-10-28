"""
LoyaltyLoop API Client
Handles authentication and API interactions with LoyaltyLoop platform
"""

import requests
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

BASE_URL = "https://app.loyaltyloop.com/api/v1"


class LoyaltyLoopClient:
    """Client for interacting with LoyaltyLoop API"""

    def __init__(self, api_token: str):
        """
        Initialize LoyaltyLoop API client

        Args:
            api_token: LoyaltyLoop API token for authentication
        """
        self.api_token = api_token
        self.base_url = BASE_URL
        
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        logger.info("LoyaltyLoopClient initialized")

    def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None, 
                      json_data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Make authenticated API request to LoyaltyLoop

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path (e.g., "/testimonials/stats")
            params: Query parameters
            json_data: Request body

        Returns:
            Response JSON as dictionary

        Raises:
            Exception if API call fails
        """
        url = f"{self.base_url}{endpoint}"

        try:
            logger.info(f"Making {method} request to: {endpoint}")
            
            response = requests.request(
                method=method,
                url=url,
                headers=self.headers,
                params=params,
                json=json_data,
                timeout=30
            )
            
            logger.info(f"Response status: {response.status_code}")
            
            if response.status_code >= 400:
                logger.error(f"API error response: {response.text}")
                response.raise_for_status()
            
            data = response.json()
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch from {endpoint}: {e}")
            raise Exception(f"LoyaltyLoop API error: {str(e)}")

    def get_testimonial_stats(self) -> Dict[str, Any]:
        """
        Fetch testimonial statistics from LoyaltyLoop. This is the only data this
        integration surfaces (NPS score and loyalty score) -- no testimonial
        content, author, or sentiment data is fetched or stored.

        Returns:
            Dict containing NPS score, loyalty score, and other stats fields
            returned by the API (only nps_score/loyalty_score are consumed
            downstream).
        """
        endpoint = "/testimonials/stats"
        
        try:
            logger.info("Fetching testimonial stats from LoyaltyLoop...")
            response = self._make_request("GET", endpoint)
            
            logger.info(f"Successfully fetched testimonial stats")
            return response
            
        except Exception as e:
            logger.error(f"Failed to fetch testimonial stats: {e}")
            raise