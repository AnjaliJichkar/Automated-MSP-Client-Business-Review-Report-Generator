"""
Cache WRITE services for storing M365 data from Graph API to Supabase cache tables.
Phase 2: Fetches fresh data and writes to cache.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
from app.core.database.supabase_services import get_organization_credentials
from app.core.database.engine import SessionLocal
from app.models.m365_cache import (
    M365LicenseSnapshot, M365MfaSnapshot, M365ComplianceSnapshot,
    M365SecureScoreHistory, M365User, M365UserDetail, M365UserDevice
)

logger = logging.getLogger(__name__)

# ============================================================================
# HELPER FUNCTION: Convert org_id to clientId for existing endpoints
# ============================================================================

async def get_client_id_from_org_id(org_id: int) -> Optional[str]:
    """
    Get decrypted client_id from org_id.

    Args:
        org_id: Organization ID

    Returns:
        Decrypted client_id (UUID string) or None if not found
    """
    try:
        creds = await get_organization_credentials(org_id)
        if not creds:
            logger.error(f"No credentials found for org_id: {org_id}")
            return None

        return creds['client_id']  # Already decrypted

    except Exception as e:
        logger.error(f"Error getting client_id for org_id {org_id}: {e}")
        return None


# ============================================================================
# WRITE FUNCTION 1: Licenses
# ============================================================================

async def write_licenses_to_cache(org_id: int) -> bool:
    """
    Fetch license data from existing endpoint and write to m365_license_snapshots.

    Args:
        org_id: Organization ID

    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"📝 Writing license cache for org_id: {org_id}")

        # Step 1: Get credentials from org_id
        creds = await get_organization_credentials(org_id)
        if not creds:
            logger.error(f"No credentials found for org_id: {org_id}")
            return False

        # Step 2: Get token directly from credentials (no database lookup!)
        from app.core.auth.middleware import get_access_token_from_credentials
        token = await get_access_token_from_credentials(
            creds['tenant_id'],
            creds['client_id'],
            creds['client_secret']
        )

        # Step 3: Call endpoint with token directly via internal call
        from app.routes.admin.licenses import get_license_summary
        credentials = (str(org_id), "org_id")
        response = await get_license_summary(credentials=credentials)

        # Step 3: Check if response is valid
        if not response or response.status_code != 200 or not response.data:
            logger.error(f"Failed to fetch license data for org_id: {org_id}")
            return False

        data = response.data

        # Step 4: Transform to database format
        license_db_data = {
            "organization_id": org_id,
            "total_users": data['totalUsers'],
            "others_count": data['licenseDistribution']['Others'],
            "standard_count": data['licenseDistribution']['Standard'],
            "premium_count": data['licenseDistribution']['Premium'],
            "basic_count": data['licenseDistribution']['Basic'],
            "license_details": {"licenseDetails": data['licenseDetails']},  # Wrap in nested structure
            "snapshot_date": datetime.now()
        }

        # Step 5: UPSERT to database
        db = SessionLocal()
        try:
            row = db.query(M365LicenseSnapshot).filter(
                M365LicenseSnapshot.organization_id == org_id
            ).first()
            if row:
                for k, v in license_db_data.items():
                    setattr(row, k, v)
                logger.info(f"✅ Updated license cache for org_id: {org_id}")
            else:
                db.add(M365LicenseSnapshot(**license_db_data))
                logger.info(f"✅ Inserted license cache for org_id: {org_id}")
            db.commit()
        finally:
            db.close()

        return True

    except Exception as e:
        logger.error(f"❌ Error writing license cache for org_id {org_id}: {e}")
        return False


# ============================================================================
# WRITE FUNCTION 2: MFA
# ============================================================================

async def write_mfa_to_cache(org_id: int) -> bool:
    """
    Fetch MFA data from existing endpoint and write to m365_mfa_snapshots.

    Args:
        org_id: Organization ID

    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"📝 Writing MFA cache for org_id: {org_id}")

        # Step 1: Get credentials from org_id
        creds = await get_organization_credentials(org_id)
        if not creds:
            logger.error(f"No credentials found for org_id: {org_id}")
            return False

        # Step 2: Get token directly from credentials (no database lookup!)
        from app.core.auth.middleware import get_access_token_from_credentials
        token = await get_access_token_from_credentials(
            creds['tenant_id'],
            creds['client_id'],
            creds['client_secret']
        )

        # Step 3: Call existing endpoint logic with clientId
        from app.routes.security.mfa import get_mfa_compliance_report
        response = await get_mfa_compliance_report(clientId=creds['client_id'], org_id=None)

        # Step 3: Check if response is valid
        if not response or response.status_code != 200 or not response.data:
            logger.error(f"Failed to fetch MFA data for org_id: {org_id}")
            return False

        # Response is an array, get first element
        mfa_data = response.data[0] if isinstance(response.data, list) else response.data

        # Step 4: Transform to database format
        mfa_db_data = {
            "organization_id": org_id,
            "percentage": float(mfa_data['percentage'].replace('%', '')),
            "status": mfa_data['status'],
            "total_users": mfa_data['total_users'],
            "mfa_enabled": mfa_data['mfa_enabled'],
            "mfa_disabled": mfa_data['mfa_disabled'],
            "mfa_registered": mfa_data['enabled_by_method']['mfa_registered'],
            "conditional_access": mfa_data['enabled_by_method']['conditional_access'],
            "security_defaults": mfa_data['enabled_by_method']['security_defaults'],
            "per_user_mfa": mfa_data['enabled_by_method']['per_user_mfa'],
            "recommendation": mfa_data['recommendation'],
            "description": mfa_data['details']['description'],
            "measurement_date": datetime.now()
        }

        # Step 5: UPSERT to database
        db = SessionLocal()
        try:
            row = db.query(M365MfaSnapshot).filter(
                M365MfaSnapshot.organization_id == org_id
            ).first()
            if row:
                for k, v in mfa_db_data.items():
                    setattr(row, k, v)
                logger.info(f"✅ Updated MFA cache for org_id: {org_id}")
            else:
                db.add(M365MfaSnapshot(**mfa_db_data))
                logger.info(f"✅ Inserted MFA cache for org_id: {org_id}")
            db.commit()
        finally:
            db.close()

        return True

    except Exception as e:
        logger.error(f"❌ Error writing MFA cache for org_id {org_id}: {e}")
        return False


# ============================================================================
# WRITE FUNCTION 3: Compliance
# ============================================================================

async def write_compliance_to_cache(org_id: int) -> bool:
    """
    Fetch compliance data from existing endpoint and write to m365_compliance_snapshots.

    Args:
        org_id: Organization ID

    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"📝 Writing compliance cache for org_id: {org_id}")

        # Step 1: Get credentials from org_id
        creds = await get_organization_credentials(org_id)
        if not creds:
            logger.error(f"No credentials found for org_id: {org_id}")
            return False

        # Step 2: Get token directly from credentials (no database lookup!)
        from app.core.auth.middleware import get_access_token_from_credentials
        token = await get_access_token_from_credentials(
            creds['tenant_id'],
            creds['client_id'],
            creds['client_secret']
        )

        # Step 3: Call existing endpoint logic with org_id
        from app.routes.compliance.status import get_all_compliance_status
        response = await get_all_compliance_status(clientId=None, org_id=org_id)

        # Step 4: Check if response is valid (returns dict, not GraphApiResponse)
        if not response or response.get('status_code') != 200 or not response.get('data'):
            logger.error(f"Failed to fetch compliance data for org_id: {org_id}")
            return False

        data = response['data']

        # Step 4: Transform to database format
        compliance_summary = data['compliance_summary']

        compliance_db_data = {
            "organization_id": org_id,
            "status": compliance_summary['status'],
            "score_percentage": int(compliance_summary['score_percentage'].replace('%', '')),
            "total_policies": compliance_summary['total_policies'],
            "policies_data": {"policies": data['policies']},  # Wrap in nested structure
            "breakdown": compliance_summary['breakdown'],
            "title": compliance_summary.get('title', 'Microsoft 365 Compliance Status'),
            "checked_at": datetime.now()
        }

        # Step 5: UPSERT to database
        db = SessionLocal()
        try:
            row = db.query(M365ComplianceSnapshot).filter(
                M365ComplianceSnapshot.organization_id == org_id
            ).first()
            if row:
                for k, v in compliance_db_data.items():
                    setattr(row, k, v)
                logger.info(f"✅ Updated compliance cache for org_id: {org_id}")
            else:
                db.add(M365ComplianceSnapshot(**compliance_db_data))
                logger.info(f"✅ Inserted compliance cache for org_id: {org_id}")
            db.commit()
        finally:
            db.close()

        return True

    except Exception as e:
        logger.error(f"❌ Error writing compliance cache for org_id {org_id}: {e}")
        return False


# ============================================================================
# WRITE FUNCTION 4: Secure Score
# ============================================================================

async def write_secure_score_to_cache(org_id: int) -> bool:
    """
    Fetch secure score from existing endpoint and write to m365_secure_score_history.

    Args:
        org_id: Organization ID

    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"📝 Writing secure score cache for org_id: {org_id}")

        # Step 1: Get credentials from org_id
        creds = await get_organization_credentials(org_id)
        if not creds:
            logger.error(f"No credentials found for org_id: {org_id}")
            return False

        # Step 2: Get token directly from credentials (no database lookup!)
        from app.core.auth.middleware import get_access_token_from_credentials
        token = await get_access_token_from_credentials(
            creds['tenant_id'],
            creds['client_id'],
            creds['client_secret']
        )

        # Step 3: Call existing endpoint logic with clientId
        from app.routes.security.secure_score import get_microsoft_secure_score
        response = await get_microsoft_secure_score(clientId=creds['client_id'], org_id=None)

        # Step 3: Check if response is valid
        if not response or response.status_code != 200 or not response.data:
            logger.error(f"Failed to fetch secure score for org_id: {org_id}")
            return False

        data = response.data
        score_data = data['scoreData']

        # Step 4: Transform to database format
        score_db_data = {
            "organization_id": org_id,
            "current_score": score_data['currentScore'],
            "max_score": score_data['maxScore'],
            "percentage": float(score_data['percentage'].replace('%', '')),
            "active_user_count": score_data['activeUserCount'],
            "licensed_user_count": score_data['licensedUserCount'],
            "score_data": {
                "date": score_data.get('createdDateTime', datetime.now().isoformat())
            },
            "top_improvement_actions": data.get('topImprovementActions', []),
            "all_improvement_actions": data.get('allImprovementActions', []),
            "completed_actions": data.get('completedActions', []),
            "created_at": datetime.now()
        }

        # Step 5: UPSERT to database
        db = SessionLocal()
        try:
            row = db.query(M365SecureScoreHistory).filter(
                M365SecureScoreHistory.organization_id == org_id
            ).first()
            if row:
                for k, v in score_db_data.items():
                    setattr(row, k, v)
                logger.info(f"✅ Updated secure score cache for org_id: {org_id}")
            else:
                db.add(M365SecureScoreHistory(**score_db_data))
                logger.info(f"✅ Inserted secure score cache for org_id: {org_id}")
            db.commit()
        finally:
            db.close()

        return True

    except Exception as e:
        logger.error(f"❌ Error writing secure score cache for org_id {org_id}: {e}")
        return False


# ============================================================================
# WRITE FUNCTION 5: Users List
# ============================================================================

async def write_users_to_cache(org_id: int) -> bool:
    """
    Fetch users list from existing endpoint and write to m365_users.

    Args:
        org_id: Organization ID

    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"📝 Writing users cache for org_id: {org_id}")

        # Step 1: Get credentials from org_id
        creds = await get_organization_credentials(org_id)
        if not creds:
            logger.error(f"No credentials found for org_id: {org_id}")
            return False

        # Step 2: Get token directly from credentials (no database lookup!)
        from app.core.auth.middleware import get_access_token_from_credentials
        token = await get_access_token_from_credentials(
            creds['tenant_id'],
            creds['client_id'],
            creds['client_secret']
        )

        # Step 3: Call existing endpoint logic with credentials tuple
        from app.routes.clients.users import list_users
        credentials = (str(org_id), "org_id")
        response = await list_users(credentials=credentials)

        # Step 2: Check if response is valid
        if not response or response.status_code != 200 or not response.data:
            logger.error(f"Failed to fetch users for org_id: {org_id}")
            return False

        users_list = response.data.get('users', [])

        # Step 4: Track which users are in the API response
        api_user_ids = [user['UserId'] for user in users_list]
        logger.info(f"Fetched {len(api_user_ids)} users from API for org_id: {org_id}")

        # Step 5: Get existing users from database for this organization
        db = SessionLocal()
        try:
            existing_user_rows = db.query(M365User.user_id).filter(
                M365User.organization_id == org_id
            ).all()
            existing_user_ids = [r.user_id for r in existing_user_rows]
            logger.info(f"Found {len(existing_user_ids)} existing users in cache for org_id: {org_id}")

            # Step 6: Find users that are in DB but NOT in API (these need to be deleted)
            users_to_delete = [uid for uid in existing_user_ids if uid not in api_user_ids]

            if users_to_delete:
                logger.info(f"Deleting {len(users_to_delete)} users that no longer exist in API: {users_to_delete}")
                # Delete in order: devices -> details -> user (child to parent)
                db.query(M365UserDevice).filter(
                    M365UserDevice.user_id.in_(users_to_delete)
                ).delete(synchronize_session=False)
                db.query(M365UserDetail).filter(
                    M365UserDetail.user_id.in_(users_to_delete)
                ).delete(synchronize_session=False)
                db.query(M365User).filter(
                    M365User.user_id.in_(users_to_delete),
                    M365User.organization_id == org_id
                ).delete(synchronize_session=False)
                db.commit()
                logger.info(f"Deleted {len(users_to_delete)} removed users and their related data from cache")
            else:
                logger.info(f"No users to delete - all cached users still exist in API")

            # Step 7: UPSERT each user from API
            for user in users_list:
                user_db_data = {
                    "organization_id": org_id,
                    "user_id": user['UserId'],
                    "display_name": user['Name'],
                    "email": user['Email'],
                    "department": user.get('Department'),
                    "role": user.get('Role'),
                    "status": user['Status'],
                    "mfa_enabled": user['MFA'],
                    "user_type": user.get('UserType'),
                    "last_synced": datetime.now()
                }
                row = db.query(M365User).filter(
                    M365User.user_id == user['UserId']
                ).first()
                if row:
                    for k, v in user_db_data.items():
                        setattr(row, k, v)
                else:
                    db.add(M365User(**user_db_data))
            db.commit()
        finally:
            db.close()

        logger.info(f"Written {len(users_list)} users to cache for org_id: {org_id}")
        return True

    except Exception as e:
        logger.error(f"❌ Error writing users cache for org_id {org_id}: {e}")
        return False


