"""
Cache services for reading M365 data from cache tables.
Transforms database columns to frontend JSON format matching original endpoints EXACTLY.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from app.core.database.engine import SessionLocal
from app.core.database.rpc import rpc_get_account_id_from_uid
from app.models.m365_cache import (
    M365ComplianceSnapshot,
    M365MfaSnapshot,
    M365LicenseSnapshot,
    M365SecureScoreHistory,
    M365User,
    M365UserDetail,
    M365UserDevice,
)
from app.models.organizations import Organization, OrganizationPoc

logger = logging.getLogger(__name__)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def is_cache_valid(checked_at, ttl_minutes: int = 30) -> bool:
    """
    Check if cached data is still valid based on TTL (Time-To-Live).

    NOTE: Cache expiration is DISABLED - always returns True.
    Accepts both datetime objects (SQLAlchemy) and ISO string (legacy).

    Args:
        checked_at: datetime object or ISO 8601 string
        ttl_minutes: Ignored — kept for backward compatibility

    Returns:
        Always returns True (cache never expires)
    """
    try:
        if isinstance(checked_at, datetime):
            logger.info(f"Cache valid - expiration disabled, last updated: {checked_at.isoformat()}")
        else:
            # Legacy string path
            checked_at_dt = datetime.fromisoformat(str(checked_at).replace('Z', '+00:00'))
            logger.info(f"Cache valid - expiration disabled, last updated: {checked_at_dt.isoformat()}")
        return True
    except Exception as e:
        logger.error(f"Error parsing cache timestamp: {e}")
        return False


def _to_iso(dt) -> Optional[str]:
    """Convert a datetime object or string to ISO format string safely."""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)


# ============================================================================
# COMPLIANCE CACHE FUNCTIONS
# ============================================================================

async def get_cached_compliance(organization_id: int) -> Optional[Dict[str, Any]]:
    """
    Read compliance data from m365_compliance_snapshots table.
    Returns JSON matching /api/GetAllComplianceStatus response format.
    """
    db = SessionLocal()
    try:
        logger.info(f"Reading compliance cache for organization_id: {organization_id}")

        row = db.query(M365ComplianceSnapshot).filter(
            M365ComplianceSnapshot.organization_id == organization_id
        ).order_by(M365ComplianceSnapshot.checked_at.desc()).first()

        if not row:
            logger.warning(f"No compliance cache found for organization_id: {organization_id}")
            return None

        if not is_cache_valid(row.checked_at, ttl_minutes=100800):
            logger.warning(f"Compliance cache expired for organization_id: {organization_id}")
            return None

        breakdown_data = row.breakdown or {}
        policies_data = row.policies_data or {}
        policies_array = policies_data.get('policies', [])

        frontend_json = {
            "compliance_summary": {
                "title": row.title or 'Microsoft 365 Compliance Status',
                "status": row.status,
                "score_percentage": f"{row.score_percentage}%",
                "total_policies": row.total_policies,
                "breakdown": breakdown_data
            },
            "policies": policies_array
        }

        logger.info(f"Compliance cache retrieved - Status: {row.status}, Score: {row.score_percentage}%")
        return frontend_json

    except Exception as e:
        logger.error(f"Error retrieving compliance cache for organization_id {organization_id}: {e}")
        return None
    finally:
        db.close()


# ============================================================================
# MFA CACHE FUNCTIONS
# ============================================================================

async def get_cached_mfa(organization_id: int) -> Optional[List[Dict[str, Any]]]:
    """
    Read MFA data from m365_mfa_snapshots table.
    Returns JSON array matching /api/GetMFAComplianceReport response format.
    """
    db = SessionLocal()
    try:
        logger.info(f"Reading MFA cache for organization_id: {organization_id}")

        row = db.query(M365MfaSnapshot).filter(
            M365MfaSnapshot.organization_id == organization_id
        ).order_by(M365MfaSnapshot.measurement_date.desc()).first()

        if not row:
            logger.warning(f"No MFA cache found for organization_id: {organization_id}")
            return None

        if not is_cache_valid(row.measurement_date, ttl_minutes=100800):
            logger.warning(f"MFA cache expired for organization_id: {organization_id}")
            return None

        percentage_value = float(row.percentage)
        percentage_str = f"{percentage_value}%" if percentage_value == int(percentage_value) else f"{percentage_value:.1f}%"

        frontend_json = [{
            "percentage": percentage_str,
            "status": row.status,
            "target": "100%",
            "total_users": row.total_users,
            "mfa_enabled": row.mfa_enabled,
            "mfa_disabled": row.mfa_disabled,
            "enabled_by_method": {
                "mfa_registered": row.mfa_registered,
                "conditional_access": row.conditional_access,
                "security_defaults": row.security_defaults,
                "per_user_mfa": row.per_user_mfa
            },
            "recommendation": row.recommendation,
            "details": {
                "description": row.description,
                "measurement_date": _to_iso(row.measurement_date)
            }
        }]

        logger.info(f"MFA cache retrieved - Status: {row.status}, Percentage: {percentage_str}")
        return frontend_json

    except Exception as e:
        logger.error(f"Error retrieving MFA cache for organization_id {organization_id}: {e}")
        return None
    finally:
        db.close()


# ============================================================================
# LICENSE CACHE FUNCTIONS
# ============================================================================

async def get_cached_licenses(organization_id: int) -> Optional[Dict[str, Any]]:
    """
    Read license data from m365_license_snapshots table.
    Returns JSON matching /api/GetLicenseSummary response format.
    """
    db = SessionLocal()
    try:
        logger.info(f"Reading license cache for organization_id: {organization_id}")

        row = db.query(M365LicenseSnapshot).filter(
            M365LicenseSnapshot.organization_id == organization_id
        ).order_by(M365LicenseSnapshot.snapshot_date.desc()).first()

        if not row:
            logger.warning(f"No license cache found for organization_id: {organization_id}")
            return None

        if not is_cache_valid(row.snapshot_date, ttl_minutes=100800):
            logger.warning(f"License cache expired for organization_id: {organization_id}")
            return None

        license_data = row.license_details or {}
        license_details_array = license_data.get('licenseDetails', [])

        frontend_json = {
            "totalUsers": row.total_users,
            "licenseDistribution": {
                "Others": row.others_count,
                "Standard": row.standard_count,
                "Premium": row.premium_count,
                "Basic": row.basic_count
            },
            "licenseDetails": license_details_array
        }

        logger.info(f"License cache retrieved - Total Users: {row.total_users}, Licenses: {len(license_details_array)}")
        return frontend_json

    except Exception as e:
        logger.error(f"Error retrieving license cache for organization_id {organization_id}: {e}")
        return None
    finally:
        db.close()


# ============================================================================
# SECURE SCORE CACHE FUNCTIONS
# ============================================================================

async def get_cached_secure_score(organization_id: int) -> Optional[Dict[str, Any]]:
    """
    Read secure score data from m365_secure_score_history table.
    Returns JSON matching /api/GetMicrosoftSecureScore response format.
    """
    db = SessionLocal()
    try:
        logger.info(f"Reading secure score cache for organization_id: {organization_id}")

        row = db.query(M365SecureScoreHistory).filter(
            M365SecureScoreHistory.organization_id == organization_id
        ).order_by(M365SecureScoreHistory.created_at.desc()).first()

        if not row:
            logger.warning(f"No secure score cache found for organization_id: {organization_id}")
            return None

        if not is_cache_valid(row.created_at, ttl_minutes=100800):
            logger.warning(f"Secure score cache expired for organization_id: {organization_id}")
            return None

        percentage_value = float(row.percentage)
        percentage_str = f"{int(percentage_value)}%" if percentage_value == int(percentage_value) else f"{percentage_value:.0f}%"

        score_data_jsonb = row.score_data or {}
        # Fallback to created_at isoformat string if createdDateTime not in JSONB
        created_date_time = score_data_jsonb.get('createdDateTime', _to_iso(row.created_at))

        frontend_json = {
            "scoreData": {
                "currentScore": int(row.current_score),
                "maxScore": int(row.max_score),
                "percentage": percentage_str,
                "activeUserCount": row.active_user_count,
                "licensedUserCount": row.licensed_user_count,
                "createdDateTime": created_date_time
            },
            "topImprovementActions": row.top_improvement_actions or [],
            "allImprovementActions": row.all_improvement_actions or [],
            "completedActions": row.completed_actions or []
        }

        logger.info(f"Secure score cache retrieved - Score: {row.current_score}/{row.max_score} ({percentage_str})")
        return frontend_json

    except Exception as e:
        logger.error(f"Error retrieving secure score cache for organization_id {organization_id}: {e}")
        return None
    finally:
        db.close()


# ============================================================================
# USER LIST CACHE FUNCTIONS
# ============================================================================

async def get_cached_users_list(organization_id: int) -> Optional[Dict[str, Any]]:
    """
    Read ALL users for an organization from m365_users table.
    Returns JSON matching /api/ListUsers response format.
    """
    db = SessionLocal()
    try:
        logger.info(f"Reading users list cache for organization_id: {organization_id}")

        rows = db.query(M365User).filter(
            M365User.organization_id == organization_id
        ).order_by(M365User.last_synced.desc()).all()

        if not rows:
            logger.warning(f"No users found for organization_id: {organization_id}")
            return None

        if not is_cache_valid(rows[0].last_synced, ttl_minutes=100800):
            logger.warning(f"Users cache expired for organization_id: {organization_id}")
            return None

        users_array = []
        for user in rows:
            users_array.append({
                "UserId": user.user_id,
                "Name": user.display_name,
                "Email": user.email,
                "Department": user.department,
                "Role": user.role,
                "Status": user.status,
                "MFA": user.mfa_enabled,
                "UserType": user.user_type
            })

        frontend_json = {"users": users_array}

        logger.info(f"Users list cache retrieved - {len(users_array)} users found")
        return frontend_json

    except Exception as e:
        logger.error(f"Error retrieving users list cache for organization_id {organization_id}: {e}")
        return None
    finally:
        db.close()


# ============================================================================
# CLIENTS CACHE FUNCTIONS
# ============================================================================

async def get_cached_clients(u_id: str) -> Optional[Dict[str, Any]]:
    """
    Read clients/organizations from organizations table filtered by user's account.
    Returns JSON matching /api/GetClients response format.
    """
    db = SessionLocal()
    try:
        logger.info(f"Reading clients/organizations for u_id: {u_id}")

        # Step 1: Resolve u_id → account_id via RPC
        account_id = rpc_get_account_id_from_uid(db, u_id)

        if not account_id:
            logger.warning(f"No account found for u_id: {u_id}")
            return None

        logger.info(f"Resolved u_id to account_id: {account_id}")

        # Step 2: Query organizations for this account
        orgs = db.query(Organization).filter(
            Organization.account_id == account_id
        ).order_by(Organization.created_at.desc()).all()

        if not orgs:
            logger.warning(f"No organizations found for account_id: {account_id}")
            return None

        if not is_cache_valid(orgs[0].created_at, ttl_minutes=201600):
            logger.warning(f"Organizations cache expired")
            return None

        # Step 3: Fetch all active POCs for these organizations in one query
        org_ids = [org.id for org in orgs]
        logger.info(f"Fetching POCs for {len(org_ids)} organizations")

        pocs = db.query(OrganizationPoc).filter(
            OrganizationPoc.organization_id.in_(org_ids),
            OrganizationPoc.is_active == True
        ).all()

        # Group POCs by organization_id
        pocs_by_org = {}
        for poc in pocs:
            if poc.organization_id not in pocs_by_org:
                pocs_by_org[poc.organization_id] = []
            pocs_by_org[poc.organization_id].append({
                "poc_name": poc.poc_name,
                "poc_email": poc.poc_email,
                "poc_role": poc.poc_role
            })

        logger.info(f"Found POCs for {len(pocs_by_org)} organizations")

        # Step 4: Build response
        clients_array = []
        for org in orgs:
            try:
                created_formatted = org.created_at.strftime("%m/%d/%Y") if org.created_at else "N/A"
                updated_formatted = org.updated_at.strftime("%m/%d/%Y") if org.updated_at else "N/A"
            except Exception:
                created_formatted = "N/A"
                updated_formatted = "N/A"

            clients_array.append({
                "ninjaone_org_id": None,
                "organization_name": org.organization_name,
                "domain": {
                    "url": org.domain,
                    "text": "Visit Website"
                },
                "org_id": org.id,
                "created": {
                    "created_date": created_formatted,
                    "updated_date": updated_formatted
                },
                "status": org.status or 'Active',
                "industry": org.industry,
                "organization_size": org.organization_size,
                "pocs_list": pocs_by_org.get(org.id, [])
            })

        frontend_json = {
            "success": True,
            "clients": clients_array,
            "count": len(clients_array)
        }

        logger.info(f"Clients cache retrieved - {len(clients_array)} organizations for account_id: {account_id}")
        return frontend_json

    except Exception as e:
        logger.error(f"Error retrieving clients cache: {e}")
        return None
    finally:
        db.close()


# ============================================================================
# USER DETAILS CACHE FUNCTIONS (Single User)
# ============================================================================

async def get_cached_user_details(user_id: str, organization_id: int) -> Optional[Dict[str, Any]]:
    """
    Read ONE user's complete details from m365_users + m365_user_details + m365_user_devices.
    Returns JSON matching /api/UserDetails/{user_id} response format.
    """
    db = SessionLocal()
    try:
        logger.info(f"Reading user details cache for user_id: {user_id}")

        # Query base user
        user = db.query(M365User).filter(
            M365User.user_id == user_id,
            M365User.organization_id == organization_id
        ).first()

        if not user:
            logger.warning(f"No user found for user_id: {user_id}")
            return None

        if not is_cache_valid(user.last_synced, ttl_minutes=100800):
            logger.warning(f"User cache expired for user_id: {user_id}")
            return None

        # Query user details
        user_detail = db.query(M365UserDetail).filter(
            M365UserDetail.user_id == user.user_id
        ).first()

        # Query user devices
        devices = db.query(M365UserDevice).filter(
            M365UserDevice.user_id == user.user_id
        ).all()

        device_list = [
            {
                "device_id": d.device_id,
                "device_name": d.device_name,
                "device_type": d.device_type
            }
            for d in devices
        ]

        # Helper to safely get attribute from user_detail (which may be None)
        def ud(field, default=None):
            return getattr(user_detail, field, default) if user_detail else default

        frontend_json = {
            "UserId": user.user_id,
            "Name": user.display_name,
            "Email": user.email,
            "Department": ud('department') or "Not Available",
            "Role": user.role,
            "Status": user.status,
            "MFA": user.mfa_enabled,
            "last_sign_in": _to_iso(ud('last_sign_in')) or "Not Available",
            "mfa_methods": ud('authentication_methods', []),
            "licenses": ud('licenses', []),
            "mailbox": {
                "size_in_mb": ud('mailbox_size_mb') or 0,
                "quota_in_mb": ud('mailbox_quota_mb') or 50000,
                "usage_percentage": ud('mailbox_usage_percentage') or 0,
                "items_count": ud('mailbox_items_count') or 0,
                "archived_items_count": ud('mailbox_archived_items_count') or 0
            },
            "one_drive": {
                "size_in_mb": ud('onedrive_size_mb') or 0,
                "quota_in_mb": ud('onedrive_quota_mb') or 0,
                "usage_percentage": ud('onedrive_usage_percentage') or 0,
                "files_count": ud('onedrive_files_count') or 0
            },
            "activity": {
                "teams_calls_minutes_last_30_days": ud('teams_calls_minutes_last_30_days') or 0,
                "teams_meetings_count_last_30_days": ud('teams_meetings_count_last_30_days') or 0,
                "teams_messages_count_last_30_days": ud('teams_messages_count_last_30_days') or 0,
                "email_sent_count_last_30_days": ud('email_sent_count_last_30_days') or 0,
                "documents_edited_last_30_days": ud('documents_edited_last_30_days') or 0
            },
            "security": {
                "risk_level": ud('risk_level') or 'low',
                "sign_in_attempts_last_30_days": ud('sign_in_attempts_last_30_days') or 0,
                "blocked_sign_in_attempts": ud('blocked_sign_in_attempts') or 0,
                "authentication_methods": ud('authentication_methods', []),
                "last_password_change": _to_iso(ud('last_password_change')) or "Not Available",
                "mfa_enabled": user.mfa_enabled,
                "last_sign_in": _to_iso(ud('last_sign_in')) or "Not Available"
            },
            "groups": ud('groups', []),
            "devices": {
                "total_devices": len(device_list),
                "device_list": device_list
            }
        }

        logger.info(f"User details cache retrieved - User: {user.display_name}, Devices: {len(device_list)}")
        return frontend_json

    except Exception as e:
        logger.error(f"Error retrieving user details cache for user_id {user_id}: {e}")
        return None
    finally:
        db.close()
