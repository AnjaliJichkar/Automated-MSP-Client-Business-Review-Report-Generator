"""
Unified Configuration Module
Merged from:
- msp_endpoints/config.py (Microsoft Graph constants)
- security_reporting_system/config/config.py (ConfigManager, credential management)
"""
import os
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
#                    AI / LLM CONFIGURATION
# ============================================================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


# ============================================================================
#                    MICROSOFT GRAPH CONFIGURATION
# ============================================================================
# Microsoft Graph configuration - these remain constant across tenants
SCOPE = ["https://graph.microsoft.com/.default"]
GRAPH_V1_URL = "https://graph.microsoft.com/v1.0"
GRAPH_BETA_URL = "https://graph.microsoft.com/beta"


# ============================================================================
#                    API CONFIGURATION CONSTANTS
# ============================================================================
DEFAULT_TIMEOUT = 30
TOKEN_BUFFER_SECONDS = 300
DEFAULT_PAGE_SIZE = 1000
MAX_PAGES = 10


# ============================================================================
#                    CONFIGURATION MANAGER CLASS
# ============================================================================
class ConfigManager:
    """
    Configuration manager with Supabase integration for credential management
    """
    def __init__(self):
        self._credentials = None
        self._encryption_manager = None
        self._supabase_manager = None

    @property
    def encryption_manager(self):
        """Lazy load encryption manager"""
        if self._encryption_manager is None:
            from app.services.encryption.manager import EncryptionManager
            self._encryption_manager = EncryptionManager()
        return self._encryption_manager

    @property
    def supabase_manager(self):
        """Lazy load Supabase credential manager"""
        if self._supabase_manager is None:
            from app.core.config.supabase import SupabaseCredentialManager
            self._supabase_manager = SupabaseCredentialManager()
        return self._supabase_manager

    def load_credentials(self, credential_id: str = None) -> Dict[str, Any]:
        """
        Load and decrypt credentials from Supabase

        Args:
            credential_id: Optional credential ID to load. If not provided, uses DEFAULT_CREDENTIAL_ID from env

        Returns:
            Dict containing decrypted credentials

        Raises:
            ValueError: If no credentials found for the given ID
        """
        if self._credentials is None:
            # Use default credential ID if none provided
            credential_id = credential_id

            # Load from Supabase
            encrypted_creds = self.supabase_manager.get_credentials_by_id(credential_id)

            if encrypted_creds:
                # Decrypt the credentials
                self._credentials = self.encryption_manager.decrypt_credentials(encrypted_creds)
                logger.info("Credentials loaded from Supabase")
            else:
                # No credentials found
                raise ValueError(f"No credentials found in Supabase for ID: {credential_id}")

        return self._credentials

    def save_credentials(self, credentials: Dict[str, Any], user_id: str = None) -> bool:
        """
        Encrypt and save credentials to Supabase

        Args:
            credentials: Dictionary of credentials to encrypt and save
            user_id: Optional user ID. If not provided, uses DEFAULT_USER_ID from env

        Returns:
            bool: True if save successful, False otherwise
        """
        user_id = user_id or os.getenv('DEFAULT_USER_ID', 'system_user')

        # Encrypt sensitive fields
        encrypted_creds = self.encryption_manager.encrypt_credentials(credentials)

        # Save to Supabase
        return self.supabase_manager.save_credentials(encrypted_creds, user_id)


# ============================================================================
#                    GLOBAL INSTANCES & HELPER FUNCTIONS
# ============================================================================
# Global config manager instance
config_manager = ConfigManager()


def get_config():
    """
    Lazy loading function - only loads credentials when called

    Returns:
        Dict containing decrypted credentials
    """
    return config_manager.load_credentials()
