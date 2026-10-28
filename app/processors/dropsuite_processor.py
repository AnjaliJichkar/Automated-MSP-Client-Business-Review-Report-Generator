import logging
from collections import defaultdict
from typing import Any, Dict, Optional, Tuple

from app.clients.dropsuite_client import DropsuiteClient

logger = logging.getLogger(__name__)


class DropsuiteProcessor:
    def __init__(self, account_id: int, dropsuite_org_token: str):
        self.account_id = account_id
        self.org_token = dropsuite_org_token
        try:
            base_url, reseller_token = self._get_dropsuite_credentials()
            self.client = DropsuiteClient(base_url, reseller_token, self.org_token)
            logger.info(f"DropsuiteProcessor initialized for account_id={account_id}")
        except Exception as e:
            logger.error(f"{e}")

    # ------------------------------------------------------------------
    # Credentials
    # ------------------------------------------------------------------

    def _get_dropsuite_credentials(self) -> Tuple[str, str]:
        try:
            from app.core.database.engine import SessionLocal
            from app.models.credentials import IntegrationCredential
            from app.services.encryption.manager import EncryptionManager

            db = SessionLocal()
            try:
                row = db.query(IntegrationCredential).filter(
                    IntegrationCredential.account_id == self.account_id,
                    IntegrationCredential.is_active == True,
                ).first()
                encrypted_blob = row.credentials if row else None
            finally:
                db.close()

            if not encrypted_blob:
                raise ValueError(f"No credentials found for account_id={self.account_id}")

            decrypted = EncryptionManager().decrypt_integration_credentials(encrypted_blob)
            creds = decrypted.get("dropsuite", {})
            base_url = creds.get("dropsuite_base_url", "https://dropsuite.us/api")
            reseller_token = creds.get("dropsuite_reseller_token")

            if not reseller_token:
                raise ValueError(f"dropsuite_reseller_token not found for account_id={self.account_id}")

            logger.info(f"Dropsuite credentials retrieved for account_id={self.account_id}")
            return base_url, reseller_token

        except Exception as e:
            logger.error(f"Failed to retrieve Dropsuite credentials: {e}")
            raise

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    def fetch_all_data(self, month_name: Optional[str] = None) -> Dict[str, Any]:
        data: Dict[str, Any] = {}

        for key, call in [
            ("accounts",    self.client.get_accounts),
            ("onedrives",   self.client.get_onedrives),
            ("sharepoints", self.client.get_sharepoints),
            ("gdrives",     self.client.get_gdrives),
            ("sharedrives", self.client.get_sharedrives),
        ]:
            try:
                data[key] = call()
            except Exception as e:
                logger.error(f"Dropsuite: failed fetching '{key}': {e}")
                data[key] = {}

        return data

    # ------------------------------------------------------------------
    # Process
    # ------------------------------------------------------------------

    def process_all_data(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        try:
            charts = {
                "mailbox_backup_status_distribution":       self._mailbox_status(raw.get("accounts", {})),
                "onedrive_backup_storage_overview":         self._onedrive_storage(raw.get("onedrives", {})),
                "onedrive_backup_status_distribution":      self._onedrive_status(raw.get("onedrives", {})),
                "sharepoint_storage_and_capacity_overview": self._sharepoint_overview(raw.get("sharepoints", {})),
                "google_drive_storage_and_capacity_overview": self._gdrive_overview(raw.get("gdrives", {})),
                "shared_drive_storage_and_capacity_overview": self._shareddrive_overview(raw.get("sharedrives", {})),
            }
            logger.info(f"Dropsuite data processed — {len(charts)} charts")
            return {"dropsuite_metrics": {"charts": charts}}
        except Exception as e:
            logger.error(f"Dropsuite process_all_data failed: {e}")
            return {"dropsuite_metrics": {"charts": self._empty_charts()}}

    # ------------------------------------------------------------------
    # Chart helpers
    # ------------------------------------------------------------------

    def _items(self, data: Any) -> list:
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("data", "items", "accounts", "onedrives", "sharepoints", "googledrives", "shareddrives", "domains"):
                val = data.get(key)
                if isinstance(val, list):
                    return val
        return []

    def _bytes_to_gb(self, n: Any) -> str:
        try:
            return f"{float(n) / (1024 ** 3):.2f} GB"
        except Exception:
            return "0.00 GB"

    def _mailbox_status(self, data: Any) -> dict:
        try:
            items = self._items(data)
            # DEBUG — uncomment to inspect raw field names
            # if items: logger.info(f"Dropsuite accounts raw sample: {items[0]}")
            counts: Dict[str, int] = defaultdict(int)
            for item in items:
                status = item.get("current_backup_status") or "Unknown"
                counts[str(status)] += 1
            return dict(counts)
        except Exception as e:
            logger.error(f"Dropsuite _mailbox_status failed: {e}")
            return {"Completed": 0}

    def _onedrive_storage(self, data: Any) -> dict:
        try:
            items = self._items(data)
            # DEBUG — uncomment to inspect raw field names
            # if items: logger.info(f"Dropsuite onedrives raw sample: {items[0]}")
            total_storage_bytes = 0
            activated = 0
            deactivated = 0
            for item in items:
                total_storage_bytes += int(item.get("storage", 0) or 0)
                if item.get("deactivated_since") is None:
                    activated += 1
                else:
                    deactivated += 1
            return {
                "total_accounts": len(items),
                "total_storage": self._bytes_to_gb(total_storage_bytes),
                "activated": activated,
                "deactivated": deactivated,
            }
        except Exception as e:
            logger.error(f"Dropsuite _onedrive_storage failed: {e}")
            return {"total_accounts": 0, "total_storage": "0.00 GB", "activated": 0, "deactivated": 0}

    def _onedrive_status(self, data: Any) -> dict:
        try:
            items = self._items(data)
            counts: Dict[str, int] = defaultdict(int)
            for item in items:
                status = item.get("current_backup_status") or "Unknown"
                counts[str(status)] += 1
            return dict(counts)
        except Exception as e:
            logger.error(f"Dropsuite _onedrive_status failed: {e}")
            return {"Completed": 0}

    def _sharepoint_overview(self, data: Any) -> dict:
        try:
            items = self._items(data)
            total_sites = 0
            total_files = 0
            total_storage_bytes = 0
            for item in items:
                total_sites += int(item.get("site_count", 0) or 0)
                total_files += int(item.get("file_count", 0) or 0)
                total_storage_bytes += int(item.get("storage", 0) or 0)
            return {
                "domain_count": len(items),
                "total_site_count": total_sites,
                "total_file_count": total_files,
                "total_storage": self._bytes_to_gb(total_storage_bytes),
            }
        except Exception as e:
            logger.error(f"Dropsuite _sharepoint_overview failed: {e}")
            return {"domain_count": 0, "total_site_count": 0, "total_file_count": 0, "total_storage": "0.00 GB"}

    def _gdrive_overview(self, data: Any) -> dict:
        try:
            items = self._items(data)
            total_files = 0
            total_storage_bytes = 0
            for item in items:
                total_files += int(item.get("file_count", 0) or 0)
                total_storage_bytes += int(item.get("storage", 0) or 0)
            return {
                "drive_count": len(items),
                "total_file_count": total_files,
                "total_storage": self._bytes_to_gb(total_storage_bytes),
            }
        except Exception as e:
            logger.error(f"Dropsuite _gdrive_overview failed: {e}")
            return {"drive_count": 0, "total_file_count": 0, "total_storage": "0.00 GB"}

    def _shareddrive_overview(self, data: Any) -> dict:
        try:
            items = self._items(data)
            total_files = 0
            total_storage_bytes = 0
            for item in items:
                total_files += int(item.get("file_count", 0) or 0)
                total_storage_bytes += int(item.get("storage", 0) or 0)
            return {
                "domain_count": len(items),
                "total_file_count": total_files,
                "total_storage": self._bytes_to_gb(total_storage_bytes),
            }
        except Exception as e:
            logger.error(f"Dropsuite _shareddrive_overview failed: {e}")
            return {"domain_count": 0, "total_file_count": 0, "total_storage": "0.00 GB"}

    def _empty_charts(self) -> dict:
        return {
            "mailbox_backup_status_distribution":       {"Completed": 0},
            "onedrive_backup_storage_overview":         {"total_accounts": 0, "total_storage": "0.00 GB", "activated": 0, "deactivated": 0},
            "onedrive_backup_status_distribution":      {"Completed": 0},
            "sharepoint_storage_and_capacity_overview": {"domain_count": 0, "total_site_count": 0, "total_file_count": 0, "total_storage": "0.00 GB"},
            "google_drive_storage_and_capacity_overview": {"drive_count": 0, "total_file_count": 0, "total_storage": "0.00 GB"},
            "shared_drive_storage_and_capacity_overview": {"domain_count": 0, "total_file_count": 0, "total_storage": "0.00 GB"},
        }
