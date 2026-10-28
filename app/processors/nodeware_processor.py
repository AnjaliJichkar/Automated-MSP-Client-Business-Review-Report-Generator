"""
NodeWare Processor
Processes NodeWare API data into chart and table format (2 charts, 4 tables)
"""

import logging
from typing import Dict, Any, List, Optional
from collections import defaultdict
from app.clients.nodeware_client import NodewareClient

logger = logging.getLogger(__name__)


class NodewareProcessor:
    """Processes NodeWare data for security reporting"""

    def __init__(self, account_id: int, nodeware_customer_token: str):
        self.account_id = account_id
        self.customer_token = nodeware_customer_token

        api_token = self._get_nodeware_credentials()
        self.client = NodewareClient(api_token)

        logger.info(f"NodewareProcessor initialized for account_id={account_id}, customer_token={nodeware_customer_token}")

    def _get_nodeware_credentials(self) -> str:
        """Fetch and decrypt NodeWare credentials from integration_credentials table"""
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

            nodeware_creds = decrypted_creds.get('nodeware', {})
            api_token = nodeware_creds.get('nodeware_api_token')

            if not api_token:
                raise ValueError(f"NodeWare API token not found for account_id={self.account_id}")

            logger.info(f"Successfully retrieved NodeWare credentials for account_id={self.account_id}")
            return api_token

        except Exception as e:
            logger.error(f"Failed to retrieve NodeWare credentials: {e}")
            raise

    def fetch_all_data(self, month_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Fetch all NodeWare data (customer info + assets).
        month_name is converted to YYYY-MM for Known Exploited CVE filtering only.
        """
        logger.info(f"Fetching NodeWare data for customer_token={self.customer_token}")

        if month_name and month_name.strip().lower() == "last_3_months":
            month_filter = self._get_quarterly_month_filters()
            logger.info(f"Month filter (Known Exploited ONLY — quarterly): {month_filter}")
        else:
            month_filter = self._convert_month_to_yyyy_mm(month_name)
            if month_filter:
                logger.info(f"Month filter (Known Exploited ONLY): {month_filter}")

        customer = self.client.get_customer(self.customer_token)
        assets = self.client.get_assets(self.customer_token)

        if not assets:
            logger.warning(f"No assets found for customer {self.customer_token}")

        logger.info(f"Fetched NodeWare data: {len(assets)} assets for {customer.get('name', 'Unknown')}")

        return {
            "customer": customer,
            "assets": assets,
            "month_filter": month_filter
        }

    def process_all_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process raw NodeWare data into 2 charts and 4 tables"""
        logger.info("Processing NodeWare data...")

        customer = raw_data.get("customer", {})
        assets = raw_data.get("assets", [])
        month = raw_data.get("month_filter")

        processed_result = self._process_nodeware_data(customer, assets, month)
        nodeware_output = processed_result.get("nodeware", {})

        result = {
            "nodeware_metrics": {
                "charts": nodeware_output.get("charts", {}),
                "tables": nodeware_output.get("tables", {})
            }
        }

        logger.info("NodeWare data processed: 2 charts, 4 tables")
        return result

    def _convert_month_to_yyyy_mm(self, month_name: Optional[str]) -> Optional[str]:
        """Convert 'january_2026' to '2026-01' for KEV date filtering"""
        if not month_name:
            return None

        month_mapping = {
            "january": "01", "february": "02", "march": "03", "april": "04",
            "may": "05", "june": "06", "july": "07", "august": "08",
            "september": "09", "october": "10", "november": "11", "december": "12"
        }

        try:
            parts = month_name.lower().split('_')
            if len(parts) == 2:
                month_num = month_mapping.get(parts[0])
                year = parts[1]
                if month_num and len(year) == 4:
                    result = f"{year}-{month_num}"
                    logger.info(f"Converted month '{month_name}' to filter: {result}")
                    return result

            logger.warning(f"Invalid month format: {month_name}, no date filter applied")
            return None

        except Exception as e:
            logger.warning(f"Error parsing month '{month_name}': {e}, no date filter applied")
            return None

    def _get_quarterly_month_filters(self) -> list:
        """Returns list of 3 YYYY-MM strings for quarterly KEV filtering."""
        from app.utils.month_selector import MonthSelector
        months = MonthSelector().get_available_months(count=3)
        return [f"{m.year}-{str(m.month_number).zfill(2)}" for m in months]

    def _filter_by_month(self, date_str: str, month_filter) -> bool:
        """Used ONLY for Known Exploited CVEs filtering"""
        if not month_filter:
            return True
        if not date_str:
            return False
        try:
            if isinstance(month_filter, list):
                return date_str[:7] in month_filter
            return date_str[:7] == month_filter
        except:
            return False

    def _process_nodeware_data(
        self,
        customer: Dict[str, Any],
        assets: List[Dict[str, Any]],
        month: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Core processing logic — exact logic from hardcoded script.
        No logic changes, only split into client/processor structure.
        """
        customer_name = customer.get("name", "Unknown")

        logger.info(f"Processing data for: {customer_name}")
        if month:
            logger.info(f"Month filter (Known Exploited ONLY): {month}")

        # 1. SUMMARY METRICS
        average_score = customer.get("score", 0) or 0
        asset_totals = customer.get("asset_totals", {}) or {}
        total_assets_internal = asset_totals.get("internal", 0) or 0
        total_assets_external = asset_totals.get("external", 0) or 0
        total_assets = total_assets_internal + total_assets_external

        # 2. PROCESS ALL CVEs FROM PLUGINS
        unique_cves = set()
        cve_details = {}           # Stores HIGHEST severity per CVE across all assets
        cve_asset_ids = defaultdict(set)

        # Known exploited
        all_known_exploited = []
        known_exploited_set = set()

        # Asset risk score table
        asset_risk_score = []

        # Stats
        valid_assets = 0
        null_report_count = 0
        total_plugins_processed = 0

        for asset in assets:
            # Use raw .get() not safe_get() to correctly detect null report
            report = asset.get("report")
            if not isinstance(report, dict):
                null_report_count += 1
                logger.warning(f"Asset {asset.get('uuid', 'unknown')} has null report - skipping")
                continue

            valid_assets += 1
            asset_uuid = asset.get("uuid", "")

            host = report.get("host") or {}

            # ASSET NAME RESOLUTION — 4-tier priority:
            # 1. hostname     -> Standard device name (e.g. "MAGT-MSYED")
            # 2. address      -> Domain name for external assets
            # 3. domain_name  -> From WHOIS lookup (fallback for external assets)
            # 4. ip_addr      -> Raw IP when no name exists
            # "Unknown"       -> Last resort if all fields are null/empty
            _whois       = host.get("whois") or {}
            _domain_name = _whois.get("domain_name") or ""

            hostname = (
                host.get("hostname")    or   # Tier 1: Device hostname
                host.get("address")     or   # Tier 2: External domain address
                _domain_name            or   # Tier 3: WHOIS domain name
                host.get("ip_addr")     or   # Tier 4: Raw IP address
                "Unknown"                    # Last resort
            )

            totals = report.get("totals") or {}
            critical_count = totals.get("critical", 0) or 0
            high_count     = totals.get("high", 0) or 0
            medium_count   = totals.get("medium", 0) or 0
            low_count      = totals.get("low", 0) or 0
            total_count    = critical_count + high_count + medium_count + low_count

            if hostname != "Unknown":
                asset_risk_score.append({
                    "asset_name": hostname,
                    "total":    total_count,
                    "critical": critical_count,
                    "high":     high_count,
                    "medium":   medium_count,
                    "low":      low_count,
                    "score":    report.get("score", 0) or 0
                })

            plugins = report.get("plugins") or []

            for plugin in plugins:
                total_plugins_processed += 1

                plugin_id = plugin.get("id", "") or ""
                if not plugin_id.startswith("CVE-"):
                    continue

                cve_id = plugin_id
                title  = plugin.get("title", "") or ""

                severity_raw = plugin.get("severity", 0)
                try:
                    severity_score = float(severity_raw) if severity_raw else 0.0
                except (ValueError, TypeError):
                    severity_score = 0.0

                unique_cves.add(cve_id)
                cve_asset_ids[cve_id].add(asset_uuid)

                # Keep HIGHEST severity details per CVE
                if cve_id not in cve_details or severity_score > cve_details[cve_id]["severity"]:
                    epss_data  = plugin.get("epss") or {}
                    epss_score = epss_data.get("epss", "") or ""

                    cve_details[cve_id] = {
                        "cve_id":     cve_id,
                        "title":      title[:200],
                        "severity":   severity_score,
                        "cisa_kev":   plugin.get("cisa_kev"),
                        "epss_score": epss_score
                    }

                # Collect Known Exploited (unfiltered)
                cisa_kev = plugin.get("cisa_kev")
                if cisa_kev and cve_id not in known_exploited_set:
                    known_exploited_set.add(cve_id)
                    all_known_exploited.append({
                        "cve_id":     cve_id,
                        "title":      title[:200],
                        "date_added": (cisa_kev.get("dateAdded") or "") if isinstance(cisa_kev, dict) else ""
                    })

        # Sort asset_risk_score by score ascending (lowest score = highest risk first)
        asset_risk_score.sort(key=lambda x: x["score"])

        # 3. CVSS BREAKDOWN
        # Bucket AFTER cve_details is fully built — guarantees each CVE is bucketed
        # by its HIGHEST severity only (no overlaps possible)
        cvss_critical_cves = set()
        cvss_high_cves     = set()
        cvss_medium_cves   = set()
        cvss_low_cves      = set()

        for cve_id, details in cve_details.items():
            sev = details["severity"]
            if sev >= 9.0:
                cvss_critical_cves.add(cve_id)
            elif sev >= 7.0:
                cvss_high_cves.add(cve_id)
            elif sev >= 4.0:
                cvss_medium_cves.add(cve_id)
            else:
                cvss_low_cves.add(cve_id)

        # Sanity check: sum must equal unique CVEs
        cvss_sum = len(cvss_critical_cves) + len(cvss_high_cves) + len(cvss_medium_cves) + len(cvss_low_cves)
        if cvss_sum != len(unique_cves):
            logger.error(f"CVSS breakdown mismatch! Sum={cvss_sum}, Unique CVEs={len(unique_cves)}")

        # 4. APPLY MONTH FILTER (KNOWN EXPLOITED ONLY)
        known_exploited_cves = []
        for kev in all_known_exploited:
            if self._filter_by_month(kev["date_added"], month):
                kev["assets"] = len(cve_asset_ids[kev["cve_id"]])
                known_exploited_cves.append(kev)

        known_exploited_cves.sort(key=lambda x: x["date_added"], reverse=True)

        logger.info(f"Known Exploited: {len(all_known_exploited)} total, {len(known_exploited_cves)} after month filter")

        # 5. EPSS PRIORITIZED (Top 10)
        epss_prioritized = []

        for cve_id in unique_cves:
            details = cve_details[cve_id]
            epss_score_str = details.get("epss_score", "") or ""

            if not epss_score_str:
                continue

            try:
                epss_score = float(epss_score_str)
                epss_pct   = epss_score * 100
                pct_display = f"{int(round(epss_pct))}%" if epss_pct >= 1.0 else "<1%"

                epss_prioritized.append({
                    "cve":             cve_id,
                    "assets":          len(cve_asset_ids[cve_id]),
                    "epss_score":      epss_score,
                    "epss_percentage": pct_display
                })
            except (ValueError, TypeError):
                pass

        def epss_sort_key(cve):
            epss   = cve["epss_score"]
            assets = cve["assets"]
            if epss >= 0.01:
                rounded_pct = round(epss * 100)
                return (-rounded_pct, -assets, -epss)
            else:
                return (-0.005, -assets, -epss)

        epss_prioritized.sort(key=epss_sort_key)
        epss_prioritized_top10 = epss_prioritized[:10]

        logger.info(f"EPSS Prioritized: {len(epss_prioritized)} CVEs with EPSS, returning top 10")

        # 6. CVSS PRIORITIZED (Top 25)
        cvss_prioritized = []

        for cve_id in unique_cves:
            details       = cve_details[cve_id]
            severity_score = details["severity"]

            if severity_score >= 9.0:
                severity_level = "CRITICAL"
            elif severity_score >= 7.0:
                severity_level = "HIGH"
            elif severity_score >= 4.0:
                severity_level = "MEDIUM"
            else:
                severity_level = "LOW"

            cvss_prioritized.append({
                "cve":        cve_id,
                "title":      details["title"],
                "severity":   severity_level,
                "cvss_score": severity_score,
                "assets":     len(cve_asset_ids[cve_id])
            })

        cvss_prioritized.sort(key=lambda x: (-x["cvss_score"], -x["assets"]))
        cvss_prioritized_top25 = cvss_prioritized[:25]

        # LOGGING
        logger.info(f"Processing complete for {customer_name}:")
        logger.info(f"  Valid assets:        {valid_assets}")
        logger.info(f"  Null report assets:  {null_report_count}")
        logger.info(f"  Total assets:        {total_assets}")
        logger.info(f"  Plugins processed:   {total_plugins_processed}")
        logger.info(f"  Unique CVEs:         {len(unique_cves)}")
        logger.info(f"  CVSS Breakdown:      Critical={len(cvss_critical_cves)}, High={len(cvss_high_cves)}, Medium={len(cvss_medium_cves)}, Low={len(cvss_low_cves)}, Sum={cvss_sum}")
        logger.info(f"  Known Exploited:     {len(all_known_exploited)} total, {len(known_exploited_cves)} after filter")

        return {
            "nodeware": {
                "charts": {
                    "summary_metrics": {
                        "average_score": average_score,
                        "assets":        total_assets,
                        "unique_cves":   len(unique_cves)
                    },
                    "cvss_breakdown": {
                        "critical": len(cvss_critical_cves),
                        "high":     len(cvss_high_cves),
                        "medium":   len(cvss_medium_cves),
                        "low":      len(cvss_low_cves)
                    }
                },
                "tables": {
                    "known_exploited_cves": known_exploited_cves,
                    "cvss_prioritized":     cvss_prioritized_top25,
                    "asset_risk_score":     asset_risk_score,
                    "epss_prioritized":     epss_prioritized_top10
                }
            }
        }
