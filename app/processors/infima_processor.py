"""
Infima Data Processor
Handles data fetching and processing for Infima Security Awareness Training:
client-level phishing/training rollup rates plus per-user dark web exposures.
"""

import calendar
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from app.clients.infima_client import InfimaClient, DarkWebMonitoringNotEnabled

logger = logging.getLogger(__name__)


class InfimaProcessor:
    """Processes Infima Security Awareness Training data for security reporting"""

    def __init__(self, account_id: int, infima_client_id: int):
        """
        Initialize InfimaProcessor

        Args:
            account_id: Account ID for credential lookup
            infima_client_id: Infima's own client id for this organization
                (from organization_integrations) -- NOT our internal account_id.
                Infima's hierarchy is Partner -> Clients -> Users; this is the
                "Client" level id.
        """
        self.account_id = account_id
        self.infima_client_id = infima_client_id

        api_key = self._get_infima_api_key()
        self.client = InfimaClient(api_key)

        logger.info(f"InfimaProcessor initialized for account_id={account_id}, infima_client_id={infima_client_id}")

    def _get_infima_api_key(self) -> str:
        """
        Fetch and decrypt Infima API key from integration_credentials

        Returns:
            Decrypted API key
        """
        try:
            from app.core.database.engine import SessionLocal
            from app.models.credentials import IntegrationCredential
            from app.services.encryption.manager import EncryptionManager

            encryption_manager = EncryptionManager()

            db = SessionLocal()
            try:
                row = db.query(IntegrationCredential).filter(
                    IntegrationCredential.account_id == self.account_id,
                    IntegrationCredential.is_active == True
                ).first()
                encrypted_blob = row.credentials if row else None
            finally:
                db.close()

            if not encrypted_blob:
                raise ValueError(f"No credentials found for account_id={self.account_id}")

            decrypted_creds = encryption_manager.decrypt_integration_credentials(encrypted_blob)

            infima_creds = decrypted_creds.get('infima', {})
            api_key = infima_creds.get('infima_api_key')

            if not api_key:
                raise ValueError(f"Infima API key not found for account_id={self.account_id}")

            logger.info(f"Successfully retrieved Infima API key for account_id={self.account_id}")
            return api_key

        except Exception as e:
            logger.error(f"Failed to retrieve Infima API key: {e}")
            raise

    def test_connection(self) -> bool:
        """
        Lightweight connectivity check used by SecurityAssessmentOrchestrator.test_all_connections().

        Returns:
            True if the API key is valid and this org's client record can be
            fetched, False otherwise.
        """
        try:
            details = self.client.get_client_details(self.infima_client_id)
            return isinstance(details, dict) and bool(details)
        except Exception as e:
            logger.error(f"Infima connection test failed: {e}")
            return False

    @staticmethod
    def _shift_month(year: int, month: int, delta: int) -> tuple:
        """Shift a (year, month) pair by `delta` months (negative moves backward)."""
        m = month - 1 + delta
        year += m // 12
        month = m % 12 + 1
        return year, month

    @staticmethod
    def _month_name_to_date_range(month_name: Optional[str]) -> tuple:
        """
        Convert the report period into (start, end) ISO dates for the Dark
        Web Exposures endpoint's start/end discovery-date filters.

        Handles two formats, both of which reports.py can pass as month_name:
        - "<month>_<year>" (e.g. "july_2026") -> that single calendar month
        - "last_3_months" (reports.py's rolling-window option) -> the last 3
          fully-completed calendar months, EXCLUDING the current month. If
          today is in August, this resolves to May + June + July -- not
          "June, July, and part of August". The current month is deliberately
          left out since it isn't finished yet and would otherwise make the
          window an inconsistent mix of full and partial months.

        Args:
            month_name: Report period string from the orchestrator

        Returns:
            (start_date, end_date) as "YYYY-MM-DD" strings, or (None, None) if
            month_name is missing/unparseable -- callers then fetch exposures
            with no date bound rather than failing the whole report.
        """
        if not month_name:
            return None, None

        normalized = month_name.strip().lower()

        if normalized == "last_3_months":
            today = datetime.now(timezone.utc).date()
            # End at the last day of the previous month (last fully-completed
            # month), start 3 months back from today -- current month excluded.
            end_year, end_month = InfimaProcessor._shift_month(today.year, today.month, -1)
            start_year, start_month = InfimaProcessor._shift_month(today.year, today.month, -3)

            start_date = f"{start_year:04d}-{start_month:02d}-01"
            last_day = calendar.monthrange(end_year, end_month)[1]
            end_date = f"{end_year:04d}-{end_month:02d}-{last_day:02d}"
            return start_date, end_date

        try:
            month_part, year_part = normalized.split("_")
            parsed = datetime.strptime(f"{month_part} {year_part}", "%B %Y")
            last_day = calendar.monthrange(parsed.year, parsed.month)[1]
            start_date = parsed.replace(day=1).strftime("%Y-%m-%d")
            end_date = parsed.replace(day=last_day).strftime("%Y-%m-%d")
            return start_date, end_date
        except (ValueError, AttributeError) as e:
            logger.warning(
                f"Could not parse Infima month_name '{month_name}' (expected '<month>_<year>', "
                f"e.g. 'july_2026'): {e}. Fetching all-time exposures instead."
            )
            return None, None

    def fetch_all_data(self, month_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Fetch Infima data from API: client-level rollup rates plus per-user
        dark web exposure counts, bounded to the report month when provided.

        Dark Web Monitoring is a per-client feature -- if this client hasn't
        enabled it, the exposures call returns 403. That's handled here as an
        expected state (not a fetch failure): dark_web_monitoring_enabled is
        set to False and dark_web_exposures stays empty, but client_details
        still comes back normally and the rest of the report isn't blocked.

        Args:
            month_name: Report period, format "<month>_<year>" e.g. "july_2026"

        Returns:
            Dict with raw API responses plus a dark_web_monitoring_enabled flag
        """
        logger.info(f"Fetching Infima data for infima_client_id={self.infima_client_id}, month_name={month_name}")

        start_date, end_date = self._month_name_to_date_range(month_name)

        client_details = self.client.get_client_details(self.infima_client_id)

        dark_web_monitoring_enabled = True
        dark_web_exposures = []
        try:
            dark_web_exposures = self.client.get_dark_web_exposures(
                self.infima_client_id, start=start_date, end=end_date
            )
        except DarkWebMonitoringNotEnabled as e:
            logger.info(f"infima_client_id={self.infima_client_id}: {e}")
            dark_web_monitoring_enabled = False

        raw_data = {
            "client_details": client_details,
            "dark_web_exposures": dark_web_exposures,
            "dark_web_monitoring_enabled": dark_web_monitoring_enabled,
        }

        logger.info(
            f"Fetched Infima data: {len(dark_web_exposures)} dark web exposure records "
            f"(monitoring enabled: {dark_web_monitoring_enabled})"
        )

        return raw_data

    def process_all_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process raw Infima data into chart and table format

        Args:
            raw_data: Raw data from fetch_all_data()

        Returns:
            Processed data with charts and tables
        """
        logger.info("Processing Infima data...")

        processed = {
            "infima_metrics": {
                "charts": {},
                "tables": {}
            }
        }

        client_details = raw_data.get("client_details", {})
        dark_web_exposures = raw_data.get("dark_web_exposures", [])
        dark_web_monitoring_enabled = raw_data.get("dark_web_monitoring_enabled", True)

        processed["infima_metrics"]["charts"]["training_rates"] = self._process_training_rates(client_details)
        processed["infima_metrics"]["tables"]["darkweb_exposures"] = self._process_darkweb_exposures(
            dark_web_exposures, dark_web_monitoring_enabled
        )

        logger.info("Infima data processed successfully")
        return processed

    def _process_training_rates(self, client_details: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract phishing click rate and training on-track rate from the
        client rollup, rounded to 2 decimals.
        """
        result = {
            "phishing_click_rate_total": round(client_details.get("phishing_click_rate_total") or 0, 2),
            "training_on_track_rate": round(client_details.get("training_on_track_rate") or 0, 2)
        }

        logger.info(
            f"Training rates - phishing click: {result['phishing_click_rate_total']}, "
            f"on-track: {result['training_on_track_rate']}"
        )
        return result

    def _process_darkweb_exposures(self, exposures: List[Dict[str, Any]], enabled: bool = True) -> Dict[str, Any]:
        """
        Process per-user dark web exposure records into table format --
        email, combined name, resolved/unresolved counts only. No other
        per-user fields are surfaced.

        Wrapped with an explicit `enabled` flag and `message` rather than
        returning a bare list, because "monitoring disabled for this client"
        and "monitoring enabled, zero exposures found" are genuinely
        different states -- collapsing both into an empty list would show
        the frontend a misleading "0 exposures" instead of the real reason
        the table is empty.

        Args:
            exposures: Per-user exposure records (empty if monitoring is disabled)
            enabled: Whether Dark Web Monitoring is enabled for this client

        Returns:
            Dict: {"enabled": bool, "message": str, "records": [...]}
        """
        if not enabled:
            return {
                "enabled": False,
                "message": "Dark Web Monitoring is not enabled for this client",
                "records": []
            }

        table_data = []
        for user in exposures:
            first_name = (user.get("first_name") or "").strip()
            last_name = (user.get("last_name") or "").strip()
            name = f"{first_name} {last_name}".strip()

            table_data.append({
                "email": user.get("email"),
                "name": name,
                "resolved_exposures": user.get("resolved_exposures") or 0,
                "unresolved_exposures": user.get("unresolved_exposures") or 0
            })

        logger.info(f"Processed {len(table_data)} dark web exposure records for table display")
        return {
            "enabled": True,
            "message": "",
            "records": table_data
        }