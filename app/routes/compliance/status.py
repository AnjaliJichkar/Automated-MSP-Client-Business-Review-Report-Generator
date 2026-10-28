import logging
import asyncio
import httpx
import uuid
from datetime import datetime
from typing import Optional,Dict,Any
from app.core.database.supabase_services import get_organization_credentials
from fastapi import APIRouter, Body, Depends, Query, HTTPException
from app.core.auth.dependencies import get_client_id
from app.core.auth.middleware import get_access_token
from app.schemas.api import GraphApiResponse
from app.core.config.settings import GRAPH_V1_URL, GRAPH_BETA_URL

# Create router for compliance endpoints
router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/GetAllComplianceStatus", response_model=Dict[str, Any], summary="Get All Compliance Status")
async def get_all_compliance_status(clientId: Optional[str] = Query(None),org_id: Optional[int] = Query(None)):
    """
    Consolidated endpoint that returns all compliance status information in frontend-friendly format.
    """
    try:
        # Handle both clientId (old) and org_id (new) parameters
        if not clientId and not org_id:
            raise HTTPException(
                status_code=400,
                detail="Either clientId or org_id query parameter is required"
            )

        if clientId:
            client_id = clientId.strip()
            # For clientId parameter, we need to get credentials to pre-cache token
            creds = await get_organization_credentials(org_id) if org_id else None
            if creds:
                # Pre-cache token to avoid lookup issues
                from app.core.auth.middleware import get_access_token_from_credentials
                await get_access_token_from_credentials(
                    creds['tenant_id'],
                    creds['client_id'],
                    creds['client_secret']
                )
        else:
            creds = await get_organization_credentials(org_id)
            if not creds:
                raise HTTPException(
                    status_code=404,
                    detail=f"No credentials found for org_id: {org_id}"
                )
            client_id = creds['client_id']
            # Pre-cache token before calling internal functions
            from app.core.auth.middleware import get_access_token_from_credentials
            await get_access_token_from_credentials(
                creds['tenant_id'],
                creds['client_id'],
                creds['client_secret']
            )

        # List of all compliance checks to run
        compliance_checks = [
            {
                "name": "adminMFAStatus",
                "function": get_admin_mfa_status,
                "description": "Administrative MFA Compliance",
                "display_name": "Admin MFA status"
            },
            {
                "name": "userMFAStatus",
                "function": get_user_mfa_status,
                "description": "User MFA Compliance",
                "display_name": "User MFA"
            },
            {
                "name": "sharePointExternalResharing",
                "function": list_sharepoint_external_resharing_status,
                "description": "SharePoint External Resharing Compliance",
                "display_name": "Resharing by external user - SharePoint"
            },
            {
                "name": "unifiedAuditingStatus",
                "function": list_unified_auditing_status,
                "description": "Unified Auditing Logs Compliance",
                "display_name": "Unified Auditing logs - Purview"
            },
            {
                "name": "highRiskUsersPolicy",
                "function": list_high_risk_users_signin_policies ,
                "description": "High Risk Users Policy Compliance",
                "display_name": "Block High Risk Users - Policy check"
            },
            {
                "name": "riskySignInPolicies",
                "function": list_risky_signin_policies,
                "description": "Risky Sign-In Policies Compliance",
                "display_name": "Block Risky Sign-ins policies"
            },
            # {
            #     "name": "sharedMailboxSignIn",
            #     "function": list_shared_mailbox_signin_status,
            #     "description": "Shared Mailbox Sign-In Blocking Compliance",
            #     "display_name": "Block Sign-in on Shared Mailboxes"
            # },
            {
                "name": "guestUserAccessPermissions",
                "function": list_guest_user_access_permissions,
                "description": "Guest User Access Permissions Compliance",
                "display_name": "Entra ID Guest User Access Permissions"
            },
            {
                "name": "sharepointSiteCreation",
                "function": list_sharepoint_site_creation_status,
                "description": "SharePoint Site Creation Governance Compliance",
                "display_name": "SharePoint Site Creation by Standard Users"
            },
            {
                "name": "weakAuthenticatorStatus",
                "function": list_weak_authenticator_status,
                "description": "Weak 2FA Authenticator Compliance",
                "display_name": "Disable weakest 2FA authenticators"
            },
            {
                "name": "globalAdminsCount",
                "function": list_global_admins,
                "description": "Global Administrators Count Compliance",
                "display_name": "Number of global admins"
            },
            {
                "name": "passwordExpirationPolicy",
                "function": check_password_expiration_policy,
                "description": "Password Expiration Policy Compliance",
                "display_name": "Password expiration policy check"
            },
            {
                "name": "spfPolicyStatus",
                "function": list_spf_policy_status,
                "description": "SPF Policy Configuration Compliance",
                "display_name": "SPF policy check"
            },
            {
                "name": "teamsExternalAccess",
                "function": check_teams_external_access,
                "description": "Teams External Access Policy Compliance",
                "display_name": "Teams Default external/guest policy check"
            },
            {
                "name": "riskyCountryPolicy",
                "function": list_risky_country_locations,
                "description": "Risky Country Policy Compliance",
                "display_name": "Risky Country Policy check"
            },
            {
                "name": "connectedAppsUserConsents",
                "function": list_connected_apps_user_consents,
                "description": "Connected Apps & User Consents Policy Compliance",
                "display_name": "Connected Apps & User consents"
            }


            # Add more endpoints here as you create them
        ]

        # Execute all compliance checks concurrently
        tasks = []
        for check in compliance_checks:
            task = asyncio.create_task(
                execute_compliance_check(check["function"], check["name"], check["description"],client_id)
            )
            tasks.append(task)

        # Wait for all checks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Transform results into frontend format
        policies = []
        status_counts = {
            "Compliant": 0,
            "Partially Compliant": 0,
            "Not Compliant": 0,
            "Not Measured": 0
        }

        for i, result in enumerate(results):
            check_info = compliance_checks[i]
            policy = extract_policy_generic(result, check_info, isinstance(result, Exception))
            policies.append(policy)

            # Count statuses for detailed breakdown
            status = policy["status"]
            if status in status_counts:
                status_counts[status] += 1

        # Calculate totals
        total_checks = len(policies)
        compliant_checks = status_counts["Compliant"]
        partially_compliant_checks = status_counts["Partially Compliant"]
        non_compliant_checks = status_counts["Not Compliant"]
        not_measured_checks = status_counts["Not Measured"]

        # Calculate posture score and overall status
        posture_score = calculate_posture_score(compliant_checks, partially_compliant_checks, total_checks)
        overall_status = determine_overall_status(compliant_checks, partially_compliant_checks, non_compliant_checks,
                                                  total_checks)

        # Return frontend-friendly format with detailed breakdown
        return {
            "status_code": 200,
            "data": {
                "compliance_summary": {
                    "title": "Microsoft 365 Compliance Status",
                    "status": overall_status,
                    "score_percentage": f"{posture_score}%",
                    "total_policies": total_checks,
                    "breakdown": {
                        "compliant": {
                            "count": compliant_checks,
                            "label": "Compliant"
                        },
                        "partially_compliant": {
                            "count": partially_compliant_checks,
                            "label": "Partially"
                        },
                        "non_compliant": {
                            "count": non_compliant_checks,
                            "label": "Non-Compliant"
                        },
                        "not_measured": {
                            "count": not_measured_checks,
                            "label": "Not Measured"
                        }
                    }
                },
                "policies": policies
            }
        }

    except Exception as e:
        logger.error(f"Error getting consolidated compliance status: {str(e)}")
        return {
            "status_code": 500,
            "data": {
                "compliance_summary": {
                    "title": "Microsoft 365 Compliance Status",
                    "status": "Error",
                    "score_percentage": "0%",
                    "total_policies": 0,
                    "breakdown": {
                        "compliant": {"count": 0, "label": "Compliant"},
                        "partially_compliant": {"count": 0, "label": "Partially"},
                        "non_compliant": {"count": 0, "label": "Non-Compliant"},
                        "not_measured": {"count": 0, "label": "Not Measured"}
                    }
                },
                "policies": []
            }
        }


def extract_policy_generic(result, check_info: dict, is_error: bool) -> dict:
    """
    Generic policy extraction function for all standardized compliance responses.
    Works with the standardized response format:
    {
        "complianceStatus": "...",
        "statusMessage": "...",
        "recommendation": "...",
        "complianceDetails": {...}
    }
    """
    # Generate unique ID based on the check name
    policy_id = f"policy-{check_info['name'].lower().replace(' ', '-')}"

    default_policy = {
        "id": policy_id,
        "name": check_info["display_name"],
        "status": "Not Measured",
        "description": "Unable to determine status",
        "recommendation": "Check system configuration and try again",
        "action": {
            "type": "investigate",
            "title": "Investigate Issue",
            "details": "Unable to retrieve compliance data"
        }
    }

    if is_error:
        return default_policy

    try:
        # Handle successful results
        if result and hasattr(result, 'data'):
            data = result.data

            # Handle different data structures (list or dict)
            if isinstance(data, list) and len(data) > 0:
                data = data[0]
            elif not isinstance(data, dict):
                return default_policy

            # Extract standardized fields
            status = data.get("complianceStatus", "Not Measured")
            description = data.get("statusMessage", "Unable to determine status")
            recommendation = data.get("recommendation", "No recommendation available")

            # Generate action info
            action_type, action_title, action_details = get_action_info(status, check_info["display_name"])

            return {
                "id": policy_id,
                "name": check_info["display_name"],
                "status": status,
                "description": description,
                "recommendation": recommendation,
                "action": {
                    "type": action_type,
                    "title": action_title,
                    "details": action_details
                }
            }

    except Exception as e:
        logger.error(f"Error in generic extraction for {check_info['name']}: {str(e)}")

    return default_policy


def get_action_info(status: str, policy_type: str) -> tuple:
    """Get action type, title and details based on compliance status."""
    if status == "Compliant":
        return (
            "none",  # ← Also consider changing type from "enhance" to "none"
            "No action needed",  # ← Change this line
            "Policy is fully compliant."  # ← And optionally this line
        )
    elif status == "Partially Compliant":
        return (
            "improve",
            f"Improve {policy_type}",
            "Address partial compliance issues to achieve full compliance."
        )
    elif status == "Not Compliant":
        return (
            "fix",
            f"Fix {policy_type}",
            "Immediate action required to address compliance failures."
        )
    else:  # Not Measured, Error, etc.
        return (
            "investigate",
            f"Investigate {policy_type}",
            "Check system configuration and permissions."
        )


def calculate_posture_score(compliant: int, partially_compliant: int, total: int) -> int:
    """Calculate overall security posture score (0-100)."""
    if total == 0:
        return 0

    # Weight: Compliant = 100%, Partially Compliant = 60%, Non-compliant/Not Measured = 0%
    score = (compliant * 100 + partially_compliant * 60) / total
    return round(score)


def determine_overall_status(compliant: int, partially_compliant: int, non_compliant: int, total: int) -> str:
    """Determine overall compliance status."""
    if total == 0:
        return "Not Measured"

    compliance_ratio = compliant / total

    if compliance_ratio == 1.0:
        return "Compliant"
    elif compliance_ratio >= 0.7:
        return "Partially Compliant"
    elif non_compliant > compliant:
        return "Not Compliant"
    else:
        return "Partially Compliant"


async def execute_compliance_check(check_function, check_name: str, description: str, client_id: str, max_retries: int = 2):
    """Execute a single compliance check function with automatic retry logic."""

    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                logger.warning(f" RETRY attempt {attempt}/{max_retries} for: {check_name}")
            else:
                logger.info(f"Starting compliance check: {check_name}")

            result = await check_function(client_id)

            # Check if the function returned an error response internally
            if (hasattr(result, 'status_code') and result.status_code >= 400) or \
                    (hasattr(result, 'data') and result.data.get('complianceStatus') in ['Not Measured', 'Error']):

                # If this is not the last attempt, retry
                if attempt < max_retries:
                    logger.warning(f"⚠️ Error response for {check_name}, will retry...")
                    await asyncio.sleep(1)  # Wait 1 second before retry
                    continue
                else:
                    logger.error(f"COMPLETED WITH ERROR after {max_retries} retries: {check_name}")
            else:
                logger.info(f" SUCCESS: {check_name}")

            return result

        except Exception as e:
            # If this is not the last attempt, retry
            if attempt < max_retries:
                logger.warning(f"⚠️ Exception in {check_name}: {type(e).__name__}, retrying...")
                await asyncio.sleep(1)  # Wait 1 second before retry
                continue
            else:
                logger.error(f"FAILED WITH EXCEPTION after {max_retries} retries: {check_name}")
                logger.error(f"Exception type: {type(e).__name__}")
                logger.error(f"Exception message: {str(e) if str(e) else 'No message'}")
                logger.error(f"Full traceback:", exc_info=True)

                # Return error response instead of raising
                return GraphApiResponse(
                    status_code=500,
                    data={
                        "complianceStatus": "Not Measured",
                        "statusMessage": f"Failed to check {description}",
                        "recommendation": "Check system configuration and try again",
                        "complianceDetails": None,
                        "reportGeneratedAt": datetime.now().isoformat() + "Z"
                    },
                    error=f"Failed to execute {description}: {str(e)}"
                )

#admin MFA
@router.get("/GetAdminMFAStatus", response_model=GraphApiResponse, summary="Get Admin MFA Status")
async def get_admin_mfa_status(clientId: Optional[str] = Query(None),org_id: Optional[int] = Query(None)):
    """
    Gets MFA compliance status specifically for administrative accounts.
    Uses roleDefinitions + roleAssignments to identify critical admins,
    then checks /users/{id}/authentication/methods for MFA status.
    """
    try:
        # Handle both clientId (old) and org_id (new) parameters
        if not clientId and not org_id:
            raise HTTPException(
                status_code=400,
                detail="Either clientId or org_id query parameter is required"
            )

        if clientId:
            client_id = clientId.strip()
        else:
            creds = await get_organization_credentials(org_id)
            if not creds:
                raise HTTPException(
                    status_code=404,
                    detail=f"No credentials found for org_id: {org_id}"
                )
            client_id = creds['client_id']
        token = await get_access_token(client_id)
        headers = {"Authorization": f"Bearer {token}", "Accept": "*/*"}

        # --- Critical admin roles we care about ---
        critical_admin_role_ids = {
            "62e90394-69f5-4237-9190-012177145e10": "Global Administrator",
            "194ae4cb-b126-40b2-bd5b-6091b380977d": "Security Administrator",
            "e8611ab8-c189-46e8-94e1-60213ab1f814": "Privileged Role Administrator",
            "b0f54661-2d74-4c50-afa3-1ec803f12efe": "Authentication Administrator",
            "17315797-102d-40b4-93e0-432062caca18": "Conditional Access Administrator",
            "fe930be7-5e62-47db-91af-98c3a49a38b1": "User Administrator",
            "29232cdf-9323-42fd-ade2-1d097af3e4de": "Exchange Administrator",
            "966707d0-3269-4727-9be2-8c3a10f19b9d": "Password Administrator"
        }

        # 1. Get all built-in role definitions
        role_definitions_url = f"{GRAPH_V1_URL}/roleManagement/directory/roleDefinitions"
        role_definitions_params = {"$filter": "isBuiltIn eq true"}
        async with httpx.AsyncClient() as client:
            role_defs_resp = await client.get(role_definitions_url, headers=headers, params=role_definitions_params, timeout=30.0)
            role_defs_resp.raise_for_status()
            role_defs_data = role_defs_resp.json()

        role_definitions = {rd["id"]: rd["displayName"] for rd in role_defs_data.get("value", [])}

        # 2. Get all role assignments
        role_assignments_url = f"{GRAPH_V1_URL}/roleManagement/directory/roleAssignments"
        async with httpx.AsyncClient() as client:
            role_asgn_resp = await client.get(role_assignments_url, headers=headers, timeout=30.0)
            role_asgn_resp.raise_for_status()
            role_asgn_data = role_asgn_resp.json()

        role_assignments = role_asgn_data.get("value", [])

        # 3. Extract unique critical admin users
        admin_users = {}

        async def fetch_user_info(principal_id, role_name):
            user_url = f"{GRAPH_V1_URL}/users/{principal_id}"
            user_params = {"$select": "id,userPrincipalName,displayName,accountEnabled"}
            async with httpx.AsyncClient() as client:
                user_resp = await client.get(user_url, headers=headers, params=user_params, timeout=10.0)
                if user_resp.status_code == 200:
                    user_data = user_resp.json()
                    if user_data.get("accountEnabled", False) and user_data.get("userPrincipalName"):
                        if principal_id not in admin_users:
                            admin_users[principal_id] = {
                                "id": principal_id,
                                "userPrincipalName": user_data.get("userPrincipalName", ""),
                                "displayName": user_data.get("displayName", ""),
                                "accountEnabled": True,
                                "roles": [],
                                "isCriticalAdmin": False
                            }
                        if role_definition_id in critical_admin_role_ids:
                            role_name = critical_admin_role_ids[role_definition_id]
                            admin_users[principal_id]["roles"].append(role_name)
                            admin_users[principal_id]["isCriticalAdmin"] = True

        # gather all admin role users
        fetch_tasks = []
        for assignment in role_assignments:
            principal_id = assignment.get("principalId")
            role_definition_id = assignment.get("roleDefinitionId")
            if not principal_id or not role_definition_id:
                continue

            if role_definition_id in critical_admin_role_ids:
                role_name = critical_admin_role_ids[role_definition_id]
                fetch_tasks.append(fetch_user_info(principal_id, role_name))
        await asyncio.gather(*fetch_tasks)

        # 4. Get MFA status for each critical admin (concurrently)
        async def fetch_admin_mfa(admin_info):
            user_id = admin_info["id"]
            upn = admin_info["userPrincipalName"]
            methods = []
            is_mfa_registered = False

            try:
                async with httpx.AsyncClient() as client:
                    auth_resp = await client.get(
                        f"{GRAPH_V1_URL}/users/{user_id}/authentication/methods",
                        headers=headers,
                        timeout=10.0
                    )
                    if auth_resp.status_code == 200:
                        auth_data = auth_resp.json()
                        for method in auth_data.get("value", []):
                            method_type = method.get("@odata.type", "")
                            if "microsoftAuthenticatorAuthenticationMethod" in method_type:
                                methods.append("microsoftAuthenticatorPush")
                            elif "phoneAuthenticationMethod" in method_type:
                                methods.append("sms")
                            elif "emailAuthenticationMethod" in method_type:
                                methods.append("email")
                            elif "fido2AuthenticationMethod" in method_type:
                                methods.append("fido2")
                            elif "softwareOathAuthenticationMethod" in method_type:
                                methods.append("softwareOath")
                            elif "passwordAuthenticationMethod" in method_type:
                                methods.append("password")

                        methods = list(set(methods))
                        if any(m for m in methods if m != "password"):
                            is_mfa_registered = True

            except Exception as e:
                logger.warning(f"Failed to get MFA methods for admin {upn}: {str(e)}")

            return {
                "id": admin_info["id"],
                "userPrincipalName": upn,
                "displayName": admin_info["displayName"],
                "administrativeRoles": admin_info["roles"],
                "isCriticalAdmin": admin_info["isCriticalAdmin"],
                "hasMfaEnabled": is_mfa_registered,
                "mfaRegistered": is_mfa_registered,
                "conditionalAccessCovered": False,   # placeholder
                "securityDefaultsEnabled": False,    # placeholder
                "complianceStatus": "Compliant" if is_mfa_registered else "Non-Compliant"
            }

        admin_results = await asyncio.gather(*(fetch_admin_mfa(admin) for admin in admin_users.values()))

        # 5. Compliance summary
        total_admins = len(admin_results)
        compliant_admins = sum(1 for a in admin_results if a["hasMfaEnabled"])
        compliance_percentage = round((compliant_admins / total_admins) * 100, 1) if total_admins > 0 else 0

        if compliance_percentage == 100:
            overall_status = "Compliant"
            recommendation = "Current status is good. Continue to monitor admin accounts for MFA compliance."
            status_message = f"{compliant_admins}/{total_admins} administrative accounts have MFA enabled"
        elif compliance_percentage >= 80:
            overall_status = "Partially Compliant"
            recommendation = f"Enable MFA for {total_admins - compliant_admins} remaining admin accounts."
            status_message = f"{compliant_admins}/{total_admins} administrative accounts have MFA enabled"
        elif compliance_percentage == 0:
            overall_status = "Not Compliant"
            recommendation = f"URGENT: No administrative accounts have MFA enabled. Enable for all {total_admins} accounts immediately."
            status_message = "No administrative accounts have MFA enabled"
        else:
            overall_status = "Not Compliant"
            recommendation = "URGENT: Enable MFA for all administrative accounts immediately."
            status_message = f"{compliant_admins}/{total_admins} administrative accounts have MFA enabled"

        response_data = {
            "complianceStatus": overall_status,
            "statusMessage": status_message,
            "recommendation": recommendation,
            "complianceDetails": {
                "complianceSummary": {
                    "totalAdministrators": total_admins,
                    "compliantAdministrators": compliant_admins,
                    "nonCompliantAdministrators": total_admins - compliant_admins,
                    "compliancePercentage": f"{compliance_percentage}%"
                },
                "administratorDetails": admin_results
            },
            "reportGeneratedAt": datetime.now().isoformat() + "Z"
        }

        return GraphApiResponse(status_code=200, data=response_data)

    except Exception as e:
        logger.error(f"Error getting admin MFA status: {str(e)}")
        return GraphApiResponse(
            status_code=500,
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to determine admin MFA compliance status",
                "recommendation": "Check system configuration and try again",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            },
            error=f"Failed to get admin MFA status: {str(e)}"
        )

# USER MFA STATUS (Simplified)

@router.get("/GetUserMFAStatus", response_model=GraphApiResponse, summary="Get User MFA Status")
async def get_user_mfa_status(clientId: Optional[str] = Query(None),org_id: Optional[int] = Query(None)):
    """
    Gets simplified MFA compliance status for all users.
    Uses /users and /users/{id}/authentication/methods endpoints only.
    Runs MFA method lookups concurrently for better performance.
    """
    try:
        # Handle both clientId (old) and org_id (new) parameters
        if not clientId and not org_id:
            raise HTTPException(
                status_code=400,
                detail="Either clientId or org_id query parameter is required"
            )

        if clientId:
            client_id = clientId.strip()
        else:
            creds = await get_organization_credentials(org_id)
            if not creds:
                raise HTTPException(
                    status_code=404,
                    detail=f"No credentials found for org_id: {org_id}"
                )
            client_id = creds['client_id']
        token = await get_access_token(client_id)
        headers = {"Authorization": f"Bearer {token}", "Accept": "*/*"}

        # 1. Get all users with basic info
        users_url = f"{GRAPH_V1_URL}/users"
        users_params = {"$select": "id,userPrincipalName,accountEnabled,assignedLicenses,displayName"}

        async with httpx.AsyncClient() as client:
            users_resp = await client.get(users_url, headers=headers, params=users_params, timeout=30.0)
            users_resp.raise_for_status()
            users_data = users_resp.json()

        users = users_data.get("value", [])

        enabled_by_method = {
            "mfa_registered": 0,
            "conditional_access": 0,   # kept for response structure
            "security_defaults": 0,    # kept for response structure
            "per_user_mfa": 0          # kept for response structure
        }

        # --- helper function for concurrent fetch ---
        async def fetch_user_mfa(user):
            user_id = user.get("id", "")
            upn = user.get("userPrincipalName", "")

            mfa_methods = []
            mfa_registration_status = False

            try:
                async with httpx.AsyncClient() as client:
                    auth_resp = await client.get(
                        f"{GRAPH_V1_URL}/users/{user_id}/authentication/methods",
                        headers=headers,
                        timeout=10.0
                    )
                    if auth_resp.status_code == 200:
                        auth_data = auth_resp.json()
                        auth_methods = auth_data.get("value", [])

                        for method in auth_methods:
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

                        #  Updated compliance check: MFA only if > "password"
                        non_password_methods = [m for m in mfa_methods if m != "password"]
                        if non_password_methods:
                            mfa_registration_status = True

            except Exception as e:
                logger.warning(f"Failed to get auth methods for user {upn}: {str(e)}")

            return {
                "id": user_id,
                "userPrincipalName": upn,
                "displayName": user.get("displayName", ""),
                "accountEnabled": user.get("accountEnabled", False),
                "assignedLicenses": user.get("assignedLicenses", []),
                "isMfaRegistered": mfa_registration_status,
                "perUserMfaState": "disabled",        # placeholder
                "securityDefaultsEnabled": False,     # placeholder
                "conditionalAccessCovered": False,    # placeholder
                "methodsRegistered": mfa_methods,
                "applicablePolicies": []              # placeholder
            }

        # 2. Run all user MFA lookups concurrently
        user_results = await asyncio.gather(*(fetch_user_mfa(user) for user in users))

        # 3. Count MFA stats
        mfa_enabled_count = sum(1 for u in user_results if u["isMfaRegistered"])
        enabled_by_method["mfa_registered"] = mfa_enabled_count
        total_users = len(user_results)
        mfa_disabled_count = total_users - mfa_enabled_count

        # Compliance logic
        if total_users == 0:
            compliance_status = "Not Measured"
            status_message = "No users found to evaluate MFA compliance"
            recommendation = "Check user accounts and permissions"
        elif mfa_enabled_count == total_users:
            compliance_status = "Compliant"
            status_message = "All users have MFA enabled"
            recommendation = "Current status is good. Continue to monitor user MFA compliance."
        elif mfa_enabled_count > 0:
            compliance_status = "Partially Compliant"
            status_message = f"{mfa_disabled_count} users do not have MFA enabled"
            recommendation = "Enable MFA for remaining users to achieve full compliance."
        else:
            compliance_status = "Not Compliant"
            status_message = "No users have MFA enabled"
            recommendation = "URGENT: Enable MFA for all users immediately."

        response_data = {
            "complianceStatus": compliance_status,
            "statusMessage": status_message,
            "recommendation": recommendation,
            "complianceDetails": {
                "total_users": total_users,
                "mfa_enabled": mfa_enabled_count,
                "mfa_disabled": mfa_disabled_count,
                "enabled_by_method": enabled_by_method,
                "user_details": user_results,
                "measurement_description": "Count of users with MFA enabled by registered methods beyond password"
            },
            "reportGeneratedAt": datetime.now().isoformat() + "Z"
        }

        return GraphApiResponse(status_code=200, data=response_data)

    except httpx.HTTPStatusError as exc:
        logger.error(f"Graph API HTTP error: {exc.response.status_code} - {exc.response.text}")
        return GraphApiResponse(
            status_code=200,
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to retrieve user MFA data",
                "recommendation": "Check Graph API permissions and try again",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )

    except Exception as e:
        logger.error(f"Error getting user MFA status: {str(e)}")
        return GraphApiResponse(
            status_code=200,
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to determine user MFA compliance status",
                "recommendation": "Check system configuration and try again",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )


# GET Endpoint for Resharing by external user - SharePoint
@router.get("/ListSharePointExternalResharingStatus", response_model=GraphApiResponse,
            summary="Check SharePoint External Resharing Policy")
