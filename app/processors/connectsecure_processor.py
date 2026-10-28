import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import Counter

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import Counter

# Add path resolution for local running - EXACTLY LIKE NINJAONE
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
security_system_root = os.path.join(current_dir, '..', '..')
if security_system_root not in sys.path:
    sys.path.insert(0, security_system_root)

# Updated imports for new app/ structure
from app.core.config.settings import config_manager
from app.clients.connectsecure_client import ConnectSecureClient, create_connectsecure_client, ConnectSecureConfig


logger = logging.getLogger(__name__)


class ConnectSecureProcessor:
    """Handles all ConnectSecure data operations."""

    def __init__(self, client: ConnectSecureClient = None, account_id: int = None, credential_id: str = None, connectsecure_company_id: str = None):
        """
        Initialize ConnectSecureProcessor with account-based credentials.

        Args:
            client: Pre-initialized ConnectSecure client (optional)
            account_id: Account ID for fetching credentials from integration_credentials table (NEW)
            credential_id: DEPRECATED - Legacy UUID for old user_credentials table
            connectsecure_company_id: ConnectSecure company ID to fetch data for
        """
        # Store the company ID for this processor instance
        self.company_id = connectsecure_company_id
        # Note: We allow None company_id now - will return empty data

        if client is None:
            # NEW: Load credentials from account_id (integration_credentials table)
            if account_id is not None:
                from app.core.config.supabase import SupabaseCredentialManager

                credential_manager = SupabaseCredentialManager()
                credentials = credential_manager.get_credentials_by_account_id(account_id)

                if not credentials:
                    raise ValueError(f"No credentials found for account_id: {account_id}")

                # Extract ConnectSecure credentials from decrypted data
                cs_creds = credentials.get('connectsecure', {})

                # ADD VALIDATION HERE
                base_url = cs_creds.get('connectsecure_base_url')
                if not base_url:
                    logger.warning("ConnectSecure base_url is missing or empty - ConnectSecure data will be skipped")
                    self.client = None
                    return

                # ADD THIS: Ensure base_url is a string and strip any whitespace
                base_url = str(base_url).strip()
                if not base_url:
                    logger.warning(
                        "ConnectSecure base_url is empty after stripping - ConnectSecure data will be skipped")
                    self.client = None
                    return

                cs_config = ConnectSecureConfig(
                    tenant_name=cs_creds.get('connectsecure_tenant_name'),
                    base_url=base_url,  # This is now validated
                    client_id=cs_creds.get('connectsecure_client_id'),
                    client_secret_b64=cs_creds.get('connectsecure_client_secret_b64')
                )

                self.client = ConnectSecureClient(cs_config)
                logger.info(f"Loaded ConnectSecure credentials from account_id: {account_id}")

            # OLD: Fallback to legacy credential_id method
            elif credential_id is not None:
                logger.warning("Using DEPRECATED credential_id method. Please migrate to account_id.")
                config = config_manager.load_credentials(credential_id)

                # ADD THIS SAFETY CHECK
                base_url = config.get('connectsecure_base_url', '').strip()
                if not base_url:
                    logger.warning(
                        "ConnectSecure base_url is missing in legacy credentials - ConnectSecure data will be skipped")
                    self.client = None
                    return

                cs_config = ConnectSecureConfig(
                    tenant_name=config['connectsecure_tenant_name'],
                    base_url=config['connectsecure_base_url'],
                    client_id=config['connectsecure_client_id'],
                    client_secret_b64=config['connectsecure_client_secret_b64']
                )

                self.client = ConnectSecureClient(cs_config)

            else:
                raise ValueError("Either account_id or credential_id must be provided")
        else:
            self.client = client

        logger.info(f"ConnectSecure processor initialized for company ID: {self.company_id}")

    def fetch_all_data(self, company_id: Optional[str] = None, month_name: str = None) -> Dict[str, Any]:
        """
        UPDATED: Fetch ConnectSecure data using new endpoints with month filtering support.
        Returns empty data if no company_id provided.
        """
        if company_id is None:
            company_id = self.company_id

        # Return empty data if no client (ConnectSecure not configured) or no company_id
        if self.client is None or not company_id:
            logger.warning("ConnectSecure not configured or no company_id provided - returning empty data")
            return {
                'total_asset_count': {},
                'assets': [],
                'vulnerabilities': [],
                'asset_status_counts': {}
            }

        data = {}

        # 1. Get total asset count from new endpoint (NO monthly filtering)
        try:
            logger.debug(f"Fetching total asset count for company {company_id}...")
            data['total_asset_count'] = self.client.get_total_asset_count(company_id)
            logger.info(f"Retrieved total asset count data")
        except Exception as e:
            logger.error(f"Failed to fetch total asset count: {e}")
            data['total_asset_count'] = {}

        # 2. Get asset view data with month filtering (for online status and asset types)
        try:
            logger.debug(f"Fetching asset view data for company {company_id}, month: {month_name}...")
            data['asset_view'] = self.client.get_asset_view_data(company_id, month_name)
            logger.info(f"Retrieved {len(data['asset_view'])} assets from asset_view")
        except Exception as e:
            logger.error(f"Failed to fetch asset view data: {e}")
            data['asset_view'] = []

        # 3. Keep the original assets call for backward compatibility (if needed by other parts)
        try:
            logger.debug(f"Fetching original assets for company {company_id}...")
            data['assets'] = self.client.get_assets_by_company(company_id)
            logger.info(f"Retrieved {len(data['assets'])} assets from original endpoint")
        except Exception as e:
            logger.error(f"Failed to fetch original assets: {e}")
            data['assets'] = []

        # 4. NEW: Get asset stats data for risk score calculation - BOTH monthly and live
        try:
            # Monthly data (with month filter)
            logger.debug(f"Fetching MONTHLY asset stats for risk score (company {company_id}, month: {month_name})...")
            data['risk_score_monthly'] = self.client.get_risk_score(company_id, month_name)
            logger.info(f" Retrieved MONTHLY risk score data from {len(data['risk_score_monthly'])} assets")
        except Exception as e:
            logger.error(f"Failed to fetch monthly asset stats for risk score: {e}")
            data['risk_score_monthly'] = []

        try:
            # Live data (no month filter)
            logger.debug(f"Fetching LIVE asset stats for risk score (company {company_id})...")
            data['risk_score_live'] = self.client.get_risk_score(company_id, month_name=None)
            logger.info(f" Retrieved LIVE risk score data from {len(data['risk_score_live'])} assets")
        except Exception as e:
            logger.error(f"Failed to fetch live asset stats for risk score: {e}")
            data['risk_score_live'] = []

        # 5. NEW: Get company stats data (vulnerability counts) - BOTH monthly and live
        try:
            # Monthly data (with month filter)
            logger.debug(f"Fetching MONTHLY company stats (company {company_id}, month: {month_name})...")
            data['company_stats_monthly'] = self.client.get_company_stats(company_id, month_name)
            logger.info(f"Retrieved MONTHLY company stats data")
        except Exception as e:
            logger.error(f"Failed to fetch monthly company stats: {e}")
            data['company_stats_monthly'] = {}

        try:
            # Live data (no month filter)
            logger.debug(f"Fetching LIVE company stats (company {company_id})...")
            data['company_stats_live'] = self.client.get_company_stats(company_id, month_name=None)
            logger.info(f" Retrieved LIVE company stats data")
        except Exception as e:
            logger.error(f"Failed to fetch live company stats: {e}")
            data['company_stats_live'] = {}

        # 6. NEW: Get agents data (no monthly filtering, only active agents)
        try:
            logger.debug(f"Fetching active agents for company {company_id}...")
            data['agents'] = self.client.get_agents(company_id)
            logger.info(f" Retrieved {len(data['agents'])} active agents")
        except Exception as e:
            logger.error(f"Failed to fetch agents: {e}")
            data['agents'] = []

        # 7. Quarterly data — always fetched (like live), used for quarterly_count in 3 charts
        try:
            logger.debug(f"Fetching QUARTERLY asset view data (company {company_id})...")
            data['asset_view_quarterly'] = self.client.get_asset_view_data(company_id, "last_3_months")
            logger.info(f"Retrieved {len(data['asset_view_quarterly'])} assets from asset_view_quarterly")
        except Exception as e:
            logger.error(f"Failed to fetch quarterly asset view data: {e}")
            data['asset_view_quarterly'] = []

        try:
            logger.debug(f"Fetching QUARTERLY risk score data (company {company_id})...")
            data['risk_score_quarterly'] = self.client.get_risk_score(company_id, "last_3_months")
            logger.info(f" Retrieved quarterly risk score data from {len(data['risk_score_quarterly'])} assets")
        except Exception as e:
            logger.error(f"Failed to fetch quarterly risk score: {e}")
            data['risk_score_quarterly'] = []

        try:
            logger.debug(f"Fetching QUARTERLY company stats (company {company_id})...")
            data['company_stats_quarterly'] = self.client.get_company_stats(company_id, "last_3_months")
            logger.info(f" Retrieved quarterly company stats data")
        except Exception as e:
            logger.error(f"Failed to fetch quarterly company stats: {e}")
            data['company_stats_quarterly'] = {}

        # Keep existing empty defaults
        data['vulnerabilities'] = []
        data['security_incidents'] = []
        data['compliance_status'] = {}

        logger.info(f" ConnectSecure data collection complete:")
        logger.info(f"   → Total asset count: {data['total_asset_count'].get('total_assets', 'N/A')}")
        logger.info(f"   → Asset view data: {len(data['asset_view'])} assets")
        logger.info(f"   → Original assets: {len(data['assets'])} assets")
        logger.info(f"   → MONTHLY risk score assets: {len(data['risk_score_monthly'])} assets")
        logger.info(f"   → LIVE risk score assets: {len(data['risk_score_live'])} assets")
        logger.info(f"   → MONTHLY company stats: {data['company_stats_monthly'].get('company_id', 'N/A')}")
        logger.info(f"   → LIVE company stats: {data['company_stats_live'].get('company_id', 'N/A')}")
        logger.info(f"   → Active agents: {len(data['agents'])} agents")

        return data

    def _process_asset_data(self, assets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process assets and return complete metrics structure."""

        if not assets:
            return {
                "total_assets": 0,
                "online_assets": 0,
                "offline_assets": 0,
                "online_percentage": 0,
                "asset_types": {"discovered": 0, "other_asset": 0},
                "os_distribution": {"Unknown": 1},
                "devices_by_status": {"online": 0, "offline": 0}
            }

        print(f"🔍 DEBUG: _process_asset_data processing {len(assets)} assets")

        # Count asset types using asset_type (singular) field from raw data
        type_counts = {'discovered': 0, 'other_asset': 0, 'unknown': 0}
        for asset in assets:
            asset_type = asset.get('asset_type', 'unknown')
            if asset_type in ['discovered', 'other_asset']:
                type_counts[asset_type] += 1
            else:
                type_counts['unknown'] += 1

        print(f" DEBUG: Asset type counts: {type_counts}")

        # Count online/offline for discovered assets only
        discovered_assets = [asset for asset in assets if asset.get('asset_type') == 'discovered']
        online_count = 0
        offline_count = 0

        for asset in discovered_assets:
            if asset.get('online_status') is True:
                online_count += 1
            else:
                offline_count += 1

        print(f"DEBUG: Online: {online_count}, Offline: {offline_count}")

        # FIXED: Process OS distribution from DISCOVERED ASSETS ONLY
        os_counts = {}
        for asset in discovered_assets:  # CHANGED: Only count discovered assets
            os_name = self._extract_os_name(asset)
            os_name = self._standardize_os_name(str(os_name))
            os_counts[os_name] = os_counts.get(os_name, 0) + 1

        # ADDED: Calculate "Other" category for missing OS data
        total_os_counted = sum(os_counts.values())
        total_assets_calculated = online_count + offline_count

        if total_os_counted < total_assets_calculated:
            other_count = total_assets_calculated - total_os_counted
            os_counts['Other'] = other_count
            print(
                f" DEBUG: Added {other_count} 'Other' OS entries (Total OS: {total_os_counted}, Total Assets: {total_assets_calculated})")

        print(f" DEBUG: Total calculated from online+offline: {total_assets_calculated}")
        print(f" DEBUG: OS distribution total: {sum(os_counts.values())}")

        # Return complete structure
        return {
            "total_assets": total_assets_calculated,  # CHANGED: Now online_count + offline_count instead of len(assets)
            "online_assets": online_count,
            "offline_assets": offline_count,
            "online_percentage": round((online_count / total_assets_calculated * 100),
                                       1) if total_assets_calculated > 0 else 0,
            "asset_types": type_counts,
            "os_distribution": os_counts,  # Now includes "Other" category
            "devices_by_status": {"online": online_count, "offline": offline_count}
        }

    def _determine_device_connectivity(self, asset: Dict[str, Any]) -> bool:
        """
        FIXED: Determine if device is online using ICMP ping statistics.
        Based on actual JSON structure from ConnectSecure.
        """
        # Priority 1: Check ICMP ping stats (most reliable)
        finger_print = asset.get('finger_print', {})
        icmp_data = finger_print.get('ICMP', {})

        if icmp_data:
            ping_stats = icmp_data.get('ping_stats', {})
            if ping_stats:
                packet_loss = ping_stats.get('packet_loss')

                # Handle packet_loss values (can be number or string "null")
                if packet_loss is not None and packet_loss != "null" and packet_loss != "":
                    try:
                        packet_loss_num = float(packet_loss)
                        # If packet loss is 100% or close to 100%, device is offline
                        if packet_loss_num >= 95:
                            return False
                        # If packet loss is low, device is online
                        elif packet_loss_num < 50:
                            return True
                    except:
                        pass

            # Check for valid RTT (round trip time)
            icmp_rtt = icmp_data.get('icmp.rtt')
            if icmp_rtt and icmp_rtt != "null" and icmp_rtt != "":
                try:
                    rtt_num = float(icmp_rtt)
                    if rtt_num > 0:  # Valid response time means online
                        return True
                except:
                    pass

            # Check ICMP type code for echo reply
            type_code = icmp_data.get('icmp.typeCode')
            if type_code == "EchoReply":
                return True

        # Priority 2: Check last ping time (recent activity)
        last_ping = asset.get('last_ping_time')
        if last_ping:
            try:
                from datetime import datetime, timedelta
                # If last ping was within last 24 hours, consider online
                last_ping_dt = datetime.fromisoformat(str(last_ping).replace('Z', '+00:00'))
                twenty_four_hours_ago = datetime.now() - timedelta(hours=24)
                if last_ping_dt.replace(tzinfo=None) > twenty_four_hours_ago:
                    return True
            except:
                pass

        # Priority 3: Check status field as fallback
        status = asset.get('status', False)
        if status is True or str(status).lower() == 'true':
            return True

        # Priority 4: Check if device was discovered recently
        discovered = asset.get('discovered') or asset.get('last_discovered_time')
        if discovered:
            try:
                from datetime import datetime, timedelta
                # If discovered within last 7 days, probably online
                discovered_dt = datetime.fromisoformat(str(discovered).replace('Z', '+00:00'))
                seven_days_ago = datetime.now() - timedelta(days=7)
                if discovered_dt.replace(tzinfo=None) > seven_days_ago:
                    return True
            except:
                pass

        # Default to offline if no positive indicators
        return False

    def _extract_os_name(self, asset: Dict[str, Any]) -> str:
        """Extract OS name from asset fingerprint data."""
        # Extract OS information from various possible locations based on your JSON structure
        os_name = None

        # Try different OS field locations based on JSON structure
        finger_print = asset.get('finger_print', {})
        if finger_print:
            # Try ARP fingerprint first (most reliable from your JSON)
            arp_info = finger_print.get('ARP', {})
            if arp_info:
                os_name = arp_info.get('ip.ttl.osGuess') or arp_info.get('fp.os.source')

            # Try basic_asset info
            if not os_name:
                basic_asset = finger_print.get('basic_asset', {})
                if basic_asset:
                    os_name = basic_asset.get('OsGuess')

        # Fallback to direct OS fields
        if not os_name:
            os_name = (asset.get('os_name') or
                       asset.get('os_full_name') or
                       asset.get('platform') or
                       'Unknown')

        return os_name

    def _standardize_os_name(self, os_name: str) -> str:
        """Standardize OS names for better grouping."""
        os_name = os_name.lower().strip()

        if 'windows' in os_name:
            # CHANGED: Combine ALL Windows variants into single "Windows" category
            return 'Windows'
        elif 'linux' in os_name:
            if 'ubuntu' in os_name:
                return 'Ubuntu Linux'
            elif 'centos' in os_name:
                return 'CentOS Linux'
            elif 'redhat' in os_name or 'rhel' in os_name:
                return 'Red Hat Linux'
            else:
                return 'Linux'
        elif 'macos' in os_name or 'mac' in os_name:
            return 'macOS'
        elif os_name in ['null', 'none', '', 'unknown']:
            return 'Unknown'
        else:
            return os_name.title()
    def _process_compliance_data(self, compliance: Dict[str, Any]) -> Dict[str, Any]:
        """Process compliance status data into metrics."""
        if not compliance:
            return {
                "overall_score": 0,
                "frameworks": {},
                "compliant_controls": 0,
                "total_controls": 0,
                "compliance_percentage": 0
            }

        overall_score = compliance.get('overall_score', compliance.get('score', 0))
        frameworks = compliance.get('frameworks', {})

        return {
            "overall_score": self._safe_float(overall_score),
            "frameworks": frameworks,
            "compliant_controls": compliance.get('compliant_controls', 0),
            "total_controls": compliance.get('total_controls', 0),
            "compliance_percentage": self._safe_float(compliance.get('compliance_percentage', 0))
        }

    def _process_agents_data(self, agents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process agents data into agent type distribution with breakdown and percentages."""
        print(f"DEBUG: Processing {len(agents)} agents for agent type distribution")

        if not agents:
            return {
                "agent_type_distribution": {
                    "total_agents": 0,
                    "breakdown": []
                }
            }

        # Count agent types dynamically
        agent_type_counts = {}
        for agent in agents:
            agent_type = agent.get('agent_type', 'UNKNOWN')
            agent_type_counts[agent_type] = agent_type_counts.get(agent_type, 0) + 1

        print(f"DEBUG: Agent type counts: {agent_type_counts}")

        total_agents = len(agents)

        # Create breakdown with percentages
        breakdown = []
        for agent_type, count in agent_type_counts.items():
            percentage = round((count / total_agents) * 100, 1) if total_agents > 0 else 0
            breakdown.append({
                "agent_type": agent_type,
                "count": count,
                "percentage": percentage
            })

        # Sort by count (highest first)
        breakdown.sort(key=lambda x: x['count'], reverse=True)

        print(f" DEBUG: Agent breakdown: {breakdown}")

        return {
            "agent_type_distribution": {
                "total_agents": total_agents,
                "breakdown": breakdown
            }
        }

    def _process_risk_score_data(self, risk_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process risk score data with insights."""
        risk_info = {
            "average_score": 0.0,
            "risk_level": "Unknown",
            "description": "Risk score data unavailable",
            "recommendation": "Enable risk scoring monitoring",
            "trend": "Stable",
            "company_name": "Unknown Company",
            "raw_score": 0.0
        }

        print(f" DEBUG: Processing risk_data: {risk_data}")

        if not risk_data:
            print("DEBUG: No risk_data provided")
            return risk_info

        try:
            # Extract risk score from the structure: {"result": {"Company Name": 69.0}}
            if "result" in risk_data:
                result_data = risk_data["result"]
                print(f" DEBUG: Found result_data: {result_data}")

                if isinstance(result_data, dict) and len(result_data) > 0:
                    # Get the first (and likely only) company entry
                    company_name = list(result_data.keys())[0]
                    risk_score = float(result_data[company_name])

                    print(f" DEBUG: Extracted company: {company_name}, score: {risk_score}")

                    risk_info["average_score"] = round(risk_score, 1)
                    risk_info["raw_score"] = risk_score
                    risk_info["company_name"] = company_name

                    # Determine risk level and description
                    if risk_score >= 80:
                        risk_info["risk_level"] = "Critical"
                        risk_info["description"] = f"Critical security risk score of {risk_score:.1f}/100"
                        risk_info["recommendation"] = "Immediate action required to address critical security risks"
                    elif risk_score >= 60:
                        risk_info["risk_level"] = "High"
                        risk_info["description"] = f"High security risk score of {risk_score:.1f}/100"
                        risk_info["recommendation"] = "Prioritize security improvements to reduce risk"
                    elif risk_score >= 40:
                        risk_info["risk_level"] = "Moderate"
                        risk_info["description"] = f"Moderate security risk score of {risk_score:.1f}/100"
                        risk_info["recommendation"] = "Review and enhance security policies"
                    else:
                        risk_info["risk_level"] = "Low"
                        risk_info["description"] = f"Low security risk score of {risk_score:.1f}/100"
                        risk_info["recommendation"] = "Maintain current security practices"

                    print(f"DEBUG: Final risk_info: {risk_info}")
                    logger.info(f" Processed risk score: {company_name} = {risk_score}")
                else:
                    print(" DEBUG: result_data is not a dict or is empty")
            else:
                print("DEBUG: No 'result' key found in risk_data")

        except Exception as e:
            print(f"DEBUG: Exception processing risk data: {e}")
            logger.error(f"Error processing ConnectSecure risk data: {e}")

        return risk_info

    def _process_vulnerabilities_count_data(self, vuln_count_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process vulnerability count data into frontend format."""
        if not vuln_count_data:
            return {
                "vulnerability_severity": {
                    "Critical": 0,
                    "High": 0,
                    "Medium": 0,
                    "Low": 0
                }
            }

        print(f" DEBUG: Processing vulnerability count data: {vuln_count_data}")

        # Map API response fields to frontend format
        vulnerability_severity = {
            "Critical": vuln_count_data.get('critical_problems', 0),
            "High": vuln_count_data.get('high_problems', 0),
            "Medium": vuln_count_data.get('medium_problems', 0),
            "Low": vuln_count_data.get('low_problems', 0)
        }

        print(f"DEBUG: Transformed vulnerability severity: {vulnerability_severity}")

        return {
            "vulnerability_severity": vulnerability_severity,
            "total_vulnerabilities": vuln_count_data.get('total_vuls_count', 0)
        }

    def _process_agents_data_to_new_format(self, agents_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Convert regular agents data to new frontend format with breakdown and percentages."""
        print(f" DEBUG: Converting {len(agents_data)} regular agents to new format")

        if not agents_data:
            return {
                "agent_type_distribution": {
                    "total_agents": 0,
                    "breakdown": []
                }
            }

        # Count agent types
        agent_type_counts = {}
        for agent in agents_data:
            agent_type = agent.get('agent_type', 'UNKNOWN')
            agent_type_counts[agent_type] = agent_type_counts.get(agent_type, 0) + 1

        print(f"DEBUG: Fallback agent type counts: {agent_type_counts}")

        # Calculate total
        total_agents = len(agents_data)

        # Create breakdown with percentages
        breakdown = []
        for agent_type, count in agent_type_counts.items():
            percentage = round((count / total_agents) * 100, 2) if total_agents > 0 else 0
            breakdown.append({
                "agent_type": agent_type,
                "count": count,
                "percentage": percentage
            })

        print(f" DEBUG: Fallback agent breakdown: {breakdown}")

        return {
            "agent_type_distribution": {
                "total_agents": total_agents,
                "breakdown": breakdown
            }
        }

    def _process_agents_monthly_data(self, agents_monthly: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process monthly agents data into new frontend format."""
        print(f"DEBUG: Processing {len(agents_monthly)} monthly agents")

        if not agents_monthly:
            return {
                "agent_type_distribution": {
                    "total_agents": 0,
                    "breakdown": []
                }
            }

        # Count agent types
        agent_type_counts = {}
        for agent in agents_monthly:
            agent_type = agent.get('agent_type', 'UNKNOWN')
            agent_type_counts[agent_type] = agent_type_counts.get(agent_type, 0) + 1

        print(f" DEBUG: Agent type counts: {agent_type_counts}")

        # Calculate total
        total_agents = len(agents_monthly)

        # Create breakdown with percentages
        breakdown = []
        for agent_type, count in agent_type_counts.items():
            percentage = round((count / total_agents) * 100, 2) if total_agents > 0 else 0
            breakdown.append({
                "agent_type": agent_type,
                "count": count,
                "percentage": percentage
            })

        print(f"DEBUG: Agent breakdown: {breakdown}")

        return {
            "agent_type_distribution": {
                "total_agents": total_agents,
                "breakdown": breakdown
            }
        }

    def _process_security_risk_score_data(self, asset_stats: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process asset stats into security risk score with distribution."""
        print(f" DEBUG: Processing {len(asset_stats)} assets for security risk score")

        if not asset_stats:
            return {
                "security_risk_score": {
                    "overall_score": 0,
                    "total_assets": 0,
                    "risk_distribution": {
                        "low": {"count": 0, "percentage": 0, "score_range": "0-40"},
                        "medium": {"count": 0, "percentage": 0, "score_range": "41-70"},
                        "high": {"count": 0, "percentage": 0, "score_range": "71-90"},
                        "critical": {"count": 0, "percentage": 0, "score_range": "91-100"}
                    }
                }
            }

        # Extract valid risk scores
        valid_scores = []
        for asset_stat in asset_stats:
            vul_stats = asset_stat.get('vul_stats', {})
            if vul_stats and 'avg_risk_score' in vul_stats:
                avg_score = vul_stats['avg_risk_score']
                if avg_score is not None:
                    valid_scores.append(float(avg_score))

        print(f" DEBUG: Found {len(valid_scores)} valid risk scores")

        if not valid_scores:
            return {
                "security_risk_score": {
                    "overall_score": 0,
                    "total_assets": 0,
                    "risk_distribution": {
                        "low": {"count": 0, "percentage": 0, "score_range": "0-40"},
                        "medium": {"count": 0, "percentage": 0, "score_range": "41-70"},
                        "high": {"count": 0, "percentage": 0, "score_range": "71-90"},
                        "critical": {"count": 0, "percentage": 0, "score_range": "91-100"}
                    }
                }
            }

        # Calculate overall score - show to 2 decimal places only (no rounding)
        raw_score = sum(valid_scores) / len(valid_scores)
        overall_score = float(f"{raw_score:.2f}")
        total_assets = len(valid_scores)

        # Categorize risk scores using the JavaScript logic provided
        risk_counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}

        for score in valid_scores:
            if score >= 91:
                risk_counts["critical"] += 1
            elif score >= 71:
                risk_counts["high"] += 1
            elif score >= 41:
                risk_counts["medium"] += 1
            else:
                risk_counts["low"] += 1

        # Calculate percentages
        risk_distribution = {}
        score_ranges = {
            "low": "0-40",
            "medium": "41-70",
            "high": "71-90",
            "critical": "91-100"
        }

        for risk_level, count in risk_counts.items():
            percentage = round((count / total_assets) * 100, 2) if total_assets > 0 else 0
            risk_distribution[risk_level] = {
                "count": count,
                "percentage": percentage,
                "score_range": score_ranges[risk_level]
            }

        print(f" DEBUG: Risk distribution: {risk_distribution}")

        return {
            "security_risk_score": {
                "overall_score": overall_score,
                "total_assets": total_assets,
                "risk_distribution": risk_distribution
            }
        }

    def _process_asset_status_data(self, asset_view: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process asset view data to extract online/offline status counts."""
        print(f" DEBUG: Processing {len(asset_view)} assets for status counts")

        if not asset_view:
            return {
                "asset_status": {
                    "online": 0,
                    "offline": 0
                }
            }

        online_count = 0
        offline_count = 0

        for asset in asset_view:
            # Check status field (true/false)
            status = asset.get('status')
            if status is True:
                online_count += 1
            else:
                offline_count += 1

        print(f" DEBUG: Asset status counts - Online: {online_count}, Offline: {offline_count}")

        return {
            "asset_status": {
                "online": online_count,
                "offline": offline_count
            }
        }

    def _generate_summary_metrics_from_real_data(self,
                                                 vulnerabilities_count: Dict[str, Any],
                                                 incidents: List[Dict[str, Any]],
                                                 compliance: Dict[str, Any],
                                                 security_risk_metrics: Dict[str, Any],
                                                 assets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate summary metrics using REAL data from new endpoints - NO HARDCODED VALUES."""

        # Get real vulnerability counts from API
        critical_vulns = vulnerabilities_count.get('critical_problems', 0)
        total_vulns = vulnerabilities_count.get('total_vuls_count', 0)

        # Count critical incidents
        critical_incidents = len([i for i in incidents
                                  if str(i.get('severity', '')).lower() == 'critical'])

        active_incidents = len([i for i in incidents
                                if 'open' in str(i.get('status', '')).lower() or
                                'active' in str(i.get('status', '')).lower()])

        # Get real risk score from security risk metrics
        risk_score = 0
        if security_risk_metrics and 'security_risk_score' in security_risk_metrics:
            risk_score = security_risk_metrics['security_risk_score'].get('overall_score', 0)

        compliance_score = 0
        if compliance:
            compliance_score = compliance.get('overall_score', compliance.get('score', 0))

        # Count real assets (online + offline from discovered assets only)
        discovered_assets = [asset for asset in assets if asset.get('asset_type') == 'discovered']
        online_count = sum(1 for asset in discovered_assets if asset.get('status') is True)
        offline_count = sum(1 for asset in discovered_assets if asset.get('status') is not True)
        total_assets_calculated = online_count + offline_count

        # Determine overall security posture using REAL data
        if critical_vulns > 0 or critical_incidents > 0 or risk_score >= 80:
            security_posture = "Critical"
        elif risk_score >= 60 or compliance_score < 70:
            security_posture = "Needs Attention"
        elif risk_score >= 40 or compliance_score < 80:
            security_posture = "Monitor Closely"
        else:
            security_posture = "Good"

        return {
            "total_vulnerabilities": total_vulns,  # REAL data from API
            "critical_vulnerabilities": critical_vulns,  # REAL data from API
            "active_incidents": active_incidents,
            "total_assets": total_assets_calculated,  # REAL count
            "risk_score": self._safe_float(risk_score),  # REAL risk score
            "compliance_score": self._safe_float(compliance_score),
            "security_posture": security_posture,  # Based on REAL data
            "threats_detected": total_vulns + len(incidents),  # REAL data
            "threats_blocked": 0,  # Would need specific endpoint data
            "last_updated": datetime.now().isoformat()
        }

    def _generate_summary_metrics(self, vulnerabilities: List[Dict[str, Any]],
                                  incidents: List[Dict[str, Any]],
                                  compliance: Dict[str, Any],
                                  risk_metrics: Dict[str, Any],  # Now expects processed dict
                                  assets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate summary metrics using only actual endpoint data."""
        # Count critical issues
        critical_vulns = len([v for v in vulnerabilities
                              if str(v.get('severity', '')).lower() == 'critical'])

        critical_incidents = len([i for i in incidents
                                  if str(i.get('severity', '')).lower() == 'critical'])

        active_incidents = len([i for i in incidents
                                if 'open' in str(i.get('status', '')).lower() or
                                'active' in str(i.get('status', '')).lower()])

        # Overall risk assessment
        risk_score = 0
        if risk_metrics and isinstance(risk_metrics, dict):
            risk_score = risk_metrics.get('average_score', risk_metrics.get('raw_score', 0))

        compliance_score = 0
        if compliance:
            compliance_score = compliance.get('overall_score', compliance.get('score', 0))

        # Determine overall security posture
        if critical_vulns > 0 or critical_incidents > 0 or risk_score >= 80:
            security_posture = "Critical"
        elif risk_score >= 60 or compliance_score < 70:
            security_posture = "Needs Attention"
        elif risk_score >= 40 or compliance_score < 80:
            security_posture = "Monitor Closely"
        else:
            security_posture = "Good"

        # Use actual data instead of estimates
        return {
            "total_vulnerabilities": len(vulnerabilities),
            "critical_vulnerabilities": critical_vulns,
            "active_incidents": active_incidents,
            "total_assets": len(assets),
            "risk_score": self._safe_float(risk_score),
            "compliance_score": self._safe_float(compliance_score),
            "security_posture": security_posture,
            "threats_detected": len(vulnerabilities) + len(incidents),
            "threats_blocked": 0,  # Would need specific endpoint data
            "last_updated": datetime.now().isoformat()
        }

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        """Safely convert value to float."""
        try:
            if value is None or value == "":
                return default
            return float(str(value))
        except (ValueError, TypeError):
            return default

    def process_all_data(self, raw_data: Dict[str, Any], company_id: str = None, month_name: str = None) -> Dict[str, Any]:
        """Process ConnectSecure raw data into final metrics with new transformations."""

        # Use instance company_id if no specific company_id provided
        if company_id is None:
            company_id = self.company_id

        # Get the asset data (prioritize month-filtered data when month specified)
        asset_view_data = raw_data.get('asset_view', [])
        assets = raw_data.get('assets', [])

        # If month_name is specified, ALWAYS use month-filtered data (asset_view_data) even if empty
        # This ensures different months return different data instead of falling back to the same dataset
        if month_name:
            assets_to_use = asset_view_data  # Use month-filtered data even if empty
            print(f"DEBUG: Month '{month_name}' specified - using month-filtered asset_view_data: {len(asset_view_data)} assets")
        else:
            # Only fall back to regular assets when no month filtering is requested
            assets_to_use = asset_view_data if asset_view_data else assets
            print(f" DEBUG: No month specified - using fallback logic: {len(assets_to_use)} assets")

        # Get other data
        vulnerabilities = raw_data.get('vulnerabilities', [])
        security_incidents = raw_data.get('security_incidents', [])
        compliance_status = raw_data.get('compliance_status', {})
        total_asset_count_data = raw_data.get('total_asset_count', {})
        agents_data = raw_data.get('agents', [])

        # NEW: Get BOTH monthly and live data for risk score and company stats
        risk_score_monthly = raw_data.get('risk_score_monthly', [])
        risk_score_live = raw_data.get('risk_score_live', [])
        company_stats_monthly = raw_data.get('company_stats_monthly', {})
        company_stats_live = raw_data.get('company_stats_live', {})

        # Quarterly data for quarterly_count in 3 charts
        asset_view_quarterly = raw_data.get('asset_view_quarterly', [])
        risk_score_quarterly = raw_data.get('risk_score_quarterly', [])
        company_stats_quarterly = raw_data.get('company_stats_quarterly', {})

        # DEBUG: Print what data we received
        print(f" DEBUG: risk_score_monthly: {len(risk_score_monthly)} assets")
        print(f" DEBUG: risk_score_live: {len(risk_score_live)} assets")
        print(f" DEBUG: company_stats_monthly: {company_stats_monthly.get('company_id', 'N/A')}")
        print(f" DEBUG: company_stats_live: {company_stats_live.get('company_id', 'N/A')}")
        print(f" DEBUG: agents_data: {len(agents_data)} agents")
        print(f" DEBUG: asset_view_data: {len(asset_view_data)} assets")

        print(f" DEBUG: Processing {len(assets_to_use)} assets")

        # Process asset metrics
        asset_metrics = self._process_asset_data(assets_to_use)

        # NEW: Process company stats data - BOTH monthly and live
        vulnerability_monthly = self._process_company_stats_data(company_stats_monthly)
        vulnerability_live = self._process_company_stats_data(company_stats_live)
        print(f" DEBUG: Vulnerability MONTHLY metrics: {vulnerability_monthly}")
        print(f" DEBUG: Vulnerability LIVE metrics: {vulnerability_live}")

        # Combine into new structure
        vulnerability_count_metrics = self._combine_vulnerability_metrics(vulnerability_monthly, vulnerability_live)
        print(f" DEBUG: Combined vulnerability metrics: {vulnerability_count_metrics}")

        # NEW: Process agents data (no monthly filtering)
        agents_metrics = self._process_agents_data(agents_data)
        print(f" DEBUG: Agents metrics: {agents_metrics}")

        # NEW: Process security risk score data - BOTH monthly and live
        risk_score_monthly_metrics = self._process_security_risk_score_data(risk_score_monthly)
        risk_score_live_metrics = self._process_security_risk_score_data(risk_score_live)
        print(f" DEBUG: Risk score MONTHLY metrics: {risk_score_monthly_metrics}")
        print(f" DEBUG: Risk score LIVE metrics: {risk_score_live_metrics}")

        # Process quarterly risk score data
        risk_score_quarterly_metrics = self._process_security_risk_score_data(risk_score_quarterly)

        # Combine into new structure (monthly + live + quarterly)
        security_risk_score_metrics = self._combine_risk_score_metrics(risk_score_monthly_metrics, risk_score_live_metrics, risk_score_quarterly_metrics)
        print(f"DEBUG: Combined risk score metrics: {security_risk_score_metrics}")

        # FALLBACK: If no risk score data, set to null (not 0)
        risk_score_data = security_risk_score_metrics.get("security_risk_score", {})
        if risk_score_data.get("live_count") is None and risk_score_data.get("monthly_count") is None:
            print(f" DEBUG: No risk score data available, both live_count and monthly_count are null")
            security_risk_score_metrics = {
                "security_risk_score": {
                    "live_count": None,
                    "monthly_count": None,
                    "quarterly_count": None
                }
            }
            print(f" DEBUG: Using fallback risk score metrics: {security_risk_score_metrics}")

        # NEW: Process asset type distribution data - monthly, live, and quarterly
        asset_type_monthly_metrics = self._process_asset_type_distribution(asset_view_data)
        asset_type_live_metrics = self._process_asset_type_distribution(assets)
        asset_type_quarterly_metrics = self._process_asset_type_distribution(asset_view_quarterly)
        print(f" DEBUG: Asset type MONTHLY metrics: {asset_type_monthly_metrics}")
        print(f" DEBUG: Asset type LIVE metrics: {asset_type_live_metrics}")

        # Combine into new structure (monthly + live + quarterly)
        asset_type_distribution_metrics = self._combine_asset_type_metrics(asset_type_monthly_metrics, asset_type_live_metrics, asset_type_quarterly_metrics)
        print(f"DEBUG: Combined asset type distribution metrics: {asset_type_distribution_metrics}")

        # NEW: Process OS distribution data - monthly, live, and quarterly
        os_dist_monthly_metrics = self._process_os_distribution(asset_view_data)
        os_dist_live_metrics = self._process_os_distribution(assets)
        os_dist_quarterly_metrics = self._process_os_distribution(asset_view_quarterly)
        print(f" DEBUG: OS distribution MONTHLY metrics: {os_dist_monthly_metrics}")
        print(f" DEBUG: OS distribution LIVE metrics: {os_dist_live_metrics}")

        # Combine into new structure (monthly + live + quarterly)
        os_distribution_metrics = self._combine_os_distribution_metrics(os_dist_monthly_metrics, os_dist_live_metrics, os_dist_quarterly_metrics)
        print(f"DEBUG: Combined OS distribution metrics: {os_distribution_metrics}")

        # Process other metrics (keep for backward compatibility)
        vulnerability_metrics = self._process_vulnerability_data(vulnerabilities)
        incident_metrics = self._process_incident_data(security_incidents)
        compliance_metrics = self._process_compliance_data(compliance_status)

        # Create summary metrics using REAL DATA from new endpoints (use live data for summary)
        summary_metrics = self._generate_summary_metrics_from_real_data(
            company_stats_live, security_incidents, compliance_status,
            security_risk_score_metrics, asset_view_data
        )

        print(f" DEBUG: Asset metrics keys: {list(asset_metrics.keys())}")

        # Frontend-ready JSON structure - NO HARDCODED VALUES
        return {
            "connectsecure_metrics": {
                # Asset inventory with real data
                "asset_inventory": asset_metrics,

                # Real vulnerability data from company stats
                **vulnerability_count_metrics,  # Merges vulnerability_severity directly

                # Real agents data (active only)
                **agents_metrics,  # Merges agent_type_distribution directly

                # Real security risk score with distribution
                **security_risk_score_metrics,  # Merges security_risk_score directly

                # Real asset type distribution data
                **asset_type_distribution_metrics,  # Merges asset_type_distribution directly

                # Real OS distribution data
                **os_distribution_metrics,  # Merges operating_system_distribution directly

                # Other metrics
                "security_incidents": incident_metrics,
                "compliance_status": compliance_metrics,
                "summary": summary_metrics
            }
        }

    def _extract_os_name_from_new_structure(self, asset: Dict[str, Any]) -> str:
        """Extract OS name from the new asset structure."""
        # Try direct OS fields first (from asset_view)
        os_name = (
                asset.get('os_name') or
                asset.get('os_full_name') or
                asset.get('platform') or
                asset.get('codename')
        )

        if os_name and os_name.lower() not in ['', 'unknown', 'null']:
            return os_name

        # Fall back to fingerprint extraction (from detailed assets)
        return self._extract_os_name(asset)

    def test_connection(self) -> bool:
        """Test ConnectSecure API connectivity."""
        try:
            return self.client.test_connection()
        except Exception as e:
            logger.error(f"ConnectSecure connection test failed: {e}")
            return False

    # Private methods for data processing
    def _process_vulnerability_data(self, vulnerabilities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process vulnerability data into metrics."""
        if not vulnerabilities:
            return {
                "total_vulnerabilities": 0,
                "by_severity": {"Critical": 0, "High": 0, "Medium": 0, "Low": 0},
                "by_category": {},
                "remediation_status": {"Open": 0, "In Progress": 0, "Resolved": 0},
                "devices_affected": 0
            }

        # Count by severity
        severity_counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
        category_counts = {}
        status_counts = {"Open": 0, "In Progress": 0, "Resolved": 0}
        affected_devices = set()

        for vuln in vulnerabilities:
            # Severity analysis
            severity = str(vuln.get('severity', 'Unknown')).title()
            if severity in severity_counts:
                severity_counts[severity] += 1

            # Alternative severity field names
            risk_level = str(vuln.get('risk_level', '')).title()
            if risk_level in severity_counts:
                severity_counts[risk_level] += 1

            # Category analysis
            category = vuln.get('category', vuln.get('type', 'Unknown'))
            if category:
                category_counts[category] = category_counts.get(category, 0) + 1

            # Status analysis
            status = str(vuln.get('status', vuln.get('state', 'Open'))).replace('_', ' ').title()
            if status in status_counts:
                status_counts[status] += 1

            # Track affected devices
            device_id = vuln.get('device_id', vuln.get('asset_id', vuln.get('host_id')))
            if device_id:
                affected_devices.add(device_id)

        return {
            "total_vulnerabilities": len(vulnerabilities),
            "by_severity": severity_counts,
            "by_category": category_counts,
            "remediation_status": status_counts,
            "devices_affected": len(affected_devices),
            "risk_score": self._calculate_vulnerability_risk_score(vulnerabilities)
        }

    def _process_incident_data(self, incidents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process security incident data into metrics."""
        if not incidents:
            return {
                "total_incidents": 0,
                "by_severity": {"Critical": 0, "High": 0, "Medium": 0, "Low": 0},
                "by_status": {"Open": 0, "Investigating": 0, "Resolved": 0},
                "avg_resolution_time": 0,
                "recent_incidents": 0
            }

        severity_counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
        status_counts = {"Open": 0, "Investigating": 0, "Resolved": 0}
        resolution_times = []
        recent_incidents = 0

        # Calculate "recent" as last 30 days
        thirty_days_ago = datetime.now() - timedelta(days=30)

        for incident in incidents:
            # Severity analysis
            severity = str(incident.get('severity', 'Unknown')).title()
            if severity in severity_counts:
                severity_counts[severity] += 1

            # Status analysis
            status = str(incident.get('status', 'Open')).replace('_', ' ').title()
            if 'resolv' in status.lower():
                status = 'Resolved'
            elif 'investigat' in status.lower() or 'progress' in status.lower():
                status = 'Investigating'
            elif 'open' in status.lower() or 'active' in status.lower():
                status = 'Open'

            if status in status_counts:
                status_counts[status] += 1

            # Resolution time calculation
            if incident.get('resolved_date') and incident.get('created_date'):
                try:
                    created = datetime.fromisoformat(str(incident['created_date']).replace('Z', '+00:00'))
                    resolved = datetime.fromisoformat(str(incident['resolved_date']).replace('Z', '+00:00'))
                    resolution_time = (resolved - created).total_seconds() / 3600  # hours
                    resolution_times.append(resolution_time)
                except:
                    pass

            # Recent incidents count
            if incident.get('created_date'):
                try:
                    created = datetime.fromisoformat(str(incident['created_date']).replace('Z', '+00:00'))
                    if created.replace(tzinfo=None) > thirty_days_ago:
                        recent_incidents += 1
                except:
                    pass

        avg_resolution = sum(resolution_times) / len(resolution_times) if resolution_times else 0

        return {
            "total_incidents": len(incidents),
            "by_severity": severity_counts,
            "by_status": status_counts,
            "avg_resolution_time": round(avg_resolution, 1),
            "recent_incidents": recent_incidents,
            "resolution_times": resolution_times
        }

    def _process_compliance_data(self, compliance: Dict[str, Any]) -> Dict[str, Any]:
        """Process compliance status data into metrics."""
        if not compliance:
            return {
                "overall_score": 0,
                "frameworks": {},
                "controls_passed": 0,
                "controls_failed": 0,
                "last_assessment": None,
                "status": "Unknown"
            }

        overall_score = compliance.get('overall_score', compliance.get('score', 0))

        # Determine status based on score
        if overall_score >= 90:
            status = "Excellent"
        elif overall_score >= 80:
            status = "Good"
        elif overall_score >= 70:
            status = "Fair"
        elif overall_score >= 60:
            status = "Poor"
        else:
            status = "Critical"

        return {
            "overall_score": overall_score,
            "frameworks": compliance.get('frameworks', {}),
            "controls_passed": compliance.get('controls_passed', 0),
            "controls_failed": compliance.get('controls_failed', 0),
            "last_assessment": compliance.get('last_assessment'),
            "status": status,
            "recommendations": compliance.get('recommendations', [])
        }

    def _process_risk_score_data(self, risk_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process risk score data from asset stats with average calculation across all assets."""

        print(
            f" DEBUG: _process_risk_score_data ENTRY - risk_data type: {type(risk_data)}, length: {len(risk_data) if isinstance(risk_data, list) else 'N/A'}")

        risk_info = {
            "average_score": 0.0,
            "risk_level": "Unknown",
            "description": "Risk score data unavailable",
            "recommendation": "Enable risk scoring monitoring",
            "trend": "Stable",
            "company_name": "Unknown Company",
            "raw_score": 0.0,
            "total_assets_evaluated": 0
        }

        print(f" DEBUG: Initial risk_info: {risk_info}")

        if not risk_data or not isinstance(risk_data, list):
            print(" DEBUG: No valid risk_data provided - returning early")
            return risk_info

        print(f"DEBUG: Processing {len(risk_data)} asset stats records...")

        try:
            # Extract avg_risk_score from each asset's vul_stats
            valid_scores = []
            company_id = None

            for asset_stat in risk_data:
                print(f" DEBUG: Processing asset_stat: asset_id={asset_stat.get('asset_id', 'N/A')}")

                # Get company info from first asset
                if company_id is None:
                    company_id = asset_stat.get('company_id')

                vul_stats = asset_stat.get('vul_stats', {})
                if vul_stats and 'avg_risk_score' in vul_stats:
                    avg_score = vul_stats['avg_risk_score']
                    if avg_score is not None:  # Include 0 scores but exclude None
                        valid_scores.append(float(avg_score))
                        print(f" DEBUG: Added score {avg_score} from asset {asset_stat.get('asset_id')}")

            print(f" DEBUG: Collected {len(valid_scores)} valid scores: {valid_scores}")

            if valid_scores:
                # Calculate the average of all asset risk scores
                average_risk_score = sum(valid_scores) / len(valid_scores)

                print(f" DEBUG: Calculated average risk score: {average_risk_score}")

                risk_info["average_score"] = round(average_risk_score, 1)
                risk_info["raw_score"] = average_risk_score
                risk_info["total_assets_evaluated"] = len(valid_scores)
                risk_info["company_name"] = f"Company {company_id}" if company_id else "Unknown Company"

                # Determine risk level and recommendations based on average score
                if average_risk_score >= 80:
                    risk_info["risk_level"] = "Critical"
                    risk_info[
                        "description"] = f"Critical average security risk score of {average_risk_score:.1f}/100 across {len(valid_scores)} assets"
                    risk_info[
                        "recommendation"] = "Immediate action required to address critical security risks across multiple assets"
                elif average_risk_score >= 60:
                    risk_info["risk_level"] = "High"
                    risk_info[
                        "description"] = f"High average security risk score of {average_risk_score:.1f}/100 across {len(valid_scores)} assets"
                    risk_info[
                        "recommendation"] = "Prioritize security improvements to reduce risk across affected assets"
                elif average_risk_score >= 40:
                    risk_info["risk_level"] = "Moderate"
                    risk_info[
                        "description"] = f"Moderate average security risk score of {average_risk_score:.1f}/100 across {len(valid_scores)} assets"
                    risk_info["recommendation"] = "Review and enhance security policies across asset inventory"
                elif average_risk_score >= 20:
                    risk_info["risk_level"] = "Low"
                    risk_info[
                        "description"] = f"Low average security risk score of {average_risk_score:.1f}/100 across {len(valid_scores)} assets"
                    risk_info["recommendation"] = "Maintain current security practices and monitor for changes"
                else:
                    risk_info["risk_level"] = "Very Low"
                    risk_info[
                        "description"] = f"Very low average security risk score of {average_risk_score:.1f}/100 across {len(valid_scores)} assets"
                    risk_info["recommendation"] = "Excellent security posture - continue current practices"

                print(f" DEBUG: Final risk_info: {risk_info}")
                logger.info(
                    f" Processed risk score: Average = {average_risk_score:.1f} across {len(valid_scores)} assets")
            else:
                print(" DEBUG: No valid risk scores found in any asset")
                risk_info["description"] = "No assets with valid risk scores found"
                risk_info["recommendation"] = "Verify asset risk scoring is enabled and functioning"

        except Exception as e:
            print(f" DEBUG: Exception processing risk data: {e}")
            logger.error(f"Error processing ConnectSecure asset stats risk data: {e}")
            import traceback
            traceback.print_exc()

        print(f" DEBUG: _process_risk_score_data EXIT - returning: {risk_info}")
        return risk_info


    def _determine_asset_online_status(self, asset: Dict[str, Any]) -> bool:
        """
        Determine if an asset is online based on ConnectSecure data structure.
        """
        # Primary status field (boolean)
        if 'status' in asset:
            return bool(asset['status'])

        # Check scan_status as secondary indicator
        if 'scan_status' in asset:
            return bool(asset['scan_status'])

        # Check last_discovered_time - consider online if discovered recently (within 7 days)
        last_discovered = asset.get('last_discovered_time')
        if last_discovered:
            try:
                seven_days_ago = datetime.now() - timedelta(days=7)
                last_discovered_dt = datetime.fromisoformat(str(last_discovered).replace('Z', '+00:00'))
                return last_discovered_dt.replace(tzinfo=None) > seven_days_ago
            except:
                pass

        # Default to True if no status indicators found
        return True

    def _extract_simplified_asset_type(self, asset: Dict[str, Any]) -> str:
        """Extract simplified asset type: either 'other_asset' or 'discovered'."""
        # Check asset_type field directly
        asset_type = asset.get('asset_type', '').lower()
        if asset_type == 'discovered':
            return 'discovered'

        # Check if this looks like a discovered asset
        agent_type = asset.get('agent_type', '')
        if agent_type == 'LIGHTWEIGHT':
            return 'discovered'

        # Check discovered_protocols
        discovered_protocols = asset.get('discovered_protocols', [])
        if discovered_protocols:
            return 'discovered'

        # Default to other_asset
        return 'other_asset'

    def _extract_os_name(self, asset: Dict[str, Any]) -> str:
        """Extract OS name from ConnectSecure data structure."""
        # Primary OS field
        os_name = asset.get('os_name', '')
        if os_name:
            return self._normalize_os_name(os_name)

        # Check codename field
        codename = asset.get('codename', '')
        if codename:
            return self._normalize_os_name(codename)

        # Check platform field
        platform = asset.get('platform', '')
        if platform:
            return self._normalize_os_name(platform)

        return 'Unknown'

    def _normalize_os_name(self, os_name: str) -> str:
        """Normalize OS name strings based on actual ConnectSecure data."""
        if not os_name:
            return 'Unknown'

        os_lower = os_name.lower()

        # Handle ConnectSecure specific OS naming
        if 'microsoft windows 11 pro' in os_lower:
            return 'Windows 11 Pro'
        elif 'microsoft windows 11' in os_lower:
            return 'Windows 11'
        elif 'microsoft windows 10 pro' in os_lower:
            return 'Windows 10 Pro'
        elif 'microsoft windows 10' in os_lower:
            return 'Windows 10'
        elif 'windows server 2022' in os_lower:
            return 'Windows Server 2022'
        elif 'windows server 2019' in os_lower:
            return 'Windows Server 2019'
        elif 'windows server 2016' in os_lower:
            return 'Windows Server 2016'
        elif 'windows server' in os_lower:
            return 'Windows Server'
        elif 'windows' in os_lower:
            return 'Windows'

        # Linux variants
        elif 'ubuntu' in os_lower:
            return 'Ubuntu Linux'
        elif 'centos' in os_lower:
            return 'CentOS Linux'
        elif 'redhat' in os_lower or 'rhel' in os_lower:
            return 'Red Hat Linux'
        elif 'linux' in os_lower:
            return 'Linux'

        # macOS variants
        elif 'mac' in os_lower or 'darwin' in os_lower or 'osx' in os_lower:
            return 'macOS'

        # Mobile OS
        elif 'ios' in os_lower:
            return 'iOS'
        elif 'android' in os_lower:
            return 'Android'

        # Return original if no normalization applies
        return os_name.title()

    def _generate_summary_metrics(self, vulnerabilities: List[Dict], incidents: List[Dict],
                                  compliance: Dict, risk_data: Dict, assets: List[Dict]) -> Dict[str, Any]:
        """Generate summary metrics using only actual endpoint data."""
        # Count critical issues
        critical_vulns = len([v for v in vulnerabilities
                              if str(v.get('severity', '')).lower() == 'critical'])

        critical_incidents = len([i for i in incidents
                                  if str(i.get('severity', '')).lower() == 'critical'])

        active_incidents = len([i for i in incidents
                                if 'open' in str(i.get('status', '')).lower() or
                                'active' in str(i.get('status', '')).lower()])

        # Overall risk assessment
        risk_score = 0
        if risk_data:
            risk_score = risk_data.get('overall_score', risk_data.get('risk_score', 0))

        compliance_score = 0
        if compliance:
            compliance_score = compliance.get('overall_score', compliance.get('score', 0))

        # Only count discovered assets that have online/offline status
        discovered_assets = [asset for asset in assets if asset.get('asset_type') == 'discovered']
        online_count = sum(1 for asset in discovered_assets if asset.get('online_status') is True)
        offline_count = sum(1 for asset in discovered_assets if asset.get('online_status') is not True)
        total_assets_calculated = online_count + offline_count

        print(
            f" DEBUG: Summary metrics - Online: {online_count}, Offline: {offline_count}, Total: {total_assets_calculated}")

        # Determine overall security posture
        if critical_vulns > 0 or critical_incidents > 0 or risk_score >= 80:
            security_posture = "Critical"
        elif risk_score >= 60 or compliance_score < 70:
            security_posture = "Needs Attention"
        elif risk_score >= 40 or compliance_score < 80:
            security_posture = "Monitor Closely"
        else:
            security_posture = "Good"

        # Use actual data from endpoints - NO HARDCODED ESTIMATES
        return {
            "total_vulnerabilities": len(vulnerabilities),
            "critical_vulnerabilities": critical_vulns,
            "active_incidents": active_incidents,
            "total_assets": total_assets_calculated,
            "risk_score": self._safe_float(risk_score),
            "compliance_score": self._safe_float(compliance_score),
            "security_posture": security_posture,
            "threats_detected": len(vulnerabilities) + len(incidents),
            "threats_blocked": 0,  # Would need specific endpoint data
            "last_updated": datetime.now().isoformat()
        }

    def _calculate_vulnerability_risk_score(self, vulnerabilities: List[Dict[str, Any]]) -> float:
        """Calculate overall risk score based on vulnerabilities."""
        if not vulnerabilities:
            return 0.0

        severity_weights = {"Critical": 10, "High": 7, "Medium": 4, "Low": 1}
        total_score = 0

        for vuln in vulnerabilities:
            severity = str(vuln.get('severity', 'Low')).title()
            weight = severity_weights.get(severity, 1)
            total_score += weight

        # Normalize to 0-100 scale
        max_possible = len(vulnerabilities) * 10
        return round((total_score / max_possible * 100), 1) if max_possible > 0 else 0.0

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        """Safely convert value to float."""
        try:
            if value is None or value == "":
                return default
            return float(str(value))
        except (ValueError, TypeError):
            return default
    def _combine_vulnerability_metrics(self, monthly_metrics: Dict[str, Any], live_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Combine monthly and live vulnerability metrics into the new structure.
        Returns vulnerability_severity with live_count and monthly_count sub-objects.
        """
        monthly_vuln = monthly_metrics.get("vulnerability_severity", {})
        live_vuln = live_metrics.get("vulnerability_severity", {})

        return {
            "vulnerability_severity": {
                "live_count": {
                    "critical": live_vuln.get("critical", 0),
                    "high": live_vuln.get("high", 0),
                    "medium": live_vuln.get("medium", 0),
                    "low": live_vuln.get("low", 0)
                },
                "monthly_count": {
                    "critical": monthly_vuln.get("critical", 0),
                    "high": monthly_vuln.get("high", 0),
                    "medium": monthly_vuln.get("medium", 0),
                    "low": monthly_vuln.get("low", 0)
                }
            }
        }

    def _combine_risk_score_metrics(self, monthly_metrics: Dict[str, Any], live_metrics: Dict[str, Any], quarterly_metrics: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Combine monthly, live, and quarterly risk score metrics into the new structure.
        Returns security_risk_score with live_count, monthly_count, and quarterly_count values (null if no data).
        """
        monthly_risk = monthly_metrics.get("security_risk_score", {})
        live_risk = live_metrics.get("security_risk_score", {})

        # Get overall_score, return null if no assets (instead of 0)
        monthly_score = monthly_risk.get("overall_score")
        live_score = live_risk.get("overall_score")

        # If total_assets is 0, set score to null instead of 0
        if monthly_risk.get("total_assets", 0) == 0:
            monthly_score = None
        if live_risk.get("total_assets", 0) == 0:
            live_score = None

        # Quarterly score
        quarterly_score = None
        if quarterly_metrics:
            quarterly_risk = quarterly_metrics.get("security_risk_score", {})
            quarterly_score = quarterly_risk.get("overall_score")
            if quarterly_risk.get("total_assets", 0) == 0:
                quarterly_score = None

        return {
            "security_risk_score": {
                "live_count": live_score,
                "monthly_count": monthly_score,
                "quarterly_count": quarterly_score
            }
        }

    def _process_company_stats_data(self, company_stats: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process company stats data to extract vulnerability counts from asset_problem_stats.
        Maps: "1" = Critical, "2" = High, "3" = Medium, "4" = Low
        """
        if not company_stats:
            print(" DEBUG: No company stats data available")
            return {
                "vulnerability_severity": {
                    "critical": 0,
                    "high": 0,
                    "medium": 0,
                    "low": 0,
                    "total": 0
                }
            }

        # Extract asset_problem_stats from company_stats
        asset_problem_stats = company_stats.get("asset_problem_stats", {})
        print(f" DEBUG: asset_problem_stats: {asset_problem_stats}")

        # Map problem IDs to severity levels
        critical_count = int(asset_problem_stats.get("1", 0))  # Critical vulnerabilities
        high_count = int(asset_problem_stats.get("2", 0))      # High vulnerabilities
        medium_count = int(asset_problem_stats.get("3", 0))    # Medium vulnerabilities
        low_count = int(asset_problem_stats.get("4", 0))       # Low vulnerabilities

        total_vulnerabilities = critical_count + high_count + medium_count + low_count

        vulnerability_data = {
            "critical": critical_count,
            "high": high_count,
            "medium": medium_count,
            "low": low_count,
            "total": total_vulnerabilities
        }

        print(f" DEBUG: Processed vulnerability counts: {vulnerability_data}")

        return {
            "vulnerability_severity": vulnerability_data
        }

    def _process_asset_type_distribution(self, assets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process assets to extract asset type distribution (discovered, other_asset, unknown)."""
        print(f" DEBUG: Processing {len(assets)} assets for asset type distribution")

        if not assets:
            return {
                "asset_type_distribution": {
                    "discovered": 0,
                    "other_asset": 0,
                    "unknown": 0
                }
            }

        # Count asset types using asset_type field from raw data
        type_counts = {'discovered': 0, 'other_asset': 0, 'unknown': 0}
        for asset in assets:
            asset_type = asset.get('asset_type', 'unknown')
            if asset_type in ['discovered', 'other_asset']:
                type_counts[asset_type] += 1
            else:
                type_counts['unknown'] += 1

        print(f" DEBUG: Asset type distribution counts: {type_counts}")

        return {
            "asset_type_distribution": type_counts
        }

    def _combine_asset_type_metrics(self, monthly_metrics: Dict[str, Any], live_metrics: Dict[str, Any], quarterly_metrics: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Combine monthly, live, and quarterly asset type distribution metrics into the new structure.
        Returns asset_type_distribution with live_count, monthly_count, and quarterly_count sub-objects.
        """
        monthly_types = monthly_metrics.get("asset_type_distribution", {})
        live_types = live_metrics.get("asset_type_distribution", {})
        quarterly_types = (quarterly_metrics or {}).get("asset_type_distribution", {})

        return {
            "asset_type_distribution": {
                "live_count": {
                    "discovered": live_types.get("discovered", 0),
                    "other_asset": live_types.get("other_asset", 0),
                    "unknown": live_types.get("unknown", 0)
                },
                "monthly_count": {
                    "discovered": monthly_types.get("discovered", 0),
                    "other_asset": monthly_types.get("other_asset", 0),
                    "unknown": monthly_types.get("unknown", 0)
                },
                "quarterly_count": {
                    "discovered": quarterly_types.get("discovered", 0),
                    "other_asset": quarterly_types.get("other_asset", 0),
                    "unknown": quarterly_types.get("unknown", 0)
                }
            }
        }

    def _process_os_distribution(self, assets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process assets to extract OS distribution (Windows 11, Windows Server, Linux, Others)."""
        print(f" DEBUG: Processing {len(assets)} assets for OS distribution")

        if not assets:
            return {
                "operating_system_distribution": {
                    "Others": 0
                }
            }

        # Only count discovered assets
        discovered_assets = [asset for asset in assets if asset.get('asset_type') == 'discovered']

        os_counts = {}
        for asset in discovered_assets:
            os_name = self._extract_os_name(asset)
            os_name = self._standardize_os_name(str(os_name))

            # Change "Unknown" to "Others"
            if os_name in ['Unknown', 'unknown', '']:
                os_name = 'Others'

            os_counts[os_name] = os_counts.get(os_name, 0) + 1

        print(f"🔍 DEBUG: OS distribution counts: {os_counts}")

        # If no OS data at all, add Others
        if not os_counts:
            os_counts['Others'] = len(discovered_assets) if discovered_assets else 0

        return {
            "operating_system_distribution": os_counts
        }

    def _combine_os_distribution_metrics(self, monthly_metrics: Dict[str, Any], live_metrics: Dict[str, Any], quarterly_metrics: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Combine monthly, live, and quarterly OS distribution metrics into the new structure.
        Returns operating_system_distribution with live_count, monthly_count, and quarterly_count sub-objects.
        """
        monthly_os = monthly_metrics.get("operating_system_distribution", {})
        live_os = live_metrics.get("operating_system_distribution", {})
        quarterly_os = (quarterly_metrics or {}).get("operating_system_distribution", {})

        return {
            "operating_system_distribution": {
                "live_count": live_os,
                "monthly_count": monthly_os,
                "quarterly_count": quarterly_os
            }
        }

