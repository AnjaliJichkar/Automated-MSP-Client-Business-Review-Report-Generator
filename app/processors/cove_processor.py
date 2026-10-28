"""
Cove Data Protection Processor
Handles data fetching and processing for Cove Backup Management platform
"""

import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# I78 active-data-sources bitmask — each 3-char code maps to a source name
_D_CODE_MAP = {
    "D01": "files_folders",
    "D02": "system_state",
    "D03": "mssql",
    "D04": "exchange",
    "D06": "network_shares",
    "D08": "vmware",
    "D10": "mssql",
    "D12": "oracle",
    "D14": "hyperv",
    "D15": "mysql",
    "D16": "virtual_dr",
    "D17": "bare_metal",
    "D19": "m365_exchange",
    "D20": "m365_onedrive",
    "D23": "m365_teams",
}


class CoveProcessor:
    """Processor for Cove Data Protection data."""

    def __init__(
        self,
        account_id: int = None,
        cove_customer_id: str = None
    ):
        """
        Initialize CoveProcessor.

        Args:
            account_id: Account ID for fetching credentials from integration_credentials table
            cove_customer_id: Cove customer ID from organization_integrations (integration_id=5)
        """
        self.customer_id = cove_customer_id
        self.client = None

        if not account_id:
            logger.warning("No account_id provided - Cove data will be skipped")
            return

        try:
            from app.clients.cove_client import CoveAPIClient

            self.client = CoveAPIClient(account_id=account_id)
            logger.info(f"Cove processor initialized for account_id: {account_id}")

        except Exception as e:
            logger.error(f"Failed to initialize Cove client: {e}")
            self.client = None

    def fetch_all_data(self, customer_id: str = None) -> Dict[str, Any]:
        """
        Fetch all Cove data for the customer.

        Makes ONE API call to get all data (not multiple calls like before).

        Args:
            customer_id: Cove customer ID (if None, uses self.customer_id)

        Returns:
            Dictionary containing raw Cove API response
        """
        if not self.client:
            logger.warning("⚠Cove client not initialized - returning empty data")
            return {}

        customer_id = customer_id or self.customer_id

        if not customer_id:
            logger.error("No customer_id provided for Cove data fetch")
            return {}

        logger.info(f"Fetching Cove data for customer: {customer_id}")

        try:
            logger.info("Fetching account statistics...")
            response = self.client.get_account_statistics(
                customer_id=customer_id,
                columns=[
                    "I1", "I14", "I16", "I32", "I81", "PN", "GM", "G@", "JM",
                    "D1", "D2", "D3", "D4", "D6", "D8", "D10", "D12",
                    "D14", "D15", "D16", "D17", "D19", "D20", "D23", "I78",
                ],
                totals=["SUM(I14)", "SUM(GM)", "SUM(G@)", "SUM(JM)"],
                start_record=0,
                records_count=200
            )
            logger.info("Account statistics fetched successfully")

            storage_nodes_raw = {}
            try:
                storage_nodes_raw = self.client.get_storage_nodes(customer_id)
                logger.info("Storage nodes fetched successfully")
            except Exception as e:
                logger.warning(f"Cove storage nodes fetch failed (non-fatal): {e}")

            return {"statistics": response, "storage_nodes": storage_nodes_raw}

        except Exception as e:
            logger.error(f"Failed to fetch Cove data: {e}")
            return {}

    def process_all_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process raw Cove data into structured metrics.

        Processes the single API response to extract 5 charts:
        1. Total Storage Used
        2. Device Count
        3. Device Distribution (Workstation/Server/Undefined)
        4. Asset Distribution (Physical/Virtual/Undefined)
        5. Retention Policy Distribution

        Args:
            raw_data: Raw data from fetch_all_data() (single API response)

        Returns:
            Processed data with cove_metrics
        """
        if not raw_data:
            logger.warning("No raw data provided - returning default metrics")
            return {
                "cove_metrics": self._get_default_metrics(),
                "cove_insights": self._get_default_insights(),
                "tables": {"inventory_cove": []},
            }

        # Handle new shape {"statistics": ..., "storage_nodes": ...} or old plain shape
        if "statistics" in raw_data:
            stats_raw = raw_data.get("statistics") or {}
            storage_raw = raw_data.get("storage_nodes") or {}
        else:
            stats_raw = raw_data
            storage_raw = {}

        if not stats_raw or 'result' not in stats_raw:
            logger.warning("No statistics data in raw response - returning default metrics")
            return {
                "cove_metrics": self._get_default_metrics(),
                "cove_insights": self._get_default_insights(),
                "tables": {"inventory_cove": []},
            }

        logger.info("Processing Cove data...")

        metrics = {}

        # Extract data from API response (use 'or' to handle None values)
        result_data = stats_raw.get('result') or {}
        devices = result_data.get('result') or []  # Array of device records
        total_statistics = result_data.get('totalStatistics') or []

        # ============================================================
        # 1. Total Storage Used (from totalStatistics)
        # Convert from bytes to TB (1 TB = 10^12 = 1,000,000,000,000 bytes)
        # totalStatistics is array of objects: [{"SUM(G@)": "0"}, {"SUM(GM)": "0"}, {"SUM(I14)": "4188932699497"}]
        # ============================================================
        if total_statistics and len(total_statistics) > 0:
            # Search for keys in the array
            total_storage_str = '0'
            user_mailboxes_str = '0'
            shared_mailboxes_str = '0'
            onedrive_accounts_str = '0'

            for stat_obj in total_statistics:
                if 'SUM(I14)' in stat_obj:
                    total_storage_str = stat_obj['SUM(I14)']
                if 'SUM(GM)' in stat_obj:
                    user_mailboxes_str = stat_obj['SUM(GM)']
                if 'SUM(G@)' in stat_obj:
                    shared_mailboxes_str = stat_obj['SUM(G@)']
                if 'SUM(JM)' in stat_obj:
                    onedrive_accounts_str = stat_obj['SUM(JM)']

            # Parse and convert storage to TB
            try:
                total_storage_bytes = int(total_storage_str)
                total_storage_tb = round(total_storage_bytes / 1_000_000_000_000, 2)  # 2 decimal places
                metrics['total_storage_used'] = total_storage_tb
            except (ValueError, TypeError):
                metrics['total_storage_used'] = 0

            # Parse user mailboxes
            try:
                metrics['user_mailboxes'] = int(user_mailboxes_str)
            except (ValueError, TypeError):
                metrics['user_mailboxes'] = 0

            # Parse shared mailboxes
            try:
                metrics['shared_mailboxes'] = int(shared_mailboxes_str)
            except (ValueError, TypeError):
                metrics['shared_mailboxes'] = 0

            # Parse OneDrive user accounts
            try:
                metrics['onedrive_user_accounts'] = int(onedrive_accounts_str)
            except (ValueError, TypeError):
                metrics['onedrive_user_accounts'] = 0
        else:
            metrics['total_storage_used'] = 0
            metrics['user_mailboxes'] = 0
            metrics['shared_mailboxes'] = 0
            metrics['onedrive_user_accounts'] = 0

        # ============================================================
        # 2. Device Count (count of devices array)
        # ============================================================
        metrics['device_count'] = len(devices) if devices else 0

        # ============================================================
        # 3. Device Distribution (Workstation vs Server)
        # ============================================================
        device_dist = {"Workstation": 0, "Server": 0, "Undefined": 0}

        for device in devices:
            settings = device.get('Settings') or []
            for setting in settings:
                if 'I32' in setting:
                    os_type = setting['I32']
                    # Convert to string for comparison (handles both int and string values)
                    os_type_str = str(os_type)
                    if os_type_str == "1":
                        device_dist['Workstation'] += 1
                    elif os_type_str == "2":
                        device_dist['Server'] += 1
                    elif os_type_str == "0":
                        device_dist['Undefined'] += 1
                    else:
                        device_dist['Undefined'] += 1
                    break  # Found I32, move to next device

        metrics['device_distribution'] = device_dist

        # ============================================================
        # 4. Asset Distribution (Physical vs Virtual)
        # ============================================================
        asset_dist = {"Physical": 0, "Virtual": 0, "Undefined": 0}

        for device in devices:
            settings = device.get('Settings') or []
            for setting in settings:
                if 'I81' in setting:
                    physicality = str(setting['I81']).lower()
                    if 'physical' in physicality:
                        asset_dist['Physical'] += 1
                    elif 'virtual' in physicality:
                        asset_dist['Virtual'] += 1
                    else:
                        asset_dist['Undefined'] += 1
                    break  # Found I81, move to next device

        metrics['asset_distribution'] = asset_dist

        # ============================================================
        # 5. Retention Policy Distribution
        # ============================================================
        retention_dist = {}

        for device in devices:
            settings = device.get('Settings') or []
            policy = None

            for setting in settings:
                if 'PN' in setting:
                    policy = setting['PN']
                    break

            if policy:
                if policy not in retention_dist:
                    retention_dist[policy] = 0
                retention_dist[policy] += 1

        metrics['retention_policy_distribution'] = retention_dist

        logger.info("Cove data processed successfully")
        logger.info(f"   Storage Used: {metrics['total_storage_used']} TB")
        logger.info(f"   Device Count: {metrics['device_count']}")
        logger.info(f"   User Mailboxes: {metrics['user_mailboxes']}, Shared Mailboxes: {metrics['shared_mailboxes']}, OneDrive Accounts: {metrics['onedrive_user_accounts']}")
        logger.info(f"   Workstations: {device_dist['Workstation']}, Servers: {device_dist['Server']}")

        cove_insights = self._build_cove_insights(devices, storage_raw)
        inventory_table = self._build_inventory_table(devices)
        return {
            "cove_metrics": metrics,
            "cove_insights": cove_insights,
            "tables": {"inventory_cove": inventory_table},
        }

    def _parse_i78(self, i78_str: str) -> dict:
        """Parse I78 string like 'D01D02D19' into per-source boolean flags."""
        flags = {name: False for name in set(_D_CODE_MAP.values())}
        if not i78_str or not isinstance(i78_str, str):
            return flags
        codes = [i78_str[i:i+3] for i in range(0, len(i78_str), 3)]
        for code in codes:
            name = _D_CODE_MAP.get(code)
            if name:
                flags[name] = True
        return flags

    def _build_cove_insights(self, devices: list, storage_raw: dict) -> dict:
        """Build cove_insights from device list and storage nodes response."""
        try:
            coverage_flags = {name: False for name in set(_D_CODE_MAP.values())}
            device_list = []

            for device in devices:
                try:
                    settings = device.get('Settings') or []
                    s = {}
                    for item in settings:
                        if isinstance(item, dict):
                            s.update(item)

                    device_name  = s.get("I1", "Unknown")
                    i78_raw      = s.get("I78", "") or ""
                    used_storage = int(s.get("I14", 0) or 0)
                    os_type_raw  = str(s.get("I32", "0") or "0")
                    physicality  = s.get("I81", "") or ""
                    retention    = s.get("PN", "") or ""

                    os_label = {"0": "Undefined", "1": "Workstation", "2": "Server"}.get(os_type_raw, os_type_raw)

                    ds = self._parse_i78(i78_raw)
                    for k, v in ds.items():
                        if v:
                            coverage_flags[k] = True

                    device_list.append({
                        "device_name":             device_name,
                        "used_storage_gb":         round(used_storage / 1e9, 2),
                        "active_data_sources_raw": i78_raw,
                        "os_type":                 os_label,
                        "physicality":             physicality,
                        "retention_policy":        retention,
                        "data_sources":            ds,
                    })
                except Exception as e:
                    logger.warning(f"Cove: error parsing device record, skipping: {e}")
                    continue

            # Storage nodes — offsite replication check
            nodes_raw = storage_raw.get("result") or {}
            if isinstance(nodes_raw, list):
                nodes = nodes_raw
            elif isinstance(nodes_raw, dict):
                nodes = nodes_raw.get("result") or nodes_raw.get("nodes") or []
            else:
                nodes = []

            node_roles = [n.get("StorageNodeRole") or n.get("Role") or "Unknown" for n in nodes]
            has_offsite = any(r in ("Cabs", "Reserve") for r in node_roles)

            # DR derived from D16/D17 flags
            has_virtual_dr = coverage_flags.get("virtual_dr", False)
            has_bare_metal  = coverage_flags.get("bare_metal", False)

            missing_critical = [
                k for k, v in coverage_flags.items()
                if not v and k in ("mssql", "exchange", "vmware", "hyperv", "oracle")
            ]

            return {
                "insight_1_backup_coverage": {
                    "org_wide_coverage_flags": coverage_flags,
                    "devices": device_list,
                },
                "insight_2_offsite_replication": {
                    "storage_nodes_raw": nodes,
                    "node_roles_found":  node_roles,
                    "has_offsite_replication": has_offsite,
                },
                "insight_3_disaster_recovery": {
                    "virtual_dr_active": has_virtual_dr,
                    "bare_metal_active": has_bare_metal,
                    "note": "DR status derived from D16/D17 column values per device.",
                },
                "ai_flags": {
                    "incomplete_backup_coverage": len(missing_critical) > 0,
                    "missing_critical_sources":   missing_critical,
                    "no_offsite_replication":     not has_offsite,
                    "no_dr_plan":                 not has_virtual_dr and not has_bare_metal,
                },
            }

        except Exception as e:
            logger.error(f"Cove: _build_cove_insights failed: {e}")
            return self._get_default_insights()

    def _build_inventory_table(self, devices: list) -> list:
        """
        Build inventory_cove table — one row per device (AccountId), direct raw values.

        Reuses the same Settings-flatten pattern and I32 os-type label map
        already used in _build_cove_insights. Does not alter any existing logic.
        """
        inventory = []

        for device in devices:
            try:
                settings = device.get('Settings') or []
                s = {}
                for item in settings:
                    if isinstance(item, dict):
                        s.update(item)

                device_name  = s.get("I1", "Unknown")
                used_storage = int(s.get("I14", 0) or 0)
                os_type_raw  = str(s.get("I32", "0") or "0")
                physicality  = s.get("I81", "Undefined")
                os_version   = s.get("I16") or "Undefined"

                os_label = {"0": "Undefined", "1": "Workstation", "2": "Server"}.get(os_type_raw, os_type_raw)

                inventory.append({
                    "Device_name":        device_name,
                    "Used_Storage":      f"{round(used_storage / 1e9, 2)} GB",
                    "OS_Type":            os_label,
                    "Device_Physicality": physicality,
                    "OS_Version":         os_version,
                })
            except Exception as e:
                logger.warning(f"Cove: error building inventory row, skipping: {e}")
                continue

        return inventory

    def _get_default_insights(self) -> dict:
        return {
            "insight_1_backup_coverage":    {"org_wide_coverage_flags": {}, "devices": []},
            "insight_2_offsite_replication": {"storage_nodes_raw": [], "node_roles_found": [], "has_offsite_replication": False},
            "insight_3_disaster_recovery":  {"virtual_dr_active": False, "bare_metal_active": False, "note": ""},
            "ai_flags":                     {"incomplete_backup_coverage": False, "missing_critical_sources": [], "no_offsite_replication": False, "no_dr_plan": False},
        }

    def _get_default_metrics(self) -> Dict[str, Any]:
        """
        Return default empty metrics structure.

        Returns:
            Dictionary with default/empty metrics
        """
        return {
            "total_storage_used": 0,
            "device_count": 0,
            "user_mailboxes": 0,
            "shared_mailboxes": 0,
            "onedrive_user_accounts": 0,
            "device_distribution": {"Workstation": 0, "Server": 0, "Undefined": 0},
            "asset_distribution": {"Physical": 0, "Virtual": 0, "Undefined": 0},
            "retention_policy_distribution": {}
        }

    def test_connection(self) -> bool:
        """
        Test Cove API connection.

        Returns:
            True if connection successful, False otherwise
        """
        if not self.client:
            return False

        try:
            return self.client.test_connection()
        except Exception as e:
            logger.error(f" Cove connection test failed: {e}")
            return False