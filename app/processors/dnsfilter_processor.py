import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
import calendar

from app.clients.dnsfilter_client import DNSFilterClient

logger = logging.getLogger(__name__)


class DNSFilterProcessor:
    def __init__(self, account_id: int, dnsfilter_org_id: str):
        self.account_id = account_id
        self.org_id = str(dnsfilter_org_id)
        try:
            api_key = self._get_dnsfilter_credentials()
            self.client = DNSFilterClient(api_key=api_key, org_id=self.org_id)
            logger.info(f"DNSFilterProcessor initialized for account_id={account_id}, org_id={self.org_id}")
        except ValueError as ve:
            logger.warning(f"DNSFilter credentials incomplete for account_id={account_id}: {ve} — Skipping DNSFilter compilation.")
            self.client = None
        except Exception as e:
            logger.error(f"Unexpected error initializing DNSFilter Client: {e} — Skipping DNSFilter compilation.")
            self.client = None

    # ------------------------------------------------------------------
    # Credentials
    # ------------------------------------------------------------------

    def _get_dnsfilter_credentials(self) -> str:
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
            api_key = decrypted.get("dnsfilter", {}).get("dnsfilter_api_key")

            if not api_key:
                raise ValueError(f"dnsfilter_api_key not found for account_id={self.account_id}")

            logger.info(f"DNSFilter credentials retrieved for account_id={self.account_id}")
            return api_key

        except Exception as e:
            logger.error(f"Failed to retrieve DNSFilter credentials: {e}")
            raise

    # ------------------------------------------------------------------
    # Date range helpers
    # ------------------------------------------------------------------

    def _last_complete_month_range(self) -> Tuple[datetime, datetime]:
        today = datetime.now(timezone.utc)
        end = today.replace(day=1, hour=23, minute=59, second=59, microsecond=0) - timedelta(days=1)
        start = end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, end

    def _is_outside_60_days(self, month_name: str) -> bool:
        try:
            from app.utils.month_selector import MonthSelector
            ms = MonthSelector()
            start_ts, _ = ms.get_month_timestamps(month_name)
            sixty_days_ago = datetime.now(timezone.utc) - timedelta(days=60)
            return datetime.fromtimestamp(start_ts, tz=timezone.utc) < sixty_days_ago
        except Exception:
            return True

    def _resolve_date_range(self, month_name: Optional[str]) -> Tuple[str, str]:
        fmt = "%Y-%m-%dT%H:%M:%SZ"

        # REMOVED: self._is_outside_60_days(month_name) so the inline clamp handles it!
        if not month_name or month_name == "last_3_months":
            start_dt, end_dt = self._last_complete_month_range()
            logger.info(
                f"DNSFilter: '{month_name}' unsupported or missing — "
                f"falling back to last month ({start_dt.strftime('%Y-%m')}) range"
            )
            return start_dt.strftime(fmt), end_dt.strftime(fmt)

        try:
            from app.utils.month_selector import MonthSelector
            ms = MonthSelector()
            start_ts, end_ts = ms.get_month_timestamps(month_name)
            return (
                datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime(fmt),
                datetime.fromtimestamp(end_ts,   tz=timezone.utc).strftime(fmt),
            )
        except Exception as e:
            logger.warning(f"DNSFilter: failed to resolve date range for '{month_name}': {e} — falling back to last month")
            start_dt, end_dt = self._last_complete_month_range()
            return start_dt.strftime(fmt), end_dt.strftime(fmt)
    # ------------------------------------------------------------------
    # Database Cache Helper
    # ------------------------------------------------------------------

    def _fetch_month_from_db(self, month_name: str, year: int) -> Optional[Dict[str, Any]]:
        """
        Queries the generated_reports table to find a previously processed 
        DNSFilter JSON for a specific month to bypass API limitations.
        """
        try:
            from app.core.database.engine import SessionLocal
            from app.models.reports import GeneratedReport
            from app.models.organizations import OrganizationIntegration

            db = SessionLocal()
            try:
                # 1. Reverse map the DNSFilter org_id string to our internal integer org_id
                org_mapping = db.query(OrganizationIntegration).filter(
                    OrganizationIntegration.platform_organization_id == str(self.org_id)
                ).first()

                if not org_mapping:
                    logger.warning(f"Could not map DNSFilter org {self.org_id} to internal DB.")
                    return None

                internal_org_id = org_mapping.organization_id

                # 2. Query the reports table for this specific month
                report = db.query(GeneratedReport).filter(
                    GeneratedReport.organization_id == internal_org_id,
                    GeneratedReport.report_year == year,
                    GeneratedReport.report_month.ilike(month_name)
                ).order_by(GeneratedReport.created_at.desc()).first()

                # 3. Extract the DNSFilter object from the saved JSON
                if report and report.organization_data:
                    dns_data = report.organization_data.get("DNSFilter")
                    if dns_data and dns_data.get("charts"):
                        logger.info(f"✓ DNSFilter DB Cache hit for {month_name} {year}")
                        return dns_data

                logger.info(f"✗ No DNSFilter DB Cache found for {month_name} {year}")
                return None
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error reading DNSFilter DB cache for {month_name}: {e}")
            return None

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    def fetch_all_data(self, month_name: Optional[str] = None) -> Dict[str, Any]:
        if not self.client:
            logger.warning(f"DNSFilter client is not initialized for org_id={self.org_id} — Returning empty dataset.")
            return {
                "source": "empty",
                "months_data": {}
            }

        # Determine boundaries
        self.is_quarterly = month_name and month_name.strip().lower() == "last_3_months"
        now = datetime.now(timezone.utc)

        # --- CASE A: QUARTERLY REPORT (LAST 3 MONTHS) ---
        if self.is_quarterly:
            logger.info("DNSFilter: Processing Quarterly Report (Tiered DB + API Fallback)")

            # Dynamically calculate the last 3 months relative to July 2026
            # target_months will be [4, 5, 6] -> April, May, June
            months_to_fetch = []
            for i in [3, 2, 1]:
                m = now.month - i
                y = now.year
                if m <= 0:
                    m += 12
                    y -= 1
                months_to_fetch.append({"month_num": m, "year": y})

            historical_months_data = {}

            for item in months_to_fetch:
                m_num = item["month_num"]
                y_num = item["year"]
                m_name = calendar.month_name[m_num]  # "April", "May", "June"
                m_key = m_name.lower()

                # 1. Always check the Local DB Cache first
                cached_data = self._fetch_month_from_db(m_name, y_num)
                if cached_data:
                    historical_months_data[m_key] = {
                        "source": "database",
                        "data": cached_data.get("charts", {})
                    }
                    continue

                # 2. DB Cache Miss -> Determine if we can make a Live API Call
                # April (3 months ago relative to July) is > 60 days -> DB Only
                months_ago = (now.year - y_num) * 12 + (now.month - m_num)
                
                if months_ago >= 3:
                    logger.warning(f"DNSFilter: Cache miss for {m_name} ({months_ago} months ago). Beyond API limit — defaulting to 0.")
                    historical_months_data[m_key] = {
                        "source": "empty",
                        "data": {}
                    }
                    continue

                # 3. Safe for Live API Call (June or May)
                logger.info(f"DNSFilter: DB Cache miss for {m_name}. Triggering live fallback API call.")
                
                # Resolve timestamps for this specific month
                try:
                    from app.utils.month_selector import MonthSelector
                    ms = MonthSelector()
                    query_key = f"{m_key}_{y_num}"  # e.g., "may_2026"
                    start_ts, end_ts = ms.get_month_timestamps(query_key)
                    
                    start_date = datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    end_date = datetime.fromtimestamp(end_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    
                    # Apply our dynamic 60-day threshold clamp right here for May
                    s_dt = datetime.strptime(start_date, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                    safe_limit = now - timedelta(days=60)
                    if s_dt < safe_limit:
                        start_date = safe_limit.strftime("%Y-%m-%dT%H:%M:%SZ")
                        logger.warning(f"Clamped {m_name} start_date to {start_date} to prevent 60-day API crash.")

                    # Fetch live data fields from the client
                    live_raw = {
                        "requests_allowed": self.client.get_total_requests(start_date, end_date, "allowed"),
                        "requests_blocked": self.client.get_total_requests(start_date, end_date, "blocked"),
                        "threats":          self.client.get_total_threats(start_date, end_date),
                        "threats_allowed":  self.client.get_total_threats(start_date, end_date, "allowed"),
                        "threats_blocked":  self.client.get_total_threats(start_date, end_date, "blocked"),
                    }
                    
                    historical_months_data[m_key] = {
                        "source": "api_live",
                        "data": live_raw
                    }

                except Exception as e:
                    logger.error(f"Failed live fallback for {m_name}: {e}")
                    historical_months_data[m_key] = {"source": "empty", "data": {}}

            return {
                "source": "quarterly_compiled",
                "months_data": historical_months_data
            }

        # --- CASE B: STANDARD SINGLE MONTH REPORT ---
        else:
            start_date, end_date = self._resolve_date_range(month_name)
            
            # Inline single month clamp check
            try:
                s_dt = datetime.strptime(start_date, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                safe_limit = now - timedelta(days=60)
                if s_dt < safe_limit:
                    start_date = safe_limit.strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                pass

            logger.info(f"DNSFilter Single Month Fetch: {start_date} to {end_date}")
            
            return {
                "source": "api_single",
                "requests_allowed": self.client.get_total_requests(start_date, end_date, "allowed"),
                "requests_blocked": self.client.get_total_requests(start_date, end_date, "blocked"),
                "threats":          self.client.get_total_threats(start_date, end_date),
                "threats_allowed":  self.client.get_total_threats(start_date, end_date, "allowed"),
                "threats_blocked":  self.client.get_total_threats(start_date, end_date, "blocked"),
            }

    # ------------------------------------------------------------------
    # Process
    # ------------------------------------------------------------------

    def process_all_data(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        # --- CASE A: QUARTERLY REPORT ---
        if raw.get("source") == "quarterly_compiled":
            return self._process_quarterly_data(raw.get("months_data", {}))

        # --- CASE B: MONTHLY REPORT (Original Logic) ---
        try:
            charts = {
                "request_counts": {
                    "total_threats_count":    self._sum_totals(raw.get("threats", {})),
                    "total_blocked_requests": self._sum_totals(raw.get("requests_blocked", {})),
                },
                "Quaterly_data": {},
                "Monthly_data": {
                    "allowed_vs_blocked_request": self._allowed_vs_blocked(
                        raw.get("requests_allowed", {}), raw.get("requests_blocked", {})
                    ),
                    "threats_over_time": self._values_over_time(raw.get("threats", {})),
                    "allowed_vs_blocked_threats": self._allowed_vs_blocked(
                        raw.get("threats_allowed", {}), raw.get("threats_blocked", {})
                    )
                }
            }
            logger.info(f"DNSFilter monthly data processed — {len(charts)} charts")
            return {"dnsfilter_metrics": {"charts": charts}}
        except Exception as e:
            logger.error(f"DNSFilter process_all_data failed: {e}")
            return {"dnsfilter_metrics": {"charts": {
                "request_counts": {"total_threats_count": 0, "total_blocked_requests": 0},
                "Quaterly_data": {},
                "Monthly_data": {}
            }}}

    def _process_quarterly_data(self, months_data: dict) -> dict:
        """
        Extracts totals from either DB-cached charts or raw Live API JSON
        and merges them into the new Quarterly PM charts.
        """
        total_threats = 0
        total_blocked_requests = 0
        
        threats_over_months = {}
        avb_threats = {"allowed": {}, "blocked": {}}
        avb_requests = {"allowed": {}, "blocked": {}}
        
        for m_key, m_payload in months_data.items():
            month_name = m_key.capitalize()  # e.g., "April"
            source = m_payload.get("source")
            data = m_payload.get("data", {})
            
            threats_over_months[month_name] = 0
            avb_requests["allowed"][month_name] = 0
            avb_requests["blocked"][month_name] = 0
            avb_threats["allowed"][month_name] = 0
            avb_threats["blocked"][month_name] = 0
            
            if source == "database":
                # Check where request_counts lives based on old vs new structure
                req_counts = data.get("request_counts", {})
                t_threats = req_counts.get("total_threats_count", 0)
                t_blocked_req = req_counts.get("total_blocked_requests", 0)
                
                # Database might have charts in root or under Monthly_data depending on when they were generated
                m_data_block = data.get("Monthly_data", data) 
                
                m_allowed_req = sum(item.get("allowed", 0) for item in m_data_block.get("allowed_vs_blocked_request", []))
                m_blocked_req = sum(item.get("blocked", 0) for item in m_data_block.get("allowed_vs_blocked_request", []))
                m_allowed_thr = sum(item.get("allowed", 0) for item in m_data_block.get("allowed_vs_blocked_threats", []))
                m_blocked_thr = sum(item.get("blocked", 0) for item in m_data_block.get("allowed_vs_blocked_threats", []))
                
            elif source == "api_live":
                t_threats = self._sum_totals(data.get("threats", {}))
                t_blocked_req = self._sum_totals(data.get("requests_blocked", {}))
                m_allowed_req = self._sum_totals(data.get("requests_allowed", {}))
                m_blocked_req = self._sum_totals(data.get("requests_blocked", {}))
                m_allowed_thr = self._sum_totals(data.get("threats_allowed", {}))
                m_blocked_thr = self._sum_totals(data.get("threats_blocked", {}))
                
            else:
                t_threats = t_blocked_req = m_allowed_req = m_blocked_req = m_allowed_thr = m_blocked_thr = 0
                
            total_threats += t_threats
            total_blocked_requests += t_blocked_req
            
            threats_over_months[month_name] = t_threats
            avb_requests["allowed"][month_name] = m_allowed_req
            avb_requests["blocked"][month_name] = m_blocked_req
            avb_threats["allowed"][month_name] = m_allowed_thr
            avb_threats["blocked"][month_name] = m_blocked_thr
            
        quarterly_charts = {
            "request_counts": {
                "total_threats_count": total_threats,
                "total_blocked_requests": total_blocked_requests
            },
            "Quaterly_data": {
                "threats_over_months": threats_over_months,
                "allowed_vs_blocked_request_quarterly": avb_requests,
                "allowed_vs_blocked_threats_quarterly": avb_threats
            },
            "Monthly_data": {}
        }
        
        logger.info(f"DNSFilter quarterly data processed — {len(quarterly_charts)} charts")
        return {"dnsfilter_metrics": {"charts": quarterly_charts}}
    # ------------------------------------------------------------------
    # Chart helpers
    # ------------------------------------------------------------------

    def _parse_date(self, ts: str) -> str:
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%d")
        except Exception:
            return ts

    def _sum_totals(self, data: dict) -> int:
        try:
            return sum(v.get("total", 0) for v in data.get("data", {}).get("values", []))
        except Exception:
            return 0

    def _values_over_time(self, data: dict) -> dict:
        try:
            return {
                self._parse_date(v["bucket"]): v.get("total", 0)
                for v in data.get("data", {}).get("values", [])
                if "bucket" in v
            }
        except Exception:
            return {}

    def _allowed_vs_blocked(self, allowed_data: dict, blocked_data: dict) -> list:
        try:
            date_map: Dict[str, dict] = {}
            for val in allowed_data.get("data", {}).get("values", []):
                if "bucket" in val:
                    d = self._parse_date(val["bucket"])
                    date_map[d] = {"date": d, "allowed": val.get("total", 0), "blocked": 0}
            for val in blocked_data.get("data", {}).get("values", []):
                if "bucket" in val:
                    d = self._parse_date(val["bucket"])
                    if d in date_map:
                        date_map[d]["blocked"] = val.get("total", 0)
                    else:
                        date_map[d] = {"date": d, "allowed": 0, "blocked": val.get("total", 0)}
            return [date_map[k] for k in sorted(date_map)]
        except Exception as e:
            logger.error(f"DNSFilter _allowed_vs_blocked failed: {e}")
            return []
