"""
Security Assessment Orchestrator
Extracted from: security_reporting_system/src/main.py (lines 56-593)

Main orchestrator for security assessment data collection and reporting.
Coordinates data collection from multiple platforms:
- NinjaOne
- Autotask
- ConnectSecure
- Bitdefender
- Cove
"""

import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

# Import processors from new structure
from app.processors.ninjaone_processor import NinjaOneProcessor
from app.processors.autotask_processor import AutotaskProcessor
from app.processors.connectsecure_processor import ConnectSecureProcessor
from app.processors.bitdefender_processor import BitdefenderProcessor
from app.processors.cove_processor import CoveProcessor
from app.processors.sentinelone_processor import SentinelOneProcessor
from app.processors.nodeware_processor import NodewareProcessor
from app.processors.dnsfilter_processor import DNSFilterProcessor
from app.processors.dropsuite_processor import DropsuiteProcessor
from app.processors.blackpoint_processor import BlackpointProcessor
from app.processors.axcient_processor import AxcientProcessor
from app.processors.loyaltyloop_processor import LoyaltyLoopProcessor
from app.processors.infima_processor import InfimaProcessor

logger = logging.getLogger(__name__)


# ============================================================================
#                    GLOBAL CACHE VARIABLES
# ============================================================================
# Global cache to prevent duplicate API calls
_ninjaone_cache = None
_autotask_cache = None
_cache_timestamp = None


def _reset_cache():
    """Reset cache for new execution."""
    global _ninjaone_cache, _autotask_cache, _cache_timestamp
    _ninjaone_cache = None
    _autotask_cache = None
    _cache_timestamp = datetime.now()


