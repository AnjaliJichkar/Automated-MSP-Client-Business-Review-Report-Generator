"""
Authentication module for NinjaOne API only.

This module handles OAuth 2.0 authentication for NinjaOne API.
"""

import base64
import time
import requests
import backoff
from typing import Dict, Optional
import logging
import os

logger = logging.getLogger(__name__)


# Update the OAuth2ClientCredentialsClient class:
class OAuth2ClientCredentialsClient:
    def __init__(self, client_id: str, client_secret: str, token_url: str,
                 base_url: str, scopes: str = None) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = token_url
        self.base_url = base_url.rstrip('/')
        self.scopes = scopes
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0.0
        self._token_buffer_seconds = int(os.getenv('TOKEN_BUFFER_SECONDS', '300'))
        self.timeout = int(os.getenv('DEFAULT_TIMEOUT', '30'))

    def _is_token_valid(self) -> bool:
        """
        Check if current token is still valid.

        Returns:
            True if token exists and hasn't expired
        """
        return (self._access_token is not None and
                time.time() < self._token_expiry - self._token_buffer_seconds)

    @backoff.on_exception(backoff.expo, requests.RequestException, max_tries=3)
    def _request_access_token(self) -> str:
        """
        Request new OAuth 2.0 access token.

        Returns:
            Access token string

        Raises:
            ValueError: If token not found in response
            requests.RequestException: If request fails
        """
        logger.info("Requesting new NinjaOne OAuth 2.0 access token...")

        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }

        data = {"grant_type": "client_credentials"}
        if self.scopes:
            data["scope"] = self.scopes

        logger.info(f"   → Token URL: {self.token_url}")
        response = requests.post(self.token_url, headers=headers, data=data, timeout=15)
        logger.info(f"   → Response Status: {response.status_code}")
        if response.status_code != 200:
            logger.error(f"   → Token Error Response: {response.text}")
            print(f"Token Error Response: {response.text}")
        response.raise_for_status()
        token_data = response.json()

        access_token = token_data.get("access_token")
        expires_in = token_data.get("expires_in", 3600)

        if not access_token:
            raise ValueError("Access token not found in response")

        self._access_token = access_token
        self._token_expiry = time.time() + expires_in

        logger.info(f"    Successfully obtained NinjaOne token (expires in {expires_in}s)")
        logger.info(f"   → Token: {access_token[:20]}...")
        return access_token

    def get_valid_token(self) -> str:
        """
        Get valid access token, refreshing if necessary.

        Returns:
            Valid access token
        """
        if not self._is_token_valid():
            self._request_access_token()
        return self._access_token

    def get_authenticated_headers(self) -> Dict[str, str]:
        """
        Get headers with valid authentication token.

        Returns:
            Dictionary containing authentication headers
        """
        token = self.get_valid_token()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }