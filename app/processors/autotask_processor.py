"""
Autotask Data Processor

This module handles all Autotask data fetching, processing, and analysis.
Extracted from main.py to improve modularity.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
# Add path resolution for local running
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
security_system_root = os.path.join(current_dir, '..', '..')
if security_system_root not in sys.path:
    sys.path.insert(0, security_system_root)

# Updated imports for new app/ structure
from app.core.config.settings import config_manager
from app.clients.autotask_client import AutotaskClient, AutotaskConfig

logger = logging.getLogger(__name__)


class AutotaskProcessor:
    """Handles all Autotask data operations."""

    def __init__(self, account_id: int = None, credential_id: str = None):
        """
        Initialize AutotaskProcessor with account-based credentials.

        Args:
            account_id: Account ID for fetching credentials from integration_credentials table (NEW)
            credential_id: DEPRECATED - Legacy UUID for old user_credentials table
        """
        # NEW: Load credentials from account_id (integration_credentials table)
        if account_id is not None:
            from app.core.config.supabase import SupabaseCredentialManager

            credential_manager = SupabaseCredentialManager()
            credentials = credential_manager.get_credentials_by_account_id(account_id)

            if not credentials:
                raise ValueError(f"No credentials found for account_id: {account_id}")

            # Extract Autotask credentials from decrypted data
            autotask_creds = credentials.get('autotask', {})

            self.config = AutotaskConfig(
                username=autotask_creds.get('autotask_username'),
                secret=autotask_creds.get('autotask_secret'),
                integration_code=autotask_creds.get('autotask_integration_code'),
                base_url=autotask_creds.get('autotask_base_url')
            )

            logger.info(f"Loaded Autotask credentials from account_id: {account_id}")

        # OLD: Fallback to legacy credential_id method
        elif credential_id is not None:
            logger.warning("Using DEPRECATED credential_id method. Please migrate to account_id.")
            config = config_manager.load_credentials(credential_id)

            self.config = AutotaskConfig(
                username=config['autotask_username'],
                secret=config['autotask_secret'],
                integration_code=config['autotask_integration_code'],
                base_url=config['autotask_base_url']
            )

        else:
            raise ValueError("Either account_id or credential_id must be provided")

    async def fetch_all_data(self, company_id: Optional[int] = None, month_name: str = None) -> Dict[str, Any]:
        """
        Fetch required Autotask data with error handling, requires company_id for filtering.
        Supports month filtering and "last_3_months" for quarterly reporting.

        Args:
            company_id: REQUIRED company ID to filter tickets - returns empty data if None
            month_name: Specific month name (e.g., "august_2025"), "last_3_months" for quarterly, or None for previous month

        Returns:
            Dictionary containing all required Autotask data (empty if no company_id)
        """
        # Return empty data if no company_id provided
        if company_id is None:
            logger.warning("No Autotask company_id provided - returning empty data")
            return {
                'created_vs_completed': {},
                'monthly_by_issue_type': [],
                'open_by_priority': [],
                'active_tickets': {},
                'slo_metrics': [],
                'tickets_by_contact': []
            }

        data = {}

        # Check if user requested quarterly data
        if month_name and month_name.strip().lower() == "last_3_months":
            logger.info("AutoTask: Fetching quarterly (last 3 months) data")
            return await self._fetch_quarterly_data(company_id)

        # Initialize date variables with default values (previous month)
        today = datetime.now()
        first_day_of_current_month = today.replace(day=1)
        end_of_month = first_day_of_current_month - timedelta(days=1)
        start_of_month = end_of_month.replace(day=1)

        # Calculate date range using MonthSelector if month_name is provided
        if month_name:
            try:
                from app.utils.month_selector import MonthSelector
                month_selector = MonthSelector()
                start_timestamp, end_timestamp = month_selector.get_month_timestamps(month_name)

                start_of_month = datetime.fromtimestamp(start_timestamp)
                end_of_month = datetime.fromtimestamp(end_timestamp)

                logger.info(f"AutoTask filtering for month: {month_name}")
                logger.info(f"Date range: {start_of_month.strftime('%Y-%m-%d')} to {end_of_month.strftime('%Y-%m-%d')}")

            except Exception as e:
                logger.warning(f"Failed to calculate month timestamps for {month_name}: {e}")
                # Keep the default previous month values that were already set
                logger.info(
                    f"Falling back to default previous month: {start_of_month.strftime('%Y-%m-%d')} to {end_of_month.strftime('%Y-%m-%d')}")
        else:
            logger.info("AutoTask using default previous month")

        # Dates for API queries
        start_date_str = start_of_month.strftime("%Y-%m-%d")
        end_date_str = end_of_month.strftime("%Y-%m-%d")

        # Year and month for the monthly issue type query
        target_month_year = start_of_month.year
        target_month_number = start_of_month.month

        logger.debug(f"AutoTask ticket metrics for {start_date_str} to {end_date_str}")

        async with AutotaskClient(self.config) as autotask_client:
            # Pre-warm entity info cache once — prevents multiple concurrent HTTP calls
            # to /entityInformation/fields which triggers Autotask's 3-thread limit
            await autotask_client.get_entity_info("Tickets")

            try:
                logger.debug("Fetching created vs completed tickets...")
                data['created_vs_completed'] = await autotask_client.get_created_vs_completed_tickets(
                    start_date_str, end_date_str, company_id
                )
            except Exception as e:
                logger.error(f"Failed to fetch created vs completed tickets: {e}")
                data['created_vs_completed'] = {}

            try:
                logger.debug("Fetching monthly tickets by issue type...")
                data['monthly_by_issue_type'] = await autotask_client.get_monthly_tickets_by_issue_type(
                    target_month_year, target_month_number, company_id
                )
            except Exception as e:
                logger.error(f"Failed to fetch monthly tickets by issue type: {e}")
                data['monthly_by_issue_type'] = []

            try:
                logger.debug("Fetching open tickets by priority...")
                data['open_by_priority'] = await autotask_client.get_open_tickets_by_priority(
                    target_month_year, target_month_number, company_id
                )
            except Exception as e:
                logger.error(f"Failed to fetch open tickets by priority: {e}")
                data['open_by_priority'] = []

            try:
                logger.debug("Fetching open tickets by issue/sub-issue type...")
                data['open_by_issue_subissue'] = await autotask_client.get_open_tickets_by_issue_subissue(
                    target_month_year, target_month_number, company_id
                )
            except Exception as e:
                logger.error(f"Failed to fetch open tickets by issue/sub-issue type: {e}")
                data['open_by_issue_subissue'] = []

            try:
                logger.debug("Fetching active tickets by priority...")
                data['active_tickets'] = await autotask_client.get_active_tickets_by_priority(
                    top_count=10, company_id=company_id
                )
            except Exception as e:
                logger.error(f"Failed to fetch active tickets by priority: {e}")
                data['active_tickets'] = {}

            try:
                logger.debug("Fetching SLO metrics...")
                data['slo_metrics'] = await autotask_client.get_slo_metrics(start_date_str, end_date_str, company_id)
            except Exception as e:
                logger.error(f"Failed to fetch SLO metrics: {e}")
                data['slo_metrics'] = []

            try:
                logger.debug("Fetching tickets created by contact...")
                data['tickets_by_contact'] = await autotask_client.get_tickets_created_by_contact(
                    start_date_str, end_date_str, company_id=company_id
                )
            except Exception as e:
                logger.error(f"Failed to fetch tickets by contact: {e}")
                data['tickets_by_contact'] = []

        return data

    async def _fetch_quarterly_data(self, company_id: int) -> Dict[str, Any]:
        """
        Fetch Autotask data for a rolling 3-month window (last_3_months).

        Args:
            company_id: Autotask company ID for filtering

        Returns:
            Data spanning the last 3 complete months
        """
        from app.utils.month_selector import MonthSelector
        month_selector = MonthSelector()
        start_ts, end_ts   = month_selector.get_quarterly_date_range()
        start_date_str     = datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d")
        end_date_str       = datetime.fromtimestamp(end_ts).strftime("%Y-%m-%d")
        most_recent        = month_selector.get_available_months(count=1)[0]
        most_recent_year   = most_recent.year
        most_recent_month  = most_recent.month_number

        data = {}
        async with AutotaskClient(self.config) as autotask_client:
            # Pre-warm entity info cache once — prevents multiple concurrent HTTP calls
            # to /entityInformation/fields which triggers Autotask's 3-thread limit
            await autotask_client.get_entity_info("Tickets")

            try:
                data['created_vs_completed'] = await autotask_client.get_created_vs_completed_tickets(
                    start_date_str, end_date_str, company_id)
            except Exception as e:
                logger.error(f"Quarterly: failed created_vs_completed: {e}"); data['created_vs_completed'] = {}

            try:
                data['monthly_by_issue_type'] = await autotask_client.get_quarterly_tickets_by_issue_type(
                    start_date_str, end_date_str, company_id)
            except Exception as e:
                logger.error(f"Quarterly: failed monthly_by_issue_type: {e}"); data['monthly_by_issue_type'] = []

            try:
                data['open_by_priority'] = await autotask_client.get_open_tickets_by_priority(
                    most_recent_year, most_recent_month, company_id)
            except Exception as e:
                logger.error(f"Quarterly: failed open_by_priority: {e}"); data['open_by_priority'] = []

            try:
                data['open_by_issue_subissue'] = await autotask_client.get_open_tickets_by_issue_subissue(
                    most_recent_year, most_recent_month, company_id)
            except Exception as e:
                logger.error(f"Quarterly: failed open_by_issue_subissue: {e}"); data['open_by_issue_subissue'] = []

            try:
                data['slo_metrics'] = await autotask_client.get_slo_metrics(
                    start_date_str, end_date_str, company_id)
            except Exception as e:
                logger.error(f"Quarterly: failed slo_metrics: {e}"); data['slo_metrics'] = []

            try:
                data['tickets_by_contact'] = await autotask_client.get_tickets_created_by_contact(
                    start_date_str, end_date_str, company_id=company_id)
            except Exception as e:
                logger.error(f"Quarterly: failed tickets_by_contact: {e}"); data['tickets_by_contact'] = []

            try:
                data['active_tickets'] = await autotask_client.get_active_tickets_by_priority(
                    top_count=10, company_id=company_id)
            except Exception as e:
                logger.error(f"Quarterly: failed active_tickets: {e}"); data['active_tickets'] = {}

        return data

    def process_all_data(self, raw_data: Dict[str, Any], company_id: Optional[int] = None) -> Dict[str, Any]:
        """Process all Autotask raw data into final metrics."""
        # Check if we got empty data due to missing company_id
        if not raw_data or all(not v for v in raw_data.values()):
            logger.warning("No Autotask data to process - returning empty metrics")
            return {
                "autotask_metrics": {
                    "ticket_analytics": {
                        "created_vs_completed": {},
                        "monthly_by_issue_type": [],
                        "open_by_priority": [],
                        "open_by_issue_subissue": [],
                        "tickets_by_contact": []
                    },
                    "active_tickets_analysis": {},
                    "slo_performance": [],
                    "summary": {
                        "total_slo_tickets": 0,
                        "resolved_tickets": 0,
                        "resolution_sla_violations": 0,
                        "resolution_sla_percentage": 0.0,
                        "first_response_evaluated": 0,
                        "first_response_violations": 0,
                        "first_response_sla_percentage": 0.0,
                        "active_tickets_count": 0,
                        "critical_tickets": 0
                    }
                }
            }

        slo_list = raw_data.get('slo_metrics', [])

        # DEBUG: Print what we found
        print(f"DEBUG: Processing {len(slo_list)} SLO metrics records")
        if slo_list:
            print(f"DEBUG: First SLO record keys: {list(slo_list[0].keys())}")

        # Calculate SLA metrics using Autotask methodology
        # Check both resolved_date (SLA contract) and completed_date (fallback) for resolved tickets
        resolved_tickets = [t for t in slo_list if t.get('resolved_date') is not None or t.get('completed_date') is not None]
        resolution_violations = len([t for t in resolved_tickets if t.get('sla_met') is False])

        # First Response SLA violations
        first_response_evaluated = [t for t in slo_list if t.get('first_response_met') is not None]
        first_response_violations = len([t for t in first_response_evaluated if t.get('first_response_met') is False])

        print(f"DEBUG: Resolved tickets: {len(resolved_tickets)}, Resolution violations: {resolution_violations}")
        print(
            f"DEBUG: First response evaluated: {len(first_response_evaluated)}, FR violations: {first_response_violations}")

        # Calculate percentages for summary
        resolution_sla_percentage = 0.0
        if resolved_tickets:
            resolution_sla_percentage = ((len(resolved_tickets) - resolution_violations) / len(resolved_tickets)) * 100

        first_response_sla_percentage = 0.0
        if first_response_evaluated:
            first_response_sla_percentage = ((len(first_response_evaluated) - first_response_violations) / len(
                first_response_evaluated)) * 100

        print(
            f"DEBUG: Resolution SLA: {resolution_sla_percentage:.1f}%, First Response SLA: {first_response_sla_percentage:.1f}%")

        return {
            "autotask_metrics": {
                "ticket_analytics": {
                    "created_vs_completed": raw_data.get('created_vs_completed', {}),
                    "monthly_by_issue_type": raw_data.get('monthly_by_issue_type', []),
                    "open_by_priority": raw_data.get('open_by_priority', []),
                    "open_by_issue_subissue": raw_data.get('open_by_issue_subissue', []),
                    "tickets_by_contact": raw_data.get('tickets_by_contact', [])
                },
                "active_tickets_analysis": raw_data.get('active_tickets', {}),
                "slo_performance": slo_list,
                "summary": {
                    "total_slo_tickets": len(slo_list),
                    "resolved_tickets": len(resolved_tickets),
                    "resolution_sla_violations": resolution_violations,
                    "resolution_sla_percentage": round(resolution_sla_percentage, 1),
                    "first_response_evaluated": len(first_response_evaluated),
                    "first_response_violations": first_response_violations,
                    "first_response_sla_percentage": round(first_response_sla_percentage, 1),
                    "active_tickets_count": raw_data.get('active_tickets', {}).get('summary', {}).get(
                        'total_active_tickets', 0),
                    "critical_tickets": raw_data.get('active_tickets', {}).get('summary', {}).get(
                        'critical_priority_tickets', 0)
                }
            }
        }

    async def test_connection(self) -> bool:
        """Test Autotask API connectivity."""
        try:
            async with AutotaskClient(self.config) as client:
                # Try a simple query to test connection - use current year/month for test
                from datetime import datetime
                now = datetime.now()
                test_data = await client.get_open_tickets_by_priority(now.year, now.month)
                return isinstance(test_data, list)
        except Exception as e:
            logger.error(f"Autotask connection test failed: {e}")
            return False