# ============================================================================
#                    SECURITY ASSESSMENT ORCHESTRATOR CLASS
# ============================================================================
class SecurityAssessmentOrchestrator:
    """Main orchestrator for security assessment data collection and reporting."""

    def __init__(self, account_id: int = None, org_id: int = None, credential_id: str = None):
        """
        Initialize SecurityAssessmentOrchestrator.

        Args:
            account_id: Account ID for fetching credentials from integration_credentials table (NEW)
            org_id: Organization ID for fetching org-specific IDs from organizations table (NEW)
            credential_id: DEPRECATED - Legacy UUID for old user_credentials table
        """
        self.account_id = account_id
        self.org_id = org_id
        self.credential_id = credential_id

        # Store for later initialization with org-specific IDs
        self.ninjaone_processor = None
        self.autotask_processor = None
        self.connectsecure_processor = None
        self.bitdefender_processor = None
        self.cove_processor = None
        self.sentinelone_processor = None
        self.nodeware_processor = None
        self.dnsfilter_processor = None
        self.dropsuite_processor = None
        self.blackpoint_processor = None
        self.axcient_processor = None
        self.loyaltyloop_processor = None
        self.infima_processor = None

        logger.info(f"SecurityAssessmentOrchestrator initialized with account_id: {account_id}, org_id: {org_id}")

    def _initialize_processors_with_org_id(self):
        """
        NEW: Initialize processors using account_id and org_id from organizations table.
        This is the preferred method for the new credential system.
        """
        from app.core.config.supabase import SupabaseCredentialManager

        if not self.account_id or not self.org_id:
            raise ValueError("Both account_id and org_id are required for new credential system")

        # Fetch organization-specific IDs from organizations table
        credential_manager = SupabaseCredentialManager()
        org_data = credential_manager.get_organization_by_id(self.org_id)

        if not org_data:
            raise ValueError(f"No organization found for org_id: {self.org_id}")

        # Verify account_id matches
        if org_data.get('account_id') != self.account_id:
            raise ValueError(f"Organization {self.org_id} does not belong to account {self.account_id}")

        ninjaone_org_id = org_data.get('ninjaone_org_id')
        autotask_company_id = org_data.get('autotask_id')
        connectsecure_company_id = org_data.get('connectsecure_id')
        bitdefender_company_id = org_data.get('bitdefender_company_id')
        cove_customer_id = org_data.get('cove_customer_id')
        sentinelone_site_id = org_data.get('sentinelone_site_id')
        nodeware_customer_token = org_data.get('nodeware_customer_token')
        dnsfilter_org_id = org_data.get('dnsfilter_org_id')
        dropsuite_org_id = org_data.get('dropsuite_org_id')
        blackpoint_tenant_id = org_data.get('blackpoint_tenant_id')
        axcient_client_id = org_data.get('axcient_client_id')
        infima_client_id = org_data.get('infima_client_id')

        logger.info(f"Organization: {org_data.get('name', 'Unknown')} (ID: {self.org_id})")
        logger.info(f"  NinjaOne Org ID: {ninjaone_org_id}")
        logger.info(f"  Autotask Company ID: {autotask_company_id}")
        logger.info(f"  ConnectSecure Company ID: {connectsecure_company_id}")
        logger.info(f"  Bitdefender Company ID: {bitdefender_company_id}")
        logger.info(f"  Cove Customer ID: {cove_customer_id}")
        logger.info(f"  SentinelOne Site ID: {sentinelone_site_id}")
        logger.info(f"  NodeWare Customer Token: {nodeware_customer_token}")
        logger.info(f"  DNSFilter Org ID: {dnsfilter_org_id}")
        logger.info(f"  Dropsuite Org Token: {dropsuite_org_id}")
        logger.info(f"  Blackpoint Tenant ID: {blackpoint_tenant_id}")
        logger.info(f"  Axcient Client ID: {axcient_client_id}")
        logger.info(f"  Infima Client ID: {infima_client_id}")

        # PHASE 1 OPTIMIZATION: Load selected platforms for this account.
        # Only initialize processors for platforms that have at least one chart selected.
        # If RPC fails, fall back to initializing all configured processors.
        selected_platforms = None
        try:
            from app.core.database.engine import SessionLocal
            from app.core.database.rpc import rpc_get_account_charts
            db = SessionLocal()
            try:
                charts_data = rpc_get_account_charts(db, self.account_id)
            finally:
                db.close()
            if charts_data:
                selected_platforms = {chart.get('integration_key') for chart in charts_data}
                logger.info(f"Selected platforms for account {self.account_id}: {selected_platforms}")
            else:
                logger.warning(f"No selected charts for account {self.account_id} — initializing all configured processors")
        except Exception as e:
            logger.warning(f"Could not load selected charts — initializing all configured processors: {e}")

        def is_selected(platform_key: str) -> bool:
            if selected_platforms is None:
                return True
            return platform_key in selected_platforms

        if ninjaone_org_id and is_selected('ninjaone'):
            self.ninjaone_processor = NinjaOneProcessor(
                account_id=self.account_id,
                ninjaone_org_id=ninjaone_org_id
            )
        else:
            logger.info(f"NinjaOne: {'not selected' if ninjaone_org_id else 'not configured'} — skipping")
            self.ninjaone_processor = None

        if autotask_company_id and is_selected('autotask'):
            self.autotask_processor = AutotaskProcessor(account_id=self.account_id)
        else:
            logger.info(f"Autotask: {'not selected' if autotask_company_id else 'not configured'} — skipping")
            self.autotask_processor = None

        if connectsecure_company_id and is_selected('connectsecure'):
            self.connectsecure_processor = ConnectSecureProcessor(
                account_id=self.account_id,
                connectsecure_company_id=connectsecure_company_id
            )
        else:
            logger.info(f"ConnectSecure: {'not selected' if connectsecure_company_id else 'not configured'} — skipping")
            self.connectsecure_processor = None

        if bitdefender_company_id and is_selected('bitdefender'):
            self.bitdefender_processor = BitdefenderProcessor(
                account_id=self.account_id,
                bitdefender_company_id=bitdefender_company_id
            )
        else:
            logger.info(f"Bitdefender: {'not selected' if bitdefender_company_id else 'not configured'} — skipping")
            self.bitdefender_processor = None

        if cove_customer_id and is_selected('cove'):
            self.cove_processor = CoveProcessor(
                account_id=self.account_id,
                cove_customer_id=cove_customer_id
            )
        else:
            logger.info(f"Cove: {'not selected' if cove_customer_id else 'not configured'} — skipping")
            self.cove_processor = None

        if sentinelone_site_id and is_selected('sentinelone'):
            self.sentinelone_processor = SentinelOneProcessor(
                account_id=self.account_id,
                sentinelone_site_id=sentinelone_site_id
            )
        else:
            logger.info(f"SentinelOne: {'not selected' if sentinelone_site_id else 'not configured'} — skipping")
            self.sentinelone_processor = None

        if nodeware_customer_token and is_selected('nodeware'):
            self.nodeware_processor = NodewareProcessor(
                account_id=self.account_id,
                nodeware_customer_token=nodeware_customer_token
            )
        else:
            logger.info(f"NodeWare: {'not selected' if nodeware_customer_token else 'not configured'} — skipping")
            self.nodeware_processor = None

        if dnsfilter_org_id and is_selected('dnsfilter'):
            self.dnsfilter_processor = DNSFilterProcessor(
                account_id=self.account_id,
                dnsfilter_org_id=dnsfilter_org_id
            )
        else:
            logger.info(f"DNSFilter: {'not selected' if dnsfilter_org_id else 'not configured'} — skipping")
            self.dnsfilter_processor = None

        if dropsuite_org_id and is_selected('dropsuite'):
            self.dropsuite_processor = DropsuiteProcessor(
                account_id=self.account_id,
                dropsuite_org_token=dropsuite_org_id
            )
        else:
            logger.info(f"Dropsuite: {'not selected' if dropsuite_org_id else 'not configured'} — skipping")
            self.dropsuite_processor = None
        
        if blackpoint_tenant_id and is_selected('blackpoint'):
            self.blackpoint_processor = BlackpointProcessor(
                account_id=self.account_id,
                blackpoint_tenant_id=blackpoint_tenant_id,
                org_id=self.org_id
            )
        else:
            self.blackpoint_processor = None

        if axcient_client_id and is_selected('axcient'):
            self.axcient_processor = AxcientProcessor(
                account_id=self.account_id,
                axcient_client_id=axcient_client_id
            )
        else:
            logger.info(f"Axcient: {'not selected' if axcient_client_id else 'not configured'} — skipping")
            self.axcient_processor = None

        # LoyaltyLoop is account-wide (one set of testimonial/NPS data per MSP account,
        # not scoped to an individual client organization), so there's no
        # loyaltyloop_id field on the organizations row to gate on like the other
        # integrations above. We gate on chart selection only, and since credential
        # absence isn't detectable up front the same way, LoyaltyLoopProcessor's
        # __init__ is wrapped so a missing/invalid credential just skips the
        # platform instead of raising into the caller.
        if is_selected('loyaltyloop'):
            try:
                self.loyaltyloop_processor = LoyaltyLoopProcessor(account_id=self.account_id)
            except Exception as e:
                logger.info(f"LoyaltyLoop: not configured for account {self.account_id} — skipping ({e})")
                self.loyaltyloop_processor = None
        else:
            logger.info("LoyaltyLoop: not selected — skipping")
            self.loyaltyloop_processor = None

        if infima_client_id and is_selected('infima'):
            
            self.infima_processor = InfimaProcessor(
                account_id=self.account_id,
                infima_client_id=infima_client_id
            )
        else:
            logger.info(f"Infima: {'not selected' if infima_client_id else 'not configure'} — skipping")
            self.infima_processor = None

        return {
            'ninjaone_org_id': ninjaone_org_id,
            'autotask_company_id': autotask_company_id,
            'connectsecure_company_id': connectsecure_company_id,
            'bitdefender_company_id': bitdefender_company_id,
            'cove_customer_id': cove_customer_id,
            'sentinelone_site_id': sentinelone_site_id,
            'nodeware_customer_token': nodeware_customer_token,
            'dnsfilter_org_id': dnsfilter_org_id,
            'dropsuite_org_id': dropsuite_org_id,
            'blackpoint_tenant_id': blackpoint_tenant_id,
            'axcient_client_id': axcient_client_id,
            'infima_client_id': infima_client_id,
            'organization_name': org_data.get('name', 'Unknown')
        }

    def _initialize_processors_for_org(self, organization_mapping: Dict[str, Any]):
        """
        DEPRECATED: Initialize processors with organization_mapping (old method).
        Use _initialize_processors_with_org_id() instead.
        """
        ninjaone_org_id = organization_mapping.get('ninjaone_org_id')
        autotask_company_id = organization_mapping.get('autotask_company_id')
        connectsecure_company_id = organization_mapping.get('connectsecure_company_id')

        if self.account_id is not None:
            if ninjaone_org_id:
                self.ninjaone_processor = NinjaOneProcessor(
                    account_id=self.account_id,
                    ninjaone_org_id=ninjaone_org_id
                )
            else:
                logger.warning(f"No NinjaOne org_id found - NinjaOne data will be skipped")
                self.ninjaone_processor = None

            if autotask_company_id:
                self.autotask_processor = AutotaskProcessor(account_id=self.account_id)
            else:
                logger.warning(f"No Autotask company_id found - Autotask data will be skipped")
                self.autotask_processor = None

            if connectsecure_company_id:
                self.connectsecure_processor = ConnectSecureProcessor(
                    account_id=self.account_id,
                    connectsecure_company_id=connectsecure_company_id
                )
            else:
                logger.warning(f"No ConnectSecure company_id found - ConnectSecure data will be skipped")
                self.connectsecure_processor = None

        elif self.credential_id is not None:
            logger.warning("Using DEPRECATED credential_id method. Please migrate to account_id.")
            if ninjaone_org_id:
                self.ninjaone_processor = NinjaOneProcessor(
                    credential_id=self.credential_id,
                    ninjaone_org_id=ninjaone_org_id
                )
            else:
                logger.warning(f"No NinjaOne org_id found - NinjaOne data will be skipped")
                self.ninjaone_processor = None

            if autotask_company_id:
                self.autotask_processor = AutotaskProcessor(credential_id=self.credential_id)
            else:
                logger.warning(f"No Autotask company_id found - Autotask data will be skipped")
                self.autotask_processor = None

            if connectsecure_company_id:
                self.connectsecure_processor = ConnectSecureProcessor(
                    credential_id=self.credential_id,
                    connectsecure_company_id=connectsecure_company_id
                )
            else:
                logger.warning(f"No ConnectSecure company_id found - ConnectSecure data will be skipped")
                self.connectsecure_processor = None

        else:
            raise ValueError("Either account_id or credential_id must be provided")

    async def collect_all_data_with_org_id(self, month_name: str = None) -> Dict[str, Any]:
        """
        NEW: Collect data using account_id and org_id from organizations table.
        This is the preferred method for the new credential system.
        """
        if not self.account_id or not self.org_id:
            raise ValueError("Both account_id and org_id are required")

        # Initialize processors using org_id
        org_info = self._initialize_processors_with_org_id()

        logger.info(f"Processing organization: {org_info['organization_name']} (Org ID: {self.org_id})")

        # Use the autotask_company_id from org_info for data collection
        autotask_company_id = org_info.get('autotask_company_id')

        # Collect data from all platforms
        final_data = await self.collect_all_data(company_id=autotask_company_id, month_name=month_name)

        # Ensure execution_info always has organization_name (even if NinjaOne is not configured)
        if "execution_info" not in final_data:
            final_data["execution_info"] = {
                "organization_id": str(self.org_id),
                "organization_name": org_info['organization_name'],
                "timestamp": datetime.now().isoformat(),
                "data_sources": []
            }
        else:
            # Override with correct org info from database
            final_data["execution_info"]["organization_id"] = str(self.org_id)
            final_data["execution_info"]["organization_name"] = org_info['organization_name']

        return final_data

    async def collect_all_data_for_org(self, ninjaone_org_id: str, month_name: str = None) -> Dict[str, Any]:
        """
        DEPRECATED: Collect data for a specific organization using organization_mapping.
        Use collect_all_data_with_org_id() instead for new credential system.
        """
        from app.services.organizations.service import OrganizationMappingService

        # Get organization mapping
        mapping_service = OrganizationMappingService()
        organization_mapping = mapping_service.get_mapping_by_ninjaone_id(ninjaone_org_id)

        if not organization_mapping:
            raise ValueError(f"No organization mapping found for NinjaOne org ID: {ninjaone_org_id}")

        logger.info(f"Processing organization: {organization_mapping.get('organization_name')} (NinjaOne ID: {ninjaone_org_id})")

        # Initialize processors with organization-specific IDs
        self._initialize_processors_for_org(organization_mapping)

        # Use the autotask_company_id from mapping for data collection
        autotask_company_id = organization_mapping.get('autotask_company_id')

        return await self.collect_all_data(company_id=autotask_company_id, month_name=month_name)

    async def collect_all_data(self, company_id: Optional[int] = None, month_name: str = None) -> Dict[str, Any]:
        """Collect data from all available sources with caching - NOW PARALLEL."""
        global _ninjaone_cache, _autotask_cache, _cache_timestamp
        _ninjaone_cache = None
        _autotask_cache = None
        _cache_timestamp = datetime.now()

        final_data = {}

        async def fetch_ninjaone():
            if not self.ninjaone_processor:
                logger.info("Skipping NinjaOne - not configured")
                return None, None
            logger.info("Fetching NinjaOne data...")
            try:
                raw = await asyncio.to_thread(
                    self.ninjaone_processor.fetch_all_data,
                    use_time_filter=True,
                    month_name=month_name
                )
                logger.info("NinjaOne data fetched successfully")
                return raw, None
            except Exception as e:
                logger.error(f"Failed to fetch NinjaOne data: {e}")
                return None, e

        async def fetch_autotask():
            if not self.autotask_processor:
                logger.info("Skipping Autotask - not configured")
                return None, None
            logger.info("Fetching Autotask data...")
            try:
                raw = await self.autotask_processor.fetch_all_data(company_id, month_name)
                logger.info("Autotask data fetched successfully")
                return raw, None
            except Exception as e:
                logger.warning(f"Failed to fetch Autotask data: {e}")
                return None, e

        async def fetch_connectsecure():
            if not self.connectsecure_processor:
                logger.info("Skipping ConnectSecure - not configured")
                return None, None
            logger.info("Fetching ConnectSecure data...")
            try:
                raw = await asyncio.to_thread(
                    self.connectsecure_processor.fetch_all_data,
                    self.connectsecure_processor.company_id,
                    month_name
                )
                logger.info("ConnectSecure data fetched successfully")
                return raw, None
            except Exception as e:
                logger.warning(f"Failed to fetch ConnectSecure data: {e}")
                return None, e

        async def fetch_bitdefender():
            if not self.bitdefender_processor:
                logger.info("=== SKIPPING BITDEFENDER - NOT CONFIGURED FOR THIS ORG ===")
                return None, None
            logger.info("=== FETCHING BITDEFENDER DATA ===")
            try:
                raw = await asyncio.to_thread(
                    self.bitdefender_processor.fetch_all_data,
                    month_name
                )
                logger.info(f"=== BITDEFENDER DATA FETCHED: {len(raw.get('endpoints_list', []))} endpoints, {len(raw.get('network_inventory', []))} inventory items ===")
                return raw, None
            except Exception as e:
                logger.error(f"=== BITDEFENDER FETCH FAILED: {e} ===")
                import traceback
                logger.error(traceback.format_exc())
                return None, e

        async def fetch_cove():
            if not self.cove_processor:
                logger.info("Skipping Cove - not configured")
                return None, None
            logger.info("Fetching Cove data...")
            try:
                raw = await asyncio.to_thread(
                    self.cove_processor.fetch_all_data,
                    self.cove_processor.customer_id
                )
                logger.info("Cove data fetched successfully")
                return raw, None
            except Exception as e:
                logger.warning(f"Failed to fetch Cove data: {e}")
                return None, e

        async def fetch_sentinelone():
            if not self.sentinelone_processor:
                logger.info("Skipping SentinelOne - not configured")
                return None, None
            logger.info("Fetching SentinelOne data...")
            try:
                raw = await asyncio.to_thread(
                    self.sentinelone_processor.fetch_all_data,
                    month_name
                )
                logger.info(f"SentinelOne data fetched: {len(raw.get('agents', []))} agents, {len(raw.get('threats', []))} threats")
                return raw, None
            except Exception as e:
                logger.error(f"Failed to fetch SentinelOne data: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return None, e

        async def fetch_nodeware():
            if not self.nodeware_processor:
                logger.info("Skipping NodeWare - not configured")
                return None, None
            logger.info("Fetching NodeWare data...")
            try:
                raw = await asyncio.to_thread(
                    self.nodeware_processor.fetch_all_data,
                    month_name
                )
                logger.info(f"NodeWare data fetched: {len(raw.get('assets', []))} assets for {raw.get('customer', {}).get('name', 'Unknown')}")
                return raw, None
            except Exception as e:
                logger.error(f"Failed to fetch NodeWare data: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return None, e

        async def fetch_dnsfilter():
            if not self.dnsfilter_processor:
                logger.info("Skipping DNSFilter - not configured")
                return None, None
            logger.info("Fetching DNSFilter data...")
            try:
                raw = await asyncio.to_thread(
                    self.dnsfilter_processor.fetch_all_data,
                    month_name
                )
                logger.info("DNSFilter data fetched successfully")
                return raw, None
            except Exception as e:
                logger.error(f"Failed to fetch DNSFilter data: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return None, e

        async def fetch_dropsuite():
            if not self.dropsuite_processor:
                logger.info("Skipping Dropsuite - not configured")
                return None, None
            logger.info("Fetching Dropsuite data...")
            try:
                raw = await asyncio.to_thread(
                    self.dropsuite_processor.fetch_all_data,
                    month_name
                )
                logger.info("Dropsuite data fetched successfully")
                return raw, None
            except Exception as e:
                logger.error(f"Failed to fetch Dropsuite data: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return None, e
        # 1. Define asynchronous execution wrapper task string mapping
        async def fetch_blackpoint():
            if not self.blackpoint_processor:
                return None, None
            try:
                raw_data = await asyncio.to_thread(self.blackpoint_processor.fetch_all_data, month_name)
                return raw_data, None
            except Exception as e:
                return None, e

        async def fetch_axcient():
            if not self.axcient_processor:
                logger.info("Skipping Axcient - not configured")
                return None, None
            logger.info("Fetching Axcient data...")
            try:
                raw = await asyncio.to_thread(
                    self.axcient_processor.fetch_all_data,
                    month_name
                )
                logger.info("Axcient data fetched successfully")
                return raw, None
            except Exception as e:
                logger.error(f"Failed to fetch Axcient data: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return None, e

        async def fetch_loyaltyloop():
            if not self.loyaltyloop_processor:
                logger.info("Skipping LoyaltyLoop - not configured")
                return None, None
            logger.info("Fetching LoyaltyLoop data...")
            try:
                raw = await asyncio.to_thread(
                    self.loyaltyloop_processor.fetch_all_data,
                    month_name
                )
                logger.info("LoyaltyLoop data fetched successfully")
                return raw, None
            except Exception as e:
                logger.warning(f"Failed to fetch LoyaltyLoop data: {e}")
                return None, e

        async def fetch_infima():
            if not self.infima_processor:
                logger.info("Skipping Infima - not configured for this org")
                return None, None
            logger.info("Fetching Infima data...")
            try:
                raw = await asyncio.to_thread(
                    self.infima_processor.fetch_all_data,
                    month_name
                )
                logger.info(f"Infima data fetched successfully: {len(raw.get('dark_web_exposures', []))} exposure records")
                return raw, None
            except Exception as e:
                logger.warning(f"Failed to fetch Infima data: {e}")
                return None, e

        logger.info("Starting PARALLEL data fetching from all platforms...")

        ninjaone_result, autotask_result, connectsecure_result, bitdefender_result, cove_result, sentinelone_result, nodeware_result, dnsfilter_result, dropsuite_result, blackpoint_result, axcient_result, loyaltyloop_result, infima_result = await asyncio.gather(
            fetch_ninjaone(),
            fetch_autotask(),
            fetch_connectsecure(),
            fetch_bitdefender(),
            fetch_cove(),
            fetch_sentinelone(),
            fetch_nodeware(),
            fetch_dnsfilter(),
            fetch_dropsuite(),
            fetch_blackpoint(),
            fetch_axcient(),
            fetch_loyaltyloop(),
            fetch_infima(),
        )

        logger.info("Processing fetched data...")

        ninjaone_raw, ninjaone_error = ninjaone_result
        if ninjaone_raw and not ninjaone_error:
            logger.info("Processing NinjaOne data...")
            ninjaone_processed = self.ninjaone_processor.process_all_data(ninjaone_raw)
            final_data.update(ninjaone_processed)
            _ninjaone_cache = ninjaone_raw
            logger.info("NinjaOne data processed successfully")
        elif ninjaone_error:
            logger.error(f"NinjaOne fetch failed: {ninjaone_error}")

        autotask_raw, autotask_error = autotask_result
        if autotask_raw and not autotask_error:
            logger.info("Processing Autotask data...")
            autotask_processed = self.autotask_processor.process_all_data(autotask_raw, company_id)
            final_data.update(autotask_processed)
            if "execution_info" in final_data:
                final_data["execution_info"]["data_sources"].append("Autotask")
            _autotask_cache = autotask_raw
            logger.info("Autotask data processed successfully")
        elif autotask_error:
            logger.warning(f"Autotask fetch failed: {autotask_error}")
            logger.info("Continuing without Autotask data...")

        connectsecure_raw, connectsecure_error = connectsecure_result
        if connectsecure_raw and not connectsecure_error:
            if len(connectsecure_raw.get('assets', [])) > 0:
                logger.info("Processing ConnectSecure data...")
                connectsecure_processed = self.connectsecure_processor.process_all_data(connectsecure_raw, month_name=month_name)
                final_data.update(connectsecure_processed)
                if "execution_info" in final_data:
                    final_data["execution_info"]["data_sources"].append("ConnectSecure")
                logger.info("ConnectSecure data processed successfully")
            else:
                logger.warning("ConnectSecure: No assets found")
        elif connectsecure_error:
            logger.warning(f"ConnectSecure fetch failed: {connectsecure_error}")
            logger.info("Continuing with available data sources...")

        bitdefender_raw, bitdefender_error = bitdefender_result
        if bitdefender_raw and not bitdefender_error:
            logger.info("=== PROCESSING BITDEFENDER DATA ===")
            bitdefender_processed = self.bitdefender_processor.process_all_data(bitdefender_raw)
            logger.info(f"=== BITDEFENDER PROCESSED DATA KEYS: {list(bitdefender_processed.keys())} ===")
            final_data.update(bitdefender_processed)
            if "execution_info" in final_data:
                final_data["execution_info"]["data_sources"].append("Bitdefender")
            logger.info("=== BITDEFENDER DATA ADDED TO FINAL OUTPUT ===")
        elif bitdefender_error:
            logger.error(f"=== BITDEFENDER FETCH FAILED: {bitdefender_error} ===")
            logger.info("Continuing with available data sources...")
        else:
            logger.info("=== BITDEFENDER: NO DATA (PROCESSOR NOT CONFIGURED) ===")

        cove_raw, cove_error = cove_result
        if cove_raw and not cove_error:
            logger.info("Processing Cove data...")
            cove_processed = self.cove_processor.process_all_data(cove_raw)
            final_data.update(cove_processed)
            final_data["cove_tables"] = cove_processed.get("tables", {})
            if "execution_info" in final_data:
                final_data["execution_info"]["data_sources"].append("Cove")
            logger.info("Cove data processed successfully")
        elif cove_error:
            logger.warning(f"Cove fetch failed: {cove_error}")
            logger.info("Continuing with available data sources...")

        sentinelone_raw, sentinelone_error = sentinelone_result
        if sentinelone_raw and not sentinelone_error:
            logger.info("Processing SentinelOne data...")
            sentinelone_processed = self.sentinelone_processor.process_all_data(sentinelone_raw)
            final_data.update(sentinelone_processed)
            if "execution_info" in final_data:
                final_data["execution_info"]["data_sources"].append("SentinelOne")
            logger.info("SentinelOne data processed successfully")
        elif sentinelone_error:
            logger.error(f"SentinelOne fetch failed: {sentinelone_error}")
            logger.info("Continuing with available data sources...")

        nodeware_raw, nodeware_error = nodeware_result
        if nodeware_raw and not nodeware_error:
            logger.info("Processing NodeWare data...")
            nodeware_processed = self.nodeware_processor.process_all_data(nodeware_raw)
            final_data.update(nodeware_processed)
            if "execution_info" in final_data:
                final_data["execution_info"]["data_sources"].append("NodeWare")
            logger.info("NodeWare data processed successfully")
        elif nodeware_error:
            logger.error(f"NodeWare fetch failed: {nodeware_error}")
            logger.info("Continuing with available data sources...")

        dnsfilter_raw, dnsfilter_error = dnsfilter_result
        if dnsfilter_raw and not dnsfilter_error:
            logger.info("Processing DNSFilter data...")
            dnsfilter_processed = self.dnsfilter_processor.process_all_data(dnsfilter_raw)
            final_data.update(dnsfilter_processed)
            if "execution_info" in final_data:
                final_data["execution_info"]["data_sources"].append("DNSFilter")
            logger.info("DNSFilter data processed successfully")
        elif dnsfilter_error:
            logger.error(f"DNSFilter fetch failed: {dnsfilter_error}")
            logger.info("Continuing with available data sources...")

        dropsuite_raw, dropsuite_error = dropsuite_result
        if dropsuite_raw and not dropsuite_error:
            logger.info("Processing Dropsuite data...")
            dropsuite_processed = self.dropsuite_processor.process_all_data(dropsuite_raw)
            final_data.update(dropsuite_processed)
            if "execution_info" in final_data:
                final_data["execution_info"]["data_sources"].append("Dropsuite")
            logger.info("Dropsuite data processed successfully")
        elif dropsuite_error:
            logger.error(f"Dropsuite fetch failed: {dropsuite_error}")
            logger.info("Continuing with available data sources...")
        
        blackpoint_raw_payload, blackpoint_execution_error = blackpoint_result
        if blackpoint_raw_payload and not blackpoint_execution_error:
            logger.info("Normalizing raw Blackpoint detection events array records...")
            processed_metrics_map = self.blackpoint_processor.process_all_data(blackpoint_raw_payload)
            final_data.update(processed_metrics_map)
            
            if "execution_info" in final_data:
                final_data["execution_info"]["data_sources"].append("Blackpoint")
        elif blackpoint_execution_error:
            logger.error(f"Bypassing active Blackpoint data pipeline processing boundary due to errors: {blackpoint_execution_error}")
        
        axcient_raw, axcient_error = axcient_result
        if axcient_raw and not axcient_error:
            logger.info("Processing Axcient data...")
            axcient_processed = self.axcient_processor.process_all_data(axcient_raw)
            final_data.update(axcient_processed)
            if "execution_info" in final_data:
                final_data["execution_info"]["data_sources"].append("Axcient")
            logger.info("Axcient data processed successfully")
        elif axcient_error:
            logger.error(f"Axcient fetch failed: {axcient_error}")
            logger.info("Continuing with available data sources...")
        

        loyaltyloop_raw, loyaltyloop_error = loyaltyloop_result
        if loyaltyloop_raw and not loyaltyloop_error:
            logger.info("Processing LoyaltyLoop data...")
            loyaltyloop_processed = self.loyaltyloop_processor.process_all_data(loyaltyloop_raw)
            final_data.update(loyaltyloop_processed)
            if "execution_info" in final_data:
                final_data["execution_info"]["data_sources"].append("LoyaltyLoop")
            logger.info("LoyaltyLoop data processed successfully")
        elif loyaltyloop_error:
            logger.warning(f"LoyaltyLoop fetch failed: {loyaltyloop_error}")
            logger.info("Continuing with available data sources...")

        infima_raw, infima_error = infima_result
        if infima_raw and not infima_error:
            logger.info("Processing Infima data...")
            infima_processed = self.infima_processor.process_all_data(infima_raw)
            final_data.update(infima_processed)
            if "execution_info" in final_data:
                final_data["execution_info"]["data_sources"].append("Infima")
            logger.info("Infima data processed successfully")
        elif infima_error:
            logger.warning(f"Infima fetch failed: {infima_error}")
            logger.info("Continuing with available data sources...")

        return final_data

    async def stream_data_per_platform(self, company_id: Optional[int] = None, month_name: str = None):
        """
        Async generator that yields each platform's data as it completes.
        All platforms run in PARALLEL, but results are yielded one-by-one as each finishes.
        Heartbeats are sent every 10 seconds to keep the connection alive.

        Yields:
            dict with keys: type, platform (optional), data (optional), progress, message (optional)
        """
        global _ninjaone_cache, _autotask_cache, _cache_timestamp
        _ninjaone_cache = None
        _autotask_cache = None
        _cache_timestamp = datetime.now()

        data_sources = []
        platforms_done = 0
        total_platforms = sum(1 for p in [
            self.ninjaone_processor, self.autotask_processor,
            self.connectsecure_processor, self.bitdefender_processor,
            self.cove_processor, self.sentinelone_processor,
            self.nodeware_processor, self.dnsfilter_processor,
            self.dropsuite_processor, self.blackpoint_processor,
            self.axcient_processor,self.loyaltyloop_processor, 
            self.infima_processor
        ] if p is not None)

        if total_platforms == 0:
            yield {"type": "error", "message": "No platforms configured", "progress": 0}
            return

        # Map platform name to its fetch+process coroutine
        async def fetch_and_process_ninjaone():
            if not self.ninjaone_processor:
                return None
            raw = await asyncio.to_thread(
                self.ninjaone_processor.fetch_all_data,
                use_time_filter=True,
                month_name=month_name
            )
            processed = self.ninjaone_processor.process_all_data(raw)
            _ninjaone_cache = raw
            return processed

        async def fetch_and_process_autotask():
            if not self.autotask_processor:
                return None
            raw = await self.autotask_processor.fetch_all_data(company_id, month_name)
            processed = self.autotask_processor.process_all_data(raw, company_id)
            _autotask_cache = raw
            return processed

        async def fetch_and_process_connectsecure():
            if not self.connectsecure_processor:
                return None
            raw = await asyncio.to_thread(
                self.connectsecure_processor.fetch_all_data,
                self.connectsecure_processor.company_id,
                month_name
            )
            if len(raw.get('assets', [])) == 0:
                logger.warning("ConnectSecure: No assets found")
                return None
            processed = self.connectsecure_processor.process_all_data(raw, month_name=month_name)
            return processed

        async def fetch_and_process_bitdefender():
            if not self.bitdefender_processor:
                return None
            raw = await asyncio.to_thread(
                self.bitdefender_processor.fetch_all_data,
                month_name
            )
            processed = self.bitdefender_processor.process_all_data(raw)
            return processed

        async def fetch_and_process_cove():
            if not self.cove_processor:
                return None
            raw = await asyncio.to_thread(
                self.cove_processor.fetch_all_data,
                self.cove_processor.customer_id
            )
            processed = self.cove_processor.process_all_data(raw)
            return processed

        async def fetch_and_process_sentinelone():
            if not self.sentinelone_processor:
                return None
            raw = await asyncio.to_thread(
                self.sentinelone_processor.fetch_all_data,
                month_name
            )
            processed = self.sentinelone_processor.process_all_data(raw)
            return processed

        async def fetch_and_process_nodeware():
            if not self.nodeware_processor:
                return None
            raw = await asyncio.to_thread(
                self.nodeware_processor.fetch_all_data,
                month_name
            )
            processed = self.nodeware_processor.process_all_data(raw)
            return processed

        async def fetch_and_process_dnsfilter():
            if not self.dnsfilter_processor:
                return None
            raw = await asyncio.to_thread(
                self.dnsfilter_processor.fetch_all_data,
                month_name
            )
            processed = self.dnsfilter_processor.process_all_data(raw)
            return processed

        async def fetch_and_process_dropsuite():
            if not self.dropsuite_processor:
                return None
            raw = await asyncio.to_thread(
                self.dropsuite_processor.fetch_all_data,
                month_name
            )
            processed = self.dropsuite_processor.process_all_data(raw)
            return processed
        
        async def fetch_and_process_blackpoint():
            if not self.blackpoint_processor:
                return None
            raw = await asyncio.to_thread(
                self.blackpoint_processor.fetch_all_data,
                month_name
            )
            processed = self.blackpoint_processor.process_all_data(raw)
            return processed
        
        async def fetch_and_process_axcient():
            if not self.axcient_processor:
                return None
            raw = await asyncio.to_thread(
                self.axcient_processor.fetch_all_data,
                month_name
            )
            processed = self.axcient_processor.process_all_data(raw)
            return processed

        async def fetch_and_process_loyaltyloop():
            if not self.loyaltyloop_processor:
                return None
            raw = await asyncio.to_thread(
                self.loyaltyloop_processor.fetch_all_data,
                month_name
            )
            processed = self.loyaltyloop_processor.process_all_data(raw)
            return processed

        async def fetch_and_process_infima():
            if not self.infima_processor:
                return None
            raw = await asyncio.to_thread(
                self.infima_processor.fetch_all_data,
                month_name
            )
            processed = self.infima_processor.process_all_data(raw)
            return processed

        # Create named tasks for all configured platforms
        tasks = {}
        if self.ninjaone_processor:
            tasks["NinjaOne"] = asyncio.create_task(fetch_and_process_ninjaone())
        if self.autotask_processor:
            tasks["Autotask"] = asyncio.create_task(fetch_and_process_autotask())
        if self.connectsecure_processor:
            tasks["ConnectSecure"] = asyncio.create_task(fetch_and_process_connectsecure())
        if self.bitdefender_processor:
            tasks["Bitdefender"] = asyncio.create_task(fetch_and_process_bitdefender())
        if self.cove_processor:
            tasks["Cove"] = asyncio.create_task(fetch_and_process_cove())
        if self.sentinelone_processor:
            tasks["SentinelOne"] = asyncio.create_task(fetch_and_process_sentinelone())
        if self.nodeware_processor:
            tasks["NodeWare"] = asyncio.create_task(fetch_and_process_nodeware())
        if self.dnsfilter_processor:
            tasks["DNSFilter"] = asyncio.create_task(fetch_and_process_dnsfilter())
        if self.dropsuite_processor:
            tasks["Dropsuite"] = asyncio.create_task(fetch_and_process_dropsuite())
        if self.blackpoint_processor:
            tasks["Blackpoint"] = asyncio.create_task(fetch_and_process_blackpoint())
        if self.axcient_processor:
            tasks["Axcient"] = asyncio.create_task(fetch_and_process_axcient())
        if self.loyaltyloop_processor:
            tasks["LoyaltyLoop"] = asyncio.create_task(fetch_and_process_loyaltyloop())
        if self.infima_processor:
            tasks["Infima"] = asyncio.create_task(fetch_and_process_infima())

        logger.info(f"Started {len(tasks)} platform tasks in parallel: {list(tasks.keys())}")

        # Poll tasks every 2 seconds, send heartbeat every 10 seconds
        heartbeat_interval = 10
        last_heartbeat = asyncio.get_event_loop().time()
        completed_platforms = set()

        while len(completed_platforms) < len(tasks):
            # Check each task
            for platform_name, task in tasks.items():
                if platform_name in completed_platforms:
                    continue
                if task.done():
                    completed_platforms.add(platform_name)
                    platforms_done += 1
                    progress = int((platforms_done / total_platforms) * 85) + 10  # 10-95 range

                    try:
                        result = task.result()
                        if result:
                            data_sources.append(platform_name)
                            yield {
                                "type": "platform_data",
                                "platform": platform_name,
                                "data": result,
                                "progress": progress
                            }
                            logger.info(f"Streamed {platform_name} data (progress: {progress}%)")
                        else:
                            yield {
                                "type": "error",
                                "platform": platform_name,
                                "message": f"{platform_name}: No data available",
                                "progress": progress
                            }
                    except Exception as e:
                        logger.error(f"{platform_name} fetch failed: {e}")
                        yield {
                            "type": "error",
                            "platform": platform_name,
                            "message": f"{platform_name} failed: {str(e)}",
                            "progress": progress
                        }

            # Send heartbeat every 10 seconds if not all done
            if len(completed_platforms) < len(tasks):
                now = asyncio.get_event_loop().time()
                if now - last_heartbeat >= heartbeat_interval:
                    pending = [p for p in tasks if p not in completed_platforms]
                    yield {
                        "type": "heartbeat",
                        "progress": int((platforms_done / total_platforms) * 85) + 10,
                        "message": f"Waiting for: {', '.join(pending)}"
                    }
                    last_heartbeat = now
                await asyncio.sleep(2)  # Poll every 2 seconds

        # Yield data_sources list for execution_info
        yield {
            "type": "stream_done",
            "data_sources": data_sources,
            "progress": 95
        }

    async def test_all_connections(self) -> Dict[str, bool]:
        """Test connectivity to all data sources."""
        results = {}

        if self.ninjaone_processor:
            try:
                org_info = self.ninjaone_processor.client.get_organization_info()
                results['ninjaone'] = bool(org_info.get('id'))
            except Exception as e:
                logger.error(f"NinjaOne connection test failed: {e}")
                results['ninjaone'] = False
        else:
            results['ninjaone'] = False

        if self.autotask_processor:
            try:
                results['autotask'] = await self.autotask_processor.test_connection()
            except Exception as e:
                logger.error(f"Autotask connection test failed: {e}")
                results['autotask'] = False
        else:
            results['autotask'] = False

        if self.connectsecure_processor:
            try:
                results['connectsecure'] = self.connectsecure_processor.test_connection()
            except Exception as e:
                logger.error(f"ConnectSecure connection test failed: {e}")
                results['connectsecure'] = False
        else:
            results['connectsecure'] = False

        if self.cove_processor:
            try:
                results['cove'] = self.cove_processor.test_connection()
            except Exception as e:
                logger.error(f"Cove connection test failed: {e}")
                results['cove'] = False
        else:
            results['cove'] = False
        
        if self.axcient_processor:
            try:
                results['axcient'] = self.axcient_processor.client.test_connection()
            except Exception as e:
                logger.error(f"Axcient connection test failed: {e}")
                results['axcient'] = False
        else:
            results['axcient'] = False

        if self.loyaltyloop_processor:
            try:
                results['loyaltyloop'] = self.loyaltyloop_processor.test_connection()
            except Exception as e:
                logger.error(f"LoyaltyLoop connection test failed: {e}")
                results['loyaltyloop'] = False
        else:
            results['loyaltyloop'] = False

        if self.infima_processor:
            try:
                results['infima'] = self.infima_processor.test_connection()
            except Exception as e:
                logger.error(f"Infima connection test failed: {e}")
                results['infima'] = False
        else:
            results['infima'] = False

        return results