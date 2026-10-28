import logging
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.dnsfilter.com/v1"


class DNSFilterClient:
    def __init__(self, api_key: str, org_id: str):
        self.org_id = str(org_id)
        self.headers = {
            "Authorization": f"Bearer {api_key}" if not api_key.startswith("Bearer ") else api_key,
            "Accept": "application/json",
        }
        logger.info(f"DNSFilterClient initialized for org_id={self.org_id}")

    def _make_request(self, endpoint: str, params: dict = None) -> Dict[str, Any]:
        url = f"{BASE_URL}{endpoint}"
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"DNSFilter API error on {endpoint}: {e}")
            if getattr(e, "response", None) is not None:
                logger.error(f"Response body: {e.response.text}")
            raise RuntimeError(f"DNSFilter API request failed: {endpoint}") from e

    def get_total_requests(self, start_date: str, end_date: str, req_type: str = "all") -> Dict[str, Any]:
        return self._make_request(
            "/traffic_reports/total_requests",
            params={
                "organization_ids": [int(self.org_id)],
                "from": start_date,
                "to": end_date,
                "bucket_size": "1day",
                "type": req_type,
            },
        )

    def get_total_threats(self, start_date: str, end_date: str, req_type: str = "all") -> Dict[str, Any]:
        return self._make_request(
            "/traffic_reports/total_threats",
            params={
                "organization_ids": [int(self.org_id)],
                "from": start_date,
                "to": end_date,
                "bucket_size": "1day",
                "type": req_type,
            },
        )
