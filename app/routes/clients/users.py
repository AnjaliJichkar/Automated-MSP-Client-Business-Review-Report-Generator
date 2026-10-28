import logging
import httpx
from fastapi import APIRouter, HTTPException, Path, Depends
from app.core.auth.middleware import get_access_token
from app.schemas.api import GraphApiResponse
from app.core.auth.dependencies import get_client_credentials
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import asyncio

# Create router for user endpoints
router = APIRouter()
logger = logging.getLogger(__name__)


# ==============================================================================
# DEAD ENDPOINTS — ListUsers, AllUsersDetails, UserDetails
# These use the old organization_mapping table (no longer exists in DB).
# ninjaone_org_id lookup path is broken. None of these are in the production
# frontend endpoint list. Commented out entirely.
# ==============================================================================

# # ----------- User Details--------------
# @router.get("/ListUsers", response_model=GraphApiResponse, summary="List All Users with MFA Status")
# async def list_users(credentials: tuple = Depends(get_client_credentials)):
#     """
#     Gets user details from Microsoft Graph API and maps them to match the UI fields,
#     including MFA status (True or False) and User ID for details lookup.
#     Supports clientId, org_id, and ninjaone_org_id parameters.
#     """
#     try:
#         identifier, identifier_type = credentials
#
#         # Convert identifier to client_id
#         if identifier_type == "org_id":
#             from app.core.database.supabase_services import get_organization_credentials
#             creds = await get_organization_credentials(int(identifier))
#             if not creds:
#                 raise Exception(f"No credentials found for org_id: {identifier}")
#             client_id = creds['client_id']
#         elif identifier_type == "ninjaone_org_id":
#             from app.core.database.supabase_services import supabase
#             response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
#             if not response.data or len(response.data) == 0:
#                 raise Exception(f"No client_id found for ninjaone_org_id: {identifier}")
#             client_id = response.data[0]['client_id']
#         else:
#             client_id = identifier
#
#         token = await get_access_token(client_id)
#         headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
#
#         users_list = []
#
#         async with httpx.AsyncClient() as client:
#             users_url = "https://graph.microsoft.com/v1.0/users?$select=id,displayName,mail,userPrincipalName,department,jobTitle,accountEnabled,userType"
#             users_response = await client.get(users_url, headers=headers, timeout=30.0)
#             users_response.raise_for_status()
#             users = users_response.json().get("value", [])
#
#             for user in users:
#                 user_id = user.get("id")
#                 upn = user.get("userPrincipalName")
#                 mfa_status = False
#                 try:
#                     mfa_url = f"https://graph.microsoft.com/v1.0/users/{upn}?$select=strongAuthenticationMethods"
#                     mfa_response = await client.get(mfa_url, headers=headers, timeout=30.0)
#                     mfa_response.raise_for_status()
#                     mfa_data = mfa_response.json()
#                     methods = mfa_data.get("strongAuthenticationMethods", [])
#                     if methods:
#                         mfa_status = True
#                 except Exception:
#                     pass
#
#                 user_data = {
#                     "UserId": user_id,
#                     "Name": user.get("displayName"),
#                     "Email": user.get("mail") or upn,
#                     "Department": user.get("department"),
#                     "Role": user.get("jobTitle"),
#                     "Status": "Active" if user.get("accountEnabled", True) else "Disabled",
#                     "MFA": mfa_status,
#                     "UserType": user.get("userType")
#                 }
#                 users_list.append(user_data)
#
#         return GraphApiResponse(status_code=200, data={"users": users_list}, error=None)
#
#     except httpx.HTTPStatusError as exc:
#         return GraphApiResponse(status_code=exc.response.status_code, data={"users": []}, error=f"Graph API error: {exc.response.text}")
#     except Exception as e:
#         return GraphApiResponse(status_code=500, data={"users": []}, error=f"Failed to get user details: {str(e)}")


# # ----------- Bulk User Details Endpoint --------------
# @router.get("/AllUsersDetails", response_model=GraphApiResponse, summary="Get Detailed Information for All Users")
# async def get_all_users_details(credentials: tuple = Depends(get_client_credentials)):
#     try:
#         identifier, identifier_type = credentials
#         if identifier_type == "org_id":
#             from app.core.database.supabase_services import get_organization_credentials
#             creds = await get_organization_credentials(int(identifier))
#             if not creds:
#                 raise Exception(f"No credentials found for org_id: {identifier}")
#             client_id = creds['client_id']
#         elif identifier_type == "ninjaone_org_id":
#             from app.core.database.supabase_services import supabase
#             response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
#             if not response.data or len(response.data) == 0:
#                 raise Exception(f"No client_id found for ninjaone_org_id: {identifier}")
#             client_id = response.data[0]['client_id']
#         else:
#             client_id = identifier
#         token = await get_access_token(client_id)
#         headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
#         logger.info("Fetching detailed information for all users")
#         async with httpx.AsyncClient(timeout=60.0) as client:
#             users_url = "https://graph.microsoft.com/v1.0/users?$select=id,displayName,mail,userPrincipalName,department,jobTitle,accountEnabled,userType"
#             users_response = await client.get(users_url, headers=headers)
#             users_response.raise_for_status()
#             users = users_response.json().get("value", [])
#             if not users:
#                 return GraphApiResponse(status_code=200, data={"users": []}, error=None)
#             thirty_days_ago = datetime.utcnow() - timedelta(days=30)
#             date_filter = thirty_days_ago.strftime("%Y-%m-%dT%H:%M:%SZ")
#             all_user_details = []
#             batch_size = 10
#             for i in range(0, len(users), batch_size):
#                 batch = users[i:i + batch_size]
#                 tasks = [fetch_single_user_complete_details(client, headers, user, date_filter) for user in batch]
#                 batch_results = await asyncio.gather(*tasks, return_exceptions=True)
#                 for result in batch_results:
#                     if not isinstance(result, Exception) and result:
#                         all_user_details.append(result)
#                 if i + batch_size < len(users):
#                     await asyncio.sleep(0.5)
#             return GraphApiResponse(status_code=200, data={"users": all_user_details}, error=None)
#     except Exception as e:
#         logger.error(f"Error fetching all users details: {str(e)}")
#         return GraphApiResponse(status_code=500, data={"users": []}, error=f"Failed to get all users details: {str(e)}")


# # ----------- Individual User Details Endpoint --------------
# @router.get("/UserDetails/{user_id}", response_model=GraphApiResponse, summary="Get Detailed User Information")
# async def get_user_details(
#         user_id: str = Path(..., description="User ID or User Principal Name"),
#         credentials: tuple = Depends(get_client_credentials)
# ):
#     try:
#         identifier, identifier_type = credentials
#         if identifier_type == "org_id":
#             from app.core.database.supabase_services import get_organization_credentials
#             creds = await get_organization_credentials(int(identifier))
#             if not creds:
#                 raise Exception(f"No credentials found for org_id: {identifier}")
#             client_id = creds['client_id']
#         elif identifier_type == "ninjaone_org_id":
#             from app.core.database.supabase_services import supabase
#             response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
#             if not response.data or len(response.data) == 0:
#                 raise Exception(f"No client_id found for ninjaone_org_id: {identifier}")
#             client_id = response.data[0]['client_id']
#         else:
#             client_id = identifier
#         token = await get_access_token(client_id)
#         headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
#         thirty_days_ago = datetime.utcnow() - timedelta(days=30)
#         date_filter = thirty_days_ago.strftime("%Y-%m-%dT%H:%M:%SZ")
#         logger.info(f"Fetching detailed information for user: {user_id}")
#         async with httpx.AsyncClient(timeout=30.0) as client:
#             tasks = [
#                 fetch_user_basic_info(client, headers, user_id),
#                 fetch_user_licenses(client, headers, user_id),
#                 fetch_mail_folders(client, headers, user_id),
#                 fetch_drive_info(client, headers, user_id),
#                 fetch_drive_files_count(client, headers, user_id),
#                 fetch_group_memberships(client, headers, user_id),
#                 fetch_authentication_methods(client, headers, user_id),
#                 fetch_signin_logs(client, headers, user_id, date_filter),
#                 fetch_user_devices(client, headers, user_id)
#             ]
#             results = await asyncio.gather(*tasks, return_exceptions=True)
#             user_info = results[0] if not isinstance(results[0], Exception) else None
#             licenses = results[1] if not isinstance(results[1], Exception) else None
#             mail_folders = results[2] if not isinstance(results[2], Exception) else None
#             drive_info = results[3] if not isinstance(results[3], Exception) else None
#             drive_files = results[4] if not isinstance(results[4], Exception) else None
#             groups = results[5] if not isinstance(results[5], Exception) else None
#             auth_methods = results[6] if not isinstance(results[6], Exception) else None
#             signin_logs = results[7] if not isinstance(results[7], Exception) else None
#             devices = results[8] if not isinstance(results[8], Exception) else None
#             transformed_data = transform_all_data({
#                 'user_info': user_info, 'licenses': licenses, 'mail_folders': mail_folders,
#                 'drive_info': drive_info, 'drive_files': drive_files, 'groups': groups,
#                 'auth_methods': auth_methods, 'signin_logs': signin_logs, 'devices': devices
#             })
#             return GraphApiResponse(status_code=200, data=transformed_data, error=None)
#     except Exception as e:
#         logger.error(f"Error fetching user details for {user_id}: {str(e)}")
#         return GraphApiResponse(status_code=500, data=None, error=f"Failed to get user details: {str(e)}")


# ==============================================================================
# Helper functions used by the above commented-out endpoints (kept for reference)
# ==============================================================================

async def fetch_single_user_complete_details(client: httpx.AsyncClient, headers: Dict, user: Dict, date_filter: str) -> Optional[Dict]:
    """Fetch complete details for a single user"""
    try:
        user_id = user.get("id")
        if not user_id:
            return None
        tasks = [
            fetch_user_licenses(client, headers, user_id),
            fetch_mail_folders(client, headers, user_id),
            fetch_drive_info(client, headers, user_id),
            fetch_drive_files_count(client, headers, user_id),
            fetch_group_memberships(client, headers, user_id),
            fetch_authentication_methods(client, headers, user_id),
            fetch_signin_logs(client, headers, user_id, date_filter),
            fetch_user_devices(client, headers, user_id)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        licenses = results[0] if not isinstance(results[0], Exception) else None
        mail_folders = results[1] if not isinstance(results[1], Exception) else None
        drive_info = results[2] if not isinstance(results[2], Exception) else None
        drive_files = results[3] if not isinstance(results[3], Exception) else None
        groups = results[4] if not isinstance(results[4], Exception) else None
        auth_methods = results[5] if not isinstance(results[5], Exception) else None
        signin_logs = results[6] if not isinstance(results[6], Exception) else None
        devices = results[7] if not isinstance(results[7], Exception) else None
        return transform_all_data({
            'user_info': user, 'licenses': licenses, 'mail_folders': mail_folders,
            'drive_info': drive_info, 'drive_files': drive_files, 'groups': groups,
            'auth_methods': auth_methods, 'signin_logs': signin_logs, 'devices': devices
        })
    except Exception as e:
        logger.error(f"Error fetching details for user {user.get('displayName', 'Unknown')}: {str(e)}")
        return None


async def fetch_user_basic_info(client: httpx.AsyncClient, headers: Dict, user_id: str):
    url = f"https://graph.microsoft.com/v1.0/users/{user_id}"
    response = await client.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


async def fetch_user_licenses(client: httpx.AsyncClient, headers: Dict, user_id: str):
    url = f"https://graph.microsoft.com/v1.0/users/{user_id}/licenseDetails"
    response = await client.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


async def fetch_mail_folders(client: httpx.AsyncClient, headers: Dict, user_id: str):
    url = f"https://graph.microsoft.com/v1.0/users/{user_id}/mailFolders"
    response = await client.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


async def fetch_drive_info(client: httpx.AsyncClient, headers: Dict, user_id: str):
    url = f"https://graph.microsoft.com/v1.0/users/{user_id}/drive"
    response = await client.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


async def fetch_drive_files_count(client: httpx.AsyncClient, headers: Dict, user_id: str):
    url = f"https://graph.microsoft.com/v1.0/users/{user_id}/drive/root/children?$count=true&$top=1"
    response = await client.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


async def fetch_group_memberships(client: httpx.AsyncClient, headers: Dict, user_id: str):
    url = f"https://graph.microsoft.com/v1.0/users/{user_id}/memberOf"
    response = await client.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


async def fetch_authentication_methods(client: httpx.AsyncClient, headers: Dict, user_id: str):
    url = f"https://graph.microsoft.com/v1.0/users/{user_id}/authentication/methods"
    response = await client.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


async def fetch_signin_logs(client: httpx.AsyncClient, headers: Dict, user_id: str, date_filter: str):
    filter_query = f"userId eq '{user_id}' and createdDateTime ge {date_filter}"
    url = f"https://graph.microsoft.com/v1.0/auditLogs/signIns?$filter={filter_query}"
    response = await client.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


async def fetch_user_devices(client: httpx.AsyncClient, headers: Dict, user_id: str):
    url = f"https://graph.microsoft.com/v1.0/users/{user_id}/ownedDevices"
    response = await client.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


def transform_all_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Transform all fetched data into final response format"""
    user_info = data.get('user_info') or {}
    licenses = transform_licenses(data.get('licenses'))
    mailbox_data = transform_mailbox_data(data.get('mail_folders'))
    onedrive_data = transform_onedrive_data(data.get('drive_info'), data.get('drive_files'))
    groups = transform_groups(data.get('groups'))
    security_data = transform_security_data(data.get('auth_methods'), data.get('signin_logs'))
    activity_data = transform_activity_data(data.get('signin_logs'))
    user_status = determine_user_status(data.get('signin_logs'))
    devices_data = transform_devices_data(data.get('devices'))

    return {
        "UserId": user_info.get("id", "Not Available"),
        "Name": user_info.get("displayName", "Not Available"),
        "Email": user_info.get("mail") or user_info.get("userPrincipalName", "Not Available"),
        "Department": user_info.get("department", "Not Available"),
        "Role": user_info.get("jobTitle", "Not Available"),
        "Status": user_status,
        "MFA": security_data.get("mfa_enabled", False),
        "last_sign_in": security_data.get("last_sign_in", "Not Available"),
        "mfa_methods": security_data.get("authentication_methods", []),
        "licenses": licenses,
        "mailbox": mailbox_data,
        "one_drive": onedrive_data,
        "activity": activity_data,
        "security": security_data,
        "groups": groups,
        "devices": devices_data
    }


def transform_licenses(license_data: Optional[Dict]) -> List[str]:
    if not license_data or not license_data.get("value"):
        return []
    license_mapping = {
        'O365_BUSINESS_ESSENTIALS': 'Microsoft 365 Business Essentials',
        'SPB_ESSENTIALS': 'Microsoft 365 Business Premium',
        'ENTERPRISEPACK': 'Office 365 E3',
        'ENTERPRISEPREMIUM': 'Office 365 E5',
        'POWER_BI_PRO': 'Power BI Pro',
        'AZDEVOPS': 'Azure DevOps'
    }
    return [
        license_mapping.get(license.get("skuPartNumber", ""), license.get("skuPartNumber", "Unknown"))
        for license in license_data.get("value", [])
    ]


def transform_mailbox_data(mail_folders: Optional[Dict]) -> Dict[str, Any]:
    if not mail_folders or not mail_folders.get("value"):
        return {"size_in_mb": 0, "quota_in_mb": 50000, "usage_percentage": 0.0, "items_count": 0, "archived_items_count": 0}
    folders = mail_folders.get("value", [])
    total_items = sum(folder.get("totalItemCount", 0) for folder in folders)
    total_size_bytes = sum(folder.get("sizeInBytes", 0) for folder in folders)
    archive_folder = next((f for f in folders if f.get("displayName") == "Archive"), None)
    archived_items = archive_folder.get("totalItemCount", 0) if archive_folder else 0
    size_in_mb = round(total_size_bytes / (1024 * 1024))
    quota_in_mb = 50000
    usage_percentage = (size_in_mb / quota_in_mb) * 100 if quota_in_mb > 0 else 0
    return {"size_in_mb": size_in_mb, "quota_in_mb": quota_in_mb, "usage_percentage": round(usage_percentage, 2), "items_count": total_items, "archived_items_count": archived_items}


def transform_onedrive_data(drive_info: Optional[Dict], drive_files: Optional[Dict]) -> Dict[str, Any]:
    if not drive_info or not drive_info.get("quota"):
        return {"size_in_mb": 0, "quota_in_mb": 0, "usage_percentage": 0.0, "files_count": 0}
    quota = drive_info.get("quota", {})
    size_in_mb = round(quota.get("used", 0) / (1024 * 1024))
    quota_in_mb = round(quota.get("total", 0) / (1024 * 1024))
    usage_percentage = (quota.get("used", 0) / quota.get("total", 1)) * 100
    files_count = drive_files.get("@odata.count", 0) if drive_files else 0
    return {"size_in_mb": size_in_mb, "quota_in_mb": quota_in_mb, "usage_percentage": round(usage_percentage, 2), "files_count": files_count}


def transform_groups(groups_data: Optional[Dict]) -> List[str]:
    if not groups_data or not groups_data.get("value"):
        return []
    return [group.get("displayName", "Unknown Group") for group in groups_data.get("value", []) if group.get("@odata.type") == "#microsoft.graph.group"]


def transform_devices_data(devices_data: Optional[Dict]) -> Dict[str, Any]:
    if not devices_data or not devices_data.get("value"):
        return {"total_devices": 0, "device_list": []}
    devices = devices_data.get("value", [])
    device_list = [{"device_id": d.get("id", ""), "device_name": d.get("displayName", "Unknown Device"), "device_type": d.get("@odata.type", "")} for d in devices]
    return {"total_devices": len(devices), "device_list": device_list}


def transform_security_data(auth_methods: Optional[Dict], signin_logs: Optional[Dict]) -> Dict[str, Any]:
    mfa_enabled = False
    mfa_methods = []
    if auth_methods and auth_methods.get("value"):
        for method in auth_methods.get("value", []):
            method_type = method.get("@odata.type", "")
            if "microsoftAuthenticatorAuthenticationMethod" in method_type:
                mfa_methods.append("microsoftAuthenticatorPush")
            elif "phoneAuthenticationMethod" in method_type:
                mfa_methods.append("sms")
            elif "emailAuthenticationMethod" in method_type:
                mfa_methods.append("email")
            elif "fido2AuthenticationMethod" in method_type:
                mfa_methods.append("fido2")
            elif "softwareOathAuthenticationMethod" in method_type:
                mfa_methods.append("softwareOath")
            elif "passwordAuthenticationMethod" in method_type:
                mfa_methods.append("password")
        mfa_methods = list(set(mfa_methods))
        non_password_methods = [m for m in mfa_methods if m != "password"]
        if non_password_methods:
            mfa_enabled = True
    last_sign_in = "Not Available"
    sign_in_attempts = 0
    blocked_attempts = 0
    risk_level = "low"
    if signin_logs and signin_logs.get("value"):
        logs = signin_logs.get("value", [])
        sign_in_attempts = len(logs)
        for log in sorted(logs, key=lambda x: x.get("createdDateTime", ""), reverse=True):
            if log.get("status", {}).get("errorCode") == 0:
                last_sign_in = log.get("createdDateTime", "Not Available")
                break
        blocked_attempts = sum(1 for log in logs if log.get("status", {}).get("errorCode", 0) != 0)
        recent_risks = [log.get("riskLevelAggregated", "none") for log in logs[:10]]
        if any(risk in ["high", "medium"] for risk in recent_risks):
            risk_level = "medium"
    return {
        "risk_level": risk_level,
        "sign_in_attempts_last_30_days": sign_in_attempts,
        "blocked_sign_in_attempts": blocked_attempts,
        "authentication_methods": mfa_methods,
        "last_password_change": "Not Available",
        "mfa_enabled": mfa_enabled,
        "last_sign_in": last_sign_in
    }


def transform_activity_data(signin_logs: Optional[Dict]) -> Dict[str, Any]:
    return {
        "teams_calls_minutes_last_30_days": 0,
        "teams_meetings_count_last_30_days": 0,
        "teams_messages_count_last_30_days": 0,
        "email_sent_count_last_30_days": 0,
        "documents_edited_last_30_days": 0
    }


def determine_user_status(signin_logs: Optional[Dict]) -> str:
    if not signin_logs or not signin_logs.get("value"):
        return "Inactive"
    logs = signin_logs.get("value", [])
    if logs:
        return "Active"
    return "Inactive"
