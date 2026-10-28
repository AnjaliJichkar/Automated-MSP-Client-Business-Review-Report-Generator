"""
NinjaOne Data Processor

This module handles all NinjaOne data fetching, processing, and analysis.
Extracted from main.py to improve modularity.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import Counter
# Add path resolution for local running
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
security_system_root = os.path.join(current_dir, '..', '..')
if security_system_root not in sys.path:
    sys.path.insert(0, security_system_root)

# Updated imports for new app/ structure
from app.core.config.settings import config_manager
from app.clients.ninjaone_client import NinjaOneAPIClient

logger = logging.getLogger(__name__)


class NinjaOneProcessor:
    """Handles all NinjaOne data operations."""

    def __init__(self, account_id: int = None, ninjaone_org_id: str = None, credential_id: str = None):
        """
        Initialize NinjaOneProcessor with account-based credentials.

        Args:
            account_id: Account ID for fetching credentials from integration_credentials table (NEW)
            ninjaone_org_id: NinjaOne organization ID to fetch data for
            credential_id: DEPRECATED - Legacy UUID for old user_credentials table
        """
        # NEW: Load credentials from account_id (integration_credentials table)
        if account_id is not None:
            from app.core.config.supabase import SupabaseCredentialManager

            credential_manager = SupabaseCredentialManager()
            credentials = credential_manager.get_credentials_by_account_id(account_id)

            if not credentials:
                raise ValueError(f"No credentials found for account_id: {account_id}")

            # Extract NinjaOne credentials from decrypted data
            ninjaone_creds = credentials.get('ninjaone', {})

            # ADD VALIDATION HERE
            client_id = ninjaone_creds.get('ninjaone_client_id')
            client_secret = ninjaone_creds.get('ninjaone_client_secret')
            instance_url = ninjaone_creds.get('ninjaone_instance_url')

            # Check if required fields are present
            if not client_id or not client_secret or not instance_url:
                logger.warning("NinjaOne credentials are incomplete - NinjaOne data will be skipped")
                self.client = None
                self.config = None
                self.org_id = None
                return

            self.config = {
                'ninjaone_client_id': client_id,
                'ninjaone_client_secret': client_secret,
                'ninjaone_instance_url': instance_url,
                'ninjaone_scopes': ninjaone_creds.get('ninjaone_scopes') or 'monitoring',
            }

            logger.info(f" Loaded credentials from account_id: {account_id}")

        # OLD: Fallback to legacy credential_id method
        elif credential_id is not None:
            logger.warning("Using DEPRECATED credential_id method. Please migrate to account_id.")
            config = config_manager.load_credentials(credential_id)

            # ADD VALIDATION HERE TOO
            client_id = config.get('ninjaone_client_id')
            client_secret = config.get('ninjaone_client_secret')
            instance_url = config.get('ninjaone_instance_url')

            if not client_id or not client_secret or not instance_url:
                logger.warning("NinjaOne credentials are incomplete - NinjaOne data will be skipped")
                self.client = None
                self.config = None
                self.org_id = None
                return

            self.config = config

        else:
            raise ValueError("Either account_id or credential_id must be provided")

        # Only initialize client if credentials are complete
        if self.config:
            # Use dynamic org_id if provided, otherwise fall back to config (no hardcoded default)
            self.org_id = ninjaone_org_id or self.config.get('target_org_id')

            # Log warning if no org_id is provided
            if not self.org_id:
                logger.warning("No ninjaone_org_id provided - organization identifier will be 'Unknown'")

            self.client = NinjaOneAPIClient(
                client_id=self.config['ninjaone_client_id'],
                client_secret=self.config['ninjaone_client_secret'],
                instance_url=self.config['ninjaone_instance_url'],
                org_id=self.org_id,
                scopes=self.config.get('ninjaone_scopes')
            )
        else:
            # Create a dummy client that returns empty data instead of None
            self.client = None
            self.org_id = None
            logger.warning("NinjaOne credentials incomplete - will return empty data")

    def fetch_all_data(self, use_time_filter: bool = True, month_name: str = None) -> Dict[str, Any]:
        """
        Fetch all NinjaOne data with selective time filtering.

        CRITICAL: Compliance data uses ALL TIME for current status.
        Only historical installation data is filtered to user-selected month.

        Args:
            use_time_filter: Whether to apply time filtering for historical data
            month_name: Month in 'month_year' format (e.g., "november_2024", "december_2024")
        """
        data = {}

        # Calculate date range for historical data only
        start_timestamp = None
        end_timestamp = None

        # Initialize month filter context
        self._current_month_filter = None

        if use_time_filter:
            # Import month selector for timestamp calculation
            from app.utils.month_selector import MonthSelector

            try:
                month_selector = MonthSelector()
                start_timestamp, end_timestamp = month_selector.get_month_timestamps(month_name)

                # Store filter for manual timestamp filtering in patch logic
                self._current_month_filter = (start_timestamp, end_timestamp)

                # Convert timestamps back to datetime for logging
                start_date = datetime.fromtimestamp(start_timestamp)
                end_date = datetime.fromtimestamp(end_timestamp)

                # DEBUG: Log the exact date range being used
                print(f"DEBUG: Today is {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"DEBUG: User selected month: {month_name if month_name else 'Previous month'}")
                print(f"DEBUG: Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
                print(f"DEBUG: Timestamps: {start_timestamp} to {end_timestamp}")

                logger.info(f"NinjaOne filtering for user-selected month ({month_name}): {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
            except Exception as e:
                logger.warning(f"Failed to calculate month timestamps: {e}")
                # Fallback to previous month calculation
                today = datetime.now()
                first_day_of_current_month = today.replace(day=1)
                end_of_previous_month = first_day_of_current_month - timedelta(days=1)
                start_of_previous_month = end_of_previous_month.replace(day=1)

                start_timestamp = start_of_previous_month.timestamp()
                end_timestamp = end_of_previous_month.timestamp()
                logger.info(f"Using fallback previous month filter: {start_of_previous_month.strftime('%Y-%m-%d')} to {end_of_previous_month.strftime('%Y-%m-%d')}")

                # Store fallback filter for manual timestamp filtering in patch logic
                self._current_month_filter = (start_timestamp, end_timestamp)

        # === CURRENT STATUS DATA (NO TIME FILTER) ===
        try:
            logger.debug("Fetching organization info...")
            data['organization_info'] = self.client.get_organization_info()
        except Exception as e:
            logger.error(f"Failed to fetch organization info: {e}")
            # FIXED: Use self.config instead of undefined config variable
            org_id = self.org_id
            data['organization_info'] = {"id": org_id, "name": f"Organization {org_id}"}

        try:
            logger.debug("Fetching locations (all organizations)...")
            data['locations'] = self.client.get_locations()
        except Exception as e:
            logger.error(f"Failed to fetch locations: {e}")
            data['locations'] = []

        try:
            logger.debug("Fetching devices (current status)...")
            data['devices'] = self.client.get_devices()
        except Exception as e:
            logger.error(f"Failed to fetch devices: {e}")
            data['devices'] = []

        try:
            logger.debug("Fetching detailed devices (current status)...")
            data['devices_detailed'] = self.client.get_devices_detailed()
        except Exception as e:
            logger.error(f"Failed to fetch detailed devices: {e}")
            data['devices_detailed'] = []

        try:
            logger.debug("Fetching OS patches (CURRENT STATUS - for compliance calculation)...")
            data['os_patches'] = self.client.get_os_patches()  # NO TIME FILTER
        except Exception as e:
            logger.error(f"Failed to fetch OS patches: {e}")
            data['os_patches'] = []

        try:
            logger.debug("Fetching software patches (CURRENT STATUS - for compliance calculation)...")
            data['software_patches'] = self.client.get_software_patches()  # NO TIME FILTER
        except Exception as e:
            logger.error(f"Failed to fetch software patches: {e}")
            data['software_patches'] = []

        # === HISTORICAL DATA (WITH TIME FILTER) ===
        try:
            if use_time_filter:
                logger.debug(f"Fetching OS patch installs (USER-SELECTED MONTH: {month_name} - for historical reporting)...")
                data['os_patch_installs'] = self.client.get_os_patch_installs(start_timestamp, end_timestamp)
            else:
                logger.debug("Fetching OS patch installs (all time)...")
                data['os_patch_installs'] = self.client.get_os_patch_installs()
        except Exception as e:
            logger.error(f"Failed to fetch OS patch installs: {e}")
            data['os_patch_installs'] = []

        try:
            if use_time_filter:
                logger.debug(f"Fetching software patch installs (USER-SELECTED MONTH: {month_name})...")
                data['software_patch_installs'] = self.client.get_software_patch_installs(start_timestamp, end_timestamp)
            else:
                logger.debug("Fetching software patch installs (all time)...")
                data['software_patch_installs'] = self.client.get_software_patch_installs()
        except Exception as e:
            logger.error(f"Failed to fetch software patch installs: {e}")
            data['software_patch_installs'] = []

        logger.info(f"NinjaOne data fetched:")
        logger.info(f"   → OS patches (current status): {len(data['os_patches'])}")
        logger.info(f"   → Software patches (current status): {len(data['software_patches'])}")
        logger.info(f"   → OS patch installs ({f'user-selected month ({month_name})' if use_time_filter else 'all time'}): {len(data['os_patch_installs'])}")
        logger.info(f"   → Software patch installs ({f'user-selected month ({month_name})' if use_time_filter else 'all time'}): {len(data['software_patch_installs'])}")

        # DEBUG: Add detailed counts for troubleshooting
        print(f"DEBUG: Raw data counts:")
        print(f"   OS patches: {len(data['os_patches'])}")
        print(f"   OS patch installs: {len(data['os_patch_installs'])}")
        print(f"   Software patches: {len(data['software_patches'])}")
        print(f"   Software patch installs: {len(data['software_patch_installs'])}")

        if data['os_patch_installs']:
            installed_count = len([p for p in data['os_patch_installs'] if p.get('status', '').upper() == 'INSTALLED'])
            failed_count = len([p for p in data['os_patch_installs'] if p.get('status', '').upper() == 'FAILED'])
            print(f"   OS installs breakdown: {installed_count} INSTALLED, {failed_count} FAILED")

        if data['os_patches']:
            approved_count = len([p for p in data['os_patches'] if p.get('status', '').upper() == 'APPROVED'])
            print(f"   OS patches approved: {approved_count}")

        return data

    def process_all_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process all NinjaOne raw data into final metrics."""
        devices = raw_data.get('devices', [])
        devices_detailed = raw_data.get('devices_detailed', [])
        os_patches = raw_data.get('os_patches', [])
        os_patch_installs = raw_data.get('os_patch_installs', [])
        software_patches = raw_data.get('software_patches', [])
        software_patch_installs = raw_data.get('software_patch_installs', [])
        locations = raw_data.get('locations', [])

        # Create location mapping: {location_id: location_name}
        location_mapping = {}
        for location in locations:
            location_id = location.get('id')
            location_name = location.get('name', 'Unknown')
            if location_id:
                location_mapping[location_id] = location_name

        logger.debug(f"Created location mapping with {len(location_mapping)} locations")

        # Calculate all metrics
        infrastructure_metrics = self._calculate_infrastructure_metrics(devices)
        patch_enablement = self._analyze_patch_enablement(devices, os_patches, software_patches, os_patch_installs, software_patch_installs)
        patch_metrics = self._calculate_comprehensive_patch_metrics(
            os_patches, software_patches, os_patch_installs, devices, software_patch_installs
        )
        device_spread = self._analyze_device_spread(devices)
        formatted_devices = self._format_device_details(devices_detailed, location_mapping)

        # Use self.org_id (already set in __init__) instead of re-reading from config
        org_id = self.org_id or "Unknown"
        org_name = raw_data.get('organization_info', {}).get('name', f'Organization {org_id}')

        return {
            "execution_info": {
                "timestamp": datetime.now().isoformat(),
                "organization_id": org_id,
                "organization_name": org_name,
                "data_sources": ["NinjaOne"]
            },
            "infrastructure_metrics": infrastructure_metrics,
            "patch_enablement": patch_enablement,
            "patch_metrics": patch_metrics["patch_metrics"],
            "patch_compliance": patch_metrics["patch_compliance"],
            "top_failed_devices": patch_metrics["top_failed_devices"],
            "device_spread": device_spread,
            "device_details": formatted_devices["workstation_devices"],  # Keep backward compatibility
            "device_details_workstation": formatted_devices["workstation_devices"],
            "device_details_server": formatted_devices["server_devices"],
            "raw_data_counts": {
                "devices": len(devices),
                "devices_detailed": len(devices_detailed),
                "os_patches": len(os_patches),
                "os_patch_installs": len(os_patch_installs),
                "software_patch_installs": len(software_patch_installs),
                "software_patches": len(software_patches)
            },
            "raw_data_content": {
                "os_patches": os_patches,
                "os_patch_installs": os_patch_installs,
                "software_patches": software_patches,
                "software_patch_installs": software_patch_installs,
                "devices": devices
            }
        }

    def _calculate_infrastructure_metrics(self, devices: List[Dict]) -> Dict[str, Any]:
        """Calculate infrastructure metrics."""
        total_devices = len(devices)
        online_devices = sum(1 for d in devices if not d.get('offline', True))
        offline_devices = total_devices - online_devices
        online_percentage = (online_devices / total_devices * 100) if total_devices > 0 else 0

        return {
            "total_devices": total_devices,
            "online_devices": online_devices,
            "offline_devices": offline_devices,
            "online_percentage": round(online_percentage, 1)
        }

    def _bytes_to_gb(self, bytes_value):
        """Convert bytes to GB with 2 decimal places."""
        if bytes_value == 0:
            return 0
        return round(bytes_value / (1024 ** 3), 2)

    def _format_device_details(self, devices_detailed: List[Dict], location_mapping: Dict[int, str] = None) -> Dict[str, List[Dict]]:
        """Format device detailed information separated by nodeClass (workstations vs servers)."""
        workstation_devices = []
        server_devices = []

        # Use empty dict if no location mapping provided
        if location_mapping is None:
            location_mapping = {}

        for device in devices_detailed:
            # Get nodeClass and check case-insensitively
            node_class = device.get("nodeClass", "").upper()

            # Get location name from mapping
            location_id = device.get("locationId")
            location_name = location_mapping.get(location_id, "Unknown")

            # Use displayName if available and not empty, otherwise fallback to systemName
            device_name = device.get("displayName") or device.get("systemName", "")

            # Standard fields with VM guest fallbacks
            os_name = device.get("os", {}).get("name", "") or device.get("guestOSFullName", "")
            ram_bytes = device.get("memory", {}).get("capacity", 0) or device.get("memorySize", 0)
            make = device.get("system", {}).get("manufacturer", "")
            model = device.get("system", {}).get("model", "")

            # VM guest fallbacks for make/model
            if not make and device.get("deviceType"):
                make = "Virtual Machine"
            if not model and device.get("deviceType"):
                model = device.get("deviceType", "")

            formatted_device = {
                "workstation": device_name,
                "user": device.get("lastLoggedInUser", ""),
                "make": make,
                "serial": device.get("system", {}).get("serialNumber", ""),
                "model": model,
                "os": os_name,
                "ram_gb": self._bytes_to_gb(ram_bytes),
                "cpu": "",
                "storage_gb": 0,
                "free_space_gb": 0,
                "created": device.get("created"),
                "nodeClass": node_class,
                "location": location_name,
                "references": device.get("references", {})
            }

            # CPU: standard field first, then VM guest fallback
            processors = device.get("processors", [])
            if processors and len(processors) > 0:
                formatted_device["cpu"] = processors[0].get("name", "")
            elif device.get("cpuCores"):
                cores = device.get("cpuCores", 0)
                formatted_device["cpu"] = f"{cores} Core{'s' if cores != 1 else ''}"

            volumes = device.get("volumes", [])
            total_storage_bytes = 0
            total_free_space_bytes = 0
            for volume in volumes:
                # Check if volume has capacity and freeSpace (cross-platform: Windows, Linux, Mac)
                capacity = volume.get("capacity")
                free_space = volume.get("freeSpace")
                if capacity and free_space:
                    total_storage_bytes += capacity
                    total_free_space_bytes += free_space

            formatted_device["storage_gb"] = self._bytes_to_gb(total_storage_bytes)
            formatted_device["free_space_gb"] = self._bytes_to_gb(total_free_space_bytes)

            # -------------------------------------------------------------------------
            # Device Classification Logic
            #
            # Priority:
            # 1. nodeClass contains "server"          -> Server
            # 2. OS contains "server"                 -> Server
            # 3. OS exists (and is not server)        -> Workstation
            # 4. OS is empty:
            #      a. storage == 0 GB                 -> Skip device
            #      b. storage > 0 GB:
            #            manufacturer/model indicates server
            #                                        -> Server
            #            otherwise                   -> Workstation
            # -------------------------------------------------------------------------
            node_class_lower = (node_class or "").lower()
            device_os_lower = (os_name or "").lower()
            manufacturer_lower = (make or "").lower()
            model_lower = (model or "").lower()

            # 1. Server identified from nodeClass or OS
            if (
                "server" in node_class_lower or
                "server" in device_os_lower
            ):
                server_devices.append(formatted_device)
            # 2. OS exists but is NOT a server
            elif device_os_lower:
                workstation_devices.append(formatted_device)
            # 3. OS is empty -> Apply fallback logic
            else:
                # Skip devices having zero storage
                if formatted_device["storage_gb"] <= 0:
                    continue
                # Determine server using manufacturer/model
                manufacturer_is_server = any(keyword in manufacturer_lower for keyword in [
                    "server",
                    "virtual machine"
                ])
                model_is_server = any(keyword in model_lower for keyword in [
                    "server",
                    "virtual machine",
                    "vmhost",
                    "poweredge",
                    "ax"
                ])
                if manufacturer_is_server or model_is_server:
                    server_devices.append(formatted_device)
                else:
                    workstation_devices.append(formatted_device)

        return {
            "workstation_devices": workstation_devices,
            "server_devices": server_devices
        }

    def _analyze_patch_enablement(self, devices: List[Dict], os_patches: List[Dict], software_patches: List[Dict],
                                  os_patch_installs: List[Dict], software_patch_installs: List[Dict]) -> Dict[str, Any]:
        """
        Analyze patch enablement based on devices that have EITHER:
        1. Current patches available/assigned (os_patches, software_patches)
        2. Historical patch installation activity (os_patch_installs, software_patch_installs)

        COMPREHENSIVE LOGIC: A device is considered "patch management enabled" if it appears in ANY of the 4 data sources,
        indicating patch management is either actively assigning patches OR has installation history.

        Args:
            devices: List of all devices
            os_patches: List of OS patches available/assigned (current status)
            software_patches: List of software patches available/assigned (current status)
            os_patch_installs: List of OS patch installation records (historical actions)
            software_patch_installs: List of software patch installation records (historical actions)
        """
        total_devices = len(devices)

        # Get unique device IDs from current patch assignments
        devices_with_os_patches = set(
            patch.get("deviceId")
            for patch in os_patches
            if patch.get("deviceId")
        )

        devices_with_sw_patches = set(
            patch.get("deviceId")
            for patch in software_patches
            if patch.get("deviceId")
        )

        # Get unique device IDs from historical patch installations
        devices_with_os_installs = set(
            install.get("deviceId")
            for install in os_patch_installs
            if install.get("deviceId")
        )

        devices_with_sw_installs = set(
            install.get("deviceId")
            for install in software_patch_installs
            if install.get("deviceId")
        )

        # Union of ALL FOUR sets = devices with ANY patch management activity
        devices_with_patch_activity = (
            devices_with_os_patches
            .union(devices_with_sw_patches)
            .union(devices_with_os_installs)
            .union(devices_with_sw_installs)
        )

        enabled_devices = len(devices_with_patch_activity)
        disabled_devices = total_devices - enabled_devices
        enabled_percentage = round((enabled_devices / total_devices * 100), 2) if total_devices > 0 else 0

        # Debug logging
        logger.info(f"Comprehensive patch enablement analysis:")
        logger.info(f"   → Total devices: {total_devices}")
        logger.info(f"   → Devices with OS patches assigned: {len(devices_with_os_patches)}")
        logger.info(f"   → Devices with SW patches assigned: {len(devices_with_sw_patches)}")
        logger.info(f"   → Devices with OS install history: {len(devices_with_os_installs)}")
        logger.info(f"   → Devices with SW install history: {len(devices_with_sw_installs)}")
        logger.info(f"   → Unique devices with ANY patch activity: {enabled_devices}")
        logger.info(f"   → Devices without any patch activity: {disabled_devices}")
        logger.info(f"   → Enabled percentage: {enabled_percentage}%")

        return {
            "total_machines": total_devices,
            "enabled_devices": enabled_devices,
            "disabled_devices": disabled_devices,
            "enabled_percentage": enabled_percentage
        }

    def _get_top_failed_devices(self, patches: List[Dict], patch_type: str, limit: int = 5, devices: Optional[List[Dict]] = None) -> List[Dict]:
        """Get top devices with failed patches based on actual status values."""
        device_stats = {}
        for patch in patches:
            device_id = patch.get("deviceId")
            if not device_id:
                continue
            if device_id not in device_stats:
                device_stats[device_id] = {"success": 0, "failed": 0, "total": 0}

            status = patch.get("status", "").upper()
            device_stats[device_id]["total"] += 1
            if status == "INSTALLED":
                device_stats[device_id]["success"] += 1
            elif status == "FAILED":
                device_stats[device_id]["failed"] += 1

        failed_devices = [(device_id, stats) for device_id, stats in device_stats.items() if stats["failed"] > 0]
        failed_devices.sort(key=lambda x: x[1]["failed"], reverse=True)

        def get_last_scan_date(device_id):
            device_patches = [p for p in patches if p.get("deviceId") == device_id]
            if device_patches:
                latest_timestamp = max(p.get("timestamp", 0) for p in device_patches)
                if latest_timestamp:
                    return datetime.fromtimestamp(latest_timestamp).strftime("%b %d, %Y")
            return "Unknown"

        def get_device_name(device_id):
            if devices:
                for d in devices:
                    if d.get('id') == device_id:
                        # Use displayName if available, otherwise fallback to systemName
                        return d.get('displayName') or d.get('systemName', f"Device{device_id}")
            return f"Device{device_id}"

        top_devices = []
        for device_id, stats in failed_devices[:limit]:
            top_devices.append({
                "device": get_device_name(device_id),
                "failed_patches": stats["failed"],
                "last_successful_scan_date": get_last_scan_date(device_id)
            })

        return top_devices

    def _analyze_device_spread(self, devices: List[Dict]) -> Dict[str, Any]:
        """Analyze device spread by type based on nodeClass."""
        total_devices = len(devices)
        device_types = {
            "Windows Workstations": 0,
            "Windows Servers": 0,
            "Mac": 0,
            "Linux Workstations": 0,
            "Linux Servers": 0,
            "NMS": 0,
            "Cloud": 0
        }

        for device in devices:
            node_class = device.get('nodeClass', '').upper()
            if 'WINDOWS_WORKSTATION' in node_class or 'WORKSTATION' in node_class:
                device_types["Windows Workstations"] += 1
            elif 'WINDOWS_SERVER' in node_class or 'SERVER' in node_class:
                device_types["Windows Servers"] += 1
            elif 'MAC' in node_class or 'DARWIN' in node_class:
                device_types["Mac"] += 1
            elif 'LINUX_WORKSTATION' in node_class:
                device_types["Linux Workstations"] += 1
            elif 'LINUX_SERVER' in node_class:
                device_types["Linux Servers"] += 1
            elif 'NMS' in node_class:
                device_types["NMS"] += 1
            elif 'CLOUD' in node_class:
                device_types["Cloud"] += 1
            else:
                device_types["Windows Workstations"] += 1

        device_types_percentage = {}
        for device_type, count in device_types.items():
            percentage = round((count / total_devices * 100), 2) if total_devices > 0 else 0
            device_types_percentage[device_type] = percentage

        return {
            "total_devices": total_devices,
            "device_types": device_types,
            "device_types_percentage": device_types_percentage
        }

    def _calculate_os_patch_compliance(self, os_patches: List[Dict], os_patch_installs: List[Dict], devices: List[Dict]) -> float:
        """Calculate OS patch compliance to match NinjaOne dashboard methodology."""
        print(f"DEBUG: Total OS patches: {len(os_patches)}")
        print(f"DEBUG: Total devices: {len(devices)}")

        # Get all online devices (exclude offline devices like NinjaOne dashboard does)
        online_devices = set()
        offline_count = 0
        for device in devices:
            device_id = device.get('id')
            if device_id:
                if device.get('offline', True):
                    offline_count += 1
                else:
                    online_devices.add(device_id)

        print(f"DEBUG: Online devices: {len(online_devices)}")
        print(f"DEBUG: Offline devices: {offline_count}")

        # Count approved patches per device
        device_approved_count = {}
        for patch in os_patches:
            device_id = patch.get("deviceId")
            status = patch.get("status", "").upper()

            if device_id and status == "APPROVED":
                device_approved_count[device_id] = device_approved_count.get(device_id, 0) + 1

        print(f"DEBUG: Devices with approved patches: {len(device_approved_count)}")

        # Calculate compliance across ALL online devices
        compliant_devices = 0
        non_compliant_devices = 0

        for device_id in online_devices:
            approved_patches = device_approved_count.get(device_id, 0)

            if approved_patches == 0:
                compliant_devices += 1
            else:
                non_compliant_devices += 1
                print(f"DEBUG: Device {device_id}: {approved_patches} approved patches -> NON-COMPLIANT")

        total_evaluated = len(online_devices)

        if total_evaluated == 0:
            print("WARNING: No online devices to evaluate - returning 100%")
            return 100.0

        compliance_percentage = (compliant_devices / total_evaluated) * 100

        print(f"DEBUG: Compliant devices: {compliant_devices}")
        print(f"DEBUG: Non-compliant devices: {non_compliant_devices}")
        print(f"DEBUG: Total devices evaluated: {total_evaluated}")
        print(f"DEBUG: Final compliance percentage: {compliance_percentage}%")

        return round(compliance_percentage, 2)

    def _calculate_comprehensive_patch_metrics(self, os_patches: List[Dict], software_patches: List[Dict],
                                               os_patch_installs: List[Dict], devices: List[Dict],
                                               software_patch_installs: List[Dict]) -> Dict[str, Any]:
        """Calculate comprehensive patch metrics using NEW LOGIC with unique patch counting."""

        # Step 1: Combine all 4 data sources
        all_patch_data = []

        # Add patch installs (with month filtering already applied) - NO TYPE FILTERING
        for patch in os_patch_installs:
            all_patch_data.append({
                "id": patch.get("id"),
                "status": patch.get("status", "").upper(),
                "source": "os_patch_installs",
                "deviceId": patch.get("deviceId"),
                "timestamp": patch.get("timestamp")
            })

        for patch in software_patch_installs:
            all_patch_data.append({
                "id": patch.get("id"),
                "status": patch.get("status", "").upper(),
                "source": "software_patch_installs",
                "deviceId": patch.get("deviceId"),
                "timestamp": patch.get("timestamp")
            })

        # Add patches with manual timestamp filtering (for user-selected month)
        # Get month timestamps for filtering
        month_filter_start = None
        month_filter_end = None

        # Try to get month filtering info from the processor context if available
        # This matches the same logic used for patch installs
        try:
            if hasattr(self, '_current_month_filter'):
                month_filter_start, month_filter_end = self._current_month_filter
                logger.info(f" Applying manual timestamp filtering to patches: {month_filter_start} to {month_filter_end}")
        except:
            logger.warning("  No month filter context available for patches - including all patches")

            # Add debug counters
        os_patches_total = 0
        os_patches_type_filtered = 0
        os_patches_timestamp_filtered = 0
        os_patches_final_included = 0

        sw_patches_total = 0
        sw_patches_type_filtered = 0
        sw_patches_timestamp_filtered = 0
        sw_patches_final_included = 0

        # ======== THEN CONTINUE WITH YOUR EXISTING CODE ========
        for patch in os_patches:
            os_patches_total += 1

            if patch.get("type", "").upper() == "PATCH":
                os_patches_type_filtered += 1

                # Apply manual timestamp filtering if available
                timestamp = patch.get("timestamp")

                # Debug: Check what timestamp fields exist
                if timestamp is None:
                    available_timestamps = {k: v for k, v in patch.items() if any(
                        time_word in k.lower() for time_word in ['time', 'date', 'create', 'modif', 'scan'])}
                    if available_timestamps and os_patches_final_included == 0:  # Log only first patch as sample
                        print(f"DEBUG OS Patch Sample - Available timestamp fields: {available_timestamps}")

                if month_filter_start and month_filter_end and timestamp:
                    if not (month_filter_start <= timestamp <= month_filter_end):
                        os_patches_timestamp_filtered += 1
                        continue  # Skip patches outside the selected month

                os_patches_final_included += 1
                all_patch_data.append({
                    "id": patch.get("id"),
                    "status": patch.get("status", "").upper(),
                    "source": "os_patches",
                    "deviceId": patch.get("deviceId"),
                    "timestamp": timestamp
                })

        for patch in software_patches:
            sw_patches_total += 1

            if patch.get("type", "").upper() == "PATCH":
                sw_patches_type_filtered += 1

                # Apply manual timestamp filtering if available
                timestamp = patch.get("timestamp")

                # Debug: Check what timestamp fields exist
                if timestamp is None:
                    available_timestamps = {k: v for k, v in patch.items() if any(
                        time_word in k.lower() for time_word in ['time', 'date', 'create', 'modif', 'scan'])}
                    if available_timestamps and sw_patches_final_included == 0:  # Log only first patch as sample
                        print(f"DEBUG Software Patch Sample - Available timestamp fields: {available_timestamps}")

                if month_filter_start and month_filter_end and timestamp:
                    if not (month_filter_start <= timestamp <= month_filter_end):
                        sw_patches_timestamp_filtered += 1
                        continue  # Skip patches outside the selected month

                sw_patches_final_included += 1
                all_patch_data.append({
                    "id": patch.get("id"),
                    "status": patch.get("status", "").upper(),
                    "source": "software_patches",
                    "deviceId": patch.get("deviceId"),
                    "timestamp": timestamp
                })

        # Print debug summary
        print(f"\n=== PATCH FILTERING DEBUG ===")
        print(f"OS Patches:")
        print(f"  Total objects: {os_patches_total}")
        print(f"  After type='PATCH' filter: {os_patches_type_filtered}")
        print(f"  Filtered out by timestamp: {os_patches_timestamp_filtered}")
        print(f"  FINAL included in month range: {os_patches_final_included}")

        print(f"\nSoftware Patches:")
        print(f"  Total objects: {sw_patches_total}")
        print(f"  After type='PATCH' filter: {sw_patches_type_filtered}")
        print(f"  Filtered out by timestamp: {sw_patches_timestamp_filtered}")
        print(f"  FINAL included in month range: {sw_patches_final_included}")

        print(f"\nMonth Filter Range:")
        if month_filter_start and month_filter_end:
            start_date = datetime.fromtimestamp(month_filter_start).strftime('%Y-%m-%d')
            end_date = datetime.fromtimestamp(month_filter_end).strftime('%Y-%m-%d')
            print(f"  {start_date} to {end_date} (timestamps: {month_filter_start} to {month_filter_end})")
        else:
            print("  No month filter applied")

        print(f"Total patches in all_patch_data: {len(all_patch_data)}")
        print("================================\n")
        # Step 2: Create unique patches map with priority logic
        unique_patches = {}
        for patch_data in all_patch_data:
            patch_id = patch_data["id"]
            if not patch_id:
                continue

            if patch_id not in unique_patches:
                unique_patches[patch_id] = patch_data
            else:
                # Priority: patch-installs status over patches status
                current_source = unique_patches[patch_id]["source"]
                new_source = patch_data["source"]

                if (new_source in ["os_patch_installs", "software_patch_installs"] and
                    current_source in ["os_patches", "software_patches"]):
                    unique_patches[patch_id] = patch_data  # Replace with higher priority

        # Step 3: Count by status (case sensitive)
        combined_stats = {"INSTALLED": 0, "APPROVED": 0, "PENDING": 0, "FAILED": 0, "REJECTED": 0}
        for patch_data in unique_patches.values():
            status = patch_data["status"]
            if status == "REJECTED":
                status = "PENDING"  # NOTE: PENDING and REJECTED are same
            if status in combined_stats:
                combined_stats[status] += 1

        # Step 4: Calculate totals
        total_patches = sum(combined_stats.values())
        device_patch_percentage = round((combined_stats["INSTALLED"] / total_patches * 100), 2) if total_patches > 0 else 0

        logger.info(f"NEW PATCH LOGIC - Unique patch analysis:")
        logger.info(f"   → Total unique patches (by id): {len(unique_patches)}")
        logger.info(f"   → Total patches with valid status: {total_patches}")
        logger.info(f"   → INSTALLED: {combined_stats['INSTALLED']}")
        logger.info(f"   → APPROVED: {combined_stats['APPROVED']}")
        logger.info(f"   → FAILED: {combined_stats['FAILED']}")
        logger.info(f"   → PENDING: {combined_stats['PENDING']}")
        logger.info(f"   → Device patch percentage: {device_patch_percentage}%")

        # OS patch statistics
        os_stats = {"INSTALLED": 0, "APPROVED": 0, "PENDING": 0, "FAILED": 0, "REJECTED": 0}
        for patch in os_patches:
            status = patch.get("status", "").upper()
            if status in os_stats:
                os_stats[status] += 1

        # Calculate OS patch compliance using the correct NinjaOne method
        os_compliance = self._calculate_os_patch_compliance(os_patches, os_patch_installs, devices)

        # Software patch statistics
        sw_stats = {"INSTALLED": 0, "APPROVED": 0, "PENDING": 0, "FAILED": 0, "REJECTED": 0}
        sw_all_devices = set()
        sw_approved_devices = set()
        for patch in software_patches:
            status = patch.get("status", "").upper()
            if status in sw_stats:
                sw_stats[status] += 1
            device_id = patch.get("deviceId")
            if device_id:
                sw_all_devices.add(device_id)
                if status == "APPROVED":
                    sw_approved_devices.add(device_id)

        sw_devices_scanned = len(sw_all_devices)
        sw_devices_needing_updates = len(sw_approved_devices)
        sw_compliance = ((sw_devices_scanned - sw_devices_needing_updates) / sw_devices_scanned * 100) if sw_devices_scanned > 0 else 100

        os_install_stats = {"INSTALLED": 0, "FAILED": 0}
        for install in os_patch_installs:
            status = install.get("status", "").upper()
            if status in os_install_stats:
                os_install_stats[status] += 1

        sw_install_stats = {"INSTALLED": 0, "FAILED": 0}
        for install in software_patch_installs:
            status = install.get("status", "").upper()
            if status in sw_install_stats:
                sw_install_stats[status] += 1

        top_os_failed = self._get_top_failed_devices(os_patch_installs, "OS", 5, devices=devices)
        top_sw_failed = self._get_top_failed_devices(software_patch_installs, "Software", 5, devices=devices)

        return {
            "patch_metrics": {
                "device_patch_percentage": device_patch_percentage,
                "total_patches": total_patches,
                "installed_patches": combined_stats["INSTALLED"],
                "approved_patches": combined_stats["APPROVED"],
                "pending_patches": combined_stats["PENDING"],
                "failed_patches": combined_stats["FAILED"],
                "rejected_patches": combined_stats["REJECTED"]
            },
            "patch_compliance": {
                "os_patch_compliance": os_compliance,
                "software_patch_compliance": round(sw_compliance, 2),
                "os_patch_details": os_stats,
                "software_patch_details": sw_stats
            },
            "top_failed_devices": {
                "os_patches": {
                    "failed_patches": len(top_os_failed),
                    "success": os_install_stats["INSTALLED"],
                    "failed": os_install_stats["FAILED"],
                    "devices": top_os_failed
                },
                "software_patches": {
                    "failed_patches": len(top_sw_failed),
                    "success": sw_install_stats["INSTALLED"],
                    "failed": sw_install_stats["FAILED"],
                    "devices": top_sw_failed
                }
            }
        }