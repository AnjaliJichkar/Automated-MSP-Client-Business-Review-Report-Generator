"""
Bitdefender Processor
Processes Bitdefender GravityZone API data into chart and table format
"""

import logging
from typing import Dict, Any, List, Optional
from app.clients.bitdefender_client import BitdefenderClient

logger = logging.getLogger(__name__)


class BitdefenderProcessor:
    """Processes Bitdefender GravityZone data for security reporting"""

    def __init__(self, account_id: int, bitdefender_company_id: str):
        """
        Initialize Bitdefender processor

        Args:
            account_id: Account ID for credential lookup
            bitdefender_company_id: Bitdefender company ID from organization_integrations
        """
        self.account_id = account_id
        self.company_id = bitdefender_company_id

        api_key = self._get_bitdefender_api_key()
        self.client = BitdefenderClient(api_key)

        logger.info(f"BitdefenderProcessor initialized for account_id={account_id}, company_id={bitdefender_company_id}")

    def _get_bitdefender_api_key(self) -> str:
        """
        Fetch and decrypt Bitdefender API key from integration_credentials

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

            bitdefender_creds = decrypted_creds.get('bitdefender', {})
            api_key = bitdefender_creds.get('bitdefender_api_key')

            if not api_key:
                raise ValueError(f"Bitdefender API key not found for account_id={self.account_id}")

            logger.info(f"Successfully retrieved Bitdefender API key for account_id={self.account_id}")
            return api_key

        except Exception as e:
            logger.error(f"Failed to retrieve Bitdefender API key: {e}")
            raise

    def fetch_all_data(self, month_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Fetch all Bitdefender data from API

        Args:
            month_name: Accepted for caller compatibility, not used.

        Returns:
            Dict with raw API responses
        """
        logger.info(f"Fetching Bitdefender data for company_id={self.company_id}")

        raw_data = {
            "company_details": self.client.get_company_details(self.company_id),
            "endpoints_list": self.client.get_all_endpoints_paginated(self.company_id, per_page=10),
            "network_inventory": self.client.get_all_network_inventory_paginated(self.company_id, per_page=1000),
        }

        logger.info(f"Fetched Bitdefender data: {len(raw_data['endpoints_list'])} endpoints, "
                   f"{len(raw_data['network_inventory'])} inventory items")

        return raw_data

    def process_all_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process raw Bitdefender data into chart and table format

        Args:
            raw_data: Raw data from fetch_all_data()

        Returns:
            Processed data with charts and tables
        """
        logger.info("Processing Bitdefender data...")

        processed = {
            "bitdefender_metrics": {
                "charts": {},
                "tables": {}
            }
        }

        company_details = raw_data.get("company_details", {})
        endpoints_list = raw_data.get("endpoints_list", [])
        network_inventory = raw_data.get("network_inventory", [])

        processed["bitdefender_metrics"]["charts"]["riskScore_bitdefender"] = self._process_risk_score(company_details)

        # Add managedEndpoints into inventory_summary count
        inventory_summary = self._process_os_summary(endpoints_list)
        managed_count = self._process_managed_endpoints(endpoints_list)
        inventory_summary["count"]["managedEndpoints"] = managed_count
        processed["bitdefender_metrics"]["charts"]["inventory_summary_bitdefender"] = inventory_summary

        processed["bitdefender_metrics"]["tables"]["networkinventory_bitdefender"] = self._process_network_inventory(
            network_inventory, endpoints_list
        )

        logger.info("Bitdefender data processed successfully")
        return processed

    def _process_risk_score(self, company_details: Dict[str, Any]) -> Dict[str, Any]:
        """Extract and format risk score data with null-safe string defaults"""
        risk_score = company_details.get("riskScore", {}) or {}

        return {
            "value": str(risk_score.get("value", 0) or 0),
            "impact": str(risk_score.get("impact", 0) or 0),
            "misconfigurations": str(risk_score.get("misconfigurations", 0) or 0),
            "appVulnerabilities": str(risk_score.get("appVulnerabilities", 0) or 0),
            "humanRisks": str(risk_score.get("humanRisks", 0) or 0),
            "industryModifier": str(risk_score.get("industryModifier", 0) or 0)
        }

    def _process_managed_endpoints(self, endpoints_list: List[Dict[str, Any]]) -> int:
        """Count managed endpoints (those with isManaged=True)"""
        count = sum(1 for endpoint in endpoints_list if endpoint.get("isManaged") is True)
        return count

    def _process_os_summary(self, endpoints_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Process OS distribution and machine types from endpoints_list.

        Args:
            endpoints_list: List of managed endpoints from getEndpointsList

        Returns:
            Dict with nested structure:
            {
                "summary": { windowsWorkstations, windowsServers, macOS, linux },
                "count": { physicalMachines, virtualMachines }
            }
        """
        os_summary = {
            "windowsWorkstations": 0,
            "windowsServers": 0,
            "macOS": 0,
            "linux": 0
        }

        machine_count = {
            "physicalMachines": 0,
            "virtualMachines": 0
        }

        for endpoint in endpoints_list:
            if endpoint.get("isManaged") is not True:
                continue

            machine_type = endpoint.get("machineType")
            if machine_type == 1:
                machine_count["physicalMachines"] += 1
            elif machine_type in (2, 3):
                machine_count["virtualMachines"] += 1

            os_version = (endpoint.get("operatingSystemVersion") or "").lower()

            if "windows" in os_version:
                if any(kw in os_version for kw in ["server", "multi-session", "datacenter"]):
                    os_summary["windowsServers"] += 1
                else:
                    os_summary["windowsWorkstations"] += 1
            elif any(kw in os_version for kw in ["mac", "macos", "os x", "darwin"]):
                os_summary["macOS"] += 1
            elif any(kw in os_version for kw in [
                "linux", "ubuntu", "centos", "redhat", "red hat",
                "debian", "suse", "fedora", "rhel", "oracle linux", "alma", "rocky"
            ]):
                os_summary["linux"] += 1

        logger.info(f"Inventory: Physical={machine_count['physicalMachines']}, Virtual={machine_count['virtualMachines']}")
        logger.info(f"OS: WinWS={os_summary['windowsWorkstations']}, WinSrv={os_summary['windowsServers']}, "
                   f"Mac={os_summary['macOS']}, Linux={os_summary['linux']}")

        return {
            "summary": os_summary,
            "count": machine_count
        }

    def _process_network_inventory(self, network_inventory: List[Dict[str, Any]],
                                    endpoints_list: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Process network inventory to extract module deployment status.
        Simplified: counts modules as enabled or not-enabled per managed endpoint.

        Args:
            network_inventory: Network inventory items from API
            endpoints_list: Endpoints list (used to get managed endpoint IDs)

        Returns:
            List of module objects with enable/notenable counts
        """
        module_mapping = {
            "antimalware": "Antimalware",
            "advancedThreatControl": "Advanced Threat Control",
            "advancedAntiExploit": "Advanced Anti-Exploit",
            "firewall": "Firewall",
            "networkAttackDefense": "Network Protection",
            "deviceControl": "Device Control",
            "encryption": "Encryption",
            "patchManagement": "Patch Management",
            "edrSensor": "EDR Sensor",
            "powerUser": "Power User",
            "exchange": "Exchange Protection",
            "containerProtection": "Container Protection",
            "integrityMonitoring": "Integrity Monitoring",
            "phASR": "PHASR"
        }

        # Count enabled modules per managed endpoint
        module_stats = {module: 0 for module in module_mapping.keys()}

        # Get managed endpoint IDs from endpoints_list
        managed_endpoint_ids = {ep.get("id") for ep in endpoints_list} if endpoints_list else set()
        managed_count = len(managed_endpoint_ids)

        for item in network_inventory:
            # Only process endpoint types (5=computer, 6=virtualMachine, 7=ec2Instance)
            if item.get("type") not in (5, 6, 7):
                continue
            # Only count managed endpoints
            if item.get("id") not in managed_endpoint_ids:
                continue

            modules = (item.get("details") or {}).get("modules") or {}
            for module_key in module_mapping.keys():
                if modules.get(module_key) is True:
                    module_stats[module_key] += 1

        logger.info(f"Security Modules: {len(module_mapping)} modules processed across {managed_count} managed endpoints")

        # Build output with enable/notenable
        network_inventory_list = [
            {
                "Module": module_key,
                "enable": module_stats[module_key],
                "notenable": managed_count - module_stats[module_key],
                "displayName": module_mapping[module_key]
            }
            for module_key in module_mapping.keys()
        ]

        return network_inventory_list
