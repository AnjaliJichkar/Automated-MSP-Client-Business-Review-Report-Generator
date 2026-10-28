"""
Axcient x360Cloud Processor
Processes Axcient API data into structured chart and table formats for reporting.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, List

from app.clients.axcient_client import AxcientClient

logger = logging.getLogger(__name__)


class AxcientProcessor:
    """Processes Axcient x360Cloud backup and protection data."""

    def __init__(self, account_id: int, axcient_client_id: str):
        """
        Initialize AxcientProcessor.

        Args:
            account_id: Account ID for credential lookup
            axcient_client_id: Tenant client ID from organization_integrations table
        """
        self.account_id = account_id
        self.client_id = axcient_client_id
        self.client: Optional[AxcientClient] = None

        if not account_id:
            logger.warning("No account_id provided - Axcient data will be skipped")
            return

        try:
            self.client = AxcientClient(account_id=account_id)
            logger.info(f"AxcientProcessor initialized for account_id={account_id}, client_id={axcient_client_id}")
        except Exception as e:
            logger.error(f"Failed to initialize AxcientClient: {e}")
            self.client = None

    # ------------------------------------------------------------------
    # Data Fetching
    # ------------------------------------------------------------------

    def fetch_all_data(self, month_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Fetch both the latest client snapshot and the dynamic backup trend.
        """
        if not self.client:
            logger.warning("Axcient client not initialized - returning empty data")
            return {}

        if not self.client_id:
            logger.error("No client_id provided for Axcient data fetch")
            return {}

        logger.info(f"Fetching Axcient data for client_id={self.client_id}")
        raw_data: Dict[str, Any] = {}

        # 1. Fetch Latest Snapshot
        try:
            raw_data["snapshot"] = self.client.get_client_snapshot(self.client_id)
            logger.info("Axcient client snapshot fetched successfully")
        except Exception as e:
            logger.error(f"Axcient: failed fetching client snapshot: {e}")
            raw_data["snapshot"] = {}

        # 2. Calculate Date Range & Fetch Trend
        try:
            from_date = None
            to_date = None
            
            if month_name:
                try:
                    from app.utils.month_selector import MonthSelector
                    month_selector = MonthSelector()
                    start_ts, end_ts = month_selector.get_month_timestamps(month_name)
                    
                    # Convert timestamps to YYYY-MM-DD strings for the Axcient API
                    from datetime import datetime
                    from_date = datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d")
                    to_date = datetime.fromtimestamp(end_ts).strftime("%Y-%m-%d")
                    logger.info(f"Axcient filtering for selected range ({month_name}): {from_date} to {to_date}")
                except Exception as e:
                    logger.warning(f"Failed to calculate dates using MonthSelector: {e}")

            # Fallback if no month_name provided or MonthSelector failed
            if not from_date or not to_date:
                today = date.today()
                first_day_curr_month = today.replace(day=1)
                last_day_prev_month = first_day_curr_month - timedelta(days=1)
                first_day_prev_month = last_day_prev_month.replace(day=1)

                from_date = first_day_prev_month.strftime("%Y-%m-%d")
                to_date = last_day_prev_month.strftime("%Y-%m-%d")
                logger.info(f"Using fallback previous month filter: {from_date} to {to_date}")

            raw_data["monthly_trend"] = self.client.get_backup_status_trend(
                client_id=self.client_id,
                from_date=from_date,
                to_date=to_date,
                page_size=100
            )
            logger.info(f"Axcient backup trend fetched ({from_date} to {to_date})")
        except Exception as e:
            logger.error(f"Axcient: failed fetching backup trend: {e}")
            raw_data["monthly_trend"] = {}

        return raw_data
    # ------------------------------------------------------------------
    # Data Processing
    # ------------------------------------------------------------------

    def process_all_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process raw Axcient data into structured charts and tables.

        Args:
            raw_data: Raw data returned by fetch_all_data()

        Returns:
            Dict containing 'axcient_metrics' with charts and tables
        """
        if not raw_data:
            logger.warning("No raw data provided - returning default Axcient metrics")
            return {"axcient_metrics": {"charts": self._empty_charts(), "tables": self._empty_tables()}}

        logger.info("Processing Axcient data...")
        snapshot_raw = raw_data.get("snapshot", {})
        monthly_raw = raw_data.get("monthly_trend", {})

        try:
            charts = {
                "account_protection_coverage": self._process_protection_coverage(snapshot_raw),
                "protected_accounts_by_status": self._process_system_status(snapshot_raw),
                "license_optimization_overview": self._process_licensing_efficiency(snapshot_raw),
                "user_backup_execution_health": self._process_user_backup_health(snapshot_raw),
                "sharepoint_backup_execution_health": self._process_sharepoint_backup_health(snapshot_raw),
                "monthly_backup_trend": self._process_monthly_trend(monthly_raw)
            }

            tables = {
                "active_backup_services": self._process_service_connectors(snapshot_raw),
                "backup_alerts": self._process_backup_alerts(snapshot_raw)
            }

            logger.info(f"Axcient data processed successfully — {len(charts)} charts, {len(tables)} tables")
            return {
                "axcient_metrics": {
                    "charts": charts,
                    "tables": tables
                }
            }

        except Exception as e:
            logger.error(f"Axcient process_all_data failed: {e}", exc_info=True)
            return {
                "axcient_metrics": {
                    "charts": self._empty_charts(),
                    "tables": self._empty_tables()
                }
            }

    # ------------------------------------------------------------------
    # Chart & Table Processing Helpers
    # ------------------------------------------------------------------

    def _unwrap(self, data: Any) -> Dict[str, Any]:
        """Helper to safely extract the payload whether nested under 'result' or at root level."""
        if isinstance(data, dict):
            if "result" in data and isinstance(data["result"], dict):
                return data["result"]
            return data
        return {}

    def _process_protection_coverage(self, data: Any) -> Dict[str, int]:
        """Total Users vs Protected Users vs Unprotected Users."""
        client = self._unwrap(data)
        total_users = int(client.get("total_users_count", 0) or 0)
        selected = client.get("selected_for_protection", {}) or {}
        protected_users = int(selected.get("users_count", 0) or 0)

        return {
            "total_users": total_users,
            "protected_users": protected_users,
            "unprotected_users": max(0, total_users - protected_users)
        }

    def _process_system_status(self, data: Any) -> Dict[str, int]:
        """Protected users grouped by source status: Active, Deleted, Inactive."""
        client = self._unwrap(data)
        selected = client.get("selected_for_protection", {}) or {}
        status_map = selected.get("user_count_by_source_system_status", {}) or {}

        return {
            "total_users": int(selected.get("users_count", 0) or 0),
            "active": int(status_map.get("active", 0) or 0),
            "deleted": int(status_map.get("deleted", 0) or 0),
            "inactive": int(status_map.get("inactive", 0) or 0)
        }

    def _process_licensing_efficiency(self, data: Any) -> Dict[str, int]:
        """Billable seats paid vs free retained accounts."""
        client = self._unwrap(data)
        selected = client.get("selected_for_protection", {}) or {}
        total_protected = int(selected.get("users_count", 0) or 0)
        billable_users = int(selected.get("billable_users_count", 0) or 0)

        return {
            "total_protected_users": total_protected,
            "billable_seats": billable_users,
            "retained_free_accounts": max(0, total_protected - billable_users)
        }

    def _process_service_connectors(self, data: Any) -> List[Dict[str, str]]:
        """Enabled/disabled status across connectors (mail, onedrive, sharepoint, etc.)."""
        client = self._unwrap(data)
        selected = client.get("selected_for_protection", {}) or {}
        connectors = selected.get("service_connectors", []) or []

        services_list = []
        if connectors and isinstance(connectors, list):
            first = connectors[0]
            if isinstance(first, dict):
                for k, v in first.items():
                    if k != "parent_tenant":
                        services_list.append({
                            "Service": str(k),
                            "Status": str(v)
                        })
                        
        return services_list

    def _process_user_backup_health(self, data: Any) -> Dict[str, Any]:
        """Latest execution status distribution for user backups."""
        client = self._unwrap(data)
        latest = client.get("latest_report", {}) or {}
        user_metrics = (latest.get("metrics", {}) or {}).get("user", {}) or {}

        return {
            "timestamp": latest.get("timestamp", ""),
            "backup_status": latest.get("backup_status", "Unknown"),
            "total_backed_up_users": int(latest.get("backed_up_users_count", 0) or 0),
            "successful": int(user_metrics.get("successful", 0) or 0),
            "unavailable": int(user_metrics.get("unavailable", 0) or 0),
            "onboarding": int(user_metrics.get("onboarding", 0) or 0),
            "failed_or_partial": int(user_metrics.get("failed_or_partial", 0) or 0),
            "in_progress": int(user_metrics.get("in_progress", 0) or 0),
            "troubled_onboarding": int(user_metrics.get("troubled_onboarding", 0) or 0)
        }

    def _process_sharepoint_backup_health(self, data: Any) -> Dict[str, Any]:
        """Latest execution status distribution for SharePoint sites."""
        client = self._unwrap(data)
        latest = client.get("latest_report", {}) or {}
        sp_metrics = (latest.get("metrics", {}) or {}).get("sharepoint_site", {}) or {}

        return {
            "timestamp": latest.get("timestamp", ""),
            "backup_status": latest.get("backup_status", "Unknown"),
            "total_backed_up_sites": int(latest.get("backed_up_sharepoint_sites_count", 0) or 0),
            "successful": int(sp_metrics.get("successful", 0) or 0),
            "unavailable": int(sp_metrics.get("unavailable", 0) or 0),
            "onboarding": int(sp_metrics.get("onboarding", 0) or 0),
            "failed_or_partial": int(sp_metrics.get("failed_or_partial", 0) or 0),
            "in_progress": int(sp_metrics.get("in_progress", 0) or 0),
            "troubled_onboarding": int(sp_metrics.get("troubled_onboarding", 0) or 0)
        }

    def _process_monthly_trend(self, monthly_data: Any) -> List[Dict[str, Any]]:
        """30-day timeline of user backup states."""
        if not isinstance(monthly_data, dict):
            return []

        results = monthly_data.get("result", [])
        if not isinstance(results, list):
            return []

        history = []
        for backup in results:
            if not isinstance(backup, dict):
                continue
            metrics = (backup.get("metrics", {}) or {}).get("user", {}) or {}
            history.append({
                "timestamp": backup.get("timestamp", ""),
                "status": backup.get("status", "Unknown"),
                "successful": int(metrics.get("successful", 0) or 0),
                "unavailable": int(metrics.get("unavailable", 0) or 0),
                "onboarding": int(metrics.get("onboarding", 0) or 0),
                "failed_or_partial": int(metrics.get("failed_or_partial", 0) or 0),
                "in_progress": int(metrics.get("in_progress", 0) or 0),
                "troubled_onboarding": int(metrics.get("troubled_onboarding", 0) or 0)
            })

        # Return oldest to newest for chronological plotting
        return list(reversed(history))

    def _process_backup_alerts(self, data: Any) -> List[Dict[str, Any]]:
        """Extract exceptions, failures, or troubled onboarding states."""
        client = self._unwrap(data)
        latest = client.get("latest_report", {}) or {}
        metrics = latest.get("metrics", {}) or {}

        alerts = []
        for resource_type in ["user", "sharepoint_site"]:
            res_metrics = metrics.get(resource_type, {}) or {}
            failed = int(res_metrics.get("failed_or_partial", 0) or 0)
            troubled = int(res_metrics.get("troubled_onboarding", 0) or 0)

            if failed > 0:
                alerts.append({
                    "resource": resource_type.replace("_", " ").title(),
                    "type": "Backup Failure / Partial",
                    "count": failed,
                    "severity": "Critical",
                    "action_required": f"Review {failed} failed {resource_type} backup(s) in x360Cloud vault"
                })
            if troubled > 0:
                alerts.append({
                    "resource": resource_type.replace("_", " ").title(),
                    "type": "Troubled Onboarding",
                    "count": troubled,
                    "severity": "Warning",
                    "action_required": f"Investigate {troubled} stalled onboarding sync(s)"
                })

        return alerts

    # ------------------------------------------------------------------
    # Empty Defaults (Defensive Fallbacks)
    # ------------------------------------------------------------------

    def _empty_charts(self) -> Dict[str, Any]:
        return {
            "account_protection_coverage": {"total_users": 0, "protected_users": 0, "unprotected_users": 0},
            "protected_accounts_by_status": {"total_users": 0, "active": 0, "deleted": 0, "inactive": 0},
            "license_optimization_overview": {"total_protected_users": 0, "billable_seats": 0, "retained_free_accounts": 0},
            "user_backup_execution_health": {
                "timestamp": "", "backup_status": "Unknown", "total_backed_up_users": 0,
                "successful": 0, "unavailable": 0, "onboarding": 0, "failed_or_partial": 0,
                "in_progress": 0, "troubled_onboarding": 0
            },
            "sharepoint_backup_execution_health": {
                "timestamp": "", "backup_status": "Unknown", "total_backed_up_sites": 0,
                "successful": 0, "unavailable": 0, "onboarding": 0, "failed_or_partial": 0,
                "in_progress": 0, "troubled_onboarding": 0
            },
            "monthly_backup_trend": []
        }

    def _empty_tables(self) -> Dict[str, Any]:
        return {
            "active_backup_services": [],
            "backup_alerts": []
        }