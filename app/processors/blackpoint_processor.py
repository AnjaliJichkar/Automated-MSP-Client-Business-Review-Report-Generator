"""
Blackpoint Cyber Processor.

Orchestrates data fetching using the BlackpointClient and transforms the raw
alerts into exact time-series charts and tables defined by the reporting schema.
"""

import os
import sys
import logging
import calendar
from typing import Dict, Any, Optional
from datetime import datetime

# Standard path resolution used across msp_platform integrations
current_dir = os.path.dirname(os.path.abspath(__file__))
security_system_root = os.path.join(current_dir, '..', '..')
if security_system_root not in sys.path:
    sys.path.insert(0, security_system_root)

from app.clients.blackpoint_client import BlackpointClient
from app.utils.month_selector import MonthSelector

logger = logging.getLogger(__name__)

class BlackpointProcessor:
    """Processes Blackpoint Cyber data for MDR and Cloud Response reporting."""

    def __init__(self, account_id: int, blackpoint_tenant_id: str, org_id: Optional[int] = None):
        self.account_id = account_id
        self.tenant_id = blackpoint_tenant_id
        self.org_id = org_id

        self.is_quarterly = False
        self.target_month_start = None
        self.target_month_end = None
        self.quarterly_start = None

        api_key = self._get_blackpoint_credentials()
        self.client = BlackpointClient(api_key, self.tenant_id)
        logger.info(f"BlackpointProcessor initialized for account_id={account_id}")

    def _get_blackpoint_credentials(self) -> str:
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
                raise ValueError("No credentials found.")

            decrypted_creds = encryption_manager.decrypt_integration_credentials(encrypted_blob)
            api_key = decrypted_creds.get('blackpoint', {}).get('blackpoint_api_key')
            if not api_key:
                raise ValueError("Blackpoint API key missing.")
            return api_key
        except Exception as e:
            logger.error(f"Failed to retrieve Blackpoint credentials: {e}")
            raise

    def _set_date_boundaries(self, month_name: Optional[str]) -> None:
        """Determines if the request is for a single month or a 3-month trend."""
        self.is_quarterly = month_name and month_name.strip().lower() == "last_3_months"
        month_selector = MonthSelector()

        try:
            if not self.is_quarterly:
                if month_name:
                    month_info = month_selector.get_month_by_name(month_name)
                    self.target_month_start = month_info.start_timestamp
                    self.target_month_end = month_info.end_timestamp
                else:
                    available = month_selector.get_available_months(count=1)
                    self.target_month_start = available[0].start_timestamp
                    self.target_month_end = available[0].end_timestamp

                # Rollback 2 months for baseline just in case
                start_dt = datetime.fromtimestamp(self.target_month_start)
                m = start_dt.month - 3
                y = start_dt.year
                if m <= 0: m += 12; y -= 1
                self.quarterly_start = start_dt.replace(year=y, month=m).timestamp()

            else:
                # If "last_3_months", dynamically find the 3 month baseline
                now = datetime.now()
                start_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                m = start_dt.month - 3
                y = start_dt.year
                if m <= 0: m += 12; y -= 1
                self.quarterly_start = start_dt.replace(year=y, month=m).timestamp()

        except Exception as e:
            logger.warning(f"Date bound failure: {e}")
            now = datetime.now()
            start_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            self.target_month_start = start_dt.timestamp()

            m = start_dt.month - 3
            y = start_dt.year
            if m <= 0: m += 12; y -= 1
            self.quarterly_start = start_dt.replace(year=y, month=m).timestamp()

    def _fetch_historical_quarterly_data(self, year: int, months: list) -> Optional[Dict[str, Any]]:
        """
        Attempts to pull Blackpoint data directly from the generated_reports table.
        Tier 1: Checks for a pre-compiled Quarterly report (e.g., 'March-May').
        Tier 2: Checks for 3 individual Monthly reports to stitch.
        """
        try:
            from app.core.database.engine import SessionLocal
            from app.models.reports import GeneratedReport
            from app.models.organizations import OrganizationIntegration

            db = SessionLocal()
            db_data = {}

            try:
                # REVERSE MAPPING: Find the integer org_id using the string tenant_id
                org_mapping = db.query(OrganizationIntegration).filter(
                    OrganizationIntegration.platform_organization_id == str(self.tenant_id)
                ).first()

                if not org_mapping:
                    logger.info(f"Could not map tenant {self.tenant_id} back to an internal org_id. Forcing API fallback.")
                    return None

                internal_org_id = org_mapping.organization_id

                import calendar
                first_month_name = calendar.month_name[months[0]]
                last_month_name = calendar.month_name[months[-1]]
                quarterly_month_string = f"{first_month_name}-{last_month_name}"

                # --- TIER 1: LOOK FOR PRE-COMPILED QUARTERLY REPORT ---
                precompiled_report = db.query(GeneratedReport).filter(
                    GeneratedReport.organization_id == internal_org_id,
                    GeneratedReport.report_year == year,
                    GeneratedReport.report_type == 'quarterly',
                    GeneratedReport.report_month.ilike(quarterly_month_string)
                ).order_by(GeneratedReport.created_at.desc()).first()

                if precompiled_report and precompiled_report.organization_data:
                    bp_data = precompiled_report.organization_data.get("Blackpoint")
                    if bp_data and bp_data.get("charts"):
                        logger.info(f"Found PRE-COMPILED Quarterly Cache for {quarterly_month_string}. Skipping stitcher!")
                        return {"source": "database_precompiled", "data": bp_data}

                # --- TIER 2: LOOK FOR INDIVIDUAL MONTHS TO STITCH ---
                logger.info("No pre-compiled quarterly report found. Attempting to stitch individual months...")
                for month_num in months:
                    month_name_full = calendar.month_name[month_num]

                    report = db.query(GeneratedReport).filter(
                        GeneratedReport.organization_id == internal_org_id,
                        GeneratedReport.report_year == year,
                        GeneratedReport.report_month.ilike(month_name_full)
                    ).order_by(GeneratedReport.created_at.desc()).first()

                    if not report or not report.organization_data:
                        logger.info(f"Missing DB data for {month_name_full} {year}. Forcing Live API fallback.")
                        return None

                    bp_data = report.organization_data.get("Blackpoint", {})
                    if not bp_data or not bp_data.get("charts"):
                        logger.info(f"Missing Blackpoint charts in DB for {month_name_full} {year}.")
                        return None

                    db_data[month_name_full.lower()] = bp_data

                logger.info("Successfully retrieved 3 individual months from local database cache!")
                return {"source": "database_stitched", "historical_data": db_data}

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error reading historical DB data: {e}")
            return None

    def fetch_all_data(self, month_name: Optional[str] = None) -> Dict[str, Any]:
        """Fetches data, prioritizing the database cache for quarterly reports."""
        self._set_date_boundaries(month_name)

        if self.is_quarterly:
            from datetime import timedelta, timezone

            # --- 1. PRIORITY: DB CACHE CHECK (Calculate months relative to current date) ---
            now = datetime.now()
            # We want the 3 complete months before the current month
            # If current month is June (6), target_months should be [3, 4, 5] (March, April, May)
            target_months = []
            for i in [3, 2, 1]:
                m = now.month - i
                if m <= 0:
                    m += 12
                target_months.append(m)

            # Use the year matching the earliest month in the window
            target_year = now.year if (now.month - 3) > 0 else now.year - 1

            db_result = self._fetch_historical_quarterly_data(target_year, target_months)
            if db_result:
                return db_result  # Return the cached data and bypass the network entirely!

            # --- 2. FALLBACK: LIVE API CALL (with 89-day retention clamp) ---
            api_start_dt = datetime.fromtimestamp(self.quarterly_start, tz=timezone.utc)
            safe_limit = datetime.now(timezone.utc) - timedelta(days=89)
            if api_start_dt < safe_limit:
                logger.info("Blackpoint query range exceeds 90 days. Clamping API request window to 89 days ago.")
                api_start_dt = safe_limit

            quarterly_iso = api_start_dt.strftime("%Y-%m-%dT00:00:00Z")
            logger.info(f"Quarterly Fetch Mode Activated: Since {quarterly_iso}")
            return {
                "source": "api",
                "cr_quarterly": self.client.get_alert_groups(since=quarterly_iso, type_filter="CR"),
                "all_quarterly": self.client.get_alert_groups(since=quarterly_iso, type_filter=None)
            }
        else:
            # --- 3. RESTORED MONTHLY BLOCK (Must align with 'if self.is_quarterly:') ---
            monthly_iso = datetime.fromtimestamp(self.target_month_start).strftime("%Y-%m-%dT00:00:00Z")
            logger.info(f"Monthly Fetch Mode Activated: Since {monthly_iso}")
            return {
                "source": "api",
                "mdr_monthly": self.client.get_alert_groups(since=monthly_iso, type_filter="MDR"),
                "cr_monthly": self.client.get_alert_groups(since=monthly_iso, type_filter="CR"),
                "all_monthly": self.client.get_alert_groups(since=monthly_iso, type_filter=None)
            }

    def process_all_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        # --- TIER 1 CACHE: PRE-COMPILED QUARTERLY DATA ---
        if raw_data.get("source") == "database_precompiled":
            logger.info("Serving pre-compiled quarterly database cache directly...")
            return {"blackpoint_metrics": raw_data["data"]}

        # --- TIER 2 CACHE: DATABASE DATA STITCHING ---
        if raw_data.get("source") == "database_stitched":
            logger.info("Stitching historical database charts into nested CR layout...")
            historical = raw_data["historical_data"]

            stitched_charts = {
                "cloud_responses_investigated": {},
                "cloud_responses_responded": {},
                "soc_response_activity_trend": {}
            }

            for month, data in historical.items():
                charts = data.get("charts", {})
                tables = data.get("tables", {})

                # Safe extract from older or newer structures
                monthly_box = charts.get("monthly-data", [{}])[0] if isinstance(charts.get("monthly-data"), list) else charts
                cloud_alerts = monthly_box.get("monthly_cloud_alerts", {}) if monthly_box else charts.get("monthly_cloud_alerts", {})

                total_investigated = sum(cloud_alerts.values()) if isinstance(cloud_alerts, dict) else 0
                total_responded = total_investigated

                soc_table = tables.get("soc_escalations_activity", [])
                total_soc = len(soc_table) if isinstance(soc_table, list) else 0

                stitched_charts["cloud_responses_investigated"][month] = total_investigated
                stitched_charts["cloud_responses_responded"][month] = total_responded
                stitched_charts["soc_response_activity_trend"][month] = total_soc

            return {
                "blackpoint_metrics": {
                    "charts": {
                        "Quaterly_data": {
                            "cloud_responses": [
                                {
                                    "cloud_responses_investigated": stitched_charts["cloud_responses_investigated"],
                                    "cloud_responses_responded": stitched_charts["cloud_responses_responded"]
                                }
                            ],
                            "soc_response_activity_trend": stitched_charts["soc_response_activity_trend"]
                        },
                        "monthly_data": {}
                    },
                    "tables": {}
                }
            }

        # --- TIER 3 CACHE: LIVE API PROCESSING ---
        logger.info(f"Processing API data (Quarterly Context: {self.is_quarterly})")

        def get_iso_date(item):
            created_str = item.get("created", "")
            try:
                clean_str = created_str.replace("Z", "+00:00")
                if "." in clean_str:
                    clean_str = clean_str.split(".")[0] + "+00:00"
                return datetime.fromisoformat(clean_str)
            except Exception:
                return None

        def extract_ticket_id(item):
            tid = item.get("ticketId") or item.get("ticket_id")
            if tid: return tid
            tickets = item.get("tickets", [])
            if tickets and isinstance(tickets, list):
                if isinstance(tickets[0], dict):
                    return tickets[0].get("id") or tickets[0].get("ticketId")
                return tickets[0]
            return None

        def extract_action(item):
            alert = item.get("alert", {})
            if isinstance(alert, dict):
                return alert.get("name") or alert.get("action") or alert.get("type") or "Unknown Action"
            return item.get("name", "Unknown Action")

        cr_investigated = {}
        cr_responded = {}
        soc_trend = {}
        monthly_endpoint_alerts = {}
        monthly_cloud_alerts = {}
        soc_escalations_activity = []

        # --- MODE A: MONTHLY TOGGLE EVALUATION ---
        if not self.is_quarterly:
            mdr_monthly = raw_data.get("mdr_monthly", [])
            cr_monthly = raw_data.get("cr_monthly", [])
            all_monthly = raw_data.get("all_monthly", [])

            target_dt_ref = datetime.fromtimestamp(self.target_month_start)
            target_year = target_dt_ref.year
            target_month = target_dt_ref.month
            num_days = calendar.monthrange(target_year, target_month)[1]

            monthly_endpoint_alerts = {f"{target_year:04d}-{target_month:02d}-{day:02d}": 0 for day in range(1, num_days + 1)}
            monthly_cloud_alerts = {f"{target_year:04d}-{target_month:02d}-{day:02d}": 0 for day in range(1, num_days + 1)}

            for item in mdr_monthly:
                dt = get_iso_date(item)
                if dt and dt.year == target_year and dt.month == target_month:
                    date_str = dt.strftime("%Y-%m-%d")
                    if date_str in monthly_endpoint_alerts:
                        monthly_endpoint_alerts[date_str] += 1

            for item in cr_monthly:
                dt = get_iso_date(item)
                if dt and dt.year == target_year and dt.month == target_month:
                    date_str = dt.strftime("%Y-%m-%d")
                    if date_str in monthly_cloud_alerts:
                        monthly_cloud_alerts[date_str] += 1

            for item in all_monthly:
                dt = get_iso_date(item)
                if dt and dt.year == target_year and dt.month == target_month:
                    ticket_id = extract_ticket_id(item)
                    if ticket_id:
                        # --- EXTRACT ENRICHED DATA ---
                        alert_obj = item.get("alert", {})
                        details_obj = alert_obj.get("details", {})

                        # 1. Target (Username)
                        target = alert_obj.get("username") or details_obj.get("user", {}).get("name") or "Unknown"

                        # 2. Risk Score
                        risk_score = item.get("riskScore") or alert_obj.get("riskScore") or "Unknown"

                        # 3. Status
                        status = item.get("status", "Unknown")

                        # 4. Source Location and IP
                        source_obj = details_obj.get("source", {})
                        ip = source_obj.get("ip", "Unknown IP")
                        geo = source_obj.get("geo", {})
                        city = geo.get("city_name", "")
                        country = geo.get("country_iso_code", "")

                        loc_str = f"{city}, {country}".strip(", ")
                        source_context = f"{ip} ({loc_str})" if loc_str else ip

                        # Append the enriched row to the table
                        soc_escalations_activity.append({
                            "date": dt.strftime("%Y-%m-%d"),
                            "ticketId": str(ticket_id),
                            "action": extract_action(item),
                            "riskScore": risk_score,
                            "target": target,
                            "status": status,
                            "sourceLocation": source_context
                        })

        # --- MODE B: QUARTERLY TOGGLE EVALUATION ---
        else:
            cr_quarterly = raw_data.get("cr_quarterly", [])
            all_quarterly = raw_data.get("all_quarterly", [])

            quarterly_bins = {}
            curr_dt = datetime.fromtimestamp(self.quarterly_start)
            for _ in range(3):
                m_name = calendar.month_name[curr_dt.month].lower()
                quarterly_bins[m_name] = 0

                m = curr_dt.month + 1
                y = curr_dt.year
                if m > 12: m = 1; y += 1
                curr_dt = curr_dt.replace(year=y, month=m)

            cr_investigated = quarterly_bins.copy()
            cr_responded = quarterly_bins.copy()
            soc_trend = quarterly_bins.copy()

            for item in cr_quarterly:
                dt = get_iso_date(item)
                ticket_id = extract_ticket_id(item)
                if ticket_id and dt:
                    month_key = dt.strftime("%B").lower()
                    if month_key in cr_investigated:
                        cr_investigated[month_key] += 1

                    status = str(item.get("status", "")).upper()
                    if status in ["RESOLVED", "CLOSED", "COMPLETED", "DONE"]:
                        if month_key in cr_responded:
                            cr_responded[month_key] += 1

            for item in all_quarterly:
                dt = get_iso_date(item)
                ticket_id = extract_ticket_id(item)
                if ticket_id and dt:
                    month_key = dt.strftime("%B").lower()
                    if month_key in soc_trend:
                        soc_trend[month_key] += 1

        # --- EXPLICIT NEW CONDITIONAL ASSEMBLY ---
        if self.is_quarterly:
            return {
                "blackpoint_metrics": {
                    "charts": {
                        "Quaterly_data": {
                            "cloud_responses": [
                                {
                                    "cloud_responses_investigated": cr_investigated,
                                    "cloud_responses_responded": cr_responded
                                }
                            ],
                            "soc_response_activity_trend": soc_trend
                        },
                        "monthly_data": {}
                    },
                    "tables": {}
                }
            }
        else:
            return {
                "blackpoint_metrics": {
                    "charts": {
                        "Quaterly_data": {},
                        "monthly_data": {
                            "monthly_endpoint_alerts": monthly_endpoint_alerts,
                            "monthly_cloud_alerts": monthly_cloud_alerts
                        }
                    },
                    "tables": {
                        "soc_escalations_activity": soc_escalations_activity
                    }
                }
            }