
"""
Autotask API Client Library

This module provides a direct-callable interface to the Autotask API
for ticket metrics and reporting without FastAPI dependencies.
"""
#ALL IMPORTS
import httpx
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
from collections import defaultdict, Counter
import asyncio
from urllib.parse import urljoin
import os
# Configure logging
logger = logging.getLogger(__name__)

class AutotaskConfig:
    """Configuration for Autotask API connection."""
    def __init__(self, username: str, secret: str, integration_code: str,
                 base_url: str = "https://webservices.autotask.net/atservicesrest/v1.0/"):
        self.username = username
        self.secret = secret
        self.integration_code = integration_code
        self.base_url = base_url

class AutotaskClient:
    """Autotask API client for direct function calls."""
    def __init__(self, config: AutotaskConfig):
        self.config = config
        self.session = None
        self.zone_url = None
        self._entity_info_cache: Dict[str, Any] = {}
        self._entity_info_locks: Dict[str, asyncio.Lock] = {}
        self.base_headers = {
            "UserName": config.username,
            "Secret": config.secret,
            "APIIntegrationcode": config.integration_code,
            "Content-Type": "application/json"
        }

    async def __aenter__(self):
        self.session = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0),
            headers=self.base_headers
        )
        await self._set_zone_url()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.aclose()

    async def _set_zone_url(self):
        """Get the zone information to determine the correct API URL and cache it."""
        if self.zone_url:
            return
        try:
            zone_info_url = f"https://webservices.autotask.net/atservicesrest/v1.0/zoneInformation?user={self.config.username}"
            async with httpx.AsyncClient(timeout=30.0) as temp_session:
                response = await temp_session.get(zone_info_url)
                response.raise_for_status()
                zone_data = response.json()
                self.zone_url = zone_data.get('url').rstrip('/') + '/'
                logger.info(f"Retrieved and set zone URL: {self.zone_url}")
        except Exception as e:
            logger.error(f"Could not get zone info. API calls will likely fail. Error: {e}")
            raise Exception(f"Could not determine Autotask API zone: {e}")

    async def _make_api_call(self, method: str, endpoint: str, **kwargs) -> httpx.Response:
        """Helper method to make an API call with error handling."""
        if not self.zone_url:
            await self._set_zone_url()
        url = urljoin(self.zone_url, endpoint)
        try:
            logger.info(f"Making {method} request to: {url}")
            if 'json' in kwargs:
                logger.info(f"Request body: {kwargs['json']}")
            response = await self.session.request(method, url, **kwargs)
            logger.info(f"Response status: {response.status_code}")
            if response.status_code >= 400:
                logger.error(f"Response body: {response.text}")
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error for {url}: {e.response.status_code} - {e.response.text}")
            raise Exception(f"Autotask API error: {e.response.text}")
        except Exception as e:
            logger.error(f"Generic error for {url}: {e}")
            raise Exception(f"Internal error: {str(e)}")

    async def query(self, entity: str, filters: List[Dict[str, Any]], fields: Optional[List[str]] = None,
                    max_records: int = 500) -> List[Dict[str, Any]]:
        """Query an entity with structured filters and field selection."""
        endpoint = f"v1.0/{entity}/query"
        query_data = {
            "MaxRecords": max_records,
            "filter": filters
        }
        if fields:
            query_data["IncludeFields"] = fields
        response = await self._make_api_call("POST", endpoint, json=query_data)
        data = response.json()
        all_items = data.get('items', [])
        while len(data.get('items', [])) == max_records:
            last_id = all_items[-1]['id']
            paginated_filters = filters + [{"field": "id", "op": "gt", "value": last_id}]
            query_data["filter"] = paginated_filters
            response = await self._make_api_call("POST", endpoint, json=query_data)
            data = response.json()
            items = data.get('items', [])
            if not items:
                break
            all_items.extend(items)
        return all_items

    async def query_count(self, entity: str, filters: List[Dict[str, Any]]) -> int:
        """Get count of entities matching structured filters."""
        endpoint = f"v1.0/{entity}/query/count"
        query_data = {"filter": filters}
        response = await self._make_api_call("POST", endpoint, json=query_data)
        data = response.json()
        return data.get('queryCount', 0)

    async def get_entity_info(self, entity_name: str = "Tickets") -> Dict[str, Any]:
        """Get entity field information including picklist values. Cached per entity per client instance.
        Lock ensures only one HTTP call is made even if multiple coroutines request simultaneously."""
        if entity_name in self._entity_info_cache:
            return self._entity_info_cache[entity_name]
        if entity_name not in self._entity_info_locks:
            self._entity_info_locks[entity_name] = asyncio.Lock()
        async with self._entity_info_locks[entity_name]:
            # Double-check after acquiring lock — another coroutine may have fetched it already
            if entity_name in self._entity_info_cache:
                return self._entity_info_cache[entity_name]
            endpoint = f"v1.0/{entity_name}/entityInformation/fields"
            response = await self._make_api_call("GET", endpoint)
            self._entity_info_cache[entity_name] = response.json()
            return self._entity_info_cache[entity_name]

    async def get_created_vs_completed_tickets(self, start_date: str, end_date: str, company_id: Optional[int] = None) -> Dict[str, Any]:
        """Get daily tickets created vs completed in a date range for a specific company."""
        try:
            start_dt = datetime.fromisoformat(start_date)
            end_dt = datetime.fromisoformat(end_date) + timedelta(days=1, seconds=-1)
        except ValueError:
            raise ValueError("Invalid date format. Use YYYY-MM-DD")

        # Get all tickets created in the date range
        created_filters = [
            {"field": "createDate", "op": "gte", "value": start_dt.isoformat()},
            {"field": "createDate", "op": "lte", "value": end_dt.isoformat()}
        ]
        if company_id is not None:
            created_filters.append({"field": "companyID", "op": "eq", "value": company_id})

        # Get all tickets created in the date range that are now completed
        completed_filters = [
            {"field": "createDate", "op": "gte", "value": start_dt.isoformat()},
            {"field": "createDate", "op": "lte", "value": end_dt.isoformat()},
            {"field": "status", "op": "eq", "value": 5}  # Assuming 5 is completed status
        ]
        if company_id is not None:
            completed_filters.append({"field": "companyID", "op": "eq", "value": company_id})

        # Fetch detailed ticket data for daily breakdown
        created_fields = ['id', 'createDate']
        completed_fields = ['id', 'createDate']  # Use createDate for completed tickets too

        created_tickets_task = self.query("Tickets", filters=created_filters, fields=created_fields, max_records=500)
        completed_tickets_task = self.query("Tickets", filters=completed_filters, fields=completed_fields, max_records=500)

        created_tickets, completed_tickets = await asyncio.gather(created_tickets_task, completed_tickets_task)

        # Create daily breakdown with better data processing
        daily_created = defaultdict(int)
        daily_completed = defaultdict(int)

        logger.info(f"Processing {len(created_tickets)} created tickets and {len(completed_tickets)} completed tickets")

        # Process created tickets with better error handling
        processed_created = 0
        for ticket in created_tickets:
            create_date_str = ticket.get('createDate')
            if create_date_str:
                try:
                    # Handle different date formats
                    if create_date_str.endswith('Z'):
                        create_date = datetime.fromisoformat(create_date_str.replace('Z', '+00:00'))
                    else:
                        create_date = datetime.fromisoformat(create_date_str)

                    day_key = create_date.date().isoformat()
                    daily_created[day_key] += 1
                    processed_created += 1
                except Exception as e:
                    logger.debug(f"Failed to parse create date: {create_date_str}, error: {e}")
                    continue

        # Process completed tickets with better error handling
        processed_completed = 0
        for ticket in completed_tickets:
            create_date_str = ticket.get('createDate')  # Use createDate for completed tickets
            if create_date_str:
                try:
                    # Handle different date formats
                    if create_date_str.endswith('Z'):
                        create_date = datetime.fromisoformat(create_date_str.replace('Z', '+00:00'))
                    else:
                        create_date = datetime.fromisoformat(create_date_str)

                    day_key = create_date.date().isoformat()
                    daily_completed[day_key] += 1
                    processed_completed += 1
                except Exception as e:
                    logger.debug(f"Failed to parse create date: {create_date_str}, error: {e}")
                    continue

        logger.info(f"Successfully processed {processed_created} created tickets and {processed_completed} completed tickets")

        logger.info(f"Date range: {start_dt.date()} to {end_dt.date()}")

        # Generate complete date range first to ensure proper ordering
        current_date = start_dt.date()
        end_date_obj = end_dt.date()
        all_dates = []

        # Build complete date range
        while current_date <= end_date_obj:
            all_dates.append(current_date)
            current_date += timedelta(days=1)

        logger.info(f"Generated {len(all_dates)} dates from {all_dates[0] if all_dates else 'None'} to {all_dates[-1] if all_dates else 'None'}")

        # Now build the arrays in proper chronological order
        days = []
        created_counts = []
        completed_counts = []
        date_labels = []

        for date_obj in all_dates:
            day_key = date_obj.isoformat()
            days.append(date_obj.day)
            date_labels.append(day_key)
            created_count = daily_created.get(day_key, 0)
            completed_count = daily_completed.get(day_key, 0)
            created_counts.append(created_count)
            completed_counts.append(completed_count)

        logger.info(f"Final arrays - Days: {days[:10]}... (showing first 10)")
        logger.info(f"Created counts: {created_counts[:10]}... (showing first 10)")
        logger.info(f"Completed counts: {completed_counts[:10]}... (showing first 10)")

        # Use actual daily data as-is, no fallback logic

        return {
            "created_count": sum(created_counts),
            "completed_count": sum(completed_counts),
            "period_start": start_dt.isoformat(),
            "period_end": end_dt.isoformat(),
            "company_id": company_id,
            "daily_breakdown": {
                "days": days,
                "date_labels": date_labels,
                "daily_created": created_counts,
                "daily_completed": completed_counts
            }
        }

    async def get_monthly_tickets_by_issue_type(self, year: int, month: int, company_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get monthly count of tickets by issue type for a specific company."""
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1) - timedelta(seconds=1)
        else:
            end_date = datetime(year, month + 1, 1) - timedelta(seconds=1)
        entity_info_task = self.get_entity_info("Tickets")
        filters = [
            {"field": "createDate", "op": "gte", "value": start_date.isoformat()},
            {"field": "createDate", "op": "lte", "value": end_date.isoformat()}
        ]
        if company_id is not None:
            filters.append({"field": "companyID", "op": "eq", "value": company_id})
        fields = ['id', 'issueType']
        tickets_task = self.query("Tickets", filters=filters, fields=fields)
        entity_info, tickets = await asyncio.gather(entity_info_task, tickets_task)
        issue_type_counts = Counter(
            ticket.get('issueType') for ticket in tickets if ticket.get('issueType') is not None)
        issue_type_map = {}
        for field in entity_info.get('fields', []):
            if field.get('name') == 'issueType':
                for pv in field.get('picklistValues', []):
                    issue_type_map[int(pv['value'])] = pv['label']
                break
        result = [
            {
                "issue_type": issue_type_map.get(issue_type_id, f"Unknown ID: {issue_type_id}"),
                "issue_type_id": issue_type_id,
                "count": count,
                "month": f"{year}-{month:02d}",
                "company_id": company_id
            }
            for issue_type_id, count in issue_type_counts.items()
        ]
        return sorted(result, key=lambda x: x["count"], reverse=True)

    async def get_quarterly_tickets_by_issue_type(
        self,
        start_date: str,
        end_date: str,
        company_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get ticket counts by issue type across a date range (used for quarterly)."""
        # A date-only inclusive upper bound otherwise resolves to midnight.
        if "T" not in end_date:
            end_date = (datetime.fromisoformat(end_date) + timedelta(days=1, seconds=-1)).isoformat()
        entity_info_task = self.get_entity_info("Tickets")
        filters = [
            {"field": "createDate", "op": "gte", "value": start_date},
            {"field": "createDate", "op": "lte", "value": end_date}
        ]
        if company_id is not None:
            filters.append({"field": "companyID", "op": "eq", "value": company_id})
        fields = ['id', 'issueType']
        tickets_task = self.query("Tickets", filters=filters, fields=fields)
        entity_info, tickets = await asyncio.gather(entity_info_task, tickets_task)
        issue_type_counts = Counter(
            ticket.get('issueType') for ticket in tickets if ticket.get('issueType') is not None)
        issue_type_map = {}
        for field in entity_info.get('fields', []):
            if field.get('name') == 'issueType':
                for pv in field.get('picklistValues', []):
                    issue_type_map[int(pv['value'])] = pv['label']
                break
        result = [
            {
                "issue_type": issue_type_map.get(issue_type_id, f"Unknown ID: {issue_type_id}"),
                "issue_type_id": issue_type_id,
                "count": count,
                "month": f"{start_date[:7]} to {end_date[:7]}",
                "company_id": company_id
            }
            for issue_type_id, count in issue_type_counts.items()
        ]
        return sorted(result, key=lambda x: x["count"], reverse=True)

    async def get_open_tickets_by_priority(self, year: int, month: int, company_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get count of currently open tickets, grouped by priority for a specific company."""
        logger.info("Starting open tickets by priority analysis...")

        # Fetch entity info for priority mapping + dynamic open status resolution
        entity_info = await self.get_entity_info("Tickets")
        priority_map = {}
        status_map = {}
        for field in entity_info.get('fields', []):
            if field.get('name') == 'priority':
                for pv in field.get('picklistValues', []):
                    priority_map[int(pv['value'])] = pv['label']
            elif field.get('name') == 'status':
                for pv in field.get('picklistValues', []):
                    status_map[int(pv['value'])] = pv['label']

        closed_keywords = ['complete', 'closed', 'resolved', 'cancelled', 'canceled', 'archived', 'stale']
        open_status_ids = [
            sid for sid, label in status_map.items()
            if not any(kw in label.lower() for kw in closed_keywords)
        ]
        if not open_status_ids:
            logger.warning("No open statuses found dynamically — using all statuses")
            open_status_ids = list(status_map.keys())

        logger.info(f"Dynamic open status IDs ({len(open_status_ids)}): {open_status_ids}")
        logger.info(f"Available priorities: {priority_map}")

        # Build filters for open tickets as of end of month (snapshot)
        # Get all tickets created on or before end of month that are still open
        open_filters = [
            {"field": "status", "op": "in", "value": open_status_ids},
        ]

        if company_id is not None:
            open_filters.append({"field": "companyID", "op": "eq", "value": company_id})

        # Fetch open tickets
        debug_fields = ['id', 'status', 'priority']
        open_tickets = await self.query("Tickets", filters=open_filters, fields=debug_fields)
        logger.info(f"Found {len(open_tickets)} open tickets")

        # Count tickets by priority
        priority_counts = Counter()
        tickets_without_priority = 0
        for ticket in open_tickets:
            priority = ticket.get('priority')
            if priority is not None:
                priority_counts[priority] += 1
            else:
                tickets_without_priority += 1

        result = [
            {
                "priority": priority_map.get(priority_id, f"Priority {priority_id}"),
                "priority_id": priority_id,
                "count": count,
                "month": f"{year}-{month:02d}",
                "company_id": company_id
            }
            for priority_id, count in priority_counts.items()
        ]
        if tickets_without_priority > 0:
            result.append({
                "priority": "No Priority",
                "priority_id": None,
                "count": tickets_without_priority,
                "month": f"{year}-{month:02d}",
                "company_id": company_id
            })
        return sorted(result, key=lambda x: x["count"], reverse=True)

    async def get_active_tickets_by_priority(self, top_count: int = 10, company_id: Optional[int] = None) -> Dict[str, Any]:
        """Get detailed analysis of active tickets by priority for a specific company."""
        logger.info("Starting active tickets by priority analysis...")
        entity_info_task = self.get_entity_info("Tickets")
        debug_fields = ['id', 'status', 'priority', 'title', 'ticketNumber', 'createDate', 'dueDateTime',
                        'assignedResourceID', 'companyID', 'contactID', 'lastActivityDate']
        sample_tickets = await self.query("Tickets", filters=[], fields=debug_fields, max_records=100)
        entity_info = await entity_info_task
        status_map = {}
        priority_map = {}
        for field in entity_info.get('fields', []):
            if field.get('name') == 'status':
                for pv in field.get('picklistValues', []):
                    status_map[int(pv['value'])] = pv['label']
            elif field.get('name') == 'priority':
                for pv in field.get('picklistValues', []):
                    priority_map[int(pv['value'])] = pv['label']
        closed_status_keywords = ['complete', 'closed', 'resolved', 'cancelled', 'canceled']
        active_status_ids = [sid for sid, label in status_map.items()
                             if not any(keyword in label.lower() for keyword in closed_status_keywords)]
        if not active_status_ids:
            logger.error("No active statuses determined from entity info - no data available")
            return {"priority_distribution": {}, "top_priority_tickets": [], "summary": {}, "autotask_priority_system": {}, "company_id": company_id}
        else:
            active_filters = [{"field": "status", "op": "in", "value": active_status_ids}]
        if company_id is not None:
            active_filters.append({"field": "companyID", "op": "eq", "value": company_id})
        active_tickets = await self.query("Tickets", filters=active_filters, fields=debug_fields)
        priority_distribution = Counter(t.get('priority') for t in active_tickets if t.get('priority') is not None)
        tickets_without_priority = sum(1 for t in active_tickets if t.get('priority') is None)
        top_priority_tickets = []
        for ticket in active_tickets:
            priority_id = ticket.get('priority', 0)
            if priority_id not in [4, 1, 2, 3]:  # Critical, High, Medium, Low
                continue
            created_date_str = ticket.get('createDate')
            created_date = None
            days_open = 0
            if created_date_str:
                try:
                    created_date = datetime.fromisoformat(created_date_str.replace('Z', '+00:00'))
                    days_open = (datetime.now(timezone.utc) - created_date.replace(tzinfo=timezone.utc)).days
                except:
                    days_open = 0
            due_date_str = ticket.get('dueDateTime')
            is_overdue = False
            due_date = None
            if due_date_str:
                try:
                    due_date = datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
                    if datetime.now(timezone.utc) > due_date.replace(tzinfo=timezone.utc):
                        is_overdue = True
                except:
                    pass
            last_activity_str = ticket.get('lastActivityDate')
            last_activity = None
            if last_activity_str:
                try:
                    last_activity = datetime.fromisoformat(last_activity_str.replace('Z', '+00:00'))
                except:
                    pass
            ticket_detail = {
                "ticket_id": ticket['id'],
                "ticket_number": ticket.get('ticketNumber', f"T{ticket['id']}"),
                "title": ticket.get('title', 'No Title'),
                "priority": priority_map.get(priority_id, f"Priority {priority_id}"),
                "priority_id": priority_id,
                "status": status_map.get(ticket.get('status'), f"Status {ticket.get('status')}"),
                "status_id": ticket.get('status', 0),
                "created_date": created_date.isoformat() if created_date else None,
                "due_date": due_date.isoformat() if due_date else None,
                "assigned_resource": f"Resource {ticket.get('assignedResourceID')}" if ticket.get('assignedResourceID') else "Unassigned",
                "company_name": f"Company {ticket.get('companyID')}" if ticket.get('companyID') else "No Company",
                "contact_name": f"Contact {ticket.get('contactID')}" if ticket.get('contactID') else "No Contact",
                "days_open": days_open,
                "is_overdue": is_overdue,
                "last_activity": last_activity.isoformat() if last_activity else None,
                "company_id": company_id
            }
            top_priority_tickets.append(ticket_detail)
        priority_order = {4: 1, 1: 2, 2: 3, 3: 4}
        top_priority_tickets.sort(key=lambda x: (
            priority_order.get(x["priority_id"], 999),
            -int(x["is_overdue"]),
            -x["days_open"]
        ))
        top_tickets = top_priority_tickets[:top_count]
        total_active = len(active_tickets)
        overdue_count = sum(1 for t in top_priority_tickets if t["is_overdue"])
        unassigned_count = sum(1 for t in top_priority_tickets if "Unassigned" in t["assigned_resource"])
        avg_days_open = sum(t["days_open"] for t in top_priority_tickets) / len(top_priority_tickets) if top_priority_tickets else 0
        critical_tickets = sum(1 for t in top_priority_tickets if t["priority_id"] == 4)
        high_tickets = sum(1 for t in top_priority_tickets if t["priority_id"] == 1)
        summary = {
            "total_active_tickets": total_active,
            "tickets_without_priority": tickets_without_priority,
            "overdue_tickets": overdue_count,
            "unassigned_tickets": unassigned_count,
            "critical_priority_tickets": critical_tickets,
            "high_priority_tickets": high_tickets,
            "average_days_open": round(avg_days_open, 1),
            "oldest_ticket_days": max((t["days_open"] for t in top_priority_tickets), default=0),
            "immediate_action_needed": overdue_count + critical_tickets + unassigned_count
        }
        autotask_system_info = {
            "priority_levels": priority_map,
            "active_statuses": {status_id: status_map[status_id] for status_id in active_status_ids},
            "priority_ranking_method": "Custom order: Critical(4) → High(1) → Medium(2) → Low(3)",
            "active_determination_method": "Excludes statuses containing: complete, closed, resolved, cancelled"
        }
        return {
            "priority_distribution": dict(priority_distribution),
            "top_priority_tickets": top_tickets,
            "summary": summary,
            "autotask_priority_system": autotask_system_info,
            "company_id": company_id
        }

    async def get_slo_metrics(self, start_date: str, end_date: str, company_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get SLA metrics for tickets created in a date range for a specific company.

        IMPORTANT: Only includes tickets where serviceLevelAgreementID is NOT null.
        Tickets without an SLA contract assigned are excluded from metrics.

        Uses HYBRID approach for Resolution SLA calculation:
        - PRIORITY 1: Uses resolvedDateTime vs resolvedDueDateTime (when SLA contract exists)
        - PRIORITY 2: Falls back to completedDate vs dueDateTime (when no SLA contract)

        Also returns first-response fields (firstResponseDateTime, firstResponseDueDateTime)
        which allow calculation of First Response Met %.

        Returns sla_calculation_method to indicate which fields were used:
        - "SLA_CONTRACT": Used official SLA resolution fields
        - "GENERAL_DUE_DATE": Fell back to general due date fields
        - "NO_DUE_DATE": No due date information available
        """
        try:
            start_dt = datetime.fromisoformat(start_date)
            end_dt = datetime.fromisoformat(end_date) + timedelta(days=1, seconds=-1)
        except ValueError:
            raise ValueError("Invalid date format. Use YYYY-MM-DD")

        filters = [
            {"field": "createDate", "op": "gte", "value": start_dt.isoformat()},
            {"field": "createDate", "op": "lte", "value": end_dt.isoformat()}
        ]
        if company_id is not None:
            filters.append({"field": "companyID", "op": "eq", "value": company_id})

        # <-- Add Autotask first-response/resolution fields here
        fields = [
            'id', 'ticketNumber', 'dueDateTime', 'completedDate', 'status',
            'firstResponseDateTime', 'firstResponseDueDateTime',
            'firstResponseAssignedResourceID', 'firstResponseInitiatingResourceID',
            'serviceLevelAgreementHasBeenMet', 'serviceLevelAgreementID',
            'resolvedDateTime', 'resolvedDueDateTime'
        ]

        tickets = await self.query("Tickets", filters=filters, fields=fields)

        # Filter out tickets away without SLA contract assigned only keeping those who have the serviceLevelAgreementID
        tickets_with_sla = [t for t in tickets if t.get('serviceLevelAgreementID') is not None]

        logger.info(f"Total tickets fetched: {len(tickets)}, Tickets with SLA: {len(tickets_with_sla)}, Excluded (no SLA): {len(tickets) - len(tickets_with_sla)}")

        result = []
        now_utc = datetime.now(timezone.utc)

        # Only process tickets that have an SLA contract assigned
        for ticket in tickets_with_sla:
            # parse existing fields
            def _parse(dt_str):
                if not dt_str:
                    return None
                # Autotask times are UTC ending with 'Z' — make them timezone-aware
                return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))

            # Parse SLA-specific resolution fields (CORRECT fields for Resolution SLA)
            resolved_due_date = _parse(ticket.get('resolvedDueDateTime'))
            resolved_date = _parse(ticket.get('resolvedDateTime'))

            # Parse general due date fields (FALLBACK when no SLA contract)
            due_date = _parse(ticket.get('dueDateTime'))
            completed_date = _parse(ticket.get('completedDate'))

            # Parse first response fields
            first_response_date = _parse(ticket.get('firstResponseDateTime'))
            first_response_due = _parse(ticket.get('firstResponseDueDateTime'))

            # Manual SLA calculation since serviceLevelAgreementHasBeenMet returns null
            autotask_sla_flag = ticket.get('serviceLevelAgreementHasBeenMet')

            # Calculate Resolution SLA using HYBRID approach
            sla_met = None
            days_overdue = None
            sla_calculation_method = None

            # PRIORITY 1: Use SLA-specific resolution fields when available
            if resolved_due_date and resolved_date:
                # SLA contract exists - use official Resolution SLA fields
                sla_met = resolved_date <= resolved_due_date
                sla_calculation_method = "SLA_CONTRACT"
                if resolved_date > resolved_due_date:
                    days_overdue = (resolved_date - resolved_due_date).days
            elif resolved_due_date and not resolved_date:
                # Ticket has SLA but is still open
                if now_utc > resolved_due_date:
                    sla_met = False
                    days_overdue = (now_utc - resolved_due_date).days
                    sla_calculation_method = "SLA_CONTRACT_OPEN"
                else:
                    sla_met = None  # Pending
                    sla_calculation_method = "SLA_CONTRACT_PENDING"
            # PRIORITY 2: Fallback to general due date when there is no resolution dates available 
            elif due_date and completed_date:
              
                sla_met = completed_date <= due_date
                sla_calculation_method = "GENERAL_DUE_DATE"
                if completed_date > due_date:
                    days_overdue = (completed_date - due_date).days

            elif due_date and not completed_date:
                # Ticket is still open - check if it's overdue
                if now_utc > due_date:
                    sla_met = False
                    days_overdue = (now_utc - due_date).days
                    sla_calculation_method = "GENERAL_DUE_DATE_OPEN"
                else:
                    # Still within SLA window
                    sla_met = None  # Pending
                    sla_calculation_method = "GENERAL_DUE_DATE_PENDING"
            else:
                # No due date set - cannot determine SLA compliance
                sla_met = None
                sla_calculation_method = "NO_DUE_DATE"

            # first-response SLA calculation
            if first_response_due:
                if first_response_date:
                    first_response_met = first_response_date <= first_response_due
                else:
                    # no first response yet; if due has passed -> not met, else pending (None)
                    first_response_met = False if now_utc > first_response_due else None
            else:
                # No firstResponseDue provided by Autotask (rare). Set None so caller can decide.
                first_response_met = None

            # Optional: if first_response_date is None and you want to compute from notes, do a child query:
            # (uncomment and adapt if needed)
            # if first_response_date is None:
            #     notes = await self.query("TicketNotes", filters=[{"field":"ticketID","op":"eq","value":ticket['id']}], fields=["id","createdDate","creatorResourceID","isNoteVisibleToCustomer"])
            #     # pick earliest note created by a resource (agent) and (optionally) visible to customer
            #     if notes:
            #         notes_sorted = sorted(notes, key=lambda n: n.get('createdDate') or '')
            #         earliest = notes_sorted[0]
            #         first_response_date = _parse(earliest.get('createdDate'))
            #         if first_response_due:
            #             first_response_met = first_response_date <= first_response_due

            result.append({
                "ticket_id": ticket['id'],
                "ticket_number": ticket.get('ticketNumber', f"T{ticket['id']}"),
                "sla_met": bool(sla_met) if sla_met is not None else None,
                "sla_calculation_method": sla_calculation_method,
                "service_level_agreement_id": ticket.get('serviceLevelAgreementID'),  # Always present (filtered for non-null)
                # SLA Resolution fields (CORRECT for Resolution SLA)
                "resolved_date": resolved_date.isoformat() if resolved_date else None,
                "resolved_due_date": resolved_due_date.isoformat() if resolved_due_date else None,
                # General due date fields (FALLBACK)
                "due_date": due_date.isoformat() if due_date else None,
                "completed_date": completed_date.isoformat() if completed_date else None,
                "days_overdue": days_overdue,
                # First Response fields
                "first_response_date": first_response_date.isoformat() if first_response_date else None,
                "first_response_due_date": first_response_due.isoformat() if first_response_due else None,
                "first_response_met": first_response_met,
                "company_id": company_id
            })

        return result

    async def get_tickets_created_by_contact(self, start_date: str, end_date: str,
                                             contact_id: Optional[int] = None, company_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get ticket counts per contact for tickets created in a date range for a specific company."""
        try:
            start_dt = datetime.fromisoformat(start_date)
            end_dt = datetime.fromisoformat(end_date) + timedelta(days=1, seconds=-1)
        except ValueError:
            raise ValueError("Invalid date format. Use YYYY-MM-DD")
        ticket_filters = [
            {"field": "createDate", "op": "gte", "value": start_dt.isoformat()},
            {"field": "createDate", "op": "lte", "value": end_dt.isoformat()}
        ]
        if contact_id is not None:
            ticket_filters.append({"field": "contactID", "op": "eq", "value": contact_id})
        if company_id is not None:
            ticket_filters.append({"field": "companyID", "op": "eq", "value": company_id})
        ticket_fields = ['id', 'contactID']
        tickets = await self.query("Tickets", filters=ticket_filters, fields=ticket_fields)
        if not tickets:
            return []
        contact_counts = Counter(t['contactID'] for t in tickets if t.get('contactID') is not None)
        all_contact_ids = list(contact_counts.keys())
        contact_name_map = {}
        if all_contact_ids:
            contact_filter = [{"field": "id", "op": "in", "value": all_contact_ids}]
            contact_fields = ["id", "firstName", "lastName"]
            contacts_data = await self.query("Contacts", filters=contact_filter, fields=contact_fields)
            for contact in contacts_data:
                first_name = contact.get("firstName", "")
                last_name = contact.get("lastName", "")
                contact_name_map[contact['id']] = f"{first_name} {last_name}".strip()
        result = [
            {
                "contact_id": cid,
                "contact_name": contact_name_map.get(cid, f"Unknown or Inactive Contact {cid}"),
                "ticket_count": count,
                "company_id": company_id
            }
            for cid, count in contact_counts.items()
        ]
        return sorted(result, key=lambda x: x["ticket_count"], reverse=True)

    async def get_open_tickets_by_issue_subissue(self, year: int, month: int, company_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get snapshot of all currently open tickets, grouped by issue type and sub-issue type for a specific company."""

        # Fetch entity info for mappings
        entity_info_task = self.get_entity_info("Tickets")
        entity_info = await entity_info_task

        # Build mapping dictionaries
        issue_type_map = {}
        sub_issue_type_map = {}

        status_map = {}
        for field in entity_info.get('fields', []):
            if field.get('name') == 'issueType':
                for pv in field.get('picklistValues', []):
                    issue_type_map[int(pv['value'])] = pv['label']
            elif field.get('name') == 'subIssueType':
                for pv in field.get('picklistValues', []):
                    sub_issue_type_map[int(pv['value'])] = pv['label']
            elif field.get('name') == 'status':
                for pv in field.get('picklistValues', []):
                    status_map[int(pv['value'])] = pv['label']

        logger.info(f"Loaded {len(issue_type_map)} issue types and {len(sub_issue_type_map)} sub-issue types")

        closed_keywords = ['complete', 'closed', 'resolved', 'cancelled', 'canceled', 'archived', 'stale']
        open_status_ids = [
            sid for sid, label in status_map.items()
            if not any(kw in label.lower() for kw in closed_keywords)
        ]
        if not open_status_ids:
            logger.warning("No open statuses found dynamically — using all statuses")
            open_status_ids = list(status_map.keys())

        logger.info(f"Dynamic open status IDs ({len(open_status_ids)}): {open_status_ids}")

        # Build filters for open tickets as of end of month (snapshot)
        # Get all tickets created on or before end of month that are still open
        filters = [
            {"field": "status", "op": "in", "value": open_status_ids},
        ]

        if company_id is not None:
            filters.append({"field": "companyID", "op": "eq", "value": company_id})

        # Fetch tickets with issue type and sub-issue type fields
        fields = ['id', 'status', 'issueType', 'subIssueType']
        tickets = await self.query("Tickets", filters=filters, fields=fields)

        logger.info(f"Found {len(tickets)} open tickets as of end of {year}-{month:02d}")

        # Group tickets by (issueType, subIssueType)
        from collections import defaultdict
        issue_groups = defaultdict(lambda: {"total": 0, "sub_issues": defaultdict(int)})

        uncategorized_count = 0

        for ticket in tickets:
            issue_type_id = ticket.get('issueType')
            sub_issue_type_id = ticket.get('subIssueType')

            # Handle uncategorized tickets (no issueType)
            if issue_type_id is None:
                uncategorized_count += 1
                continue

            issue_type_label = issue_type_map.get(issue_type_id, f"Unknown Issue Type {issue_type_id}")

            # Increment total count for this issue type
            issue_groups[issue_type_label]["total"] += 1

            # Handle sub-issue type
            if sub_issue_type_id is not None:
                sub_issue_label = sub_issue_type_map.get(sub_issue_type_id, f"Unknown Sub-Issue {sub_issue_type_id}")
                issue_groups[issue_type_label]["sub_issues"][sub_issue_label] += 1
            else:
                # Tickets with issueType but no subIssueType
                issue_groups[issue_type_label]["sub_issues"]["Unspecified"] += 1

        # Convert to list format
        result = []

        for issue_type, data in issue_groups.items():
            issue_item = {
                "issue_type": issue_type,
                "total_count": data["total"],
                "sub_issues": [
                    {
                        "sub_issue_type": sub_type,
                        "count": count
                    }
                    for sub_type, count in data["sub_issues"].items()
                ],
                "month": f"{year}-{month:02d}",
                "company_id": company_id
            }

            # Sort sub-issues by count descending
            issue_item["sub_issues"].sort(key=lambda x: x["count"], reverse=True)

            result.append(issue_item)

        # Add uncategorized tickets if any
        if uncategorized_count > 0:
            result.append({
                "issue_type": "Uncategorized",
                "total_count": uncategorized_count,
                "sub_issues": [
                    {
                        "sub_issue_type": "No Issue Type Assigned",
                        "count": uncategorized_count
                    }
                ],
                "month": f"{year}-{month:02d}",
                "company_id": company_id
            })

        # Sort by total_count descending
        result.sort(key=lambda x: x["total_count"], reverse=True)

        logger.info(f"Grouped into {len(result)} issue types (including {uncategorized_count} uncategorized)")

        return result

# Convenience functions for direct usage without async context manager
async def create_autotask_client(username: str, secret: str, integration_code: str,
                                 base_url: str = "https://webservices.autotask.net/atservicesrest/v1.0/") -> AutotaskClient:
    """Create and initialize an Autotask client."""
    config = AutotaskConfig(username, secret, integration_code, base_url)
    client = AutotaskClient(config)
    await client.__aenter__()
    return client

async def get_created_vs_completed_tickets(client: AutotaskClient, start_date: str, end_date: str, company_id: Optional[int] = None) -> Dict[str, Any]:
    """Wrapper function for getting created vs completed tickets."""
    return await client.get_created_vs_completed_tickets(start_date, end_date, company_id)

async def get_monthly_tickets_by_issue_type(client: AutotaskClient, year: int, month: int, company_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Wrapper function for getting monthly tickets by issue type."""
    return await client.get_monthly_tickets_by_issue_type(year, month, company_id)

async def get_open_tickets_by_priority(client: AutotaskClient, year: int, month: int, company_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Wrapper function for getting open tickets by priority."""
    return await client.get_open_tickets_by_priority(year, month, company_id)

async def get_active_tickets_by_priority(client: AutotaskClient, top_count: int = 10, company_id: Optional[int] = None) -> Dict[str, Any]:
    """Wrapper function for getting active tickets by priority."""
    return await client.get_active_tickets_by_priority(top_count, company_id)

async def get_slo_metrics(client: AutotaskClient, start_date: str, end_date: str, company_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Wrapper function for getting SLO metrics."""
    return await client.get_slo_metrics(start_date, end_date, company_id)

async def get_tickets_created_by_contact(client: AutotaskClient, start_date: str, end_date: str,
                                         contact_id: Optional[int] = None, company_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Wrapper function for getting tickets created by contact."""
    return await client.get_tickets_created_by_contact(start_date, end_date, contact_id, company_id)