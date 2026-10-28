"""
NodeWare API Client
Handles all API interactions with NodeWare platform
"""

import requests
import time
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

BASE_URL = "https://api.nodeware.com/api/v4"

# Using (connect_timeout, read_timeout) tuple — NOT a single total timeout.
# read_timeout = max seconds between data CHUNKS, not total response time.
# This means large responses (500+ assets) succeed as long as data keeps
# flowing — the request will never timeout mid-transfer on a slow company.
API_CONNECT_TIMEOUT = 10   # seconds to establish TCP connection
API_READ_TIMEOUT    = 30   # max seconds of silence between data chunks

# Retry config — handles transient failures (network blip, 5xx errors)
API_MAX_RETRIES     = 3    # max attempts before giving up
API_RETRY_BACKOFF   = 2    # seconds before retry (doubles: 2s, 4s, 8s)


class NodewareClient:
    """Client for interacting with NodeWare API"""

    def __init__(self, api_token: str):
        self.api_token = api_token
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
        logger.info("NodewareClient initialized")

    def make_api_request(self, endpoint: str, params: Dict = None) -> Any:
        """
        GET request to NodeWare API with:

        1. Per-chunk timeout tuple (connect_timeout, read_timeout)
           - connect_timeout: seconds to establish TCP connection
           - read_timeout:    max SILENCE between data chunks (NOT total time)
           - This means 500+ asset responses NEVER timeout mid-transfer
             as long as NodeWare keeps sending data

        2. Automatic retry with exponential backoff
           - Retries on: ConnectionError, Timeout, 5xx server errors
           - Does NOT retry on: 401, 404, 4xx (not transient)
           - Backoff: 2s -> 4s -> 8s between attempts
        """
        url     = f"{BASE_URL}{endpoint}"
        timeout = (API_CONNECT_TIMEOUT, API_READ_TIMEOUT)

        for attempt in range(1, API_MAX_RETRIES + 1):
            try:
                logger.info(f"GET {url} (attempt {attempt}/{API_MAX_RETRIES})")
                response = requests.get(url, headers=self.headers, params=params, timeout=timeout)

                # 401 — bad token, never retry
                if response.status_code == 401:
                    raise RuntimeError(f"Invalid NodeWare API token (401 Unauthorized)")

                # 404 — not found, never retry
                if response.status_code == 404:
                    raise RuntimeError(f"Resource not found: {endpoint} (404)")

                # 5xx — transient server error, retry
                if response.status_code >= 500:
                    logger.warning(f"Server error {response.status_code} on attempt {attempt}")
                    if attempt < API_MAX_RETRIES:
                        wait = API_RETRY_BACKOFF * attempt
                        logger.info(f"Retrying in {wait}s...")
                        time.sleep(wait)
                        continue
                    raise RuntimeError(
                        f"NodeWare API error after {API_MAX_RETRIES} attempts: {response.text}"
                    )

                # other non-200 — no retry
                if response.status_code != 200:
                    logger.error(f"API Error {response.status_code}: {response.text}")
                    raise RuntimeError(f"NodeWare API Error {response.status_code}: {response.text}")

                return response.json()

            except requests.ConnectionError as e:
                logger.warning(f"Connection error on attempt {attempt}: {e}")
                if attempt < API_MAX_RETRIES:
                    wait = API_RETRY_BACKOFF * attempt
                    logger.info(f"Retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"Cannot reach NodeWare API after {API_MAX_RETRIES} attempts")

            except requests.Timeout:
                logger.warning(f"Read timeout on attempt {attempt} — no data for {API_READ_TIMEOUT}s")
                if attempt < API_MAX_RETRIES:
                    wait = API_RETRY_BACKOFF * attempt
                    logger.info(f"Retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                raise RuntimeError("NodeWare API not responding — timed out after all retries")

            except requests.RequestException as e:
                raise RuntimeError(f"Request error: {str(e)}")

    def get_customer(self, customer_token: str) -> Dict[str, Any]:
        """Fetch customer details by customer token from /customers/ list"""
        customers = self.make_api_request("/customers/")
        customer = next((c for c in customers if c.get("id") == customer_token), None)
        if not customer:
            raise RuntimeError(f"Customer '{customer_token}' not found in NodeWare")
        logger.info(f"Found customer: {customer.get('name', 'Unknown')} ({customer_token})")
        return customer

    def get_assets(self, customer_token: str) -> List[Dict[str, Any]]:
        """Fetch all assets for a customer"""
        assets = self.make_api_request(f"/assets/{customer_token}/")
        result = assets or []
        logger.info(f"Fetched {len(result)} assets for customer {customer_token}")
        return result
