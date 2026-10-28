"""
Frontend JSON Transformer

This module transforms the complex 26,000-line JSON output into a clean,
frontend-optimized JSON structure that matches the PDF report layout.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class FrontendTransformer:

    def _calculate_risk_level(self, score: Optional[float]) -> str:
        """Calculate risk level from numerical score, handling None values."""
        if score is None:
            return "Unknown"
        elif score >= 80:
            return "Critical"
        elif score >= 60:
            return "High"
        elif score >= 40:
            return "Medium"
        elif score > 0:
            return "Low"
        else:
            return "Unknown"
    """Transforms complex security data into frontend-optimized JSON structure."""

    def __init__(self):
        pass

    def transform_to_frontend_json(self, full_data: Dict[str, Any], account_id: int = None, reporting_period: str = None) -> Dict[str, Any]:
        """
        Transform the full security assessment data into frontend-optimized JSON.

        Args:
            full_data: Complete data from SecurityAssessmentOrchestrator
            account_id: Account ID for filtering selected charts (optional)
            reporting_period: Reporting period in "Month Year" format (e.g., "November 2024") (optional)

        Returns:
            Frontend-optimized JSON structure filtered by account's selected charts
        """
        try:
            # Validate input data
            if not isinstance(full_data, dict):
                raise ValueError(f"Expected dict, got {type(full_data)}")

            # Extract basic organization info
            execution_info = full_data.get("execution_info", {})
            organization_id = execution_info.get("organization_id", "unknown")
            organization_name = execution_info.get("organization_name", "Unknown Organization")

            logger.info(f" Transforming data for {organization_name} (ID: {organization_id})")

            # Build frontend-optimized structure with individual error handling
            frontend_json = {}

            try:
                frontend_json["organization"] = self._extract_organization_info(full_data, reporting_period, account_id)
            except Exception as e:
                logger.warning(f"Failed to extract organization info: {e}")
                frontend_json["organization"] = {"id": "unknown", "name": "Unknown Organization"}

            selected_charts = None
            if account_id:
                try:
                    from app.core.database.engine import SessionLocal
                    from app.core.database.rpc import rpc_get_account_charts
                    _db = SessionLocal()
                    try:
                        charts_data = rpc_get_account_charts(_db, account_id)
                    finally:
                        _db.close()

                    if charts_data:
                        selected_charts = {}
                        for chart in charts_data:
                            integration_key = chart.get('integration_key')
                            chart_key = chart.get('chart_key')
                            json_path = chart.get('json_path')

                            if integration_key not in selected_charts:
                                selected_charts[integration_key] = []
                            selected_charts[integration_key].append({
                                'chart_key': chart_key,
                                'json_path': json_path
                            })

                        logger.info(f"Loaded {len(charts_data)} selected charts for account {account_id}")
                        logger.info(f"Selected charts by platform: {dict((k, len(v)) for k, v in selected_charts.items())}")
                    else:
                        logger.warning(f"No selected charts found for account {account_id} - returning all charts")
                except Exception as e:
                    logger.error(f"Failed to load selected charts for account {account_id}: {e}")
                    logger.warning("Falling back to returning all charts")

            def is_chart_selected(platform_key, chart_key):
                if not selected_charts:
                    return True
                if platform_key not in selected_charts:
                    return False
                return any(c['chart_key'] == chart_key for c in selected_charts[platform_key])

            try:
                charts_data = self._extract_chart_data(full_data)
                table_data = self._extract_table_data(full_data)

                tickets_by_contact_data = table_data.get("tickets_by_contact", [])
                contacts_summary = None
                contacts_list = []
                for item in tickets_by_contact_data:
                    if isinstance(item, dict) and "contacts_summary" in item:
                        contacts_summary = item["contacts_summary"]
                    else:
                        contacts_list.append(item)

                if is_chart_selected('ninjaone', 'patch_management_enablement') and "patch_management_enablement" in charts_data:
                    if "NinjaOne" not in frontend_json:
                        frontend_json["NinjaOne"] = {"charts": {}, "tables": {}}
                    frontend_json["NinjaOne"]["charts"]["patch_management_enablement"] = charts_data["patch_management_enablement"]

                if is_chart_selected('ninjaone', 'patch_status_distribution') and "patch_status_distribution" in charts_data:
                    if "NinjaOne" not in frontend_json:
                        frontend_json["NinjaOne"] = {"charts": {}, "tables": {}}
                    frontend_json["NinjaOne"]["charts"]["patch_status_distribution"] = charts_data["patch_status_distribution"]

                if is_chart_selected('ninjaone', 'patch_management'):
                    if "NinjaOne" not in frontend_json:
                        frontend_json["NinjaOne"] = {"charts": {}, "tables": {}}
                    frontend_json["NinjaOne"]["charts"]["patch_management"] = table_data.get("patch_management", {
                        "os_patches": {"summary": {"total": 0, "successful": 0, "failed": 0, "success_rate": 0.0}, "failed_devices": []},
                        "third_party_patches": {"summary": {"total": 0, "successful": 0, "failed": 0, "success_rate": 0.0}, "failed_devices": []}
                    })

                if is_chart_selected('ninjaone', 'devices_with_failed_patches'):
                    if "NinjaOne" not in frontend_json:
                        frontend_json["NinjaOne"] = {"charts": {}, "tables": {}}
                    frontend_json["NinjaOne"]["charts"]["devices_with_failed_patches"] = table_data.get("devices_with_failed_patches", {
                        "count": 0, "devices": [], "message": "No devices with failed patches"
                    })

                if is_chart_selected('ninjaone', 'agent_type_distribution') and "agent_type_distribution" in charts_data:
                    if "NinjaOne" not in frontend_json:
                        frontend_json["NinjaOne"] = {"charts": {}, "tables": {}}
                    frontend_json["NinjaOne"]["charts"]["agent_type_distribution"] = charts_data["agent_type_distribution"]

                if is_chart_selected('ninjaone', 'device_inventory'):
                    if "NinjaOne" not in frontend_json:
                        frontend_json["NinjaOne"] = {"charts": {}, "tables": {}}
                    if "tables" not in frontend_json["NinjaOne"]:
                        frontend_json["NinjaOne"]["tables"] = {}
                    frontend_json["NinjaOne"]["tables"]["device_inventory"] = table_data.get("device_inventory", [])

                if is_chart_selected('ninjaone', 'device_inventory_server'):
                    if "NinjaOne" not in frontend_json:
                        frontend_json["NinjaOne"] = {"charts": {}, "tables": {}}
                    if "tables" not in frontend_json["NinjaOne"]:
                        frontend_json["NinjaOne"]["tables"] = {}
                    frontend_json["NinjaOne"]["tables"]["device_inventory_server"] = table_data.get("device_inventory_server", [])

                # Only add Autotask charts if autotask_metrics exists in full_data
                if "autotask_metrics" in full_data:
                    if is_chart_selected('autotask', 'daily_tickets_trend') and "daily_tickets_trend" in charts_data:
                        if "Autotask" not in frontend_json:
                            frontend_json["Autotask"] = {"charts": {}}
                        frontend_json["Autotask"]["charts"]["daily_tickets_trend"] = charts_data["daily_tickets_trend"]

                    if is_chart_selected('autotask', 'monthly_tickets_by_type') and "monthly_tickets_by_type" in charts_data:
                        if "Autotask" not in frontend_json:
                            frontend_json["Autotask"] = {"charts": {}}
                        frontend_json["Autotask"]["charts"]["monthly_tickets_by_type"] = charts_data["monthly_tickets_by_type"]

                    if is_chart_selected('autotask', 'open_tickets_by_issue_type') and "open_tickets_by_issue_type" in charts_data:
                        if "Autotask" not in frontend_json:
                            frontend_json["Autotask"] = {"charts": {}}
                        frontend_json["Autotask"]["charts"]["open_tickets_by_issue_type"] = charts_data["open_tickets_by_issue_type"]

                    if is_chart_selected('autotask', 'open_ticket_priority_distribution') and "open_ticket_priority_distribution" in charts_data:
                        if "Autotask" not in frontend_json:
                            frontend_json["Autotask"] = {"charts": {}}
                        frontend_json["Autotask"]["charts"]["open_ticket_priority_distribution"] = charts_data["open_ticket_priority_distribution"]

                    if is_chart_selected('autotask', 'sla_performance') and "sla_performance" in charts_data:
                        if "Autotask" not in frontend_json:
                            frontend_json["Autotask"] = {"charts": {}}
                        frontend_json["Autotask"]["charts"]["sla_performance"] = charts_data["sla_performance"]

                    if is_chart_selected('autotask', 'tickets_by_contact'):
                        if "Autotask" not in frontend_json:
                            frontend_json["Autotask"] = {"charts": {}}
                        frontend_json["Autotask"]["charts"]["tickets_by_contact"] = {
                            "tickets_by_contact_summary": {
                                "contacts_summary": contacts_summary if contacts_summary else {
                                    "contacts_count": 0,
                                    "total_tickets": 0,
                                    "top_contact": "Unknown"
                                }
                            },
                            "data": contacts_list
                        }

                # Only add ConnectSecure charts if connectsecure_metrics exists in full_data
                if "connectsecure_metrics" in full_data:
                    if is_chart_selected('connectsecure', 'asset_type_distribution') and "asset_type_distribution" in charts_data:
                        if "ConnectSecure" not in frontend_json:
                            frontend_json["ConnectSecure"] = {"charts": {}}
                        frontend_json["ConnectSecure"]["charts"]["asset_type_distribution"] = charts_data["asset_type_distribution"]

                    if is_chart_selected('connectsecure', 'operating_system_distribution') and "operating_system_distribution" in charts_data:
                        if "ConnectSecure" not in frontend_json:
                            frontend_json["ConnectSecure"] = {"charts": {}}
                        frontend_json["ConnectSecure"]["charts"]["operating_system_distribution"] = charts_data["operating_system_distribution"]

                    if is_chart_selected('connectsecure', 'security_risk_score') and "security_risk_score" in charts_data:
                        if "ConnectSecure" not in frontend_json:
                            frontend_json["ConnectSecure"] = {"charts": {}}
                        frontend_json["ConnectSecure"]["charts"]["security_risk_score"] = charts_data["security_risk_score"]

                    if is_chart_selected('connectsecure', 'vulnerability_severity') and "vulnerability_severity" in charts_data:
                        if "ConnectSecure" not in frontend_json:
                            frontend_json["ConnectSecure"] = {"charts": {}}
                        frontend_json["ConnectSecure"]["charts"]["vulnerability_severity"] = charts_data["vulnerability_severity"]

                    if is_chart_selected('connectsecure', 'agent_type_distribution') and "agent_type_distribution" in charts_data:
                        if "ConnectSecure" not in frontend_json:
                            frontend_json["ConnectSecure"] = {"charts": {}}
                        frontend_json["ConnectSecure"]["charts"]["agent_type_distribution"] = charts_data["agent_type_distribution"]

                # Bitdefender charts
                bitdefender_metrics = full_data.get("bitdefender_metrics", {})
                if bitdefender_metrics:
                    bd_charts = bitdefender_metrics.get("charts", {})
                    bd_tables = bitdefender_metrics.get("tables", {})

                    # Chart 1: Risk Score
                    if is_chart_selected('bitdefender', 'riskScore_bitdefender') and "riskScore_bitdefender" in bd_charts:
                        if "Bitdefender" not in frontend_json:
                            frontend_json["Bitdefender"] = {"charts": {}, "tables": {}}
                        frontend_json["Bitdefender"]["charts"]["riskScore_bitdefender"] = bd_charts["riskScore_bitdefender"]

                    # Chart 3: Inventory Summary
                    if is_chart_selected('bitdefender', 'inventory_summary_bitdefender') and "inventory_summary_bitdefender" in bd_charts:
                        if "Bitdefender" not in frontend_json:
                            frontend_json["Bitdefender"] = {"charts": {}, "tables": {}}
                        frontend_json["Bitdefender"]["charts"]["inventory_summary_bitdefender"] = bd_charts["inventory_summary_bitdefender"]

                    # Table 1: Network Inventory
                    if is_chart_selected('bitdefender', 'networkinventory_bitdefender') and "networkinventory_bitdefender" in bd_tables:
                        if "Bitdefender" not in frontend_json:
                            frontend_json["Bitdefender"] = {"charts": {}, "tables": {}}
                        frontend_json["Bitdefender"]["tables"]["networkinventory_bitdefender"] = bd_tables["networkinventory_bitdefender"]

                # LoyaltyLoop charts -- separate NPS and loyalty score charts
                loyaltyloop_metrics = full_data.get("loyaltyloop_metrics", {})
                if loyaltyloop_metrics:
                    ll_charts = loyaltyloop_metrics.get("charts", {})

                    if is_chart_selected('loyaltyloop', 'nps_score') and "nps_score" in ll_charts:
                        if "LoyaltyLoop" not in frontend_json:
                            frontend_json["LoyaltyLoop"] = {"charts": {}}
                        frontend_json["LoyaltyLoop"]["charts"]["nps_score"] = ll_charts["nps_score"]

                    if is_chart_selected('loyaltyloop', 'loyalty_score') and "loyalty_score" in ll_charts:
                        if "LoyaltyLoop" not in frontend_json:
                            frontend_json["LoyaltyLoop"] = {"charts": {}}
                        frontend_json["LoyaltyLoop"]["charts"]["loyalty_score"] = ll_charts["loyalty_score"]

                # Infima charts + table -- training rates rollup, per-user dark web exposures
                infima_metrics = full_data.get("infima_metrics", {})
                if infima_metrics:
                    infima_charts = infima_metrics.get("charts", {})
                    infima_tables = infima_metrics.get("tables", {})

                    if is_chart_selected('infima', 'training_rates') and "training_rates" in infima_charts:
                        if "Infima" not in frontend_json:
                            frontend_json["Infima"] = {"charts": {}, "tables": {}}
                        frontend_json["Infima"]["charts"]["training_rates"] = infima_charts["training_rates"]

                    if is_chart_selected('infima', 'darkweb_exposures') and "darkweb_exposures" in infima_tables:
                        if "Infima" not in frontend_json:
                            frontend_json["Infima"] = {"charts": {}, "tables": {}}
                        frontend_json["Infima"]["tables"]["darkweb_exposures"] = infima_tables["darkweb_exposures"]

                # Cove charts
                cove_metrics = full_data.get("cove_metrics", {})
                if cove_metrics:
                    # Chart 1: Total Devices & Storage Summary
                    if is_chart_selected('cove', 'total_devices_storage_summary_cove'):
                        if "Cove" not in frontend_json:
                            frontend_json["Cove"] = {"charts": {}}
                        frontend_json["Cove"]["charts"]["total_devices_storage_summary_cove"] = {
                            "totalDevices": cove_metrics.get("device_count", 0) or 0,
                            "used_storage": cove_metrics.get("total_storage_used", 0.0) or 0.0,
                            "user_mailboxes": cove_metrics.get("user_mailboxes", 0) or 0,
                            "shared_mailboxes": cove_metrics.get("shared_mailboxes", 0) or 0,
                            "onedrive_user_accounts": cove_metrics.get("onedrive_user_accounts", 0) or 0
                        }

                    # Chart 2: Asset Type Distribution (Physical/Virtual)
                    if is_chart_selected('cove', 'asset_type_distribution_cove'):
                        if "Cove" not in frontend_json:
                            frontend_json["Cove"] = {"charts": {}}
                        asset_dist = cove_metrics.get("asset_distribution", {})
                        frontend_json["Cove"]["charts"]["asset_type_distribution_cove"] = {
                            "physical": asset_dist.get("Physical", 0) or 0,
                            "virtual": asset_dist.get("Virtual", 0) or 0,
                            "others": asset_dist.get("Undefined", 0) or 0
                        }

                    # Chart 3: Devices Distribution (Workstation/Server)
                    if is_chart_selected('cove', 'devices_distribution_cove'):
                        if "Cove" not in frontend_json:
                            frontend_json["Cove"] = {"charts": {}}
                        device_dist = cove_metrics.get("device_distribution", {})
                        frontend_json["Cove"]["charts"]["devices_distribution_cove"] = {
                            "workstations": device_dist.get("Workstation", 0) or 0,
                            "servers": device_dist.get("Server", 0) or 0,
                            "others": device_dist.get("Undefined", 0) or 0
                        }

                    # Chart 4: Retention Policy Distribution
                    if is_chart_selected('cove', 'retention_policy_distribution_cove'):
                        if "Cove" not in frontend_json:
                            frontend_json["Cove"] = {"charts": {}}
                        retention_dist = cove_metrics.get("retention_policy_distribution", {})
                        # Ensure all values are integers and handle None/empty
                        cleaned_retention = {}
                        for policy, count in retention_dist.items():
                            if policy:  # Skip empty/None keys
                                cleaned_retention[policy] = count or 0
                        frontend_json["Cove"]["charts"]["retention_policy_distribution_cove"] = cleaned_retention or {}

                    # cove_insights — always included when Cove data is present
                    if "Cove" not in frontend_json:
                        frontend_json["Cove"] = {"charts": {}}
                    frontend_json["Cove"]["cove_insights"] = full_data.get("cove_insights") or {}

                    # tables — inventory table (added; existing charts/insights logic untouched)
                    cove_tables = full_data.get("cove_tables") or {}
                    frontend_json["Cove"]["tables"] = {
                        "inventory_cove": cove_tables.get("inventory_cove", [])
                    }

                # SentinelOne charts (11 charts, no tables)
                sentinelone_metrics = full_data.get("sentinelone_metrics", {})
                if sentinelone_metrics:
                    s1_charts = sentinelone_metrics.get("charts", {})

                    s1_chart_keys = [
                        "secured_devices_by_domain", "secured_devices_by_role",
                        "secured_devices_by_os", "infected_endpoints",
                        "agent_version_coverage", "endpoint_connection_status",
                        "severity_levels_threats", "incident_status",
                        "analyst_verdicts_threats", "threats_by_detection_engine",
                        "threats_by_type"
                    ]

                    for chart_key in s1_chart_keys:
                        if is_chart_selected('sentinelone', chart_key) and chart_key in s1_charts:
                            if "SentinelOne" not in frontend_json:
                                frontend_json["SentinelOne"] = {"charts": {}}
                            frontend_json["SentinelOne"]["charts"][chart_key] = s1_charts[chart_key]

                # NodeWare charts (2 charts, 4 tables)
                nodeware_metrics = full_data.get("nodeware_metrics", {})
                if nodeware_metrics:
                    nw_charts = nodeware_metrics.get("charts", {})
                    nw_tables = nodeware_metrics.get("tables", {})

                    nw_chart_keys = ["summary_metrics", "cvss_breakdown"]
                    for chart_key in nw_chart_keys:
                        if is_chart_selected('nodeware', chart_key) and chart_key in nw_charts:
                            if "NodeWare" not in frontend_json:
                                frontend_json["NodeWare"] = {"charts": {}, "tables": {}}
                            frontend_json["NodeWare"]["charts"][chart_key] = nw_charts[chart_key]

                    nw_table_keys = ["known_exploited_cves", "cvss_prioritized", "asset_risk_score", "epss_prioritized"]
                    for table_key in nw_table_keys:
                        if is_chart_selected('nodeware', table_key) and table_key in nw_tables:
                            if "NodeWare" not in frontend_json:
                                frontend_json["NodeWare"] = {"charts": {}, "tables": {}}
                            frontend_json["NodeWare"]["tables"][table_key] = nw_tables[table_key]

                # DNSFilter charts
                dnsfilter_metrics = full_data.get("dnsfilter_metrics", {})
                if dnsfilter_metrics:
                    if "DNSFilter" not in frontend_json:
                        frontend_json["DNSFilter"] = {"charts": {}}
                        
                    dns_charts = dnsfilter_metrics.get("charts", {})

                    # 1. Map Request Counts (Root Level)
                    if is_chart_selected('dnsfilter', 'request_counts') and 'request_counts' in dns_charts:
                        frontend_json["DNSFilter"]["charts"]["request_counts"] = dns_charts["request_counts"]

                    # 2. Map Quarterly Data (Nested Object)
                    quarterly_data = dns_charts.get("Quaterly_data", {})
                    if quarterly_data:
                        filtered_quarterly = {}
                        for chart_key in ["threats_over_months", "allowed_vs_blocked_request_quarterly", "allowed_vs_blocked_threats_quarterly"]:
                            # Bypassing DB check for these new quarterly charts
                            if chart_key in quarterly_data:
                                filtered_quarterly[chart_key] = quarterly_data[chart_key]
                        
                        if filtered_quarterly:
                            frontend_json["DNSFilter"]["charts"]["Quaterly_data"] = filtered_quarterly

                    # 3. Map Monthly Data (Nested Object)
                    monthly_data = dns_charts.get("Monthly_data", {})
                    if monthly_data:
                        filtered_monthly = {}
                        for chart_key in ["allowed_vs_blocked_request", "threats_over_time", "allowed_vs_blocked_threats"]:
                            if is_chart_selected('dnsfilter', chart_key) and chart_key in monthly_data:
                                filtered_monthly[chart_key] = monthly_data[chart_key]
                        
                        if filtered_monthly:
                            frontend_json["DNSFilter"]["charts"]["Monthly_data"] = filtered_monthly

                # Dropsuite charts
                dropsuite_metrics = full_data.get("dropsuite_metrics", {})
                if dropsuite_metrics:
                    ds_charts = dropsuite_metrics.get("charts", {})
                    ds_chart_keys = [
                        "mailbox_backup_status_distribution",
                        "onedrive_backup_storage_overview",
                        "onedrive_backup_status_distribution",
                        "sharepoint_storage_and_capacity_overview",
                        "google_drive_storage_and_capacity_overview",
                        "shared_drive_storage_and_capacity_overview",
                    ]
                    for chart_key in ds_chart_keys:
                        if is_chart_selected('dropsuite', chart_key) and chart_key in ds_charts:
                            if "Dropsuite" not in frontend_json:
                                frontend_json["Dropsuite"] = {"charts": {}}
                            frontend_json["Dropsuite"]["charts"][chart_key] = ds_charts[chart_key]

                # --- Blackpoint Metrics ---
                if "blackpoint_metrics" in full_data:
                    bp_metrics = full_data["blackpoint_metrics"]
                    if "Blackpoint" not in frontend_json:
                        frontend_json["Blackpoint"] = {"charts": {}, "tables": {}}

                    bp_charts = bp_metrics.get("charts", {})

                    # 1. Map Monthly Data (Look for underscore key matching your processor)
                    monthly_data = bp_charts.get("monthly_data", {})  # <-- Changed - to _
                    if monthly_data:
                        filtered_monthly = {}
                        if is_chart_selected('blackpoint', 'monthly_endpoint_alerts') and 'monthly_endpoint_alerts' in monthly_data:
                            filtered_monthly['monthly_endpoint_alerts'] = monthly_data['monthly_endpoint_alerts']
                        if is_chart_selected('blackpoint', 'monthly_cloud_alerts') and 'monthly_cloud_alerts' in monthly_data:
                            filtered_monthly['monthly_cloud_alerts'] = monthly_data['monthly_cloud_alerts']
                            
                        if filtered_monthly:
                            frontend_json["Blackpoint"]["charts"]["monthly_data"] = filtered_monthly  

                    # 2. Map Quarterly Data (Look for underscore key matching your processor)
                    quarterly_data = bp_charts.get("Quaterly_data", {})  # <-- Changed - to _
                    if quarterly_data:
                        frontend_json["Blackpoint"]["charts"]["Quaterly_data"] = quarterly_data

                    # 3. Map Tables
                    bp_tables = bp_metrics.get("tables", {})
                    if is_chart_selected("blackpoint", "soc_escalations_activity") and "soc_escalations_activity" in bp_tables:
                        frontend_json["Blackpoint"]["tables"]["soc_escalations_activity"] = bp_tables["soc_escalations_activity"]
                    if not frontend_json["Blackpoint"].get("tables"):
                        frontend_json["Blackpoint"].pop("tables", None)

                # --- Axcient Metrics ---
                if "axcient_metrics" in full_data:
                    ax_metrics = full_data["axcient_metrics"]
                    if "Axcient" not in frontend_json:
                        frontend_json["Axcient"] = {"charts": {}, "tables": {}}

                    ax_charts = ax_metrics.get("charts", {})
                    ax_tables = ax_metrics.get("tables", {})

                    # Process all Axcient charts
                    ax_chart_keys = [
                        "account_protection_coverage",
                        "protected_accounts_by_status",
                        "license_optimization_overview",
                        "user_backup_execution_health",
                        "sharepoint_backup_execution_health",
                        "monthly_backup_trend"
                    ]
                    
                    for chart_key in ax_chart_keys:
                        if is_chart_selected('axcient', chart_key) and chart_key in ax_charts:
                            frontend_json["Axcient"]["charts"][chart_key] = ax_charts[chart_key]

                    # Process Axcient tables
                    if is_chart_selected('axcient', 'backup_alerts') and "backup_alerts" in ax_tables:
                        frontend_json["Axcient"]["tables"]["backup_alerts"] = ax_tables["backup_alerts"]

                    if is_chart_selected('axcient', 'active_backup_services') and "active_backup_services" in ax_tables:
                        frontend_json["Axcient"]["tables"]["active_backup_services"] = ax_tables["active_backup_services"]

                    # Cleanup empty tables object if none selected/present
                    if not frontend_json["Axcient"].get("tables"):
                        frontend_json["Axcient"].pop("tables", None)

            except Exception as e:
                logger.warning(f"Failed to extract chart/table data: {e}")
                # Fallback structure
                frontend_json["NinjaOne"] = {
                    "charts": {
                        "patch_management_enablement": {"enabled": 0, "disabled": 0},
                        "patch_status_distribution": {"installed": 0, "approved": 0, "failed": 0, "pending": 0},
                        "patch_management": {
                            "os_patches": {"summary": {"total": 0, "successful": 0, "failed": 0, "success_rate": 0.0}, "failed_devices": []},
                            "third_party_patches": {"summary": {"total": 0, "successful": 0, "failed": 0, "success_rate": 0.0}, "failed_devices": []}
                        },
                        "devices_with_failed_patches": {"count": 0, "devices": [], "message": "No devices with failed patches"}
                    },
                    "tables": {
                        "device_inventory": [],
                        "device_inventory_server": []
                    }
                }
                frontend_json["Autotask"] = {
                    "charts": {
                        "daily_tickets_trend": {},
                        "monthly_tickets_by_type": {},
                        "open_tickets_by_issue_type": [],
                        "open_ticket_priority_distribution": {},
                        "sla_performance": {},
                        "tickets_by_contact": {
                            "tickets_by_contact_summary": {"contacts_summary": {"contacts_count": 0, "total_tickets": 0, "top_contact": "Unknown"}},
                            "data": []
                        }
                    }
                }
                frontend_json["ConnectSecure"] = {
                    "charts": {
                        "asset_type_distribution": {"live_count": {"discovered": 0, "other_asset": 0, "unknown": 0}, "monthly_count": {"discovered": 0, "other_asset": 0, "unknown": 0}, "quarterly_count": {"discovered": 0, "other_asset": 0, "unknown": 0}},
                        "operating_system_distribution": {"live_count": {"Others": 0}, "monthly_count": {"Others": 0}, "quarterly_count": {"Others": 0}},
                        "security_risk_score": {"live_count": None, "monthly_count": None, "quarterly_count": None},
                        "vulnerability_severity": {"live_count": {"critical": 0, "high": 0, "medium": 0, "low": 0}, "monthly_count": {"critical": 0, "high": 0, "medium": 0, "low": 0}},
                        "agent_type_distribution": {}
                    }
                }
                frontend_json["Bitdefender"] = {
                    "charts": {
                        "riskScore_bitdefender": {
                            "value": "0",
                            "impact": "0",
                            "misconfigurations": "0",
                            "appVulnerabilities": "0",
                            "humanRisks": "0",
                            "industryModifier": "0"
                        },
                        "inventory_summary_bitdefender": {
                            "summary": {
                                "windowsWorkstations": 0,
                                "windowsServers": 0,
                                "macOS": 0,
                                "linux": 0
                            },
                            "count": {
                                "managedEndpoints": 0,
                                "physicalMachines": 0,
                                "virtualMachines": 0
                            }
                        }
                    },
                    "tables": {
                        "networkinventory_bitdefender": []
                    }
                }
                frontend_json["LoyaltyLoop"] = {
                    "charts": {
                        "nps_score": 0,
                        "loyalty_score": 0
                    }
                }
                frontend_json["Infima"] = {
                    "charts": {
                        "training_rates": {
                            "phishing_click_rate_total": 0,
                            "training_on_track_rate": 0
                        }
                    },
                    "tables": {
                        "darkweb_exposures": []
                    }
                }
                frontend_json["Cove"] = {
                    "charts": {
                        "total_devices_storage_summary_cove": {
                            "totalDevices": 0,
                            "used_storage": 0.0,
                            "user_mailboxes": 0,
                            "shared_mailboxes": 0,
                            "onedrive_user_accounts": 0
                        },
                        "asset_type_distribution_cove": {
                            "physical": 0,
                            "virtual": 0,
                            "others": 0
                        },
                        "devices_distribution_cove": {
                            "workstations": 0,
                            "servers": 0,
                            "others": 0
                        },
                        "retention_policy_distribution_cove": {}
                    },
                    "cove_insights": {},
                    "tables": {
                        "inventory_cove": []
                    }
                }
                frontend_json["SentinelOne"] = {
                    "charts": {
                        "secured_devices_by_domain": {},
                        "secured_devices_by_role": {},
                        "secured_devices_by_os": {},
                        "infected_endpoints": {"healthy": 0, "infected": 0},
                        "agent_version_coverage": {},
                        "endpoint_connection_status": {"connected": 0, "disconnected": 0, "connecting": 0, "disconnecting": 0},
                        "severity_levels_threats": {},
                        "incident_status": {"resolved": 0, "unresolved": 0, "in_progress": 0},
                        "analyst_verdicts_threats": {"false_positive": 0, "true_positive": 0, "suspicious": 0, "undefined": 0},
                        "threats_by_detection_engine": {},
                        "threats_by_type": {}
                    }
                }
                frontend_json["NodeWare"] = {
                    "charts": {
                        "summary_metrics": {"average_score": 0, "assets": 0, "unique_cves": 0},
                        "cvss_breakdown": {"critical": 0, "high": 0, "medium": 0, "low": 0, "unique_cves": 0}
                    },
                    "tables": {
                        "known_exploited_cves": [],
                        "cvss_prioritized": [],
                        "asset_risk_score": [],
                        "epss_prioritized": []
                    }
                }
                frontend_json["DNSFilter"] = {
                    "charts": {
                        "request_counts": {"total_threats_count": 0, "total_blocked_requests": 0},
                        "Quaterly_data": {},
                        "Monthly_data": {}
                    }
                }
                frontend_json["Dropsuite"] = {
                    "charts": {
                        "mailbox_backup_status_distribution": {"Completed": 0},
                        "onedrive_backup_storage_overview": {"total_accounts": 0, "total_storage": "0.00 GB", "activated": 0, "deactivated": 0},
                        "onedrive_backup_status_distribution": {"Completed": 0},
                        "sharepoint_storage_and_capacity_overview": {"domain_count": 0, "total_site_count": 0, "total_file_count": 0, "total_storage": "0.00 GB"},
                        "google_drive_storage_and_capacity_overview": {"drive_count": 0, "total_file_count": 0, "total_storage": "0.00 GB"},
                        "shared_drive_storage_and_capacity_overview": {"domain_count": 0, "total_file_count": 0, "total_storage": "0.00 GB"},
                    }
                }
                frontend_json["Blackpoint"] = {
                    "charts": {
                        "Quaterly_data": {},
                        "monthly_data": {}
                    },
                    "tables": {
                        "soc_escalations_activity": []
                    }
                }

                frontend_json["Axcient"] = {
                    "charts": {
                        "account_protection_coverage": {"total_users": 0, "protected_users": 0, "unprotected_users": 0},
                        "protected_users_by_system_status": {"total_users": 0, "active": 0, "deleted": 0, "inactive": 0},
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
                    },
                    "tables": {
                        "backup_alerts": [],
                        "active_backup_services": []
                    }
                }

            try:
                frontend_json["execution_info"] = self._extract_execution_info(full_data)
            except Exception as e:
                logger.warning(f"Failed to extract execution info: {e}")
                frontend_json["execution_info"] = {"generated_at": datetime.now().isoformat()}

            logger.info(f" Frontend JSON generated for {organization_name}")
            return frontend_json

        except Exception as e:
            logger.error(f"Failed to transform data to frontend JSON: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return self._create_error_response(str(e))

    def transform_single_platform(self, platform_name: str, platform_raw_data: Dict[str, Any],
                                  account_id: int = None) -> Dict[str, Any]:
        """
        Transform a single platform's raw processed data into frontend-optimized JSON.
        Used by the streaming endpoint to transform each platform independently.

        Args:
            platform_name: Platform key from orchestrator (e.g., "NinjaOne", "Autotask")
            platform_raw_data: The processed data dict from the orchestrator for this platform
            account_id: Account ID for filtering selected charts (optional)

        Returns:
            Dict with the platform's frontend JSON, e.g. {"NinjaOne": {"charts": {...}, "tables": {...}}}
        """
        try:
            # Load selected charts filter if account_id provided
            selected_charts = None
            if account_id:
                try:
                    from app.core.database.engine import SessionLocal
                    from app.core.database.rpc import rpc_get_account_charts
                    _db = SessionLocal()
                    try:
                        charts_data = rpc_get_account_charts(_db, account_id)
                    finally:
                        _db.close()

                    if charts_data:
                        selected_charts = {}
                        for chart in charts_data:
                            integration_key = chart.get('integration_key')
                            chart_key = chart.get('chart_key')
                            if integration_key not in selected_charts:
                                selected_charts[integration_key] = []
                            selected_charts[integration_key].append({'chart_key': chart_key})
                except Exception as e:
                    logger.error(f"Failed to load selected charts: {e}")

            def is_chart_selected(platform_key, chart_key):
                if not selected_charts:
                    return True
                if platform_key not in selected_charts:
                    return False
                return any(c['chart_key'] == chart_key for c in selected_charts[platform_key])

            frontend_json = {}

            # Build a temporary full_data dict so existing _extract methods work
            full_data = {}
            full_data.update(platform_raw_data)

            try:
                charts_data = self._extract_chart_data(full_data)
            except Exception as e:
                logger.error(f"Failed to extract chart data for {platform_name}: {e}")
                charts_data = {}

            try:
                table_data = self._extract_table_data(full_data)
            except Exception as e:
                logger.error(f"Failed to extract table data for {platform_name}: {e}")
                table_data = {}

            # --- NinjaOne ---
            if platform_name == "NinjaOne":
                ninja = {"charts": {}, "tables": {}}

                if is_chart_selected('ninjaone', 'patch_management_enablement') and "patch_management_enablement" in charts_data:
                    ninja["charts"]["patch_management_enablement"] = charts_data["patch_management_enablement"]
                if is_chart_selected('ninjaone', 'patch_status_distribution') and "patch_status_distribution" in charts_data:
                    ninja["charts"]["patch_status_distribution"] = charts_data["patch_status_distribution"]
                if is_chart_selected('ninjaone', 'patch_management'):
                    ninja["charts"]["patch_management"] = table_data.get("patch_management", {
                        "os_patches": {"summary": {"total": 0, "successful": 0, "failed": 0, "success_rate": 0.0}, "failed_devices": []},
                        "third_party_patches": {"summary": {"total": 0, "successful": 0, "failed": 0, "success_rate": 0.0}, "failed_devices": []}
                    })
                if is_chart_selected('ninjaone', 'devices_with_failed_patches'):
                    ninja["charts"]["devices_with_failed_patches"] = table_data.get("devices_with_failed_patches", {
                        "count": 0, "devices": [], "message": "No devices with failed patches"
                    })
                if is_chart_selected('ninjaone', 'agent_type_distribution') and "agent_type_distribution" in charts_data:
                    ninja["charts"]["agent_type_distribution"] = charts_data["agent_type_distribution"]
                if is_chart_selected('ninjaone', 'device_inventory'):
                    ninja["tables"]["device_inventory"] = table_data.get("device_inventory", [])
                if is_chart_selected('ninjaone', 'device_inventory_server'):
                    ninja["tables"]["device_inventory_server"] = table_data.get("device_inventory_server", [])

                frontend_json["NinjaOne"] = ninja

            # --- Autotask ---
            elif platform_name == "Autotask" and "autotask_metrics" in full_data:
                at = {"charts": {}}

                tickets_by_contact_data = table_data.get("tickets_by_contact", [])
                contacts_summary = None
                contacts_list = []
                for item in tickets_by_contact_data:
                    if isinstance(item, dict) and "contacts_summary" in item:
                        contacts_summary = item["contacts_summary"]
                    else:
                        contacts_list.append(item)

                if is_chart_selected('autotask', 'daily_tickets_trend') and "daily_tickets_trend" in charts_data:
                    at["charts"]["daily_tickets_trend"] = charts_data["daily_tickets_trend"]
                if is_chart_selected('autotask', 'monthly_tickets_by_type') and "monthly_tickets_by_type" in charts_data:
                    at["charts"]["monthly_tickets_by_type"] = charts_data["monthly_tickets_by_type"]
                if is_chart_selected('autotask', 'open_tickets_by_issue_type') and "open_tickets_by_issue_type" in charts_data:
                    at["charts"]["open_tickets_by_issue_type"] = charts_data["open_tickets_by_issue_type"]
                if is_chart_selected('autotask', 'open_ticket_priority_distribution') and "open_ticket_priority_distribution" in charts_data:
                    at["charts"]["open_ticket_priority_distribution"] = charts_data["open_ticket_priority_distribution"]
                if is_chart_selected('autotask', 'sla_performance') and "sla_performance" in charts_data:
                    at["charts"]["sla_performance"] = charts_data["sla_performance"]
                if is_chart_selected('autotask', 'tickets_by_contact'):
                    at["charts"]["tickets_by_contact"] = {
                        "tickets_by_contact_summary": {
                            "contacts_summary": contacts_summary if contacts_summary else {
                                "contacts_count": 0, "total_tickets": 0, "top_contact": "Unknown"
                            }
                        },
                        "data": contacts_list
                    }

                frontend_json["Autotask"] = at

            # --- ConnectSecure ---
            elif platform_name == "ConnectSecure" and "connectsecure_metrics" in full_data:
                cs = {"charts": {}}

                if is_chart_selected('connectsecure', 'asset_type_distribution') and "asset_type_distribution" in charts_data:
                    cs["charts"]["asset_type_distribution"] = charts_data["asset_type_distribution"]
                if is_chart_selected('connectsecure', 'operating_system_distribution') and "operating_system_distribution" in charts_data:
                    cs["charts"]["operating_system_distribution"] = charts_data["operating_system_distribution"]
                if is_chart_selected('connectsecure', 'security_risk_score') and "security_risk_score" in charts_data:
                    cs["charts"]["security_risk_score"] = charts_data["security_risk_score"]
                if is_chart_selected('connectsecure', 'vulnerability_severity') and "vulnerability_severity" in charts_data:
                    cs["charts"]["vulnerability_severity"] = charts_data["vulnerability_severity"]
                if is_chart_selected('connectsecure', 'agent_type_distribution') and "agent_type_distribution" in charts_data:
                    cs["charts"]["agent_type_distribution"] = charts_data["agent_type_distribution"]

                frontend_json["ConnectSecure"] = cs

            # --- Bitdefender ---
            elif platform_name == "Bitdefender":
                bitdefender_metrics = full_data.get("bitdefender_metrics", {})
                if bitdefender_metrics:
                    bd = {"charts": {}, "tables": {}}
                    bd_charts = bitdefender_metrics.get("charts", {})
                    bd_tables = bitdefender_metrics.get("tables", {})

                    if is_chart_selected('bitdefender', 'riskScore_bitdefender') and "riskScore_bitdefender" in bd_charts:
                        bd["charts"]["riskScore_bitdefender"] = bd_charts["riskScore_bitdefender"]
                    if is_chart_selected('bitdefender', 'inventory_summary_bitdefender') and "inventory_summary_bitdefender" in bd_charts:
                        bd["charts"]["inventory_summary_bitdefender"] = bd_charts["inventory_summary_bitdefender"]
                    if is_chart_selected('bitdefender', 'networkinventory_bitdefender') and "networkinventory_bitdefender" in bd_tables:
                        bd["tables"]["networkinventory_bitdefender"] = bd_tables["networkinventory_bitdefender"]

                    frontend_json["Bitdefender"] = bd

            # --- LoyaltyLoop ---
            elif platform_name == "LoyaltyLoop":
                loyaltyloop_metrics = full_data.get("loyaltyloop_metrics", {})
                if loyaltyloop_metrics:
                    ll = {"charts": {}}
                    ll_charts = loyaltyloop_metrics.get("charts", {})

                    if is_chart_selected('loyaltyloop', 'nps_score') and "nps_score" in ll_charts:
                        ll["charts"]["nps_score"] = ll_charts["nps_score"]
                    if is_chart_selected('loyaltyloop', 'loyalty_score') and "loyalty_score" in ll_charts:
                        ll["charts"]["loyalty_score"] = ll_charts["loyalty_score"]

                    frontend_json["LoyaltyLoop"] = ll

            # --- Infima ---
            elif platform_name == "Infima":
                infima_metrics = full_data.get("infima_metrics", {})
                if infima_metrics:
                    infima_out = {"charts": {}, "tables": {}}
                    infima_charts = infima_metrics.get("charts", {})
                    infima_tables = infima_metrics.get("tables", {})

                    if is_chart_selected('infima', 'training_rates') and "training_rates" in infima_charts:
                        infima_out["charts"]["training_rates"] = infima_charts["training_rates"]
                    if is_chart_selected('infima', 'darkweb_exposures') and "darkweb_exposures" in infima_tables:
                        infima_out["tables"]["darkweb_exposures"] = infima_tables["darkweb_exposures"]

                    frontend_json["Infima"] = infima_out

            # --- SentinelOne ---
            elif platform_name == "SentinelOne":
                sentinelone_metrics = full_data.get("sentinelone_metrics", {})
                if sentinelone_metrics:
                    s1 = {"charts": {}}
                    s1_charts = sentinelone_metrics.get("charts", {})

                    s1_chart_keys = [
                        "secured_devices_by_domain", "secured_devices_by_role",
                        "secured_devices_by_os", "infected_endpoints",
                        "agent_version_coverage", "endpoint_connection_status",
                        "severity_levels_threats", "incident_status",
                        "analyst_verdicts_threats", "threats_by_detection_engine",
                        "threats_by_type"
                    ]

                    for chart_key in s1_chart_keys:
                        if is_chart_selected('sentinelone', chart_key) and chart_key in s1_charts:
                            s1["charts"][chart_key] = s1_charts[chart_key]

                    frontend_json["SentinelOne"] = s1

            # --- NodeWare ---
            elif platform_name == "NodeWare":
                nodeware_metrics = full_data.get("nodeware_metrics", {})
                if nodeware_metrics:
                    nw = {"charts": {}, "tables": {}}
                    nw_charts = nodeware_metrics.get("charts", {})
                    nw_tables = nodeware_metrics.get("tables", {})

                    for chart_key in ["summary_metrics", "cvss_breakdown"]:
                        if is_chart_selected('nodeware', chart_key) and chart_key in nw_charts:
                            nw["charts"][chart_key] = nw_charts[chart_key]

                    for table_key in ["known_exploited_cves", "cvss_prioritized", "asset_risk_score", "epss_prioritized"]:
                        if is_chart_selected('nodeware', table_key) and table_key in nw_tables:
                            nw["tables"][table_key] = nw_tables[table_key]

                    frontend_json["NodeWare"] = nw

            # --- Cove ---
            elif platform_name == "Cove":
                cove_metrics = full_data.get("cove_metrics", {})
                if cove_metrics:
                    cove = {"charts": {}}

                    if is_chart_selected('cove', 'total_devices_storage_summary_cove'):
                        cove["charts"]["total_devices_storage_summary_cove"] = {
                            "totalDevices": cove_metrics.get("device_count", 0) or 0,
                            "used_storage": cove_metrics.get("total_storage_used", 0.0) or 0.0,
                            "user_mailboxes": cove_metrics.get("user_mailboxes", 0) or 0,
                            "shared_mailboxes": cove_metrics.get("shared_mailboxes", 0) or 0,
                            "onedrive_user_accounts": cove_metrics.get("onedrive_user_accounts", 0) or 0
                        }
                    if is_chart_selected('cove', 'asset_type_distribution_cove'):
                        asset_dist = cove_metrics.get("asset_distribution", {})
                        cove["charts"]["asset_type_distribution_cove"] = {
                            "physical": asset_dist.get("Physical", 0) or 0,
                            "virtual": asset_dist.get("Virtual", 0) or 0,
                            "others": asset_dist.get("Undefined", 0) or 0
                        }
                    if is_chart_selected('cove', 'devices_distribution_cove'):
                        device_dist = cove_metrics.get("device_distribution", {})
                        cove["charts"]["devices_distribution_cove"] = {
                            "workstations": device_dist.get("Workstation", 0) or 0,
                            "servers": device_dist.get("Server", 0) or 0,
                            "others": device_dist.get("Undefined", 0) or 0
                        }
                    if is_chart_selected('cove', 'retention_policy_distribution_cove'):
                        retention_dist = cove_metrics.get("retention_policy_distribution", {})
                        cleaned_retention = {}
                        for policy, count in retention_dist.items():
                            if policy:
                                cleaned_retention[policy] = count or 0
                        cove["charts"]["retention_policy_distribution_cove"] = cleaned_retention or {}

                    cove["cove_insights"] = full_data.get("cove_insights") or {}

                    # tables — inventory table (added; existing charts/insights logic untouched)
                    cove_tables = full_data.get("cove_tables") or {}
                    cove["tables"] = {
                        "inventory_cove": cove_tables.get("inventory_cove", [])
                    }

                    frontend_json["Cove"] = cove

            # --- DNSFilter ---
            elif platform_name == "DNSFilter":
                dnsfilter_metrics = full_data.get("dnsfilter_metrics", {})
                if dnsfilter_metrics:
                    dns = {"charts": {}}
                    dns_charts = dnsfilter_metrics.get("charts", {})
                    
                    if is_chart_selected('dnsfilter', 'request_counts') and 'request_counts' in dns_charts:
                        dns["charts"]["request_counts"] = dns_charts["request_counts"]
                        
                    quarterly_data = dns_charts.get("Quaterly_data", {})
                    if quarterly_data:
                        filtered_quarterly = {}
                        for chart_key in ["threats_over_months", "allowed_vs_blocked_request_quarterly", "allowed_vs_blocked_threats_quarterly"]:
                            if chart_key in quarterly_data:
                                filtered_quarterly[chart_key] = quarterly_data[chart_key]
                        if filtered_quarterly:
                            dns["charts"]["Quaterly_data"] = filtered_quarterly
                            
                    monthly_data = dns_charts.get("Monthly_data", {})
                    if monthly_data:
                        filtered_monthly = {}
                        for chart_key in ["allowed_vs_blocked_request", "threats_over_time", "allowed_vs_blocked_threats"]:
                            if is_chart_selected('dnsfilter', chart_key) and chart_key in monthly_data:
                                filtered_monthly[chart_key] = monthly_data[chart_key]
                        if filtered_monthly:
                            dns["charts"]["Monthly_data"] = filtered_monthly

                    frontend_json["DNSFilter"] = dns

            # --- Dropsuite ---
            elif platform_name == "Dropsuite":
                dropsuite_metrics = full_data.get("dropsuite_metrics", {})
                if dropsuite_metrics:
                    ds = {"charts": {}}
                    ds_charts = dropsuite_metrics.get("charts", {})
                    ds_chart_keys = [
                        "mailbox_backup_status_distribution",
                        "onedrive_backup_storage_overview",
                        "onedrive_backup_status_distribution",
                        "sharepoint_storage_and_capacity_overview",
                        "google_drive_storage_and_capacity_overview",
                        "shared_drive_storage_and_capacity_overview",
                    ]
                    for chart_key in ds_chart_keys:
                        if is_chart_selected('dropsuite', chart_key) and chart_key in ds_charts:
                            ds["charts"][chart_key] = ds_charts[chart_key]
                    frontend_json["Dropsuite"] = ds

            # --- Blackpoint Standalone Handler ---
            elif platform_name == "Blackpoint":
                blackpoint_metrics = full_data.get("blackpoint_metrics", {})
                if blackpoint_metrics:
                    bp = {"charts": {}, "tables": {}}
                    bp_charts = blackpoint_metrics.get("charts", {})
                    bp_tables = blackpoint_metrics.get("tables", {})
                    
                    # Match the underscore structure from your processor
                    if "Quaterly_data" in bp_charts:  # <-- Changed - to _
                        bp["charts"]["Quaterly_data"] = bp_charts["Quaterly_data"]
                    if "monthly_data" in bp_charts:   # <-- Changed - to _
                        bp["charts"]["monthly_data"] = bp_charts["monthly_data"]
                            
                    if is_chart_selected('blackpoint', 'soc_escalations_activity') and "soc_escalations_activity" in bp_tables:
                        bp["tables"]["soc_escalations_activity"] = bp_tables["soc_escalations_activity"]
                    
                    if not bp.get("tables"):
                        bp.pop("tables", None)
                        
                    frontend_json["Blackpoint"] = bp
            
            elif platform_name == "Axcient":
                axcient_metrics = full_data.get("axcient_metrics", {})
                if axcient_metrics:
                    ax = {"charts": {}, "tables": {}}
                    ax_charts = axcient_metrics.get("charts", {})
                    ax_tables = axcient_metrics.get("tables", {})

                    ax_chart_keys = [
                        "account_protection_coverage",
                        "protected_accounts_by_status",
                        "license_optimization_overview",
                        "active_backup_services",
                        "user_backup_execution_health",
                        "sharepoint_backup_execution_health",
                        "monthly_backup_trend"
                    ]
                    
                    for chart_key in ax_chart_keys:
                        if is_chart_selected('axcient', chart_key) and chart_key in ax_charts:
                            ax["charts"][chart_key] = ax_charts[chart_key]

                    if is_chart_selected('axcient', 'backup_alerts') and "backup_alerts" in ax_tables:
                        ax["tables"]["backup_alerts"] = ax_tables["backup_alerts"]

                    if not ax.get("tables"):
                        ax.pop("tables", None)
                        
                    frontend_json["Axcient"] = ax

            return frontend_json

        except Exception as e:
            import traceback
            logger.error(f"Failed to transform {platform_name} data: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {}

    def _extract_organization_info(self, data: Dict[str, Any], reporting_period: str = None, account_id: int = None) -> Dict[str, Any]:
        """Extract organization information with dynamic company name from accounts table."""
        execution_info = data.get("execution_info", {})

        # Use provided reporting_period, fallback to execution_info, then current month
        if not reporting_period:
            reporting_period = execution_info.get("reporting_period")
        if not reporting_period:
            reporting_period = datetime.now().strftime("%B %Y")

        # Fetch account_name from accounts table using account_id
        company_name = "Unknown Company"  # Default fallback
        if account_id:
            try:
                from app.core.database.engine import SessionLocal
                from app.models.users import Account
                _db = SessionLocal()
                try:
                    account = _db.query(Account).filter(Account.id == account_id).first()
                    if account:
                        company_name = account.account_name
                        logger.info(f"Fetched company name: {company_name} for account_id: {account_id}")
                    else:
                        logger.warning(f"No account found for account_id: {account_id}")
                finally:
                    _db.close()
            except Exception as e:
                logger.error(f"Failed to fetch account_name from accounts table: {e}")
                # Fallback to default

        return {
            "id": execution_info.get("organization_id", "unknown"),
            "name": execution_info.get("organization_name", "Unknown Organization"),
            "report_date": execution_info.get("timestamp", datetime.now().isoformat()),
            "created_by": "Security Reporting System",
            "company": company_name,
            "reporting_period": reporting_period
        }

    def _extract_summary_metrics(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract high-level summary metrics."""
        # Initialize with complete default structure
        summary = {
            "total_devices": 0,
            "online_devices": 0,
            "offline_devices": 0,
            "total_assets": 0,
            "online_assets": 0,
            "offline_assets": 0,
            "total_tickets": 0,
            "completed_tickets": 0,
            "total_patches": 0,
            "patch_compliance_percentage": 0,
            "security_risk_score": {"live_count": None, "monthly_count": None},
            "risk_level": "Unknown",
            "total_vulnerabilities": 0,
            "data_sources": []
        }

        try:
            # Infrastructure metrics
            infra = data.get("infrastructure_metrics", {})

            # Patch metrics
            patch_metrics = data.get("patch_metrics", {})
            patch_compliance = data.get("patch_compliance", {})

            # ConnectSecure metrics
            cs_metrics = data.get("connectsecure_metrics", {})
            cs_summary = cs_metrics.get("summary", {}) if cs_metrics else {}
            cs_asset_inventory = cs_metrics.get("asset_inventory", {}) if cs_metrics else {}
            # Updated to use NEW security_risk_score structure with live_count and monthly_count
            cs_risk_data = cs_metrics.get("security_risk_score", {}) if cs_metrics else {}
            # Extract live and monthly counts (can be None)
            live_count = cs_risk_data.get("live_count")
            monthly_count = cs_risk_data.get("monthly_count")

            # Calculate risk level based on live_count (primary) or monthly_count (fallback)
            score_for_risk_level = live_count if live_count is not None else monthly_count
            risk_level = self._calculate_risk_level(score_for_risk_level) if score_for_risk_level is not None else "Unknown"

            # Get vulnerability data from NEW structure
            vuln_severity = cs_metrics.get("vulnerability_severity", {}) if cs_metrics else {}
            # Safety check for None values
            if vuln_severity is None:
                vuln_severity = {}

            # Calculate total vulnerabilities from live_count
            live_vuln = vuln_severity.get("live_count", {})
            total_vulnerabilities = (live_vuln.get("critical", 0) + live_vuln.get("high", 0) +
                                   live_vuln.get("medium", 0) + live_vuln.get("low", 0))

            # Autotask data
            autotask_metrics = data.get("autotask_metrics", {})
            ticket_analytics = autotask_metrics.get("ticket_analytics", {}) if autotask_metrics else {}
            created_vs_completed = ticket_analytics.get("created_vs_completed", {}) if ticket_analytics else {}

            # Calculate real total patches from actual patch data
            top_failed = data.get("top_failed_devices", {})
            os_patches_data = top_failed.get("os_patches", {}) if top_failed else {}
            os_patch_details = patch_compliance.get("os_patch_details", {}) if patch_compliance else {}

            real_total_patches = (
                os_patches_data.get("success", 0) +  # 531 installed
                os_patches_data.get("failed", 0) +   # 1 failed
                os_patch_details.get("APPROVED", 0) + # 62 approved
                os_patch_details.get("PENDING", 0)    # 0 pending
            )

            # Update with real data when available
            summary.update({
                "total_devices": infra.get("total_devices", 0),
                "online_devices": infra.get("online_devices", 0),
                "offline_devices": infra.get("offline_devices", 0),
                "total_assets": cs_asset_inventory.get("total_assets", 0),
                "online_assets": cs_asset_inventory.get("online_assets", 0),
                "offline_assets": cs_asset_inventory.get("offline_assets", 0),
                "total_tickets": created_vs_completed.get("created_count", 0),
                "completed_tickets": created_vs_completed.get("completed_count", 0),
                "total_patches": real_total_patches,  # Real total: 594
                "patch_compliance_percentage": round(patch_compliance.get("os_patch_compliance", 0), 1),
                "security_risk_score": {"live_count": live_count, "monthly_count": monthly_count},
                "risk_level": risk_level,
                "total_vulnerabilities": total_vulnerabilities,
                "data_sources": data.get("execution_info", {}).get("data_sources", [])
            })

        except Exception as e:
            logger.error(f"Error extracting summary metrics: {e}")
            # Keep default summary structure - no need to reassign

        return summary

    def _extract_chart_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract data for charts and visualizations."""
        # Initialize with complete default structure
        charts = {
            "daily_tickets_trend": {
                "created": [],
                "completed": [],
                "days": []
            },
            "monthly_tickets_by_type": {},
            "open_ticket_priority_distribution": {
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0
            },
            "sla_performance": {
                "first_response_percentage": 0,
                "resolution_percentage": 0
            },
            "patch_management_enablement": {
                "enabled": 0,
                "disabled": 0
            },
            "patch_status_distribution": {
                "installed": 0,
                "approved": 0,
                "failed": 0,
                "pending": 0
            },
            "asset_type_distribution": {
                "live_count": {
                    "discovered": 0,
                    "other_asset": 0,
                    "unknown": 0
                },
                "monthly_count": {
                    "discovered": 0,
                    "other_asset": 0,
                    "unknown": 0
                },
                "quarterly_count": {
                    "discovered": 0,
                    "other_asset": 0,
                    "unknown": 0
                }
            },
            "operating_system_distribution": {
                "live_count": {
                    "Others": 0
                },
                "monthly_count": {
                    "Others": 0
                },
                "quarterly_count": {
                    "Others": 0
                }
            },
            "security_risk_score": {
                "live_count": None,
                "monthly_count": None,
                "quarterly_count": None
            },
            "vulnerability_severity": {
                "live_count": {
                    "critical": 0,
                    "high": 0,
                    "medium": 0,
                    "low": 0
                },
                "monthly_count": {
                    "critical": 0,
                    "high": 0,
                    "medium": 0,
                    "low": 0
                }
            },
            "agent_type_distribution": {
                "total_agents": 0,
                "breakdown": []
            }
        }

        # Autotask data
        autotask_metrics = data.get("autotask_metrics", {})
        if autotask_metrics:
            ticket_analytics = autotask_metrics.get("ticket_analytics", {})

            # Daily tickets trend
            created_vs_completed = ticket_analytics.get("created_vs_completed", {})
            if created_vs_completed:
                import math
                daily_breakdown = created_vs_completed.get("daily_breakdown", {})
                daily_created   = daily_breakdown.get("daily_created", [])
                daily_completed = daily_breakdown.get("daily_completed", [])
                days            = daily_breakdown.get("days", [])
                total           = len(daily_created)
                span            = max(1, math.ceil(total / 30))
                if total > 60:
                    agg_created, agg_completed, agg_days = [], [], []
                    for i in range(0, total, span):
                        agg_created.append(sum(daily_created[i:i+span]))
                        agg_completed.append(sum(daily_completed[i:i+span]))
                        agg_days.append(i + 1)
                    daily_created, daily_completed, days = agg_created, agg_completed, agg_days
                charts["daily_tickets_trend"] = {
                    "created": daily_created,
                    "completed": daily_completed,
                    "days": days
                }

            # Monthly tickets by issue type (always include with fallback)
            monthly_by_issue = ticket_analytics.get("monthly_by_issue_type", [])

            # Build dynamic issue type dict directly from API labels
            ticket_types = {}

            if monthly_by_issue:
                for item in monthly_by_issue:
                    issue_type = item.get("issue_type", "Unknown")
                    count = item.get("count", 0)
                    if issue_type:
                        ticket_types[issue_type] = ticket_types.get(issue_type, 0) + count

            # Always include this data structure
            charts["monthly_tickets_by_type"] = ticket_types

            # Open tickets by issue/sub-issue type
            open_by_issue_subissue = ticket_analytics.get("open_by_issue_subissue", [])

            # Transform to frontend structure with fallback
            charts["open_tickets_by_issue_type"] = []

            if open_by_issue_subissue and isinstance(open_by_issue_subissue, list):
                for issue_group in open_by_issue_subissue:
                    if not isinstance(issue_group, dict):
                        continue

                    issue_type = issue_group.get("issue_type", "Unknown")
                    # Handle empty or None values
                    if not issue_type or (isinstance(issue_type, str) and issue_type.strip() == ""):
                        issue_type = "Unknown"

                    issue_item = {
                        "issue_type": issue_type,
                        "total_count": issue_group.get("total_count", 0),
                        "sub_issues": []
                    }

                    sub_issues = issue_group.get("sub_issues", [])
                    if sub_issues and isinstance(sub_issues, list):
                        for sub_issue in sub_issues:
                            if not isinstance(sub_issue, dict):
                                continue

                            sub_issue_type = sub_issue.get("sub_issue_type", "Unknown")
                            # Handle empty or None values
                            if not sub_issue_type or (isinstance(sub_issue_type, str) and sub_issue_type.strip() == ""):
                                sub_issue_type = "Unknown"

                            issue_item["sub_issues"].append({
                                "sub_issue_type": sub_issue_type,
                                "count": sub_issue.get("count", 0)
                            })

                    charts["open_tickets_by_issue_type"].append(issue_item)
            else:
                # Fallback: empty array
                charts["open_tickets_by_issue_type"] = []

            # Priority distribution from ticket analytics — use raw labels as-is
            open_by_priority = ticket_analytics.get("open_by_priority", [])
            priority_counts = {}

            if isinstance(open_by_priority, list):
                for priority_item in open_by_priority:
                    if isinstance(priority_item, dict):
                        label = priority_item.get("priority", "Unknown")
                        count = priority_item.get("count", 0)
                        priority_counts[label] = count

            charts["open_ticket_priority_distribution"] = priority_counts

            # SLA performance from summary section (real API data)
            sla_summary = autotask_metrics.get("summary", {})
            if sla_summary:
                charts["sla_performance"] = {
                    "first_response_percentage": round(sla_summary.get("first_response_sla_percentage", 0), 1),
                    "resolution_percentage": round(sla_summary.get("resolution_sla_percentage", 0), 1)
                }

        # Patch management from NinjaOne
        patch_enablement = data.get("patch_enablement", {})
        if patch_enablement:
            charts["patch_management_enablement"] = {
                "enabled": patch_enablement.get("enabled_devices", 0),
                "disabled": patch_enablement.get("disabled_devices", 0)
            }

        # Patch status distribution (using real patch data)
        top_failed = data.get("top_failed_devices", {})
        os_patches_data = top_failed.get("os_patches", {}) if top_failed else {}
        patch_compliance = data.get("patch_compliance", {})
        os_patch_details = patch_compliance.get("os_patch_details", {}) if patch_compliance else {}

        if os_patches_data:
            charts["patch_status_distribution"] = {
                "installed": os_patches_data.get("success", 0),  # Real installed count
                "approved": os_patch_details.get("APPROVED", 0),  # From compliance data
                "failed": os_patches_data.get("failed", 0),  # Real failed count
                "pending": os_patch_details.get("PENDING", 0)
            }

        # REMOVED: device_os_distribution from NinjaOne - no longer needed

        # ConnectSecure charts
        cs_metrics = data.get("connectsecure_metrics", {})
        if cs_metrics:
            # Asset type distribution - UPDATED to use new live_count/monthly_count structure
            asset_type_dist = cs_metrics.get("asset_type_distribution", {})
            if asset_type_dist is None:
                asset_type_dist = {}

            # Extract live_count, monthly_count, quarterly_count (with defaults)
            live_types = asset_type_dist.get("live_count", {"discovered": 0, "other_asset": 0, "unknown": 0})
            monthly_types = asset_type_dist.get("monthly_count", {"discovered": 0, "other_asset": 0, "unknown": 0})
            quarterly_types = asset_type_dist.get("quarterly_count", {"discovered": 0, "other_asset": 0, "unknown": 0})

            charts["asset_type_distribution"] = {
                "live_count": live_types,
                "monthly_count": monthly_types,
                "quarterly_count": quarterly_types
            }

            # OS distribution - UPDATED to use new live_count/monthly_count/quarterly_count structure
            os_dist = cs_metrics.get("operating_system_distribution", {})
            if os_dist is None:
                os_dist = {}

            # Extract live_count, monthly_count, quarterly_count (with defaults)
            live_os = os_dist.get("live_count", {"Others": 0})
            monthly_os = os_dist.get("monthly_count", {"Others": 0})
            quarterly_os = os_dist.get("quarterly_count", {"Others": 0})

            charts["operating_system_distribution"] = {
                "live_count": live_os,
                "monthly_count": monthly_os,
                "quarterly_count": quarterly_os
            }

            # Security risk score - UPDATED to use new live_count/monthly_count/quarterly_count structure
            cs_risk_data = cs_metrics.get("security_risk_score", {})
            if cs_risk_data is None:
                cs_risk_data = {}

            # Extract live_count, monthly_count, quarterly_count (can be None for empty data)
            live_risk = cs_risk_data.get("live_count")
            monthly_risk = cs_risk_data.get("monthly_count")
            quarterly_risk = cs_risk_data.get("quarterly_count")

            charts["security_risk_score"] = {
                "live_count": live_risk,
                "monthly_count": monthly_risk,
                "quarterly_count": quarterly_risk
            }

            # Vulnerability severity - UPDATED to use new live_count/monthly_count structure
            vuln_severity = cs_metrics.get("vulnerability_severity", {})
            if vuln_severity is None:
                vuln_severity = {}

            # Extract live_count and monthly_count with defaults
            live_vuln = vuln_severity.get("live_count", {"critical": 0, "high": 0, "medium": 0, "low": 0})
            monthly_vuln = vuln_severity.get("monthly_count", {"critical": 0, "high": 0, "medium": 0, "low": 0})

            charts["vulnerability_severity"] = {
                "live_count": live_vuln,
                "monthly_count": monthly_vuln
            }

            # Agent type distribution - Keep full structure with breakdown and percentages
            agent_dist = cs_metrics.get("agent_type_distribution", {})
            if agent_dist and agent_dist.get("breakdown"):
                # Use the real data structure with total_agents, breakdown, and percentages
                charts["agent_type_distribution"] = {
                    "total_agents": agent_dist.get("total_agents", 0),
                    "breakdown": agent_dist.get("breakdown", [])
                }
            else:
                # Default empty structure when no data
                charts["agent_type_distribution"] = {
                    "total_agents": 0,
                    "breakdown": []
                }

        # Ensure monthly_tickets_by_type is always present (fallback if no Autotask data)
        if "monthly_tickets_by_type" not in charts:
            charts["monthly_tickets_by_type"] = {}

        # Ensure priority_distribution is always present (fallback if no Autotask data)
        if "open_ticket_priority_distribution" not in charts:
            charts["open_ticket_priority_distribution"] = {
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0
            }

        return charts

    def _extract_table_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract data for tables with new patch management structure."""
        # Initialize with updated structure
        tables = {
            "tickets_by_contact": [],
            "patch_management": {
                "os_patches": {
                    "summary": {
                        "total": 0,
                        "successful": 0,
                        "failed": 0,
                        "success_rate": 0.0
                    },
                    "failed_devices": []
                },
                "third_party_patches": {
                    "summary": {
                        "total": 0,
                        "successful": 0,
                        "failed": 0,
                        "success_rate": 0.0
                    },
                    "failed_devices": []
                }
            },
            "devices_with_failed_patches": {
                "count": 0,
                "devices": [],
                "message": "No devices with failed patches"
            },
            "last_scan_info": {
                "last_successful_scan": datetime.now().isoformat(),
                "scan_status": "completed"
            },
            "device_inventory": [],
            "device_inventory_server": []
        }

        try:
            # Top contacts (from Autotask) - keep existing logic
            autotask_metrics = data.get("autotask_metrics", {})
            ticket_analytics = autotask_metrics.get("ticket_analytics", {}) if autotask_metrics else {}
            tickets_by_contact = ticket_analytics.get("tickets_by_contact", [])

            if isinstance(tickets_by_contact, list) and tickets_by_contact:
                # Sort contacts by ticket count (descending)
                sorted_contacts = sorted(tickets_by_contact, key=lambda x: x.get("ticket_count", 0), reverse=True)

                # Get top 12 contacts
                top_12_contacts = sorted_contacts[:12]
                remaining_contacts = sorted_contacts[12:]

                # Calculate "Other" sum from contacts ranked 13+
                other_count = sum(contact.get("ticket_count", 0) for contact in remaining_contacts)

                # Create contact list with top 12 + Other (if there are remaining contacts)
                contact_list = []
                for contact in top_12_contacts:
                    contact_list.append({
                        "name": contact.get("contact_name", "Unknown"),
                        "tickets": contact.get("ticket_count", 0)
                    })

                # Add "Other" entry if there are remaining contacts
                if other_count > 0:
                    contact_list.append({
                        "name": "Other",
                        "tickets": other_count
                    })

                # Sort final list by ticket count (so "Other" finds its natural position)
                contact_list.sort(key=lambda x: x["tickets"], reverse=True)

                # Add contacts summary as the last item in the array
                contact_list.append({
                    "contacts_summary": {
                        "contacts_count": len(sorted_contacts),
                        "total_tickets": sum(contact.get("ticket_count", 0) for contact in sorted_contacts),
                        "top_contact": sorted_contacts[0].get("contact_name",
                                                              "Unknown") if sorted_contacts else "Unknown"
                    }
                })

                tables["tickets_by_contact"] = contact_list
            else:
                tables["tickets_by_contact"] = [{
                    "contacts_summary": {
                        "contacts_count": 0,
                        "total_tickets": 0,
                        "top_contact": "Unknown"
                    }
                }]

            # NEW: Patch management structure
            top_failed = data.get("top_failed_devices", {})
            patch_compliance = data.get("patch_compliance", {})

            # OS Patches data
            os_patches_data = top_failed.get("os_patches", {}) if top_failed else {}
            os_patch_details = patch_compliance.get("os_patch_details", {}) if patch_compliance else {}
            os_failed_devices_list = os_patches_data.get("devices", []) if os_patches_data else []

            os_successful = os_patches_data.get("success", 0)
            os_failed = os_patches_data.get("failed", 0)
            os_total = os_successful + os_failed
            os_success_rate = (os_successful / os_total * 100) if os_total > 0 else 100.0

            tables["patch_management"]["os_patches"] = {
                "summary": {
                    "total": os_total,
                    "successful": os_successful,
                    "failed": os_failed,
                    "success_rate": round(os_success_rate, 1)
                },
                "failed_devices": [
                    {
                        "device_name": device.get("device", "Unknown"),
                        "failed_patches": device.get("failed_patches", 0),
                        "last_successful_scan": device.get("last_successful_scan_date", "Unknown")
                    }
                    for device in os_failed_devices_list[:10]  # Top 10 only
                    if device and isinstance(device, dict)
                ]
            }

            # Third-party/Software Patches data
            sw_patches_data = top_failed.get("software_patches", {}) if top_failed else {}
            sw_failed_devices_list = sw_patches_data.get("devices", []) if sw_patches_data else []

            sw_successful = sw_patches_data.get("success", 0)
            sw_failed = sw_patches_data.get("failed", 0)
            sw_total = sw_successful + sw_failed
            sw_success_rate = (sw_successful / sw_total * 100) if sw_total > 0 else 100.0

            tables["patch_management"]["third_party_patches"] = {
                "summary": {
                    "total": sw_total,
                    "successful": sw_successful,
                    "failed": sw_failed,
                    "success_rate": round(sw_success_rate, 1)
                },
                "failed_devices": [
                    {
                        "device_name": device.get("device", "Unknown"),
                        "failed_patches": device.get("failed_patches", 0),
                        "last_successful_scan": device.get("last_successful_scan_date", "Unknown")
                    }
                    for device in sw_failed_devices_list[:10]  # Top 10 only
                    if device and isinstance(device, dict)
                ]
            }

            # Combined failed devices summary
            all_failed_devices = []
            all_failed_devices.extend(os_failed_devices_list)
            all_failed_devices.extend(sw_failed_devices_list)

            # Remove duplicates based on device name
            unique_failed_devices = {}
            for device in all_failed_devices:
                if device and isinstance(device, dict):
                    device_name = device.get("device", "Unknown")
                    if device_name not in unique_failed_devices:
                        unique_failed_devices[device_name] = device
                    else:
                        # Combine failed patch counts if same device appears in both lists
                        unique_failed_devices[device_name]["failed_patches"] = (
                                unique_failed_devices[device_name].get("failed_patches", 0) +
                                device.get("failed_patches", 0)
                        )

            failed_devices_final = list(unique_failed_devices.values())
            total_failed_count = len(failed_devices_final)

            tables["devices_with_failed_patches"] = {
                "count": total_failed_count,
                "devices": [
                    {
                        "device_name": device.get("device", "Unknown"),
                        "failed_patches": device.get("failed_patches", 0),
                        "last_successful_scan": device.get("last_successful_scan_date", "Unknown"),
                        "patch_type": "Mixed"  # Since we're combining both OS and software
                    }
                    for device in failed_devices_final[:10]  # Top 10 only
                ],
                "message": "No devices with failed patches" if total_failed_count == 0 else f"{total_failed_count} devices with failed patches"
            }

            # Last scan info - try to get the most recent scan timestamp
            latest_timestamp = None

            # Check for timestamps in various data sources
            all_timestamps = []

            # From os_patch_installs
            os_patch_installs = data.get("raw_data_content", {}).get("os_patch_installs", [])
            for install in os_patch_installs:
                if install.get("timestamp"):
                    all_timestamps.append(install["timestamp"])

            # From software_patch_installs
            sw_patch_installs = data.get("raw_data_content", {}).get("software_patch_installs", [])
            for install in sw_patch_installs:
                if install.get("timestamp"):
                    all_timestamps.append(install["timestamp"])

            if all_timestamps:
                latest_timestamp = max(all_timestamps)
                last_scan_date = datetime.fromtimestamp(latest_timestamp).isoformat()
            else:
                last_scan_date = datetime.now().isoformat()

            tables["last_scan_info"] = {
                "last_successful_scan": last_scan_date,
                "scan_status": "completed"
            }

            # Device inventory - separated by workstations and servers
            # Get workstation devices (WINDOWS_WORKSTATION + all other device types except WINDOWS_SERVER)
            device_details_workstation = data.get("device_details_workstation", [])
            if isinstance(device_details_workstation, list) and device_details_workstation:
                tables["device_inventory"] = [
                    self._format_device_for_frontend(device)
                    for device in device_details_workstation
                    if device and isinstance(device, dict)
                ]
            else:
                tables["device_inventory"] = []

            # Get server devices (WINDOWS_SERVER only)
            device_details_server = data.get("device_details_server", [])
            if isinstance(device_details_server, list) and device_details_server:
                tables["device_inventory_server"] = [
                    self._format_device_for_frontend(device)
                    for device in device_details_server
                    if device and isinstance(device, dict)
                ]
            else:
                tables["device_inventory_server"] = []

        except Exception as e:
            logger.error(f"Error extracting table data: {e}")
            # Keep default structure - no need to reassign

        return tables

    def _extract_detailed_metrics(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract detailed metrics for KPI cards."""
        # Initialize with complete default structure
        metrics = {
            "patch_compliance": {
                "success_rate": 0,
                "total_patches": 0,
                "installed": 0,
                "failed": 0,
                "pending": 0
            },
            "security_metrics": {
                "security_risk_score": {"live_count": None, "monthly_count": None},
                "risk_level": "Unknown",
                "total_vulnerabilities": 0,
                "critical_vulnerabilities": 0,
                "high_vulnerabilities": 0,
                "medium_vulnerabilities": 0,
                "low_vulnerabilities": 0
            },
            "infrastructure_health": {
                "total_assets": 0,
                "online_percentage": 0,
                "offline_percentage": 100,
                "patch_enablement_percentage": 0
            },
            "support_metrics": {
                "total_tickets_month": 0,
                "completed_tickets": 0,
                "open_tickets": 0,
                "sla_first_response": 0,
                "sla_resolution": 0
            }
        }

        try:
            patch_metrics = data.get("patch_metrics", {})
            patch_compliance = data.get("patch_compliance", {})
            patch_enablement = data.get("patch_enablement", {})

            cs_metrics = data.get("connectsecure_metrics", {})
            cs_summary = cs_metrics.get("summary", {}) if cs_metrics else {}
            cs_asset_inventory = cs_metrics.get("asset_inventory", {}) if cs_metrics else {}
            # Updated to use NEW security_risk_score structure with live_count and monthly_count
            cs_risk_data = cs_metrics.get("security_risk_score", {}) if cs_metrics else {}
            live_count = cs_risk_data.get("live_count")
            monthly_count = cs_risk_data.get("monthly_count")

            # Calculate risk level based on live_count (primary) or monthly_count (fallback)
            score_for_risk_level = live_count if live_count is not None else monthly_count
            risk_level = self._calculate_risk_level(score_for_risk_level) if score_for_risk_level is not None else "Unknown"

            infra_metrics = data.get("infrastructure_metrics", {})

            autotask_metrics = data.get("autotask_metrics", {})
            ticket_analytics = autotask_metrics.get("ticket_analytics", {}) if autotask_metrics else {}
            created_vs_completed = ticket_analytics.get("created_vs_completed", {}) if ticket_analytics else {}
            sla_summary = autotask_metrics.get("summary", {}) if autotask_metrics else {}

            # Use real patch data
            top_failed = data.get("top_failed_devices", {})
            os_patches_data = top_failed.get("os_patches", {}) if top_failed else {}
            os_patch_details = patch_compliance.get("os_patch_details", {}) if patch_compliance else {}

            real_total_patches = (
                os_patches_data.get("success", 0) +
                os_patches_data.get("failed", 0) +
                os_patch_details.get("APPROVED", 0) +
                os_patch_details.get("PENDING", 0)
            )

            # Update with real data when available
            metrics["patch_compliance"].update({
                "success_rate": round(patch_compliance.get("os_patch_compliance", 0), 1),
                "total_patches": real_total_patches,  # Real total: 594
                "installed": os_patches_data.get("success", 0),  # Real installed: 531
                "failed": os_patches_data.get("failed", 0),  # Real failed: 1
                "pending": os_patch_details.get("PENDING", 0)
            })

            # Get vulnerability data from NEW structure
            vuln_severity = cs_metrics.get("vulnerability_severity", {})
            # Safety check for None values
            if vuln_severity is None:
                vuln_severity = {}

            # Extract live_count vulnerabilities
            live_vuln = vuln_severity.get("live_count", {})
            total_vulnerabilities = (live_vuln.get("critical", 0) + live_vuln.get("high", 0) +
                                   live_vuln.get("medium", 0) + live_vuln.get("low", 0))

            metrics["security_metrics"].update({
                "security_risk_score": {"live_count": live_count, "monthly_count": monthly_count},
                "risk_level": risk_level,
                "total_vulnerabilities": total_vulnerabilities,
                "critical_vulnerabilities": live_vuln.get("critical", 0),
                "high_vulnerabilities": live_vuln.get("high", 0),
                "medium_vulnerabilities": live_vuln.get("medium", 0),
                "low_vulnerabilities": live_vuln.get("low", 0)
            })

            metrics["infrastructure_health"].update({
                "total_assets": cs_asset_inventory.get("total_assets", infra_metrics.get("total_devices", 0)),
                "online_percentage": round(infra_metrics.get("online_percentage", 0), 1),
                "offline_percentage": round(100 - infra_metrics.get("online_percentage", 0), 1),
                "patch_enablement_percentage": round(patch_enablement.get("enabled_percentage", 0), 1)
            })

            metrics["support_metrics"].update({
                "total_tickets_month": created_vs_completed.get("created_count", 0),
                "completed_tickets": created_vs_completed.get("completed_count", 0),
                "open_tickets": sla_summary.get("active_tickets_count", 0),
                "sla_first_response": round(sla_summary.get("first_response_sla_percentage", 0), 1),
                "sla_resolution": round(sla_summary.get("resolution_sla_percentage", 0), 1)
            })

        except Exception as e:
            logger.error(f"Error extracting detailed metrics: {e}")
            # Keep default metrics structure - no need to reassign

        return metrics

    def _generate_alerts(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate alert notifications based on data."""
        alerts = []

        # Failed patches alert - FIX: Handle case where top_failed_devices is a string
        failed_devices_raw = data.get("top_failed_devices", [])

        # Ensure we have a proper data structure
        failed_devices = []
        if isinstance(failed_devices_raw, dict):
            # Extract device lists from nested structure
            os_devices = failed_devices_raw.get("os_patches", {}).get("devices", [])
            sw_devices = failed_devices_raw.get("software_patches", {}).get("devices", [])
            failed_devices.extend(os_devices)
            failed_devices.extend(sw_devices)
        elif isinstance(failed_devices_raw, list):
            failed_devices = failed_devices_raw
        # If it's a string or other type, failed_devices remains empty list

        if failed_devices:
            total_failed = sum(device.get("failed_patches", 0) for device in failed_devices if isinstance(device, dict))
            alerts.append({
                "type": "warning",
                "message": f"{len(failed_devices)} device(s) have failed patches requiring attention",
                "devices_affected": len(failed_devices),
                "action_required": "Review patch deployment"
            })

        # Vulnerability alert
        cs_metrics = data.get("connectsecure_metrics", {})
        vuln_severity = cs_metrics.get("vulnerability_severity", {})
        # ADD SAFETY CHECK
        if vuln_severity is None:
            vuln_severity = {}
        total_vulns = vuln_severity.get("total", 0)
        critical_vulns = vuln_severity.get("critical", 0)

        if total_vulns > 0:
            alert_type = "critical" if critical_vulns > 0 else "warning"
            alerts.append({
                "type": alert_type,
                "message": f"{total_vulns} total vulnerabilities detected",
                "critical_count": critical_vulns,
                "action_required": "Review vulnerability assessment"
            })

        # Patch compliance success
        patch_compliance = data.get("patch_compliance", {})
        compliance_rate = patch_compliance.get("compliance_percentage", 0)
        if compliance_rate >= 90:
            alerts.append({
                "type": "success",
                "message": f"{compliance_rate:.1f}% patch compliance rate achieved",
                "status": "meeting_target"
            })

        return alerts

    def _extract_execution_info(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract execution metadata."""
        execution_info = data.get("execution_info", {})

        return {
            "generated_at": execution_info.get("timestamp", datetime.now().isoformat()),
            "data_sources_processed": execution_info.get("data_sources", []),
            "report_type": "Monthly Customer Report",
            "processing_time_seconds": execution_info.get("duration_seconds", 0),
            "next_update": self._calculate_next_update()
        }

    def _get_risk_level(self, risk_score: float) -> str:
        """Convert numeric risk score to risk level."""
        if risk_score >= 80:
            return "Critical"
        elif risk_score >= 60:
            return "High"
        elif risk_score >= 40:
            return "Moderate"
        elif risk_score >= 20:
            return "Low"
        else:
            return "Minimal"

    def _calculate_next_update(self) -> str:
        """Calculate next update time (monthly)."""
        from datetime import datetime, timedelta
        next_month = datetime.now() + timedelta(days=30)
        return next_month.isoformat()

    def _format_device_for_frontend(self, device: Dict[str, Any]) -> Dict[str, Any]:
        """Format device data for frontend with new field names and additional columns."""
        # Extract user and remove domain prefix
        user = device.get("user", "Unknown")
        # ADD STRING CONVERSION
        if user is None:
            user = "Unknown"
        else:
            user = str(user)
        if "\\" in user:
            user = user.split("\\")[-1]  # Remove domain prefix like "SKG\"

        # Age calculation using warranty.startDate from NinjaOne
        # Get warranty start date from references.warranty.startDate
        warranty_start = device.get("references", {}).get("warranty", {}).get("startDate", 0)
        age_value = None  # Default to None if no warranty data

        if warranty_start and warranty_start != 0:
            try:
                warranty_start_date = datetime.fromtimestamp(warranty_start)
                age_years = (datetime.now() - warranty_start_date).days / 365.25

                # Round to 1 decimal place
                age_rounded = round(age_years, 1)

                # Return numeric value only (no "years" string)
                age_value = age_rounded
            except:
                age_value = None
        else:
            # If warranty.startDate not present or is 0, set age to None
            age_value = None

        # Calculate free storage from raw data
        free_storage_gb = device.get("free_space_gb", 0)

        # Get location with proper fallback for empty/None values
        location = device.get("location", "Unknown")
        # ADD STRING CONVERSION AND STRIP
        if location is None:
            location = "Unknown"
        else:
            location = str(location).strip()
        if not location or location == "":
            location = "Unknown"
        if not location or location.strip() == "":
            location = "Unknown"

        return {
            "device": device.get("workstation", "Unknown"),
            "lastLoggedInUser": user,
            "manufacturer": device.get("make", "Unknown"),
            "model": device.get("model", "Unknown"),
            "os": device.get("os", "Unknown"),
            "ram": f"{device.get('ram_gb', 0):.1f}GB",
            "cpu": device.get("cpu", "Unknown"),
            "total_storage": f"{device.get('storage_gb', 0):.1f}GB",
            "free_storage": f"{free_storage_gb:.1f}GB",
            "age": age_value,  # Numeric value only (e.g., 2.4, 5, 6.8), 0 if no warranty data
            "location": location
        }

    def _create_error_response(self, error_message: str) -> Dict[str, Any]:
        """Create error response for failed transformations."""
        return {
            "status": "error",
            "error": error_message,
            "timestamp": datetime.now().isoformat(),
            "organization": {
                "id": "unknown",
                "name": "Error Processing Organization",
                "report_date": datetime.now().isoformat()
            },
            "summary": {},
            "charts": {},
            "tables": {},
            "metrics": {},
            "alerts": [
                {
                    "type": "critical",
                    "message": f"Failed to generate report: {error_message}",
                    "action_required": "Contact system administrator"
                }
            ],
            "execution_info": {
                "generated_at": datetime.now().isoformat(),
                "data_sources_processed": [],
                "report_type": "Error Report"
            }
        }