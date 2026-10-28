from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import os
import logging

logger = logging.getLogger(__name__)


class EncryptionManager:
    def __init__(self, master_key: str = None):
        """Initialize with master key from environment"""
        if not master_key:
            master_key = os.getenv('ENCRYPTION_KEY')

        if not master_key:
            raise ValueError("ENCRYPTION_KEY not found in environment")

        self.master_key = master_key.encode()

    def _derive_key(self, salt: bytes = None, use_integration_salt: bool = False) -> Fernet:
        """Derive encryption key from master key"""
        if salt is None:
            if use_integration_salt:
                # For integration_credentials table (from encryption_manager_backup.py)
                salt = b'stable_salt_12345678'
            else:
                # For m365_credentials table (from crypto_utils_backup.py)
                salt = b'stable_salt_for_consistency'

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(self.master_key))
        return Fernet(key)

    def encrypt_field(self, plaintext: str) -> str:
        """Encrypt a single field"""
        if not plaintext:
            return plaintext

        try:
            f = self._derive_key()
            encrypted_bytes = f.encrypt(plaintext.encode())
            return base64.urlsafe_b64encode(encrypted_bytes).decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise

    def decrypt_field(self, encrypted_text: str) -> str:
        """Decrypt a single field"""
        if not encrypted_text:
            return encrypted_text

        try:
            f = self._derive_key()
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_text.encode())
            decrypted_bytes = f.decrypt(encrypted_bytes)
            return decrypted_bytes.decode()
        except Exception as e:
            logger.error(f"Decryption failed: {type(e).__name__}: {str(e)}")
            raise

    # Backward compatibility aliases from crypto_utils.py
    def encrypt_secret(self, secret: str) -> str:
        """
        Encrypt a client secret (backward compatibility alias for encrypt_field)

        Args:
            secret: The plaintext secret to encrypt

        Returns:
            Base64 encoded encrypted secret
        """
        return self.encrypt_field(secret)

    def decrypt_secret(self, encrypted_secret: str) -> str:
        """
        Decrypt a client secret (backward compatibility alias for decrypt_field)

        Args:
            encrypted_secret: The base64 encoded encrypted secret

        Returns:
            Decrypted plaintext secret
        """
        return self.decrypt_field(encrypted_secret)

    def encrypt_credentials(self, credentials: dict) -> dict:
        """Encrypt all sensitive fields in credentials dict"""
        sensitive_fields = [
            'ninjaone_client_secret',
            'autotask_secret',
            'connectsecure_client_secret_b64'
        ]

        encrypted_creds = credentials.copy()

        for field in sensitive_fields:
            if field in encrypted_creds and encrypted_creds[field]:
                encrypted_creds[field] = self.encrypt_field(encrypted_creds[field])

        return encrypted_creds

    def decrypt_credentials(self, encrypted_credentials: dict) -> dict:
        """Decrypt all sensitive fields in credentials dict"""
        sensitive_fields = [
            'ninjaone_client_secret',
            'autotask_secret',
            'connectsecure_client_secret_b64'
        ]

        decrypted_creds = encrypted_credentials.copy()

        for field in sensitive_fields:
            if field in decrypted_creds and decrypted_creds[field]:
                decrypted_creds[field] = self.decrypt_field(decrypted_creds[field])

        return decrypted_creds

    def encrypt_integration_credentials(self, credentials: dict) -> dict:
        """
        Encrypt entire credentials dict for integration_credentials table.
        Returns JSONB format: {"encrypted": "base64_encrypted_blob"}

        Args:
            credentials: Dict containing autotask, ninjaone, connectsecure credentials

        Returns:
            Dict with encrypted blob: {"encrypted": "..."}
        """
        import json
        try:
            # Convert credentials dict to JSON string
            credentials_json = json.dumps(credentials)

            # Encrypt the entire JSON string using integration salt
            f = self._derive_key(use_integration_salt=True)
            encrypted_bytes = f.encrypt(credentials_json.encode())
            encrypted_blob = base64.urlsafe_b64encode(encrypted_bytes).decode()

            # Return in JSONB wrapper format
            return {"encrypted": encrypted_blob}
        except Exception as e:
            logger.error(f"Failed to encrypt integration credentials: {e}")
            raise

    def decrypt_integration_credentials(self, encrypted_data: dict) -> dict:
        """
        Decrypt credentials from integration_credentials table.
        Expects JSONB format: {"encrypted": "base64_encrypted_blob"}

        Args:
            encrypted_data: Dict containing {"encrypted": "blob"}

        Returns:
            Decrypted credentials dict with autotask, ninjaone, connectsecure in NESTED format
        """
        import json
        try:
            # Extract encrypted blob from wrapper
            if "encrypted" not in encrypted_data:
                raise ValueError("Invalid encrypted data format - missing 'encrypted' key")

            encrypted_blob = encrypted_data["encrypted"]

            # Decrypt the blob using integration salt
            f = self._derive_key(use_integration_salt=True)
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_blob.encode())
            decrypted_bytes = f.decrypt(encrypted_bytes)
            decrypted_json = decrypted_bytes.decode()

            # Parse JSON back to dict
            credentials = json.loads(decrypted_json)

            # TRANSFORM: Convert flat structure to nested structure if needed
            credentials = self._transform_to_nested_structure(credentials)

            return credentials
        except Exception as e:
            logger.error(f"Failed to decrypt integration credentials: {type(e).__name__}: {str(e)}", exc_info=True)
            raise

    def _transform_to_nested_structure(self, credentials: dict) -> dict:
        """
        Transform flat credential structure to nested platform structure.

        Flat format:
        {
          "ninjaone_client_id": "...",
          "ninjaone_client_secret": "...",
          "autotask_username": "...",
          ...
        }

        Nested format:
        {
          "ninjaone": {
            "ninjaone_client_id": "...",
            "ninjaone_client_secret": "...",
            ...
          },
          "autotask": {
            "autotask_username": "...",
            ...
          },
          "connectsecure": {
            ...
          }
        }
        """
        # Check if already in nested format (has platform keys)
        if any(key in credentials for key in ['ninjaone', 'autotask', 'connectsecure', 'bitdefender', 'cove', 'sentinelone', 'nodeware', 'dnsfilter', 'dropsuit' ,'blackpoint']):
            logger.debug("Credentials already in nested format")
            return credentials

        # Transform flat to nested
        logger.debug("Transforming flat credentials to nested structure")

        nested_credentials = {
            'ninjaone': {},
            'autotask': {},
            'connectsecure': {},
            'bitdefender': {},
            'cove': {},
            'sentinelone': {},
            'nodeware': {},
            'dnsfilter': {},
            'dropsuite':{},
            'blackpoint': {}
        }

        # Map each credential to its platform
        for key, value in credentials.items():
            if key.startswith('ninjaone_'):
                nested_credentials['ninjaone'][key] = value
            elif key.startswith('autotask_'):
                nested_credentials['autotask'][key] = value
            elif key.startswith('connectsecure_'):
                nested_credentials['connectsecure'][key] = value
            elif key.startswith('bitdefender_'):
                nested_credentials['bitdefender'][key] = value
            elif key.startswith('cove_'):
                nested_credentials['cove'][key] = value
            elif key.startswith('sentinelone_'):
                nested_credentials['sentinelone'][key] = value
            elif key.startswith('nodeware_'):
                nested_credentials['nodeware'][key] = value
            elif key.startswith('dnsfilter_'):
                nested_credentials['dnsfilter'][key] = value
            elif key.startswith('dropsuite_'):                 # <--- ADD THIS
                nested_credentials['dropsuite'][key] = value
            elif key.startswith('blackpoint_'):
                nested_credentials['blackpoint'][key] = value
            else:
                # Unknown credential, keep it at root level
                logger.warning(f"Unknown credential key: {key}")

        # Remove empty platform sections
        result = {}
        for platform, creds in nested_credentials.items():
            if creds:  # Only include platforms that have credentials
                result[platform] = creds

        logger.info(f"Transformed credentials - platforms found: {list(result.keys())}")
        return result


# Global instance for backward compatibility with crypto_utils.py
encryption_manager = EncryptionManager()


def encrypt_client_secret(secret: str) -> str:
    """Convenience function to encrypt a client secret"""
    return encryption_manager.encrypt_secret(secret)


def decrypt_client_secret(encrypted_secret: str) -> str:
    """Convenience function to decrypt a client secret"""
    return encryption_manager.decrypt_secret(encrypted_secret)