async def list_sharepoint_external_resharing_status(clientId: Optional[str] = Query(None),org_id: Optional[int] = Query(None)):
    """
    Checks SharePoint external resharing policy settings for compliance.
    Returns compliance status with recommendations.
    """
    try:
        # Handle both clientId (old) and org_id (new) parameters
        if not clientId and not org_id:
            raise HTTPException(
                status_code=400,
                detail="Either clientId or org_id query parameter is required"
            )

        if clientId:
            client_id = clientId.strip()
        else:
            creds = await get_organization_credentials(org_id)
            if not creds:
                raise HTTPException(
                    status_code=404,
                    detail=f"No credentials found for org_id: {org_id}"
                )
            client_id = creds['client_id']
        token = await get_access_token(client_id)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        # Get SharePoint settings with key fields for external resharing compliance
        sharepoint_settings_url = f"{GRAPH_BETA_URL}/admin/sharepoint/settings"
        params = {
            "$select": "isResharingByExternalUsersEnabled,sharingCapability,sharingDomainRestrictionMode,sharingAllowedDomainList"
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(sharepoint_settings_url, headers=headers, params=params, timeout=30.0)
            response.raise_for_status()
            settings_data = response.json()

        # Extract settings
        is_resharing_enabled = settings_data.get("isResharingByExternalUsersEnabled")
        sharing_capability = settings_data.get("sharingCapability")
        domain_restriction_mode = settings_data.get("sharingDomainRestrictionMode")
        allowed_domains = settings_data.get("sharingAllowedDomainList", [])

        # Determine compliance status and get recommendations
        compliance_info = determine_sharepoint_compliance_status(
            is_resharing_enabled, sharing_capability, domain_restriction_mode, allowed_domains
        )

        # Build standardized response
        result_data = {
            "complianceStatus": compliance_info["status"],
            "statusMessage": compliance_info["message"],
            "recommendation": compliance_info["recommendation"],
            "complianceDetails": {
                "sharepointExternalResharingSettings": {
                    "isResharingByExternalUsersEnabled": is_resharing_enabled,
                    "sharingCapability": sharing_capability,
                    "sharingDomainRestrictionMode": domain_restriction_mode,
                    "sharingAllowedDomainList": allowed_domains
                }
            },
            "reportGeneratedAt": datetime.now().isoformat() + "Z"
        }

        return GraphApiResponse(status_code=200, data=result_data)

    except httpx.HTTPStatusError as exc:
        logger.error(f"Graph API HTTP error: {exc.response.status_code} - {exc.response.text}")
        # Return Not Measured status for API failures
        return GraphApiResponse(
            status_code=200,  # Return 200 but with Not Measured status
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to retrieve SharePoint settings",
                "recommendation": "Check SharePoint admin permissions and try again",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )
    except Exception as e:
        logger.error(f"Error checking SharePoint external resharing status: {str(e)}")
        # Return Not Measured status for other failures
        return GraphApiResponse(
            status_code=200,  # Return 200 but with Not Measured status
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to retrieve SharePoint settings",
                "recommendation": "Check SharePoint admin permissions and try again",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )

# Keep all your existing helper functions unchanged
async def get_simple_mfa_status(user_id: str, headers: dict) -> dict:
    """
    Get simplified MFA status for a user - just boolean checks, no detailed method info
    """
    mfa_registered = False

    # Check if user has ANY MFA methods registered
    mfa_registered = await has_any_mfa_methods(user_id, headers)

    # Check Conditional Access coverage
    ca_covered = await check_admin_ca_coverage(user_id, headers)

    # Check Security Defaults
    security_defaults = await get_security_defaults_status(headers)

    # Determine overall MFA status
    has_mfa = mfa_registered or ca_covered or security_defaults

    return {
        "has_mfa": has_mfa,
        "mfa_registered": mfa_registered,
        "ca_covered": ca_covered,
        "security_defaults": security_defaults
    }

async def has_any_mfa_methods(user_id: str, headers: dict) -> bool:
    """
    Simple check if user has ANY MFA methods registered
    Returns True if any MFA method is found, False otherwise
    """
    mfa_endpoints = [
        f"{GRAPH_V1_URL}/users/{user_id}/authentication/microsoftAuthenticatorMethods",
        f"{GRAPH_V1_URL}/users/{user_id}/authentication/phoneMethods",
        f"{GRAPH_V1_URL}/users/{user_id}/authentication/fido2Methods"
    ]

    for endpoint in mfa_endpoints:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(endpoint, headers=headers, timeout=5.0)
                if resp.status_code == 200:
                    data = resp.json()
                    methods = data.get("value", [])
                    if methods and len(methods) > 0:
                        return True
        except Exception as e:
            logger.debug(f"Could not check endpoint {endpoint}: {str(e)}")
            continue

    return False

async def check_admin_ca_coverage(user_id: str, headers: dict) -> bool:
    """Check if admin user is covered by Conditional Access policies requiring MFA"""
    try:
        ca_policies_url = f"{GRAPH_BETA_URL}/identity/conditionalAccess/policies"
        ca_params = {"$filter": "state eq 'enabled'"}

        async with httpx.AsyncClient() as client:
            ca_resp = await client.get(ca_policies_url, headers=headers, params=ca_params, timeout=20.0)
            if ca_resp.status_code == 200:
                ca_data = ca_resp.json()
                ca_policies = ca_data.get("value", [])

                for policy in ca_policies:
                    # Check if policy applies to this user
                    conditions = policy.get("conditions", {})
                    users_condition = conditions.get("users", {})
                    include_users = users_condition.get("includeUsers", [])

                    if "All" in include_users or user_id in include_users:
                        # Check if policy requires MFA
                        grant_controls = policy.get("grantControls", {})
                        built_in_controls = grant_controls.get("builtInControls", [])

                        # Check for MFA requirements
                        if ("mfa" in built_in_controls or
                                "multiFactorAuthentication" in built_in_controls):
                            return True

                        # Check authentication strength
                        auth_strength = grant_controls.get("authenticationStrength", {})
                        if auth_strength and auth_strength.get("requirementsSatisfied") == "mfa":
                            return True

        return False
    except Exception as e:
        logger.warning(f"Failed to check CA policies for user {user_id}: {str(e)}")
        return False

async def get_security_defaults_status(headers: dict) -> bool:
    """Get Security Defaults status for the tenant"""
    try:
        security_defaults_url = f"{GRAPH_BETA_URL}/policies/identitySecurityDefaultsEnforcementPolicy"
        async with httpx.AsyncClient() as client:
            sd_resp = await client.get(security_defaults_url, headers=headers, timeout=20.0)
            if sd_resp.status_code == 200:
                sd_data = sd_resp.json()
                return sd_data.get("isEnabled", False)
    except Exception as e:
        logger.warning(f"Failed to get security defaults status: {str(e)}")
    return False

def determine_sharepoint_compliance_status(
        is_resharing_enabled: bool,
        sharing_capability: str,
        domain_restriction_mode: str,
        allowed_domains: list
) -> dict:
    """
    Determines SharePoint external resharing compliance status based on settings.
    """

    # Check for Not Measured conditions first
    if is_resharing_enabled is None or sharing_capability is None:
        return {
            "status": "Not Measured",
            "message": "SharePoint settings could not be determined",
            "recommendation": "Verify SharePoint admin permissions and tenant configuration"
        }

    # Check for Not Compliant conditions
    # Fixed: Handle both None and "none" (case-insensitive)
    no_domain_restrictions = (
            domain_restriction_mode is None or
            domain_restriction_mode == "" or
            domain_restriction_mode.lower() in ["none", "null"]
    )

    if is_resharing_enabled and no_domain_restrictions:
        return {
            "status": "Not Compliant",
            "message": "External sharing is enabled without restrictions",
            "recommendation": "Restrict external sharing to specific domains or disable resharing by external users"
        }

    if sharing_capability in ["Anyone", "AnonymousAndExternalUserSharing"]:
        return {
            "status": "Not Compliant",
            "message": "Sharing capability allows anonymous access",
            "recommendation": "Change sharing capability to limit external access and disable anonymous sharing"
        }

    # Check for Compliant conditions
    if not is_resharing_enabled:
        return {
            "status": "Compliant",
            "message": "External resharing by external users is disabled",
            "recommendation": "Maintain current secure settings to prevent external resharing"
        }

    if (is_resharing_enabled and
            domain_restriction_mode and
            domain_restriction_mode.lower() == "allowlist" and
            isinstance(allowed_domains, list) and
            len(allowed_domains) <= 5 and  # Strict domain control
            len(allowed_domains) > 0):
        return {
            "status": "Compliant",
            "message": "External sharing is enabled with strict domain restrictions",
            "recommendation": "Monitor allowed domains list and remove any unnecessary domains"
        }

    # Partially Compliant conditions
    if (is_resharing_enabled and
            domain_restriction_mode and
            domain_restriction_mode.lower() == "allowlist" and
            isinstance(allowed_domains, list) and
            len(allowed_domains) > 5):
        return {
            "status": "Partially Compliant",
            "message": "External sharing has domain restrictions but allows many domains",
            "recommendation": "Review and reduce the number of allowed domains to improve security"
        }

    if (is_resharing_enabled and
            domain_restriction_mode and
            domain_restriction_mode.lower() == "blocklist" and
            isinstance(allowed_domains, list)):
        return {
            "status": "Partially Compliant",
            "message": "External sharing uses block list instead of allow list",
            "recommendation": "Consider switching to allow list for better security control"
        }

    if (is_resharing_enabled and
            domain_restriction_mode and
            domain_restriction_mode.lower() == "allowlist" and
            len(allowed_domains) == 0):
        return {
            "status": "Partially Compliant",
            "message": "Domain allow list is configured but empty",
            "recommendation": "Add specific trusted domains to the allow list or disable external resharing"
        }

    # Default fallback
    return {
        "status": "Not Measured",
        "message": "Unable to determine compliance status from current settings",
        "recommendation": "Review SharePoint external sharing configuration manually"
    }


# Endpoint for Audit logs are enabled and retained properly(partially compliant - no endpoint for retained period )
@router.get("/ListUnifiedAuditingStatus", response_model=GraphApiResponse, summary="Check Unified Auditing Logs Status")
async def list_unified_auditing_status(clientId: Optional[str] = Query(None),org_id: Optional[int] = Query(None)):
    """
    Checks unified auditing logs status for compliance by verifying directory audit logs are enabled and active.
    Uses directory audits endpoint to confirm audit logging is working properly.
    """
    try:
        # Handle both clientId (old) and org_id (new) parameters
        if not clientId and not org_id:
            raise HTTPException(
                status_code=400,
                detail="Either clientId or org_id query parameter is required"
            )

        if clientId:
            client_id = clientId.strip()
        else:
            creds = await get_organization_credentials(org_id)
            if not creds:
                raise HTTPException(
                    status_code=404,
                    detail=f"No credentials found for org_id: {org_id}"
                )
            client_id = creds['client_id']
        token = await get_access_token(client_id)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        # Get directory audit logs with key fields for audit compliance check
        audit_logs_url = f"{GRAPH_V1_URL}/auditLogs/directoryAudits"
        params = {
            "$select": "id,category,result,activityDisplayName,activityDateTime,loggedByService",
            "$top": 10,
            "$orderby": "activityDateTime desc"
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(audit_logs_url, headers=headers, params=params, timeout=30.0)
            response.raise_for_status()
            audit_data = response.json()

        audit_logs = audit_data.get("value", [])

        # Determine compliance status
        compliance_info = determine_audit_compliance_status(audit_logs)

        # Build standardized response
        result_data = {
            "complianceStatus": compliance_info["status"],
            "statusMessage": compliance_info["message"],
            "recommendation": compliance_info["recommendation"],
            "complianceDetails": {
                "unifiedAuditingStatus": {
                    "auditLogsEnabled": len(audit_logs) > 0,
                    "totalRecentAuditLogs": len(audit_logs),
                    "mostRecentAuditActivity": audit_logs[0].get("activityDateTime", "") if audit_logs else None,
                    "auditLogEntries": audit_logs
                }
            },
            "reportGeneratedAt": datetime.now().isoformat() + "Z"
        }

        return GraphApiResponse(status_code=200, data=result_data)

    except httpx.HTTPStatusError as exc:
        logger.error(f"Graph API HTTP error: {exc.response.status_code} - {exc.response.text}")
        return GraphApiResponse(
            status_code=200,  # Return 200 but with Not Measured status
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to retrieve audit log information",
                "recommendation": "Check audit log permissions and Graph API access",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )
    except Exception as e:
        logger.error(f"Error checking unified auditing status: {str(e)}")
        return GraphApiResponse(
            status_code=200,  # Return 200 but with Not Measured status
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to determine audit compliance status",
                "recommendation": "Check system configuration and try again",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )


def determine_audit_compliance_status(audit_logs: list) -> dict:
    """
    Determines audit compliance status based on audit log data.
    """

    # Check if audit logs exist
    if not audit_logs or len(audit_logs) == 0:
        return {
            "status": "Not Compliant",
            "message": "No audit logs found - unified auditing may be disabled",
            "recommendation": "Enable unified auditing in Microsoft 365 Compliance Center and ensure proper permissions are configured"
        }

    # Get most recent activity
    most_recent_activity = audit_logs[0].get("activityDateTime", "")
    total_logs = len(audit_logs)

    if not most_recent_activity:
        return {
            "status": "Not Compliant",
            "message": "Audit logs found but no recent activity timestamps available",
            "recommendation": "Verify audit log configuration and ensure activity timestamps are being recorded"
        }

    # Parse the most recent activity date
    try:
        from datetime import datetime, timezone
        recent_date = datetime.fromisoformat(most_recent_activity.replace('Z', '+00:00'))
        current_date = datetime.now(timezone.utc)
        days_since_activity = (current_date - recent_date).days

        # Format the date for display (simple date format)
        activity_date_str = recent_date.strftime("%B %d, %Y")

    except Exception as e:
        logger.warning(f"Error parsing audit activity date: {str(e)}")
        return {
            "status": "Partially Compliant",
            "message": f"Audit logs are enabled with {total_logs} recent entries, but unable to verify activity timing",
            "recommendation": "Verify audit log retention settings and ensure logs are properly archived for compliance requirements"
        }

    # Determine status based on recent activity and limitations
    if days_since_activity <= 1:
        # Recent activity within 1 day - but can't verify retention period
        return {
            "status": "Partially Compliant",
            "message": f"Audit logs are enabled with {total_logs} recent entries, last activity on {activity_date_str}",
            "recommendation": "Verify audit log retention settings and ensure logs are properly archived for compliance requirements. Retention period verification not available via API."
        }
    elif days_since_activity <= 7:
        # Activity within a week
        return {
            "status": "Partially Compliant",
            "message": f"Audit logs are enabled with {total_logs} recent entries, last activity on {activity_date_str} ({days_since_activity} days ago)",
            "recommendation": "Monitor audit activity more closely and verify audit log retention settings for compliance requirements"
        }
    else:
        # Old activity - potential compliance issue
        return {
            "status": "Not Compliant",
            "message": f"Audit logs are enabled but last activity was on {activity_date_str} ({days_since_activity} days ago)",
            "recommendation": "Investigate why audit activity is not recent and ensure unified auditing is properly configured and active"
        }


# Endpoint for Block High Risk Users - Policy check
@router.get("/ListHighRiskUsersPolicies", response_model=GraphApiResponse,
            summary="Check Block High Risk Users Policies")
async def list_high_risk_users_signin_policies(clientId: Optional[str] = Query(None),org_id: Optional[int] = Query(None)):
    """
    Checks conditional access policies and security defaults for high risk users blocking.
    Returns compliance status for high-risk user protection policies.
    """
    try:
        # Handle both clientId (old) and org_id (new) parameters
        if not clientId and not org_id:
            raise HTTPException(
                status_code=400,
                detail="Either clientId or org_id query parameter is required"
            )

        if clientId:
            client_id = clientId.strip()
        else:
            creds = await get_organization_credentials(org_id)
            if not creds:
                raise HTTPException(
                    status_code=404,
                    detail=f"No credentials found for org_id: {org_id}"
                )
            client_id = creds['client_id']
        token = await get_access_token(client_id)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        # Step 1: Get Conditional Access policies with key fields
        ca_policies_url = f"{GRAPH_V1_URL}/identity/conditionalAccess/policies"
        ca_params = {
            "$select": "id,displayName,state,conditions,grantControls"
        }

        async with httpx.AsyncClient() as client:
            ca_response = await client.get(ca_policies_url, headers=headers, params=ca_params, timeout=30.0)
            ca_response.raise_for_status()
            ca_data = ca_response.json()

        ca_policies = ca_data.get("value", [])

        # Step 2: Get Security Defaults policy
        security_defaults_url = f"{GRAPH_BETA_URL}/policies/identitySecurityDefaultsEnforcementPolicy"
        sd_params = {
            "$select": "id,displayName,description,isEnabled"
        }

        async with httpx.AsyncClient() as client:
            sd_response = await client.get(security_defaults_url, headers=headers, params=sd_params, timeout=30.0)
            sd_response.raise_for_status()
            sd_data = sd_response.json()

        # Determine compliance status
        compliance_info = determine_high_risk_users_compliance_status(ca_policies, sd_data)

        # Build standardized response
        result_data = {
            "complianceStatus": compliance_info["status"],
            "statusMessage": compliance_info["message"],
            "recommendation": compliance_info["recommendation"],
            "complianceDetails": {
                "conditionalAccessPolicies": ca_policies,
                "identitySecurityDefaultsEnforcementPolicy": {
                    "id": sd_data.get("id", ""),
                    "displayName": sd_data.get("displayName", ""),
                    "description": sd_data.get("description", ""),
                    "isEnabled": sd_data.get("isEnabled", False)
                },
                "highRiskUserPolicies": extract_high_risk_user_policies(ca_policies)
            },
            "reportGeneratedAt": datetime.now().isoformat() + "Z"
        }

        return GraphApiResponse(status_code=200, data=result_data)

    except httpx.HTTPStatusError as exc:
        logger.error(f"Graph API HTTP error: {exc.response.status_code} - {exc.response.text}")
        return GraphApiResponse(
            status_code=200,  # Return 200 but with Not Measured status
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to retrieve high-risk user policy information",
                "recommendation": "Check Conditional Access permissions and Graph API access",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )
    except Exception as e:
        logger.error(f"Error checking high risk users policies: {str(e)}")
        return GraphApiResponse(
            status_code=200,  # Return 200 but with Not Measured status
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to determine high-risk user policy compliance status",
                "recommendation": "Check system configuration and try again",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )


def determine_high_risk_users_compliance_status(ca_policies: list, security_defaults_data: dict) -> dict:
    """
    Determines high-risk users compliance status based on CA policies and Security Defaults.
    Focuses specifically on blocking high-risk users.
    """

    # Extract enabled CA policies
    enabled_ca_policies = [policy for policy in ca_policies if policy.get("state", "").lower() == "enabled"]

    # Check for high-risk user specific policies
    high_risk_user_policies = []

    for policy in enabled_ca_policies:
        conditions = policy.get("conditions", {})
        user_risk = conditions.get("userRisk", {})

        # Check if policy targets high-risk users
        if user_risk and "high" in user_risk.get("levels", []):
            grant_controls = policy.get("grantControls", {})
            built_in_controls = grant_controls.get("builtInControls", [])

            # Check if policy blocks access
            if "block" in built_in_controls or "blockAccess" in built_in_controls:
                high_risk_user_policies.append({
                    "name": policy.get("displayName", "Unknown Policy"),
                    "action": "blocks high-risk users"
                })
            # Check if policy requires additional authentication
            elif any(control in built_in_controls for control in ["mfa", "multiFactorAuthentication"]):
                high_risk_user_policies.append({
                    "name": policy.get("displayName", "Unknown Policy"),
                    "action": "requires MFA for high-risk users"
                })

    # Check Security Defaults status
    security_defaults_enabled = security_defaults_data.get("isEnabled", False)

    # Determine compliance status
    if high_risk_user_policies:
        # Has specific high-risk user policies
        policy_names = [p["name"] for p in high_risk_user_policies]
        return {
            "status": "Compliant",
            "message": f"High-risk user policies are configured: {', '.join(policy_names)}",
            "recommendation": "Continue monitoring high-risk user policies and review their effectiveness regularly"
        }
    elif security_defaults_enabled:
        # Security Defaults enabled - provides some protection but not specific high-risk blocking
        return {
            "status": "Partially Compliant",
            "message": "Security Defaults enabled provides basic protection, but no specific high-risk user blocking policy",
            "recommendation": "Implement Conditional Access policy to block or require additional steps for high-risk users"
        }
    elif enabled_ca_policies:
        # Has CA policies but none target high-risk users specifically
        return {
            "status": "Not Compliant",
            "message": f"Found {len(enabled_ca_policies)} Conditional Access policies but none specifically target high-risk users",
            "recommendation": "Create a Conditional Access policy to block or require additional authentication for high-risk users"
        }
    else:
        # No policies at all
        return {
            "status": "Not Compliant",
            "message": "No policy in place to block high-risk user accounts",
            "recommendation": "Implement Conditional Access policy to block or require additional steps for high-risk users"
        }


def extract_high_risk_user_policies(ca_policies: list) -> list:
    """
    Extract only policies that specifically target high-risk users.
    """
    high_risk_policies = []

    for policy in ca_policies:
        if policy.get("state", "").lower() != "enabled":
            continue

        conditions = policy.get("conditions", {})
        user_risk = conditions.get("userRisk", {})

        # Check if policy targets high-risk users
        if user_risk and "high" in user_risk.get("levels", []):
            grant_controls = policy.get("grantControls", {})
            built_in_controls = grant_controls.get("builtInControls", [])

            high_risk_policies.append({
                "id": policy.get("id", ""),
                "displayName": policy.get("displayName", ""),
                "state": policy.get("state", ""),
                "userRiskLevels": user_risk.get("levels", []),
                "controls": built_in_controls
            })
    return high_risk_policies


# Endpoint for Block risky sign-ins policies
@router.get("/ListRiskySignInPolicies", response_model=GraphApiResponse, summary="Check Block Risky Sign-In Policies")
async def list_risky_signin_policies(clientId: Optional[str] = Query(None),org_id: Optional[int] = Query(None)):
    """
    Checks conditional access policies and security defaults for risky sign-ins blocking.
    Returns compliance status for sign-in risk protection policies.
    """
    try:
        # Handle both clientId (old) and org_id (new) parameters
        if not clientId and not org_id:
            raise HTTPException(
                status_code=400,
                detail="Either clientId or org_id query parameter is required"
            )

        if clientId:
            client_id = clientId.strip()
        else:
            creds = await get_organization_credentials(org_id)
            if not creds:
                raise HTTPException(
                    status_code=404,
                    detail=f"No credentials found for org_id: {org_id}"
                )
            client_id = creds['client_id']
        token = await get_access_token(client_id)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        # Step 1: Get Conditional Access policies with key fields
        ca_policies_url = f"{GRAPH_V1_URL}/identity/conditionalAccess/policies"
        ca_params = {
            "$select": "id,displayName,state,conditions,grantControls"
        }

        async with httpx.AsyncClient() as client:
            ca_response = await client.get(ca_policies_url, headers=headers, params=ca_params, timeout=30.0)
            ca_response.raise_for_status()
            ca_data = ca_response.json()

        ca_policies = ca_data.get("value", [])

        # Step 2: Get Security Defaults policy
        security_defaults_url = f"{GRAPH_BETA_URL}/policies/identitySecurityDefaultsEnforcementPolicy"
        sd_params = {
            "$select": "id,displayName,description,isEnabled"
        }

        async with httpx.AsyncClient() as client:
            sd_response = await client.get(security_defaults_url, headers=headers, params=sd_params, timeout=30.0)
            sd_response.raise_for_status()
            sd_data = sd_response.json()

        # Determine compliance status
        compliance_info = determine_risky_signin_compliance_status(ca_policies, sd_data)

        # Build standardized response
        result_data = {
            "complianceStatus": compliance_info["status"],
            "statusMessage": compliance_info["message"],
            "recommendation": compliance_info["recommendation"],
            "complianceDetails": {
                "conditionalAccessPolicies": ca_policies,
                "identitySecurityDefaultsEnforcementPolicy": {
                    "id": sd_data.get("id", ""),
                    "displayName": sd_data.get("displayName", ""),
                    "description": sd_data.get("description", ""),
                    "isEnabled": sd_data.get("isEnabled", False)
                },
                "riskySignInPolicies": extract_risky_signin_policies(ca_policies)
            },
            "reportGeneratedAt": datetime.now().isoformat() + "Z"
        }

        return GraphApiResponse(status_code=200, data=result_data)

    except httpx.HTTPStatusError as exc:
        logger.error(f"Graph API HTTP error: {exc.response.status_code} - {exc.response.text}")
        return GraphApiResponse(
            status_code=200,  # Return 200 but with Not Measured status
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to retrieve risky sign-in policy information",
                "recommendation": "Check Conditional Access permissions and Graph API access",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )
    except Exception as e:
        logger.error(f"Error checking risky sign-in policies: {str(e)}")
        return GraphApiResponse(
            status_code=200,  # Return 200 but with Not Measured status
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to determine risky sign-in policy compliance status",
                "recommendation": "Check system configuration and try again",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )


def determine_risky_signin_compliance_status(ca_policies: list, security_defaults_data: dict) -> dict:
    """
    Determines risky sign-ins compliance status based on CA policies and Security Defaults.
    Focuses specifically on blocking risky sign-ins based on sign-in risk levels.
    """

    # Extract enabled CA policies
    enabled_ca_policies = [policy for policy in ca_policies if policy.get("state", "").lower() == "enabled"]

    # Check for sign-in risk specific policies
    signin_risk_policies = []
    has_high_risk_protection = False
    has_medium_risk_protection = False

    for policy in enabled_ca_policies:
        conditions = policy.get("conditions", {})
        signin_risk = conditions.get("signInRisk", {})

        # Check if policy targets risky sign-ins
        if signin_risk:
            risk_levels = signin_risk.get("levels", [])
            grant_controls = policy.get("grantControls", {})
            built_in_controls = grant_controls.get("builtInControls", [])

            # Check what risk levels are covered
            if "high" in risk_levels:
                has_high_risk_protection = True
            if "medium" in risk_levels:
                has_medium_risk_protection = True

            # Check if policy blocks access or requires MFA
            if any(control in built_in_controls for control in
                   ["block", "blockAccess", "mfa", "multiFactorAuthentication"]):
                action = "blocks access" if any(
                    control in built_in_controls for control in ["block", "blockAccess"]) else "requires MFA"
                signin_risk_policies.append({
                    "name": policy.get("displayName", "Unknown Policy"),
                    "risk_levels": risk_levels,
                    "action": f"{action} for {', '.join(risk_levels)} risk sign-ins"
                })

    # Check Security Defaults status
    security_defaults_enabled = security_defaults_data.get("isEnabled", False)

    # Determine compliance status
    if signin_risk_policies:
        if has_high_risk_protection and has_medium_risk_protection:
            # Has both high and medium risk protection
            policy_names = [p["name"] for p in signin_risk_policies]
            return {
                "status": "Compliant",
                "message": f"Sign-in risk policies cover both high and medium risk levels: {', '.join(policy_names)}",
                "recommendation": "Continue monitoring risky sign-in policies and review their effectiveness regularly"
            }
        elif has_high_risk_protection and not has_medium_risk_protection:
            # Only high-risk protection - matches your UI example
            return {
                "status": "Partially Compliant",
                "message": "Only high-risk sign-ins are blocked, medium not addressed",
                "recommendation": "Extend policy to also handle medium-risk sign-ins with step-up authentication"
            }
        elif has_medium_risk_protection and not has_high_risk_protection:
            # Only medium-risk protection (unusual but possible)
            return {
                "status": "Partially Compliant",
                "message": "Only medium-risk sign-ins are addressed, high-risk not specifically targeted",
                "recommendation": "Extend policy to also block high-risk sign-ins for complete protection"
            }
        else:
            # Has policies but neither high nor medium (low risk only)
            return {
                "status": "Partially Compliant",
                "message": "Sign-in risk policies exist but don't target high or medium risk levels",
                "recommendation": "Configure policies to block or require additional authentication for high and medium risk sign-ins"
            }
    elif security_defaults_enabled:
        # Security Defaults enabled - provides some protection but not specific sign-in risk blocking
        return {
            "status": "Partially Compliant",
            "message": "Security Defaults enabled provides basic protection, but no specific risky sign-in blocking policy",
            "recommendation": "Implement Conditional Access policy to block or require additional steps for risky sign-ins"
        }
    elif enabled_ca_policies:
        # Has CA policies but none target sign-in risk
        return {
            "status": "Not Compliant",
            "message": f"Found {len(enabled_ca_policies)} Conditional Access policies but none specifically target risky sign-ins",
            "recommendation": "Create a Conditional Access policy to block or require additional authentication for risky sign-ins"
        }
    else:
        # No policies at all
        return {
            "status": "Not Compliant",
            "message": "No policy in place to block risky sign-ins",
            "recommendation": "Implement Conditional Access policy to block or require additional steps for risky sign-ins"
        }
def extract_risky_signin_policies(ca_policies: list) -> list:
    """
    Extract only policies that specifically target risky sign-ins.
    """
    risky_signin_policies = []

    for policy in ca_policies:
        if policy.get("state", "").lower() != "enabled":
            continue

        conditions = policy.get("conditions", {})
        signin_risk = conditions.get("signInRisk", {})

        # Check if policy targets risky sign-ins
        if signin_risk:
            risk_levels = signin_risk.get("levels", [])
            grant_controls = policy.get("grantControls", {})
            built_in_controls = grant_controls.get("builtInControls", [])

            risky_signin_policies.append({
                "id": policy.get("id", ""),
                "displayName": policy.get("displayName", ""),
                "state": policy.get("state", ""),
                "signInRiskLevels": risk_levels,
                "controls": built_in_controls
            })

    return risky_signin_policies

# Endpoint for Block Sign-in on Shared Mailboxes
# @router.get("/ListSharedMailboxSignInStatus", response_model=GraphApiResponse,
#             summary="Check Block Sign-in on Shared Mailboxes")
# async def list_shared_mailbox_signin_status(clientId: Optional[str] = Query(None), org_id: Optional[int] = Query(None)):
#     """
#     Checks shared mailboxes and their sign-in status using Graph API.
#     Returns compliance status for shared mailbox sign-in blocking.
#
#     """
#     try:
#         # Handle both clientId (old) and org_id (new) parameters
#         if not clientId and not org_id:
#             raise HTTPException(
#                 status_code=400,
#                 detail="Either clientId or org_id query parameter is required"
#             )
#
#         if clientId:
#             client_id = clientId.strip()
#         else:
#             creds = await get_organization_credentials(org_id)
#             if not creds:
#                 raise HTTPException(
#                     status_code=404,
#                     detail=f"No credentials found for org_id: {org_id}"
#                 )
#             client_id = creds['client_id']
#
#         token = await get_access_token(client_id)
#         headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
#
#         # Step 1: Get all users with basic info and licenses
#         users_url = f"{GRAPH_BETA_URL}/users"
#         users_params = {
#             "$select": "id,userPrincipalName,accountEnabled,assignedLicenses,displayName",
#             "$top": 999
#         }
#
#         async with httpx.AsyncClient() as client:
#             users_response = await client.get(users_url, headers=headers, params=users_params, timeout=30.0)
#             users_response.raise_for_status()
#             users_data = users_response.json()
#
#         users = users_data.get("value", [])
#
#         # --- Helper function for concurrent fetch (like MFA function) ---
#         async def fetch_mailbox_info(user):
#             """Fetch mailbox settings for a single user to identify shared mailboxes"""
#             user_id = user.get("id", "")
#             upn = user.get("userPrincipalName", "")
#             account_enabled = user.get("accountEnabled", False)
#             assigned_licenses = user.get("assignedLicenses", [])
#             display_name = user.get("displayName", "")
#
#             # Only check users without licenses (potential shared mailboxes)
#             has_no_licenses = len(assigned_licenses) == 0
#
#             if not has_no_licenses:
#                 return None  # Skip users with licenses
#
#             try:
#                 mailbox_url = f"{GRAPH_BETA_URL}/users/{user_id}/mailboxSettings"
#
#                 async with httpx.AsyncClient() as client:
#                     mailbox_response = await client.get(mailbox_url, headers=headers, timeout=10.0)
#
#                     # If mailbox settings exist, this is likely a mailbox user
#                     if mailbox_response.status_code == 200:
#                         mailbox_data = mailbox_response.json()
#
#                         # This user has a mailbox and no licenses = likely shared mailbox
#                         return {
#                             "id": user_id,
#                             "userPrincipalName": upn,
#                             "displayName": display_name,
#                             "accountEnabled": account_enabled,
#                             "assignedLicenses": assigned_licenses,
#                             "mailboxSettings": mailbox_data,
#                             "signInStatus": "enabled" if account_enabled else "disabled"
#                         }
#
#             except Exception as e:
#                 # If mailbox settings call fails, skip this user
#                 logger.warning(f"Failed to get mailbox settings for user {upn}: {str(e)}")
#
#             return None
#
#         # Step 2: ✨ Run ALL mailbox checks concurrently (OPTIMIZED!)
#         logger.info(f"Checking {len(users)} users for shared mailboxes concurrently...")
#         mailbox_results = await asyncio.gather(
#             *(fetch_mailbox_info(user) for user in users)
#         )
#
#         # Step 3: Filter out None values (users that aren't shared mailboxes)
#         shared_mailboxes = [mb for mb in mailbox_results if mb is not None]
#         logger.info(f"Found {len(shared_mailboxes)} shared mailboxes")
#
#         # Determine compliance status
#         compliance_info = determine_shared_mailbox_compliance_status(shared_mailboxes)
#
#         # Build standardized response
#         result_data = {
#             "complianceStatus": compliance_info["status"],
#             "statusMessage": compliance_info["message"],
#             "recommendation": compliance_info["recommendation"],
#             "complianceDetails": {
#                 "sharedMailboxes": shared_mailboxes,
#                 "summary": {
#                     "totalSharedMailboxes": len(shared_mailboxes),
#                     "signInDisabled": len([mb for mb in shared_mailboxes if not mb["accountEnabled"]]),
#                     "signInEnabled": len([mb for mb in shared_mailboxes if mb["accountEnabled"]])
#                 }
#             },
#             "reportGeneratedAt": datetime.now().isoformat() + "Z"
#         }
#
#         return GraphApiResponse(status_code=200, data=result_data)
#
#     except httpx.HTTPStatusError as exc:
#         logger.error(f"Graph API HTTP error: {exc.response.status_code} - {exc.response.text}")
#         return GraphApiResponse(
#             status_code=200,  # Return 200 but with Not Measured status
#             data={
#                 "complianceStatus": "Not Measured",
#                 "statusMessage": "Unable to retrieve shared mailbox information",
#                 "recommendation": "Check Graph API permissions and user access",
#                 "complianceDetails": None,
#                 "reportGeneratedAt": datetime.now().isoformat() + "Z"
#             }
#         )
#     except Exception as e:
#         logger.error(f"Error checking shared mailbox sign-in status: {str(e)}")
#         return GraphApiResponse(
#             status_code=200,  # Return 200 but with Not Measured status
#             data={
#                 "complianceStatus": "Not Measured",
#                 "statusMessage": "Unable to determine shared mailbox sign-in compliance status",
#                 "recommendation": "Check system configuration and try again",
#                 "complianceDetails": None,
#                 "reportGeneratedAt": datetime.now().isoformat() + "Z"
#             }
#         )
#
#
# def determine_shared_mailbox_compliance_status(shared_mailboxes: list) -> dict:
#     """
#     Determines shared mailbox compliance status based on sign-in settings.
#     """
#
#     total_mailboxes = len(shared_mailboxes)
#
#     # If no shared mailboxes found
#     if total_mailboxes == 0:
#         return {
#             "status": "Not Measured",
#             "message": "No shared mailboxes found to evaluate sign-in compliance",
#             "recommendation": "If you have shared mailboxes, ensure they are properly configured and accessible via Graph API"
#         }
#
#     # Count mailboxes with sign-in enabled/disabled
#     signin_disabled_count = len([mb for mb in shared_mailboxes if not mb["accountEnabled"]])
#     signin_enabled_count = len([mb for mb in shared_mailboxes if mb["accountEnabled"]])
#
#     # Determine compliance status
#     if signin_disabled_count == total_mailboxes:
#         # All shared mailboxes have sign-in disabled - Compliant
#         return {
#             "status": "Compliant",
#             "message": "Direct sign-in to shared mailboxes is disabled",
#             "recommendation": "Current status is good. Continue to monitor for policy changes"
#         }
#     elif signin_disabled_count > 0 and signin_enabled_count > 0:
#         # Mixed state - some disabled, some enabled
#         return {
#             "status": "Partially Compliant",
#             "message": f"{signin_disabled_count} of {total_mailboxes} shared mailboxes have sign-in disabled",
#             "recommendation": f"Disable direct sign-in for the remaining {signin_enabled_count} shared mailboxes to improve security"
#         }
#     else:
#         # All shared mailboxes have sign-in enabled - Not Compliant
#         return {
#             "status": "Not Compliant",
#             "message": f"All {total_mailboxes} shared mailboxes have direct sign-in enabled",
#             "recommendation": "Disable direct sign-in access for all shared mailboxes to prevent unauthorized access"
#         }


# Endpoint for Entra ID Guest User Access Permissions
@router.get("/ListGuestUserAccessPermissions", response_model=GraphApiResponse,
            summary="Check Entra ID Guest User Access Permissions")
async def list_guest_user_access_permissions(clientId: Optional[str] = Query(None),org_id: Optional[int] = Query(None)):
    """
    Checks Entra ID guest user access permissions for all guest users in the tenant.
    Returns compliance status for guest user access restrictions.
    """
    try:
        # Handle both clientId (old) and org_id (new) parameters
        if not clientId and not org_id:
            raise HTTPException(
                status_code=400,
                detail="Either clientId or org_id query parameter is required"
            )

        if clientId:
            client_id = clientId.strip()
        else:
            creds = await get_organization_credentials(org_id)
            if not creds:
                raise HTTPException(
                    status_code=404,
                    detail=f"No credentials found for org_id: {org_id}"
                )
            client_id = creds['client_id']
        token = await get_access_token(client_id)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        # Step 1: Get authorization policy
        auth_policy_url = f"{GRAPH_V1_URL}/policies/authorizationPolicy"

        async with httpx.AsyncClient() as client:
            auth_response = await client.get(auth_policy_url, headers=headers, timeout=30.0)
            auth_response.raise_for_status()
            auth_data = auth_response.json()

        # Step 2: Get all guest users
        guest_users_url = f"{GRAPH_V1_URL}/users"
        guest_params = {
            "$filter": "userType eq 'Guest'",
            "$select": "id,userPrincipalName,displayName,accountEnabled,userType,externalUserState"
        }

        async with httpx.AsyncClient() as client:
            guests_response = await client.get(guest_users_url, headers=headers, params=guest_params, timeout=30.0)
            guests_response.raise_for_status()
            guests_data = guests_response.json()

        guest_users = guests_data.get("value", [])
        guest_permissions_list = []

        # Step 3: For each guest user, get their role assignments and permissions
        for guest_user in guest_users:
            guest_id = guest_user.get("id", "")
            guest_upn = guest_user.get("userPrincipalName", "")

            # Get role assignments for this specific guest user
            role_assignments_url = f"{GRAPH_V1_URL}/roleManagement/directory/roleAssignments"
            role_params = {"$filter": f"principalId eq '{guest_id}'", "$expand": "roleDefinition"}

            try:
                async with httpx.AsyncClient() as client:
                    role_assignments_response = await client.get(role_assignments_url, headers=headers,
                                                                 params=role_params, timeout=10.0)

                    if role_assignments_response.status_code == 200:
                        role_assignments_data = role_assignments_response.json()
                        role_assignments = role_assignments_data.get("value", [])
                    else:
                        role_assignments = []

            except Exception as e:
                logger.warning(f"Failed to get role assignments for guest {guest_upn}: {str(e)}")
                role_assignments = []

            # Get default guest user role definition
            default_guest_role_id = auth_data.get("guestUserRoleId", "")
            default_guest_role = None

            if default_guest_role_id:
                try:
                    role_def_url = f"{GRAPH_V1_URL}/roleManagement/directory/roleDefinitions/{default_guest_role_id}"

                    async with httpx.AsyncClient() as client:
                        role_def_response = await client.get(role_def_url, headers=headers, timeout=10.0)

                        if role_def_response.status_code == 200:
                            default_guest_role = role_def_response.json()

                except Exception as e:
                    logger.warning(f"Failed to get default guest role definition: {str(e)}")

            # Analyze permissions for this guest user
            all_permissions = []
            assigned_roles = []

            # Add permissions from assigned roles
            for assignment in role_assignments:
                role_definition = assignment.get("roleDefinition", {})
                if role_definition:
                    assigned_roles.append({
                        "roleId": role_definition.get("id", ""),
                        "displayName": role_definition.get("displayName", ""),
                        "description": role_definition.get("description", ""),
                        "assignmentId": assignment.get("id", "")
                    })

                    # Extract permissions from this role
                    role_permissions = role_definition.get("rolePermissions", [])
                    for permission in role_permissions:
                        actions = permission.get("allowedResourceActions", [])
                        condition = permission.get("condition", None)

                        for action in actions:
                            all_permissions.append({
                                "action": action,
                                "condition": condition,
                                "source": role_definition.get("displayName", "Unknown Role")
                            })

            # Add default guest role permissions if no specific roles assigned
            if not assigned_roles and default_guest_role:
                default_permissions = default_guest_role.get("rolePermissions", [])
                for permission in default_permissions:
                    actions = permission.get("allowedResourceActions", [])
                    condition = permission.get("condition", None)

                    for action in actions:
                        all_permissions.append({
                            "action": action,
                            "condition": condition,
                            "source": "Default Guest Role"
                        })

            # Analyze capabilities
            can_invite_guests = any("inviteGuest" in perm["action"] for perm in all_permissions)
            can_read_users = any("users/standard/read" in perm["action"] for perm in all_permissions)
            can_read_groups = any("groups/standard" in perm["action"] for perm in all_permissions)

            # Build guest user permission info
            guest_permission_info = {
                "guestUser": {
                    "id": guest_id,
                    "userPrincipalName": guest_upn,
                    "displayName": guest_user.get("displayName", ""),
                    "accountEnabled": guest_user.get("accountEnabled", False),
                    "userType": guest_user.get("userType", ""),
                    "externalUserState": guest_user.get("externalUserState", "")
                },
                "assignedRoles": assigned_roles,
                "defaultGuestRole": default_guest_role.get("displayName", "") if default_guest_role else "",
                "permissions": all_permissions,
                "capabilities": {
                    "canInviteOtherGuests": can_invite_guests,
                    "canReadLimitedUserInfo": can_read_users,
                    "canReadLimitedGroupInfo": can_read_groups,
                    "totalPermissions": len(all_permissions),
                    "hasCustomRoles": len(assigned_roles) > 0
                }
            }

            guest_permissions_list.append(guest_permission_info)

        # Determine compliance status
        compliance_info = determine_guest_user_compliance_status(auth_data, guest_permissions_list)

        # Build standardized response
        result_data = {
            "complianceStatus": compliance_info["status"],
            "statusMessage": compliance_info["message"],
            "recommendation": compliance_info["recommendation"],
            "complianceDetails": {
                "authorizationPolicy": {
                    "id": auth_data.get("id", ""),
                    "allowInvitesFrom": auth_data.get("allowInvitesFrom", ""),
                    "allowEmailVerifiedUsersToJoinOrganization": auth_data.get(
                        "allowEmailVerifiedUsersToJoinOrganization", False),
                    "allowUserConsentForRiskyApps": auth_data.get("allowUserConsentForRiskyApps"),
                    "guestUserRoleId": auth_data.get("guestUserRoleId", ""),
                    "permissionGrantPoliciesAssigned": auth_data.get("defaultUserRolePermissions", {}).get(
                        "permissionGrantPoliciesAssigned", []),
                    "blockMsolPowerShell": auth_data.get("blockMsolPowerShell", False),
                    "allowedToCreateApps": auth_data.get("defaultUserRolePermissions", {}).get("allowedToCreateApps",
                                                                                               False),
                    "allowedToCreateSecurityGroups": auth_data.get("defaultUserRolePermissions", {}).get(
                        "allowedToCreateSecurityGroups", False),
                    "allowedToCreateTenants": auth_data.get("defaultUserRolePermissions", {}).get(
                        "allowedToCreateTenants", False),
                    "allowedToReadBitlockerKeysForOwnedDevice": auth_data.get("defaultUserRolePermissions", {}).get(
                        "allowedToReadBitlockerKeysForOwnedDevice", False),
                    "allowedToReadOtherUsers": auth_data.get("defaultUserRolePermissions", {}).get(
                        "allowedToReadOtherUsers", False)
                },
                "guestUsers": guest_permissions_list,
                "summary": {
                    "totalGuestUsers": len(guest_users),
                    "guestsWithCustomRoles": len(
                        [g for g in guest_permissions_list if g["capabilities"]["hasCustomRoles"]]),
                    "guestsWithInviteCapability": len(
                        [g for g in guest_permissions_list if g["capabilities"]["canInviteOtherGuests"]])
                }
            },
            "reportGeneratedAt": datetime.now().isoformat() + "Z"
        }

        return GraphApiResponse(status_code=200, data=result_data)

    except httpx.HTTPStatusError as exc:
        logger.error(f"Graph API HTTP error: {exc.response.status_code} - {exc.response.text}")
        return GraphApiResponse(
            status_code=200,  # Return 200 but with Not Measured status
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to retrieve guest user access permission information",
                "recommendation": "Check Graph API permissions and authorization policy access",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )
    except Exception as e:
        logger.error(f"Error checking guest user access permissions: {str(e)}")
        return GraphApiResponse(
            status_code=200,  # Return 200 but with Not Measured status
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to determine guest user access compliance status",
                "recommendation": "Check system configuration and try again",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )


def determine_guest_user_compliance_status(auth_data: dict, guest_permissions_list: list) -> dict:
    """
    Determines guest user access compliance status based on authorization policies and guest permissions.
    """

    # Extract key policy settings
    allow_invites_from = auth_data.get("allowInvitesFrom", "")
    allow_email_verified_join = auth_data.get("allowEmailVerifiedUsersToJoinOrganization", False)
    total_guests = len(guest_permissions_list)
    guests_with_custom_roles = len([g for g in guest_permissions_list if g["capabilities"]["hasCustomRoles"]])
    guests_with_invite_capability = len(
        [g for g in guest_permissions_list if g["capabilities"]["canInviteOtherGuests"]])

    # Determine compliance based on policy restrictiveness
    policy_issues = []

    # Check invitation policy
    if allow_invites_from == "everyone":
        policy_issues.append("anyone can invite guest users")

    # Check email verified users policy
    if allow_email_verified_join:
        policy_issues.append("email verified users can self-join organization")

    # Check guest user permissions if guests exist
    permission_issues = []
    if total_guests > 0:
        if guests_with_custom_roles > 0:
            permission_issues.append(f"{guests_with_custom_roles} guests have custom roles")
        if guests_with_invite_capability > 0:
            permission_issues.append(f"{guests_with_invite_capability} guests can invite other users")

    # Determine compliance status
    if not policy_issues and not permission_issues:
        # No policy or permission issues
        if total_guests == 0:
            return {
                "status": "Compliant",
                "message": "Guest access policies are restrictive and no guest users currently exist",
                "recommendation": "Continue monitoring guest access policies and review any new guest user additions"
            }
        else:
            return {
                "status": "Compliant",
                "message": f"Guest access policies are restrictive and {total_guests} guest users have appropriate permissions",
                "recommendation": "Continue monitoring guest user permissions and review periodically"
            }
    elif policy_issues and not permission_issues:
        # Policy issues but guest permissions are ok
        if total_guests == 0:
            return {
                "status": "Partially Compliant",
                "message": f"Guest access restrictions in place but requires review: {', '.join(policy_issues)}",
                "recommendation": "Review current guest user permissions and implement least privilege access"
            }
        else:
            return {
                "status": "Partially Compliant",
                "message": f"Guest permissions are appropriate but policy needs review: {', '.join(policy_issues)}",
                "recommendation": "Restrict guest invitation policies and review guest access settings"
            }
    elif not policy_issues and permission_issues:
        # Policies are ok but guest permissions are concerning
        return {
            "status": "Partially Compliant",
            "message": f"Invitation policies are restrictive but guest permissions need review: {', '.join(permission_issues)}",
            "recommendation": "Review and reduce guest user permissions to implement least privilege access"
        }
    else:
        # Both policy and permission issues
        all_issues = policy_issues + permission_issues
        return {
            "status": "Not Compliant",
            "message": f"Multiple guest access concerns identified: {', '.join(all_issues)}",
            "recommendation": "Implement restrictive guest invitation policies and review all guest user permissions immediately"
        }


# Endpoint for SharePoint site creation by standard users
@router.get("/ListSharePointSiteCreationStatus", response_model=GraphApiResponse,
            summary="Check SharePoint Site Creation by Standard Users")
async def list_sharepoint_site_creation_status(clientId: Optional[str] = Query(None),org_id: Optional[int] = Query(None)):
    """
    Checks SharePoint site creation settings to determine if standard users can create sites without approval.
    Returns compliance status for site creation governance.
    """
    try:
        # Handle both clientId (old) and org_id (new) parameters
        if not clientId and not org_id:
            raise HTTPException(
                status_code=400,
                detail="Either clientId or org_id query parameter is required"
            )

        if clientId:
            client_id = clientId.strip()
        else:
            creds = await get_organization_credentials(org_id)
            if not creds:
                raise HTTPException(
                    status_code=404,
                    detail=f"No credentials found for org_id: {org_id}"
                )
            client_id = creds['client_id']
        token = await get_access_token(client_id)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        # Get SharePoint settings with site creation specific fields
        sharepoint_settings_url = f"{GRAPH_V1_URL}/admin/sharepoint/settings"
        params = {
            "$select": "siteCreationDefaultManagedPath,siteCreationDefaultStorageLimitInMB,isSiteCreationEnabled"
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(sharepoint_settings_url, headers=headers, params=params, timeout=30.0)
            response.raise_for_status()
            settings_data = response.json()

        # Determine compliance status
        compliance_info = determine_sharepoint_site_creation_compliance_status(settings_data)

        # Build standardized response
        result_data = {
            "complianceStatus": compliance_info["status"],
            "statusMessage": compliance_info["message"],
            "recommendation": compliance_info["recommendation"],
            "complianceDetails": {
                "sharepointSiteCreationSettings": {
                    "siteCreationDefaultManagedPath": settings_data.get("siteCreationDefaultManagedPath", ""),
                    "siteCreationDefaultStorageLimitInMB": settings_data.get("siteCreationDefaultStorageLimitInMB", 0),
                    "isSiteCreationEnabled": settings_data.get("isSiteCreationEnabled", False)
                }
            },
            "reportGeneratedAt": datetime.now().isoformat() + "Z"
        }

        return GraphApiResponse(status_code=200, data=result_data)

    except httpx.HTTPStatusError as exc:
        logger.error(f"Graph API HTTP error: {exc.response.status_code} - {exc.response.text}")
        return GraphApiResponse(
            status_code=200,  # Return 200 but with Not Measured status
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to retrieve SharePoint site creation settings",
                "recommendation": "Check SharePoint admin permissions and Graph API access",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )
    except Exception as e:
        logger.error(f"Error checking SharePoint site creation status: {str(e)}")
        return GraphApiResponse(
            status_code=200,  # Return 200 but with Not Measured status
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to determine SharePoint site creation compliance status",
                "recommendation": "Check system configuration and try again",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )


def determine_sharepoint_site_creation_compliance_status(settings_data: dict) -> dict:
    """
    Determines SharePoint site creation compliance status based on creation settings.
    """

    is_site_creation_enabled = settings_data.get("isSiteCreationEnabled")
    default_managed_path = settings_data.get("siteCreationDefaultManagedPath", "")
    storage_limit_mb = settings_data.get("siteCreationDefaultStorageLimitInMB", 0)

    # Check for Not Measured conditions first
    if is_site_creation_enabled is None:
        return {
            "status": "Not Measured",
            "message": "SharePoint site creation settings could not be determined",
            "recommendation": "Verify SharePoint admin permissions and tenant configuration"
        }

    # Determine compliance status
    if is_site_creation_enabled:
        # Site creation is enabled for all users
        return {
            "status": "Not Compliant",
            "message": "Any user can create SharePoint sites without approval",
            "recommendation": "Restrict site creation to specific groups or implement an approval process"
        }
    else:
        # Site creation is disabled/restricted
        return {
            "status": "Compliant",
            "message": "SharePoint site creation is restricted and requires approval",
            "recommendation": "Continue monitoring site creation settings and review approval processes regularly"
        }


@router.get("/ListWeakAuthenticatorStatus", response_model=GraphApiResponse,
            summary="Check Disable Weakest 2FA Authenticators")
async def list_weak_authenticator_status(clientId: Optional[str] = Query(None),org_id: Optional[int] = Query(None)):
    """
    Checks if weakest 2FA authenticators (SMS and Voice) are disabled for compliance.
    Returns compliance status for weak authentication method governance.
    """
    try:
        # Handle both clientId (old) and org_id (new) parameters
        if not clientId and not org_id:
            raise HTTPException(
                status_code=400,
                detail="Either clientId or org_id query parameter is required"
            )

        if clientId:
            client_id = clientId.strip()
        else:
            creds = await get_organization_credentials(org_id)
            if not creds:
                raise HTTPException(
                    status_code=404,
                    detail=f"No credentials found for org_id: {org_id}"
                )
            client_id = creds['client_id']
        token = await get_access_token(client_id)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        # Get SMS authentication method configuration
        sms_url = f"{GRAPH_V1_URL}/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/Sms"

        async with httpx.AsyncClient() as client:
            sms_response = await client.get(sms_url, headers=headers, timeout=30.0)
            sms_response.raise_for_status()
            sms_data = sms_response.json()

        # Get Voice authentication method configuration
        voice_url = f"{GRAPH_V1_URL}/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/Voice"

        async with httpx.AsyncClient() as client:
            voice_response = await client.get(voice_url, headers=headers, timeout=30.0)
            voice_response.raise_for_status()
            voice_data = voice_response.json()

        # Determine compliance status
        compliance_info = determine_weak_authenticator_compliance_status(sms_data, voice_data)

        # Build standardized response
        result_data = {
            "complianceStatus": compliance_info["status"],
            "statusMessage": compliance_info["message"],
            "recommendation": compliance_info["recommendation"],
            "complianceDetails": {
                "smsAuthenticationMethodConfiguration": sms_data,
                "voiceAuthenticationMethodConfiguration": voice_data,
                "summary": {
                    "smsStatus": sms_data.get("state", "unknown"),
                    "voiceStatus": voice_data.get("state", "unknown"),
                    "isOfficePhoneAllowed": voice_data.get("isOfficePhoneAllowed", False)
                }
            },
            "reportGeneratedAt": datetime.now().isoformat() + "Z"
        }

        return GraphApiResponse(status_code=200, data=result_data)

    except httpx.HTTPStatusError as exc:
        logger.error(f"Graph API HTTP error: {exc.response.status_code} - {exc.response.text}")
        return GraphApiResponse(
            status_code=200,  # Return 200 but with Not Measured status
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to retrieve weak authenticator configuration",
                "recommendation": "Check authentication method policy permissions and Graph API access",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )
    except Exception as e:
        logger.error(f"Error checking weak authenticator status: {str(e)}", exc_info=True)
        return GraphApiResponse(
            status_code=200,  # Return 200 but with Not Measured status
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to determine weak authenticator compliance status",
                "recommendation": "Check system configuration and try again",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )


def determine_weak_authenticator_compliance_status(sms_data: dict, voice_data: dict) -> dict:
    """
    Determines weak authenticator compliance status based on SMS and Voice authentication method states.
    """

    sms_state = sms_data.get("state", "").lower()
    voice_state = voice_data.get("state", "").lower()

    # Check for Not Measured conditions first
    if not sms_state or not voice_state:
        return {
            "status": "Not Measured",
            "message": "Authentication method states could not be determined",
            "recommendation": "Verify authentication method policy permissions and configuration"
        }

    # Count disabled methods
    disabled_methods = []
    enabled_methods = []

    if sms_state == "disabled":
        disabled_methods.append("SMS")
    elif sms_state == "enabled":
        enabled_methods.append("SMS")

    if voice_state == "disabled":
        disabled_methods.append("Voice")
    elif voice_state == "enabled":
        enabled_methods.append("Voice")

    # Determine compliance status
    if len(disabled_methods) == 2:
        # Both SMS and Voice are disabled - Compliant
        return {
            "status": "Compliant",
            "message": "SMS and voice calls are disabled for MFA",
            "recommendation": "Current status is good. Encourage use of authenticator apps or FIDO2 keys"
        }
    elif len(disabled_methods) == 1:
        # One disabled, one enabled - Partially Compliant
        return {
            "status": "Partially Compliant",
            "message": f"{', '.join(disabled_methods)} authentication is disabled but {', '.join(enabled_methods)} is still enabled",
            "recommendation": f"Disable {', '.join(enabled_methods)} authentication to eliminate all weak 2FA methods"
        }
    elif len(enabled_methods) == 2:
        # Both enabled - Not Compliant
        return {
            "status": "Not Compliant",
            "message": "SMS and voice call authentication methods are still enabled",
            "recommendation": "Disable SMS and voice authentication methods and promote stronger alternatives like authenticator apps or FIDO2 keys"
        }
    else:
        # Unknown states
        return {
            "status": "Not Measured",
            "message": "Unable to determine authentication method compliance status",
            "recommendation": "Review authentication method policy configuration manually"
        }


@router.get("/ListGlobalAdmins", response_model=GraphApiResponse,
            summary="List all Global Administrators in the tenant")
async def list_global_admins(clientId: Optional[str] = Query(None),org_id: Optional[int] = Query(None)):
    """
    Lists all Global Administrators and returns compliance status based on admin count.
    Returns compliance status for global admin governance with optimal range of 4-5 admins.
    """
    try:
        # Handle both clientId (old) and org_id (new) parameters
        if not clientId and not org_id:
            raise HTTPException(
                status_code=400,
                detail="Either clientId or org_id query parameter is required"
            )

        if clientId:
            client_id = clientId.strip()
        else:
            creds = await get_organization_credentials(org_id)
            if not creds:
                raise HTTPException(
                    status_code=404,
                    detail=f"No credentials found for org_id: {org_id}"
                )
            client_id = creds['client_id']
        token = await get_access_token(client_id)
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "ConsistencyLevel": "eventual"
        }

        # Global Administrator role template ID (constant across all tenants)
        global_admin_role_id = "62e90394-69f5-4237-9190-012177145e10"

        # Step 1: Get role assignments for Global Administrator role
        assignments_url = f"{GRAPH_V1_URL}/roleManagement/directory/roleAssignments"
        assignments_params = {
            "$filter": f"roleDefinitionId eq '{global_admin_role_id}'",
            "$expand": "principal"
        }

        async with httpx.AsyncClient() as client:
            assign_resp = await client.get(assignments_url, headers=headers, params=assignments_params, timeout=30.0)
            assign_resp.raise_for_status()
            assign_data = assign_resp.json()

        assignments = assign_data.get("value", [])

        # Step 2: Extract user information from assignments
        members = []
        seen_user_ids = set()  # Avoid duplicates

        for assignment in assignments:
            principal = assignment.get("principal", {})
            user_id = principal.get("id")

            # Skip if not a user or already processed
            if not user_id or user_id in seen_user_ids:
                continue

            # Check if it's a user (not a service principal or group)
            if principal.get("@odata.type") == "#microsoft.graph.user":
                seen_user_ids.add(user_id)
                members.append({
                    "id": user_id,
                    "displayName": principal.get("displayName", ""),
                    "userPrincipalName": principal.get("userPrincipalName", "")
                })

        total_admins = len(members)

        # Determine compliance status with updated logic
        compliance_info = determine_global_admin_compliance_status(total_admins)

        # Build standardized response
        result_data = {
            "complianceStatus": compliance_info["status"],
            "statusMessage": compliance_info["message"],
            "recommendation": compliance_info["recommendation"],
            "complianceDetails": {
                "totalAdmins": total_admins,
                "admins": members,
                "recommendedRange": "4-5 administrators"
            },
            "reportGeneratedAt": datetime.now().isoformat() + "Z"
        }

        return GraphApiResponse(status_code=200, data=result_data)

    except httpx.HTTPStatusError as exc:
        logger.error(f"Graph API HTTP error: {exc.response.status_code} - {exc.response.text}")
        return GraphApiResponse(
            status_code=200,  # Return 200 but with Not Measured status
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to retrieve global administrator information",
                "recommendation": "Check directory roles permissions and Graph API access",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )
    except Exception as e:
        logger.error(f"Error listing global admins: {str(e)}")
        return GraphApiResponse(
            status_code=200,  # Return 200 but with Not Measured status
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to determine global administrator compliance status",
                "recommendation": "Check system configuration and try again",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )


def determine_global_admin_compliance_status(total_admins: int) -> dict:
    """
    Determines global admin compliance status based on admin count.
    Updated logic: Recommended optimal range is 4-5 global administrators.
    """

    if total_admins >= 4 and total_admins <= 5:
        # Optimal range - Compliant
        return {
            "status": "Compliant",
            "message": f"{total_admins} global admins, within optimal range of 4-5",
            "recommendation": "Current admin count is optimal. Continue monitoring and maintain emergency access procedures"
        }
    elif total_admins >= 2 and total_admins <= 3:
        # Slightly below optimal - Partially Compliant
        return {
            "status": "Partially Compliant",
            "message": f"{total_admins} global admins, below recommended range of 4-5",
            "recommendation": "Consider adding 1-2 additional global admins to reach optimal range for better redundancy"
        }
    elif total_admins >= 6 and total_admins <= 8:
        # Slightly above optimal - Partially Compliant
        return {
            "status": "Partially Compliant",
            "message": f"{total_admins} global admins, above recommended range of 4-5",
            "recommendation": "Consider reducing global admin count to 4-5 and implement Privileged Identity Management for other roles"
        }
    elif total_admins == 1:
        # Too few - single point of failure - Not Compliant
        return {
            "status": "Not Compliant",
            "message": "Only 1 global admin creates single point of failure",
            "recommendation": "Add 3-4 additional global admins to reach optimal range and ensure emergency access"
        }
    elif total_admins == 0:
        # No global admins (should not happen) - Not Compliant
        return {
            "status": "Not Compliant",
            "message": "No global administrators found",
            "recommendation": "Ensure 4-5 global administrators are assigned for proper tenant management and redundancy"
        }
    else:
        # Too many (>8) - security risk - Not Compliant
        return {
            "status": "Not Compliant",
            "message": f"{total_admins} global admins significantly exceeds recommended maximum",
            "recommendation": "Reduce global admin count to 4-5 and use role-based access with Privileged Identity Management for better security"
        }

# Endpoint for Password Expiration Policy check (read-only, simplified)
@router.get("/CheckPasswordExpirationPolicy", response_model=GraphApiResponse,
            summary="Check Password Expiration Policy for All Domains (Simplified)")
async def check_password_expiration_policy(clientId: Optional[str] = Query(None),org_id: Optional[int] = Query(None)):
    """
    Checks password expiration policy for all domains.
    Returns compliance status based only on password validity period.

    Logic:
    - Compliant: passwordValidityPeriodInDays = 2147483647 (never expires)
    - Compliant: passwordValidityPeriodInDays = 1–999999 days
    - Not Compliant: null/unconfigured or invalid values
    """
    try:
        # Handle both clientId (old) and org_id (new) parameters
        if not clientId and not org_id:
            raise HTTPException(
                status_code=400,
                detail="Either clientId or org_id query parameter is required"
            )

        if clientId:
            client_id = clientId.strip()
        else:
            creds = await get_organization_credentials(org_id)
            if not creds:
                raise HTTPException(
                    status_code=404,
                    detail=f"No credentials found for org_id: {org_id}"
                )
            client_id = creds['client_id']
        token = await get_access_token(client_id)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        # Step 1: Get all domains
        domains_url = f"{GRAPH_V1_URL}/domains"

        async with httpx.AsyncClient() as client:
            domains_response = await client.get(domains_url, headers=headers, timeout=30.0)
            domains_response.raise_for_status()
            domains_data = domains_response.json()

        domains = domains_data.get("value", [])

        compliant_domains = []
        non_compliant_domains = []
        federated_domains = []

        # Step 2: Analyze each domain
        for domain in domains:
            domain_id = domain.get("id", "")
            auth_type = domain.get("authenticationType", "")
            current_validity = domain.get("passwordValidityPeriodInDays")

            domain_info = {
                "domainId": domain_id,
                "authenticationType": auth_type,
                "isDefault": domain.get("isDefault", False),
                "isInitial": domain.get("isInitial", False),
                "passwordValidityPeriodInDays": current_validity,
                "passwordNotificationWindowInDays": domain.get("passwordNotificationWindowInDays")
            }

            # Skip federated domains (managed externally)
            if auth_type != "Managed":
                domain_info["status"] = f"Skipped - {auth_type} domain (password policy managed externally)"
                domain_info["compliant"] = "N/A"
                federated_domains.append(domain_info)
                continue

            # Compliance logic
            if current_validity is None:
                domain_info["status"] = "Password validity period is null/unconfigured"
                domain_info["compliant"] = "Not Compliant"
                domain_info["issue"] = "No password expiration policy configured"
                non_compliant_domains.append(domain_info)
            elif current_validity == 2147483647:
                domain_info["status"] = "Compliant - Passwords never expire"
                domain_info["compliant"] = "Compliant"
                compliant_domains.append(domain_info)
            elif 1 <= current_validity <= 999999:
                domain_info["status"] = f"Compliant - {current_validity} days validity period"
                domain_info["compliant"] = "Compliant"
                compliant_domains.append(domain_info)
            else:
                domain_info["status"] = f"Invalid password validity value: {current_validity}"
                domain_info["compliant"] = "Not Compliant"
                domain_info["issue"] = "Invalid password validity configuration"
                non_compliant_domains.append(domain_info)

        # Step 3: Determine overall compliance
        total_managed = len(compliant_domains) + len(non_compliant_domains)
        if total_managed == 0:
            compliance_info = {
                "status": "Not Measured",
                "message": "No managed domains found to evaluate password expiration policies",
                "recommendation": "Password policies for federated domains are managed externally"
            }
        elif len(non_compliant_domains) == 0:
            compliance_info = {
                "status": "Compliant",
                "message": f"All {len(compliant_domains)} managed domain(s) are compliant",
                "recommendation": "Maintain current configuration"
            }
        elif len(compliant_domains) > 0:
            compliance_info = {
                "status": "Partially Compliant",
                "message": f"{len(compliant_domains)} compliant, {len(non_compliant_domains)} not compliant",
                "recommendation": "Some domains need attention. Configure password expiration to either 'Never Expire' or set a specific number of days (1-999999)."
            }
        else:
            compliance_info = {
                "status": "Not Compliant",
                "message": "All managed domains are misconfigured or unconfigured",
                "recommendation": "Password expiration policy is not configured. Set passwords to either 'Never Expire' or choose an expiration period between 1-999999 days."
            }

        # Step 4: Build response
        result_data = {
            "complianceStatus": compliance_info["status"],
            "statusMessage": compliance_info["message"],
            "recommendation": compliance_info["recommendation"],
            "complianceDetails": {
                "summary": {
                    "totalDomains": len(domains),
                    "managedDomains": total_managed,
                    "compliantDomains": len(compliant_domains),
                    "nonCompliantDomains": len(non_compliant_domains),
                    "federatedDomains": len(federated_domains)
                },
                "compliantDomains": compliant_domains,
                "nonCompliantDomains": non_compliant_domains,
                "federatedDomains": federated_domains,
                "policyGuidelines": {
                    "compliant": "2147483647 (never expires) or 1–999999 days",
                    "notCompliant": "null/unconfigured or invalid values"
                }
            },
            "reportGeneratedAt": datetime.now().isoformat() + "Z"
        }

        return GraphApiResponse(status_code=200, data=result_data)

    except httpx.HTTPStatusError as exc:
        logger.error(f"Graph API HTTP error: {exc.response.status_code} - {exc.response.text}")
        return GraphApiResponse(
            status_code=200,
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to retrieve password expiration policy information",
                "recommendation": "Check domain permissions and Graph API access",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )
    except Exception as e:
        logger.error(f"Error checking password expiration policy: {str(e)}")
        return GraphApiResponse(
            status_code=200,
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to determine password expiration policy compliance status",
                "recommendation": "Check system configuration and try again",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )


# Endpoint for SPF policy check
@router.get("/ListSPFPolicyStatus", response_model=GraphApiResponse, summary="Check SPF Policy Configuration")
async def list_spf_policy_status(clientId: Optional[str] = Query(None),org_id: Optional[int] = Query(None)):
    """
    Checks SPF policy configuration for all domains in the tenant.
    Returns compliance status for SPF record configuration.
    """
    try:
        # Handle both clientId (old) and org_id (new) parameters
        if not clientId and not org_id:
            raise HTTPException(
                status_code=400,
                detail="Either clientId or org_id query parameter is required"
            )

        if clientId:
            client_id = clientId.strip()
        else:
            creds = await get_organization_credentials(org_id)
            if not creds:
                raise HTTPException(
                    status_code=404,
                    detail=f"No credentials found for org_id: {org_id}"
                )
            client_id = creds['client_id']
        token = await get_access_token(client_id)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        # Step 1: Get all domains with just the id field (domain names)
        domains_url = f"{GRAPH_V1_URL}/domains"
        domains_params = {"$select": "id"}

        async with httpx.AsyncClient() as client:
            domains_response = await client.get(domains_url, headers=headers, params=domains_params, timeout=30.0)
            domains_response.raise_for_status()
            domains_data = domains_response.json()

        domains = domains_data.get("value", [])
        domain_spf_records = {}
        spf_analysis = []

        # Step 2: For each domain, get its service configuration records and analyze SPF
        for domain in domains:
            domain_name = domain.get("id", "")

            if domain_name:
                try:
                    # Get DNS service configuration records for this domain
                    service_config_url = f"{GRAPH_V1_URL}/domains/{domain_name}/serviceConfigurationRecords"

                    async with httpx.AsyncClient() as client:
                        config_response = await client.get(service_config_url, headers=headers, timeout=10.0)
                        config_response.raise_for_status()
                        config_data = config_response.json()

                    # Store the complete response for this domain
                    domain_records = config_data.get("value", [])
                    domain_spf_records[domain_name] = {
                        "@odata.context": config_data.get("@odata.context", ""),
                        "value": domain_records
                    }

                    # Analyze SPF records for this domain
                    spf_info = analyze_domain_spf_records(domain_name, domain_records)
                    spf_analysis.append(spf_info)

                except Exception as e:
                    logger.warning(f"Failed to get service configuration records for domain {domain_name}: {str(e)}")
                    domain_spf_records[domain_name] = {
                        "@odata.context": "",
                        "value": [],
                        "error": f"Failed to retrieve records: {str(e)}"
                    }

                    # Add failed domain to analysis
                    spf_analysis.append({
                        "domainName": domain_name,
                        "hasSPF": False,
                        "spfRecords": [],
                        "compliance": "Not Measured",
                        "issue": f"Failed to retrieve DNS records: {str(e)}"
                    })

        # Determine overall compliance status
        compliance_info = determine_spf_compliance_status(spf_analysis)

        # Build standardized response
        result_data = {
            "complianceStatus": compliance_info["status"],
            "statusMessage": compliance_info["message"],
            "recommendation": compliance_info["recommendation"],
            "complianceDetails": {
                "domainServiceConfigurationRecords": domain_spf_records,
                "spfAnalysis": spf_analysis,
                "summary": {
                    "totalDomains": len(domains),
                    "domainsWithSPF": len([d for d in spf_analysis if d["hasSPF"]]),
                    "domainsWithoutSPF": len(
                        [d for d in spf_analysis if not d["hasSPF"] and d["compliance"] != "Not Measured"]),
                    "failedDomains": len([d for d in spf_analysis if d["compliance"] == "Not Measured"])
                }
            },
            "reportGeneratedAt": datetime.now().isoformat() + "Z"
        }

        return GraphApiResponse(status_code=200, data=result_data)

    except httpx.HTTPStatusError as exc:
        logger.error(f"Graph API HTTP error: {exc.response.status_code} - {exc.response.text}")
        return GraphApiResponse(
            status_code=200,  # Return 200 but with Not Measured status
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to retrieve SPF policy information",
                "recommendation": "Check DNS configuration permissions and Graph API access",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )
    except Exception as e:
        logger.error(f"Error checking SPF policy status: {str(e)}")
        return GraphApiResponse(
            status_code=200,  # Return 200 but with Not Measured status
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to determine SPF policy compliance status",
                "recommendation": "Check system configuration and try again",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )


def analyze_domain_spf_records(domain_name: str, dns_records: list) -> dict:
    """
    Analyze DNS records for a domain to check SPF compliance.
    """
    spf_records = []

    # Look for TXT records that contain SPF policies
    for record in dns_records:
        if record.get("@odata.type") == "#microsoft.graph.domainDnsTxtRecord":
            txt_content = record.get("text", "")
            if txt_content.startswith("v=spf1"):
                spf_records.append({
                    "id": record.get("id", ""),
                    "label": record.get("label", ""),
                    "text": txt_content,
                    "supportedService": record.get("supportedService", ""),
                    "ttl": record.get("ttl", 0)
                })

    # Determine compliance for this domain
    has_spf = len(spf_records) > 0

    if has_spf:
        # Check if SPF records are properly configured
        valid_spf_count = 0
        for spf_record in spf_records:
            if is_valid_spf_record(spf_record["text"]):
                valid_spf_count += 1

        if valid_spf_count == len(spf_records):
            compliance = "Compliant"
            issue = None
        else:
            compliance = "Partially Compliant"
            issue = f"{valid_spf_count}/{len(spf_records)} SPF records are properly configured"
    else:
        compliance = "Not Compliant"
        issue = "No SPF records found"

    return {
        "domainName": domain_name,
        "hasSPF": has_spf,
        "spfRecords": spf_records,
        "compliance": compliance,
        "issue": issue
    }


def is_valid_spf_record(spf_text: str) -> bool:
    """
    Basic validation of SPF record format.
    """
    if not spf_text.startswith("v=spf1"):
        return False

    # Check for proper termination (should end with -all, ~all, or ?all)
    valid_endings = ["-all", "~all", "?all"]
    has_valid_ending = any(spf_text.endswith(ending) for ending in valid_endings)

    # Check for include mechanisms (common in Office 365)
    has_include = "include:" in spf_text

    return has_valid_ending and (has_include or "ip4:" in spf_text or "ip6:" in spf_text)


def determine_spf_compliance_status(spf_analysis: list) -> dict:
    """
    Determines overall SPF compliance status based on domain analysis.
    """

    if not spf_analysis:
        return {
            "status": "Not Measured",
            "message": "No domains found to evaluate SPF policy",
            "recommendation": "Ensure domains are properly configured and accessible"
        }

    # Count domain compliance states
    compliant_domains = [d for d in spf_analysis if d["compliance"] == "Compliant"]
    partially_compliant_domains = [d for d in spf_analysis if d["compliance"] == "Partially Compliant"]
    non_compliant_domains = [d for d in spf_analysis if d["compliance"] == "Not Compliant"]
    not_measured_domains = [d for d in spf_analysis if d["compliance"] == "Not Measured"]

    total_domains = len(spf_analysis)
    compliant_count = len(compliant_domains)

    # Determine overall status
    if not_measured_domains and len(not_measured_domains) == total_domains:
        # All domains failed to be measured
        return {
            "status": "Not Measured",
            "message": "Unable to retrieve SPF configuration for any domain",
            "recommendation": "Check DNS configuration permissions and retry"
        }
    elif compliant_count == total_domains - len(not_measured_domains):
        # All measurable domains are compliant
        if total_domains == 1:
            return {
                "status": "Compliant",
                "message": "SPF records are configured correctly",
                "recommendation": "Current status is good. Review SPF records when adding new email services"
            }
        else:
            return {
                "status": "Compliant",
                "message": f"SPF records are configured correctly for all {compliant_count} domains",
                "recommendation": "Current status is good. Review SPF records when adding new email services"
            }
    elif compliant_count > 0:
        # Mixed compliance
        issues = []
        if non_compliant_domains:
            issues.append(f"{len(non_compliant_domains)} domains without SPF records")
        if partially_compliant_domains:
            issues.append(f"{len(partially_compliant_domains)} domains with SPF configuration issues")

        return {
            "status": "Partially Compliant",
            "message": f"{compliant_count} of {total_domains} domains have proper SPF configuration, issues: {', '.join(issues)}",
            "recommendation": "Configure SPF records for all domains to prevent email spoofing and improve deliverability"
        }
    else:
        # No compliant domains
        return {
            "status": "Not Compliant",
            "message": f"No domains have proper SPF records configured",
            "recommendation": "Implement SPF records for all domains to prevent email spoofing and ensure proper email delivery"
        }


# Endpoint for Teams Default external/guest policy check
@router.get("/CheckTeamsExternalAccess", response_model=GraphApiResponse,
            summary="Check Teams External Access Policy")
async def check_teams_external_access(clientId: Optional[str] = Query(None),org_id: Optional[int] = Query(None)):
    """
    Checks if Teams allows all external access without restrictions.
    Returns compliance status for Teams external access governance.
    """
    try:
        # Handle both clientId (old) and org_id (new) parameters
        if not clientId and not org_id:
            raise HTTPException(
                status_code=400,
                detail="Either clientId or org_id query parameter is required"
            )

        if clientId:
            client_id = clientId.strip()
        else:
            creds = await get_organization_credentials(org_id)
            if not creds:
                raise HTTPException(
                    status_code=404,
                    detail=f"No credentials found for org_id: {org_id}"
                )
            client_id = creds['client_id']
        token = await get_access_token(client_id)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        # Step 1: Get Cross-Tenant Access Policy Default Configuration
        cross_tenant_url = f"{GRAPH_V1_URL}/policies/crossTenantAccessPolicy/default"

        async with httpx.AsyncClient() as client:
            cross_tenant_response = await client.get(cross_tenant_url, headers=headers, timeout=30.0)
            cross_tenant_response.raise_for_status()
            cross_tenant_data = cross_tenant_response.json()

        # Check current b2bCollaborationInbound configuration
        b2b_inbound = cross_tenant_data.get("b2bCollaborationInbound", {})
        users_groups = b2b_inbound.get("usersAndGroups", {})
        current_access_type = users_groups.get("accessType", "")
        current_targets = users_groups.get("targets", [])

        # Check if it allows all external access
        allows_all_external = (
                current_access_type == "allowed" and
                len(current_targets) == 1 and
                current_targets[0].get("target") == "AllUsers" and
                current_targets[0].get("targetType") == "user"
        )

        # Step 2: Get Authorization Policy for additional context
        auth_policy_url = f"{GRAPH_V1_URL}/policies/authorizationPolicy"

        async with httpx.AsyncClient() as client:
            auth_response = await client.get(auth_policy_url, headers=headers, timeout=30.0)
            auth_response.raise_for_status()
            auth_data = auth_response.json()

        # Step 3: Get External Identities Policy
        external_identities_url = f"{GRAPH_BETA_URL}/policies/externalIdentitiesPolicy"

        async with httpx.AsyncClient() as client:
            external_response = await client.get(external_identities_url, headers=headers, timeout=30.0)
            external_response.raise_for_status()
            external_data = external_response.json()

        # Determine compliance status
        compliance_info = determine_teams_external_access_compliance_status(allows_all_external)

        # Build standardized response
        result_data = {
            "complianceStatus": compliance_info["status"],
            "statusMessage": compliance_info["message"],
            "recommendation": compliance_info["recommendation"],
            "complianceDetails": {
                "crossTenantAccessPolicy": {
                    "currentConfiguration": cross_tenant_data,
                    "allowsAllExternalAccess": allows_all_external,
                    "accessType": current_access_type,
                    "targets": current_targets
                },
                "authorizationPolicy": {
                    "allowInvitesFrom": auth_data.get("allowInvitesFrom", ""),
                    "allowEmailVerifiedUsersToJoinOrganization": auth_data.get(
                        "allowEmailVerifiedUsersToJoinOrganization", False),
                    "guestUserRoleId": auth_data.get("guestUserRoleId", ""),
                    "fullConfiguration": auth_data
                },
                "externalIdentitiesPolicy": {
                    "allowExternalIdentitiesToLeave": external_data.get("allowExternalIdentitiesToLeave", False),
                    "allowDeletedIdentitiesDataRemoval": external_data.get("allowDeletedIdentitiesDataRemoval", False),
                    "fullConfiguration": external_data
                },
                "summary": {
                    "teamsAllowsAllExternalAccess": allows_all_external,
                    "securityRisk": allows_all_external
                }
            },
            "reportGeneratedAt": datetime.now().isoformat() + "Z"
        }

        return GraphApiResponse(status_code=200, data=result_data)

    except httpx.HTTPStatusError as exc:
        logger.error(f"Graph API HTTP error: {exc.response.status_code} - {exc.response.text}")
        return GraphApiResponse(
            status_code=200,  # Return 200 but with Not Measured status
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to retrieve Teams external access policy information",
                "recommendation": "Check cross-tenant access policy permissions and Graph API access",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )
    except Exception as e:
        logger.error(f"Error checking Teams external access policy: {str(e)}", exc_info=True)
        return GraphApiResponse(
            status_code=200,  # Return 200 but with Not Measured status
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to determine Teams external access compliance status",
                "recommendation": "Check system configuration and try again",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )


def determine_teams_external_access_compliance_status(allows_all_external: bool) -> dict:
    """
    Determines Teams external access compliance status based on policy configuration.
    From a security perspective, allowing all external access is considered non-compliant.
    """

    if allows_all_external:
        # Allowing all external access without restrictions - security risk
        return {
            "status": "Not Compliant",
            "message": "Teams allows all external access without restrictions",
            "recommendation": "Configure Teams to only allow specific external domains to collaborate"
        }
    else:
        # External access is restricted - compliant
        return {
            "status": "Compliant",
            "message": "Teams external access is properly restricted",
            "recommendation": "Continue monitoring Teams external access settings and review approved domains regularly"
        }


# Endpoint for Risky Country Policy check
@router.get("/ListRiskyCountryLocations", response_model=GraphApiResponse,
            summary="Check Risky Country Named Locations Policy")
async def list_risky_country_locations(clientId: Optional[str] = Query(None),org_id: Optional[int] = Query(None)):
    """
    Checks risky country named locations and their usage in conditional access policies.
    Returns compliance status for risky country blocking governance.
    """
    try:
        # Handle both clientId (old) and org_id (new) parameters
        if not clientId and not org_id:
            raise HTTPException(
                status_code=400,
                detail="Either clientId or org_id query parameter is required"
            )

        if clientId:
            client_id = clientId.strip()
        else:
            creds = await get_organization_credentials(org_id)
            if not creds:
                raise HTTPException(
                    status_code=404,
                    detail=f"No credentials found for org_id: {org_id}"
                )
            client_id = creds['client_id']
        token = await get_access_token(client_id)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        # Step 1: Get named locations
        named_locations_url = f"{GRAPH_V1_URL}/identity/conditionalAccess/namedLocations"

        async with httpx.AsyncClient() as client:
            response = await client.get(named_locations_url, headers=headers, timeout=30.0)
            response.raise_for_status()
            locations_data = response.json()

        all_locations = locations_data.get("value", [])

        # Extract locations based on type-specific risky conditions
        risky_locations = []
        trusted_locations = []

        for location in all_locations:
            is_risky = False

            # Check if isTrusted field exists and is false
            if "isTrusted" in location and location.get("isTrusted") == False:
                is_risky = True

            # Check if includeUnknownCountriesAndRegions field exists and is true
            if "includeUnknownCountriesAndRegions" in location and location.get(
                    "includeUnknownCountriesAndRegions") == True:
                is_risky = True

            location_info = {
                "@odata.type": location.get("@odata.type", ""),
                "id": location.get("id", ""),
                "displayName": location.get("displayName", ""),
                "modifiedDateTime": location.get("modifiedDateTime", ""),
                "createdDateTime": location.get("createdDateTime", "")
            }

            # Add type-specific fields if they exist
            if "isTrusted" in location:
                location_info["isTrusted"] = location.get("isTrusted")
            if "includeUnknownCountriesAndRegions" in location:
                location_info["includeUnknownCountriesAndRegions"] = location.get("includeUnknownCountriesAndRegions")
            if "countriesAndRegions" in location:
                location_info["countriesAndRegions"] = location.get("countriesAndRegions", [])
            if "ipRanges" in location:
                location_info["ipRanges"] = location.get("ipRanges", [])

            if is_risky:
                risky_locations.append(location_info)
            else:
                trusted_locations.append(location_info)

        # Step 2: Get conditional access policies to check if risky locations are used
        ca_policies_url = f"{GRAPH_V1_URL}/identity/conditionalAccess/policies"
        ca_params = {"$filter": "state eq 'enabled'", "$select": "id,displayName,conditions,grantControls"}

        async with httpx.AsyncClient() as client:
            ca_response = await client.get(ca_policies_url, headers=headers, params=ca_params, timeout=30.0)
            ca_response.raise_for_status()
            ca_data = ca_response.json()

        ca_policies = ca_data.get("value", [])

        # Analyze which policies use risky locations
        policies_using_risky_locations = []
        risky_location_ids = [loc["id"] for loc in risky_locations]

        for policy in ca_policies:
            conditions = policy.get("conditions", {})
            locations_condition = conditions.get("locations", {})

            if locations_condition:
                include_locations = locations_condition.get("includeLocations", [])
                exclude_locations = locations_condition.get("excludeLocations", [])

                # Check if policy includes any risky locations
                uses_risky_location = any(loc_id in risky_location_ids for loc_id in include_locations)

                if uses_risky_location:
                    grant_controls = policy.get("grantControls", {})
                    built_in_controls = grant_controls.get("builtInControls", [])

                    policies_using_risky_locations.append({
                        "policyId": policy.get("id", ""),
                        "displayName": policy.get("displayName", ""),
                        "includeLocations": include_locations,
                        "excludeLocations": exclude_locations,
                        "controls": built_in_controls
                    })

        # Determine compliance status
        compliance_info = determine_risky_country_compliance_status(
            risky_locations, trusted_locations, policies_using_risky_locations
        )

        # Build standardized response
        result_data = {
            "complianceStatus": compliance_info["status"],
            "statusMessage": compliance_info["message"],
            "recommendation": compliance_info["recommendation"],
            "complianceDetails": {
                "riskyNamedLocations": risky_locations,
                "trustedNamedLocations": trusted_locations,
                "policiesUsingRiskyLocations": policies_using_risky_locations,
                "summary": {
                    "totalNamedLocations": len(all_locations),
                    "riskyLocationsCount": len(risky_locations),
                    "trustedLocationsCount": len(trusted_locations),
                    "policiesBlockingRiskyCountries": len(policies_using_risky_locations)
                }
            },
            "reportGeneratedAt": datetime.now().isoformat() + "Z"
        }

        return GraphApiResponse(status_code=200, data=result_data)

    except httpx.HTTPStatusError as exc:
        logger.error(f"Graph API HTTP error: {exc.response.status_code} - {exc.response.text}")
        return GraphApiResponse(
            status_code=200,  # Return 200 but with Not Measured status
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to retrieve risky country policy information",
                "recommendation": "Check conditional access and named locations permissions",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )
    except Exception as e:
        logger.error(f"Error checking risky country locations: {str(e)}")
        return GraphApiResponse(
            status_code=200,  # Return 200 but with Not Measured status
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to determine risky country policy compliance status",
                "recommendation": "Check system configuration and try again",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )

def determine_risky_country_compliance_status(risky_locations: list, trusted_locations: list,
                                              blocking_policies: list) -> dict:
    """
    Determines risky country policy compliance status based on named locations and policies.
    """

    risky_count = len(risky_locations)
    trusted_count = len(trusted_locations)
    blocking_policies_count = len(blocking_policies)

    if risky_count == 0 and trusted_count == 0:
        # No named locations configured at all
        return {
            "status": "Not Compliant",
            "message": "No country-based named locations configured for risk assessment",
            "recommendation": "Create named locations for high-risk countries and implement conditional access policies to block access from these locations"
        }

    elif risky_count == 0:
        # Only trusted locations, no risky ones defined
        return {
            "status": "Not Compliant",
            "message": "No high-risk countries are configured for blocking",
            "recommendation": "Configure named locations for high-risk countries identified in your risk assessment and create policies to block access"
        }

    elif risky_count > 0 and blocking_policies_count == 0:
        # Risky locations defined but no policies using them
        return {
            "status": "Not Compliant",
            "message": f"{risky_count} risky country locations configured but no conditional access policies block them",
            "recommendation": "Create conditional access policies to block or require additional authentication from risky country locations"
        }

    elif risky_count > 0 and blocking_policies_count > 0:
        # Some risky locations and some policies - need to assess coverage
        if blocking_policies_count >= risky_count:
            # Good coverage of risky locations with policies
            return {
                "status": "Compliant",
                "message": f"All {risky_count} risky country locations are protected by {blocking_policies_count} conditional access policies",
                "recommendation": "Continue monitoring risky country policies and update based on threat intelligence"
            }
        else:
            # Partial coverage
            return {
                "status": "Partially Compliant",
                "message": f"Some but not all high-risk countries are blocked ({blocking_policies_count} policies for {risky_count} risky locations)",
                "recommendation": "Complete the implementation to block all high-risk countries identified in your risk assessment"
            }

    else:
        # Edge case
        return {
            "status": "Not Measured",
            "message": "Unable to determine risky country policy status from current configuration",
            "recommendation": "Review named locations and conditional access policy configuration manually"
        }


# Endpoint for Connected Apps & User consents compliance check
@router.get("/ListConnectedAppsUserConsents", response_model=GraphApiResponse,
            summary="Check Connected Apps & User Consents Compliance")
async def list_connected_apps_user_consents(clientId: Optional[str] = Query(None),org_id: Optional[int] = Query(None)):
    """
    Checks connected apps and user consents compliance by analyzing OAuth2 permission grants
    and service principals. Returns compliance status for app consent policies.
    """
    try:
        # Handle both clientId (old) and org_id (new) parameters
        if not clientId and not org_id:
            raise HTTPException(
                status_code=400,
                detail="Either clientId or org_id query parameter is required"
            )

        if clientId:
            client_id = clientId.strip()
        else:
            creds = await get_organization_credentials(org_id)
            if not creds:
                raise HTTPException(
                    status_code=404,
                    detail=f"No credentials found for org_id: {org_id}"
                )
            client_id = creds['client_id']
        token = await get_access_token(client_id)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        # Step 1: Get OAuth2 permission grants (user consents)
        oauth2_grants_url = f"{GRAPH_V1_URL}/oauth2PermissionGrants"
        grants_params = {
            "$select": "clientId,consentType,id,principalId,resourceId,scope"
        }

        async with httpx.AsyncClient() as client:
            grants_response = await client.get(oauth2_grants_url, headers=headers, params=grants_params, timeout=30.0)
            grants_response.raise_for_status()
            grants_data = grants_response.json()

        oauth2_grants = grants_data.get("value", [])

        # Step 2: Get service principals (connected apps)
        service_principals_url = f"{GRAPH_V1_URL}/servicePrincipals"
        sp_params = {
            "$select": "appId,displayName,servicePrincipalType,signInAudience,id"
        }

        async with httpx.AsyncClient() as client:
            sp_response = await client.get(service_principals_url, headers=headers, params=sp_params, timeout=30.0)
            sp_response.raise_for_status()
            sp_data = sp_response.json()

        service_principals = sp_data.get("value", [])

        # Step 3: Analyze connected apps and consents
        app_analysis = analyze_connected_apps_compliance(oauth2_grants, service_principals)

        # Determine overall compliance status
        compliance_info = determine_connected_apps_compliance_status(app_analysis)

        # Build standardized response
        result_data = {
            "complianceStatus": compliance_info["status"],
            "statusMessage": compliance_info["message"],
            "recommendation": compliance_info["recommendation"],
            "complianceDetails": {
                "oauth2PermissionGrants": oauth2_grants,
                "servicePrincipals": service_principals,
                "appAnalysis": app_analysis,
                "summary": {
                    "totalApps": len(service_principals),
                    "totalGrants": len(oauth2_grants),
                    "adminConsentApps": len([g for g in oauth2_grants if g.get("consentType") == "AllPrincipals"]),
                    "userConsentApps": len([g for g in oauth2_grants if g.get("consentType") == "Principal"]),
                    "highRiskApps": len([a for a in app_analysis if a.get("riskLevel") == "High"]),
                    "unverifiedPublishers": len([a for a in app_analysis if not a.get("isVerifiedPublisher", True)])
                }
            },
            "reportGeneratedAt": datetime.now().isoformat() + "Z"
        }

        return GraphApiResponse(status_code=200, data=result_data)

    except httpx.HTTPStatusError as exc:
        logger.error(f"Graph API HTTP error: {exc.response.status_code} - {exc.response.text}")
        return GraphApiResponse(
            status_code=200,  # Return 200 but with Not Measured status
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to retrieve connected apps and user consent information",
                "recommendation": "Check Graph API permissions and connectivity",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )
    except Exception as e:
        logger.error(f"Error checking connected apps compliance: {str(e)}")
        return GraphApiResponse(
            status_code=200,  # Return 200 but with Not Measured status
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to determine connected apps compliance status",
                "recommendation": "Check system configuration and try again",
                "complianceDetails": None,
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )


def analyze_connected_apps_compliance(oauth2_grants: list, service_principals: list) -> list:
    """
    Analyze connected apps and OAuth2 grants for compliance risks.
    """
    app_analysis = []

    # Create lookup dictionary for service principals
    sp_lookup = {sp["id"]: sp for sp in service_principals}

    # Group grants by clientId to analyze each app
    client_grants = {}
    for grant in oauth2_grants:
        client_id = grant.get("clientId")
        if client_id not in client_grants:
            client_grants[client_id] = []
        client_grants[client_id].append(grant)

    # Analyze each connected app
    for client_id, grants in client_grants.items():
        # Find corresponding service principal
        sp = None
        for principal in service_principals:
            if principal.get("id") == client_id:
                sp = principal
                break

        if not sp:
            continue

        app_info = analyze_app_risk_level(sp, grants)
        app_analysis.append(app_info)

    return app_analysis


def analyze_app_risk_level(service_principal: dict, grants: list) -> dict:
    """
    Analyze individual app for compliance and risk factors.
    """
    app_name = service_principal.get("displayName", "Unknown App")
    app_id = service_principal.get("appId", "")

    # Analyze permissions across all grants for this app
    all_scopes = []
    has_admin_consent = False
    has_user_consent = False

    for grant in grants:
        scopes = grant.get("scope", "").split()
        all_scopes.extend(scopes)

        if grant.get("consentType") == "AllPrincipals":
            has_admin_consent = True
        elif grant.get("consentType") == "Principal":
            has_user_consent = True

    # Remove duplicates
    unique_scopes = list(set(all_scopes))

    # Determine risk level based on permissions and app characteristics
    risk_level = determine_app_risk_level(unique_scopes, service_principal)

    # Check if it's a Microsoft first-party app
    is_microsoft_app = is_microsoft_first_party_app(service_principal)

    # Check publisher verification (simplified - in real implementation you'd check more details)
    is_verified_publisher = is_microsoft_app or service_principal.get("signInAudience") == "AzureADMultipleOrgs"

    compliance_status = determine_app_compliance_status(risk_level, is_microsoft_app, has_admin_consent)

    return {
        "appName": app_name,
        "appId": app_id,
        "servicePrincipalId": service_principal.get("id", ""),
        "riskLevel": risk_level,
        "permissions": unique_scopes,
        "permissionCount": len(unique_scopes),
        "hasAdminConsent": has_admin_consent,
        "hasUserConsent": has_user_consent,
        "isMicrosoftApp": is_microsoft_app,
        "isVerifiedPublisher": is_verified_publisher,
        "signInAudience": service_principal.get("signInAudience", ""),
        "compliance": compliance_status["status"],
        "issues": compliance_status["issues"]
    }


def determine_app_risk_level(scopes: list, service_principal: dict) -> str:
    """
    Determine risk level based on permissions and app characteristics.
    """
    # High-risk permission scopes
    high_risk_scopes = [
        "Directory.ReadWrite.All", "Directory.AccessAsUser.All", "User.ReadWrite.All",
        "Group.ReadWrite.All", "Mail.ReadWrite", "Files.ReadWrite.All",
        "Sites.ReadWrite.All", "Application.ReadWrite.All", "RoleManagement.ReadWrite.Directory"
    ]

    # Medium-risk permission scopes
    medium_risk_scopes = [
        "Directory.Read.All", "User.Read.All", "Group.Read.All", "Mail.Read",
        "Files.Read.All", "Sites.Read.All", "Reports.Read.All"
    ]

    # Check for high-risk permissions
    high_risk_perms = [scope for scope in scopes if any(risk_scope in scope for risk_scope in high_risk_scopes)]
    if high_risk_perms:
        return "High"

    # Check for medium-risk permissions
    medium_risk_perms = [scope for scope in scopes if any(risk_scope in scope for risk_scope in medium_risk_scopes)]
    if medium_risk_perms:
        return "Medium"

    # Check if it's a third-party app with multiple permissions
    is_microsoft_app = is_microsoft_first_party_app(service_principal)
    if not is_microsoft_app and len(scopes) > 5:
        return "Medium"

    return "Low"


def is_microsoft_first_party_app(service_principal: dict) -> bool:
    """
    Determine if the app is a Microsoft first-party application.
    """
    microsoft_app_ids = {
        "00000003-0000-0000-c000-000000000000",  # Microsoft Graph
        "00000002-0000-0000-c000-000000000000",  # Azure AD Graph
        "00000006-0000-0ff1-ce00-000000000000",  # Office 365 Portal
        "cc15fd57-2c6c-4117-a88c-83b1d56b4bbe",  # Microsoft Teams Services
        "1b730954-1685-4b74-9bfd-dac224a7b894"  # Azure Portal
    }

    app_id = service_principal.get("appId", "")
    app_name = service_principal.get("displayName", "").lower()

    # Check against known Microsoft app IDs
    if app_id in microsoft_app_ids:
        return True

    # Check if app name contains Microsoft indicators
    microsoft_indicators = ["microsoft", "office", "azure", "sharepoint", "teams", "outlook"]
    if any(indicator in app_name for indicator in microsoft_indicators):
        return True

    return False


def determine_app_compliance_status(risk_level: str, is_microsoft_app: bool, has_admin_consent: bool) -> dict:
    """
    Determine compliance status for individual app.
    """
    issues = []

    if risk_level == "High" and not is_microsoft_app:
        issues.append("High-risk permissions granted to third-party app")

    if has_admin_consent and not is_microsoft_app and risk_level in ["High", "Medium"]:
        issues.append("Admin consent granted for potentially risky third-party app")

    if not is_microsoft_app and risk_level == "High":
        return {"status": "Not Compliant", "issues": issues}
    elif issues:
        return {"status": "Partially Compliant", "issues": issues}
    else:
        return {"status": "Compliant", "issues": None}


def determine_connected_apps_compliance_status(app_analysis: list) -> dict:
    """
    Determines overall connected apps compliance status based on app analysis.
    """
    if not app_analysis:
        return {
            "status": "Not Measured",
            "message": "No connected apps found to evaluate",
            "recommendation": "Review app registration and consent policies"
        }

    # Count compliance states
    compliant_apps = [app for app in app_analysis if app["compliance"] == "Compliant"]
    partially_compliant_apps = [app for app in app_analysis if app["compliance"] == "Partially Compliant"]
    non_compliant_apps = [app for app in app_analysis if app["compliance"] == "Not Compliant"]

    total_apps = len(app_analysis)
    compliant_count = len(compliant_apps)
    high_risk_count = len([app for app in app_analysis if app["riskLevel"] == "High"])
    third_party_count = len([app for app in app_analysis if not app["isMicrosoftApp"]])

    # Determine overall status
    if non_compliant_apps:
        issues = []
        if high_risk_count > 0:
            issues.append(f"{high_risk_count} high-risk applications")
        if third_party_count > 5:
            issues.append(f"{third_party_count} third-party applications with access")

        return {
            "status": "Not Compliant",
            "message": f"{len(non_compliant_apps)} of {total_apps} connected apps pose security risks, issues: {', '.join(issues)}",
            "recommendation": "Configure app consent policy to limit which apps can access organization data. Review and revoke access for high-risk third-party applications."
        }
    elif partially_compliant_apps:
        return {
            "status": "Partially Compliant",
            "message": f"{len(partially_compliant_apps)} of {total_apps} connected apps require attention for optimal security",
            "recommendation": "Review apps with medium-risk permissions and consider implementing app consent policies for better control."
        }
    elif high_risk_count == 0 and third_party_count <= 3:
        return {
            "status": "Compliant",
            "message": f"All {total_apps} connected apps follow security best practices",
            "recommendation": "Current app consent configuration is secure. Continue monitoring new app installations and permissions."
        }
    else:
        return {
            "status": "Partially Compliant",
            "message": f"Connected apps are generally secure but {third_party_count} third-party apps have access",
            "recommendation": "Consider implementing app consent policies to provide better control over third-party application access."
        }




