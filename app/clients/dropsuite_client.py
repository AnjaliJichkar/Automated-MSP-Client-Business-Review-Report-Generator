import logging
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)


class DropsuiteClient:
    def __init__(self, base_url: str, reseller_token: str, org_auth_token: str):
        self.base_url = base_url.rstrip("/")
        self.reseller_token = reseller_token
        self.org_headers = {
            "X-Reseller-Token": reseller_token,
            "X-Access-Token": org_auth_token,
        }
        logger.info("DropsuiteClient initialized")

    def _get(self, path: str, headers: dict, params: dict = None) -> Any:
        url = f"{self.base_url}{path}"
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Dropsuite API error on {path}: {e}")
            if getattr(e, "response", None) is not None:
                logger.error(f"Response body: {e.response.text}")
            raise RuntimeError(f"Dropsuite API request failed: {path}") from e

    def get_accounts(self) -> Dict[str, Any]:
        return self._get("/accounts", headers=self.org_headers)

    def get_onedrives(self) -> Dict[str, Any]:
        return self._get("/onedrives", headers=self.org_headers)

    def get_sharepoints(self) -> Dict[str, Any]:
        return self._get("/sharepoints/domains", headers=self.org_headers)

    def get_gdrives(self) -> Dict[str, Any]:
        return self._get("/googledrives", headers=self.org_headers)

    def get_sharedrives(self) -> Dict[str, Any]:
        return self._get("/shareddrives/domains", headers=self.org_headers)