# ============================================================================
# WRITE FUNCTION 6: User Details
# ============================================================================

async def write_user_details_to_cache(user_id: str, org_id: int) -> bool:
    """
    Fetch single user details from existing endpoint and write to m365_user_details + m365_user_devices.

    Args:
        user_id: Graph API user ID (UUID)
        org_id: Organization ID

    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"📝 Writing user details cache for user_id: {user_id}, org_id: {org_id}")

        # Step 1: Get credentials from org_id
        creds = await get_organization_credentials(org_id)
        if not creds:
            logger.error(f"No credentials found for org_id: {org_id}")
            return False

        # Step 2: Get token directly from credentials (no database lookup!)
        from app.core.auth.middleware import get_access_token_from_credentials
        token = await get_access_token_from_credentials(
            creds['tenant_id'],
            creds['client_id'],
            creds['client_secret']
        )

        # Step 3: Call existing endpoint logic with credentials tuple
        from app.routes.clients.users import get_user_details
        credentials = (str(org_id), "org_id")
        response = await get_user_details(user_id=user_id, credentials=credentials)

        # Step 2: Check if response is valid
        if not response or response.status_code != 200 or not response.data:
            logger.error(f"Failed to fetch user details for user_id: {user_id}")
            return False

        data = response.data

        # Step 4: Transform user_details
        # Helper function to convert "Not Available" to None for timestamp fields
        def clean_timestamp(value):
            return None if value == "Not Available" else value

        user_details_data = {
            "user_id": user_id,
            "licenses": data.get('licenses', []),
            "mailbox_size_mb": data['mailbox']['size_in_mb'],
            "mailbox_quota_mb": data['mailbox']['quota_in_mb'],
            "mailbox_usage_percentage": data['mailbox']['usage_percentage'],
            "mailbox_items_count": data['mailbox']['items_count'],
            "mailbox_archived_items_count": data['mailbox']['archived_items_count'],
            "onedrive_size_mb": data['one_drive']['size_in_mb'],
            "onedrive_quota_mb": data['one_drive']['quota_in_mb'],
            "onedrive_usage_percentage": data['one_drive']['usage_percentage'],
            "onedrive_files_count": data['one_drive']['files_count'],
            "teams_calls_minutes_last_30_days": data['activity']['teams_calls_minutes_last_30_days'],
            "teams_meetings_count_last_30_days": data['activity']['teams_meetings_count_last_30_days'],
            "teams_messages_count_last_30_days": data['activity']['teams_messages_count_last_30_days'],
            "email_sent_count_last_30_days": data['activity']['email_sent_count_last_30_days'],
            "documents_edited_last_30_days": data['activity']['documents_edited_last_30_days'],
            "risk_level": data['security']['risk_level'],
            "sign_in_attempts_last_30_days": data['security']['sign_in_attempts_last_30_days'],
            "blocked_sign_in_attempts": data['security']['blocked_sign_in_attempts'],
            "authentication_methods": data['security']['authentication_methods'],
            "last_password_change": clean_timestamp(data['security'].get('last_password_change')),
            "last_sign_in": clean_timestamp(data['security'].get('last_sign_in')),
            "groups": data.get('groups', []),
            "last_updated": datetime.now()
        }

        # Step 5: UPSERT user_details
        db = SessionLocal()
        try:
            detail_row = db.query(M365UserDetail).filter(
                M365UserDetail.user_id == user_id
            ).first()
            if detail_row:
                for k, v in user_details_data.items():
                    setattr(detail_row, k, v)
            else:
                db.add(M365UserDetail(**user_details_data))
            db.commit()

            # Step 6: Track which devices are in the API response
            devices_list = data['devices']['device_list']
            api_device_ids = [device['device_id'] for device in devices_list]
            logger.info(f"Fetched {len(api_device_ids)} devices from API for user_id: {user_id}")

            # Step 7: Get existing devices from database for this user
            existing_device_rows = db.query(M365UserDevice.device_id).filter(
                M365UserDevice.user_id == user_id
            ).all()
            existing_device_ids = [r.device_id for r in existing_device_rows]
            logger.info(f"Found {len(existing_device_ids)} existing devices in cache for user_id: {user_id}")

            # Step 8: Delete devices no longer in API
            devices_to_delete = [did for did in existing_device_ids if did not in api_device_ids]
            if devices_to_delete:
                logger.info(f"Deleting {len(devices_to_delete)} devices that no longer exist in API: {devices_to_delete}")
                db.query(M365UserDevice).filter(
                    M365UserDevice.device_id.in_(devices_to_delete),
                    M365UserDevice.user_id == user_id
                ).delete(synchronize_session=False)
                db.commit()
                logger.info(f"Deleted {len(devices_to_delete)} removed devices from cache")
            else:
                logger.info(f"No devices to delete - all cached devices still exist in API")

            # Step 9: UPSERT devices from API
            for device in devices_list:
                device_db_data = {
                    "user_id": user_id,
                    "device_id": device['device_id'],
                    "device_name": device['device_name'],
                    "device_type": device['device_type'],
                    "last_synced": datetime.now()
                }
                device_row = db.query(M365UserDevice).filter(
                    M365UserDevice.device_id == device['device_id']
                ).first()
                if device_row:
                    for k, v in device_db_data.items():
                        setattr(device_row, k, v)
                else:
                    db.add(M365UserDevice(**device_db_data))
            db.commit()
        finally:
            db.close()

        logger.info(f"Written user details for user_id: {user_id}, devices: {len(devices_list)}")
        return True

    except Exception as e:
        logger.error(f"❌ Error writing user details for user_id {user_id}: {e}")
        return False


# ============================================================================
# WRITE ALL FUNCTION
# ============================================================================

async def write_all_caches_to_cache(org_id: int) -> Dict[str, bool]:
    """
    Write all cache types at once for an organization.

    Args:
        org_id: Organization ID

    Returns:
        Dictionary with success/failure status for each cache type
    """
    logger.info(f"📝 Writing ALL caches for org_id: {org_id}")

    results = {}

    results['compliance'] = await write_compliance_to_cache(org_id)
    results['mfa'] = await write_mfa_to_cache(org_id)
    results['licenses'] = await write_licenses_to_cache(org_id)
    results['secure_score'] = await write_secure_score_to_cache(org_id)
    results['users'] = await write_users_to_cache(org_id)

    # Count successes
    total_success = sum(1 for v in results.values() if v)
    total_failed = sum(1 for v in results.values() if not v)

    logger.info(f"✅ Write all caches complete - Success: {total_success}, Failed: {total_failed}")

    return results
