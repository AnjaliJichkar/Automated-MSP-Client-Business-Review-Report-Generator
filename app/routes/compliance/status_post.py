
"""
Main compliance fix router that routes policy fix requests to appropriate functions.
This is a separate Python file that imports functions from compliance_endpoints.py
"""
import logging
from fastapi import APIRouter, HTTPException, Body, Depends
from pydantic import ValidationError, BaseModel, Field, validator
from typing import Optional, List
import logging
import asyncio
import httpx
import uuid
from datetime import datetime
from typing import List, Dict, Any
from fastapi import APIRouter, Body
from app.core.auth.middleware import get_access_token
from app.core.auth.dependencies import get_client_credentials
from app.schemas.api import GraphApiResponse
from app.core.config.settings import GRAPH_V1_URL, GRAPH_BETA_URL

from app.schemas.api import (
    PolicyIdEnum,
    OptionalFixParameters,
    MFAFixRequest,
    SharePointFixRequest,
    GuestAccessFixRequest,
    PolicyIdValidation,
    validate_and_sanitize_policy_id
)
# Import the specific POST functions from the main compliance endpoints file
from app.routes.compliance.status import (
     # get_admin_mfa_status,
    get_user_mfa_status,
list_sharepoint_external_resharing_status,
determine_audit_compliance_status,
determine_high_risk_users_compliance_status,
# determine_shared_mailbox_compliance_status,
determine_sharepoint_site_creation_compliance_status,
determine_weak_authenticator_compliance_status

)

# Create router for fix endpoints
router = APIRouter()
logger = logging.getLogger(__name__)

# DEPENDENCY FUNCTIONS FOR VALIDATION
# =============================================================================

def validate_policy_id_dependency(policy_id: str) -> str:
    """Dependency to validate policy ID path parameter"""
    try:
        return validate_and_sanitize_policy_id(policy_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ADD THESE REQUEST SCHEMAS (since you have PolicyIdEnum in schemas.py)
class OptionalFixParameters(BaseModel):
    """Optional parameters for fix operations"""
    dry_run: bool = Field(default=False, description="Simulate without applying changes")
    force: bool = Field(default=False, description="Force fix even if compliant")
    notification_email: Optional[str] = Field(None, description="Email for notifications")

    @validator('notification_email')
    def validate_email(cls, v):
        if v:
            import re
            email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
            if not email_pattern.match(v.strip()):
                raise ValueError(f'Invalid email format: {v}')
            return v.strip().lower()
        return v


class MFAFixRequest(BaseModel):
    """Request parameters for MFA fixes"""
    exclude_emergency_accounts: bool = Field(default=True, description="Exclude emergency accounts")
    policy_name_suffix: Optional[str] = Field(None, max_length=50, description="Custom policy name suffix")
    target_users: Optional[List[str]] = Field(None, description="Specific user IDs to target")

    @validator('target_users')
    def validate_user_ids(cls, v):
        if v:
            import re
            guid_pattern = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
            valid_ids = []
            for user_id in v:
                if user_id.strip() and guid_pattern.match(user_id.strip()):
                    valid_ids.append(user_id.strip())
                else:
                    raise ValueError(f'Invalid user ID format: {user_id}')
            return valid_ids
        return v

@router.post("/FixCompliancePolicy/{policy_id}", response_model=GraphApiResponse, summary="Fix Compliance Policy by ID")
async def fix_compliance_policy(
        policy_id: str = Depends(validate_policy_id_dependency),
        credentials: tuple = Depends(get_client_credentials)
        ):

    """
    Main endpoint that routes to appropriate compliance fix function based on policy ID.

    Parameters:
    - policy_id: The policy ID to fix (e.g., 'policy-adminmfastatus')

    Usage:
    POST /api/FixCompliancePolicy/policy-adminmfastatus
    POST /api/FixCompliancePolicy/policy-usermfastatus
    """
    try:
        # policy_id is already validated and normalized by dependency
        logger.info(f"Executing validated fix for policy: {policy_id}")

        # Mapping of policy IDs to their corresponding fix functions
        POLICY_FIX_MAPPING = {
            # "policy-adminmfastatus": {
            #     "function": enable_mfa_for_all_admins,
            #     "name": "Admin MFA Status",
            #     "description": "Enable MFA for all administrators via Conditional Access policy"
            # },
            # "policy-usermfastatus": {
            #     "function": enable_mfa_for_all_users,
            #     "name": "User MFA Status",
            #     "description": "Enable MFA for all users via Conditional Access policy"
            # },
            "policy-sharepointexternalresharing": {
                "function": fix_sharepoint_external_resharing,
                "name": "SharePoint External Resharing",
                "description": "Fix SharePoint external sharing restrictions and disable anonymous access"
            },
            "policy-unifiedauditingstatus":{
                "function": fix_unified_auditing_status,
                "name": "Unified Logs Activity",
                "description": "Fix Unified Auditing Compliance Issues"
            },
            "policy-highriskuserspolicy": {
                "function": fix_high_risk_users_policies,
                "name": "High Risk Users Policy",
                "description": "Create Conditional Access policies to block high-risk users and enable security protection"
            },
            "policy-riskysigninpolicies": {
                "function": fix_risky_signin_policies,
                "name": "Risky Sign-In Policies",
                "description": "Enable Security Defaults to provide basic protection against risky sign-ins"
            },
            "policy-sharedmailboxsignin": {
                "function": fix_shared_mailbox_signin_status,
                "name": "Shared Mailbox Sign-In",
                "description": "Restrict or disable direct sign-in to shared mailboxes to improve security"
            },
            "policy-guestuseraccesspermissions": {
                "function": fix_guest_user_access_permissions,
                "name": "Guest User Access Permissions",
                "description": "Restrict guest invitation policies and limit guest user permissions for enhanced security"
            },
            "policy-sharepointsitecreation": {
                "function": fix_sharepoint_site_creation_status,
                "name": "SharePoint Site Creation",
                "description": "Restrict SharePoint site creation to require admin approval and prevent unauthorized site proliferation"
            },
            "policy-weakauthenticatorstatus": {
                "function": fix_weak_authenticator_status,
                "name": "Weak Authenticator Methods",
                "description": "Disable weak 2FA methods (SMS and Voice) and promote stronger authentication alternatives like authenticator apps"
            },
            "policy-passwordexpirationpolicy": {
                "function": fix_password_expiration_policy,
                "name": "Password Expiration Policy",
                "description": "Ensure password expiration is set to NIST-compliant values (never expires or valid range) to improve tenant security posture"
            },
            "policy-teamsexternalaccess":{
                "name": "fixTeamsExternalAccess",
                "function": fix_teams_external_access,
                "description": "Fix Teams External Access Policy by blocking external collaboration",
                "display_name": "Fix Teams External Access"
            }


            # Add more mappings as you create more POST endpoints:

        }

        # Validate policy ID
        if not policy_id:
            raise HTTPException(
                status_code=400,
                detail="Policy ID cannot be empty"
            )

        # Check if policy ID exists in mapping
        if policy_id not in POLICY_FIX_MAPPING:
            available_policies = list(POLICY_FIX_MAPPING.keys())
            logger.warning(f"Unsupported policy ID requested: {policy_id}")

            return GraphApiResponse(
                status_code=400,
                data={
                    "complianceStatus": "Failed to Fix",
                    "statusMessage": f"Unsupported policy ID: {policy_id}",
                    "recommendation": f"Use one of the supported policy IDs: {', '.join(available_policies)}",
                    "complianceDetails": {
                        "supportedPolicies": available_policies,
                        "requestedPolicy": policy_id,
                        "supportedPolicyDetails": {
                            pid: {"name": details["name"], "description": details["description"]}
                            for pid, details in POLICY_FIX_MAPPING.items()
                        }
                    },
                    "reportGeneratedAt": datetime.now().isoformat() + "Z"
                },
                error=f"Policy ID '{policy_id}' is not supported for automated fixing"
            )

        # Get the policy configuration
        policy_config = POLICY_FIX_MAPPING[policy_id]
        fix_function = policy_config["function"]
        policy_name = policy_config["name"]

        # Log the action
        logger.info(f"Executing fix for policy: {policy_id} ({policy_name})")

        # Call the appropriate fix function
        result = await fix_function(credentials=credentials)

        # Enhance the response with routing metadata
        if hasattr(result, 'data') and isinstance(result.data, dict):
            if "complianceDetails" not in result.data:
                result.data["complianceDetails"] = {}

            # Add metadata about which policy was fixed and how
            result.data["complianceDetails"]["policyFixMetadata"] = {
                "requestedPolicyId": policy_id,
                "policyName": policy_name,
                "functionCalled": fix_function.__name__,
                "routedVia": "fix_compliance_policy",
                "executionTimestamp": datetime.now().isoformat() + "Z"
            }

        logger.info(f"Successfully executed fix for policy: {policy_id}")
        return result

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Error in fix_compliance_policy for policy '{policy_id}': {str(e)}")
        return GraphApiResponse(
            status_code=500,
            data={
                "complianceStatus": "Failed to Fix",
                "statusMessage": "Internal error occurred while fixing compliance policy",
                "recommendation": "Check system logs and contact administrator if the issue persists",
                "complianceDetails": {
                    "requestedPolicy": policy_id,
                    "errorDetails": str(e),
                    "troubleshooting": [
                        "Verify the policy ID is correct",
                        "Check system permissions and authentication",
                        "Review server logs for detailed error information",
                        "Ensure the target system (Microsoft Graph API) is accessible"
                    ]
                },
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            },
            error=f"Internal server error while fixing policy '{policy_id}': {str(e)}"
        )


# @router.get("/GetSupportedFixPolicies", response_model=GraphApiResponse, summary="Get List of Supported Fix Policies")
# async def get_supported_fix_policies():
#     """
#     Returns list of policy IDs that support automated fixing.
#     Useful for frontend to determine which policies have fix functionality available.
#     """
#     try:
#         # Define supported policies (same as in fix function)
#         SUPPORTED_POLICIES = {
#             "policy-adminmfastatus": {
#                 "name": "Admin MFA Status",
#                 "description": "Enable MFA for all administrators via Conditional Access policy",
#                 "category": "Identity & Access Management",
#                 "riskLevel": "High",
#                 "estimatedTime": "2-5 minutes"
#             },
#             "policy-usermfastatus": {
#                 "name": "User MFA Status",
#                 "description": "Enable MFA for all users via Conditional Access policy",
#                 "category": "Identity & Access Management",
#                 "riskLevel": "Medium",
#                 "estimatedTime": "3-7 minutes"
#             }
#             # Add more as you create them
#         }
#
#         return GraphApiResponse(
#             status_code=200,
#             data={
#                 "supportedPolicies": SUPPORTED_POLICIES,
#                 "totalSupportedPolicies": len(SUPPORTED_POLICIES),
#                 "categories": list(set(policy["category"] for policy in SUPPORTED_POLICIES.values())),
#                 "usage": {
#                     "endpoint": "/api/FixCompliancePolicy/{policy_id}",
#                     "method": "POST",
#                     "examples": [
#                         "/api/FixCompliancePolicy/policy-adminmfastatus",
#                         "/api/FixCompliancePolicy/policy-usermfastatus"
#                     ]
#                 },
#                 "responseFormat": {
#                     "complianceStatus": "Fixed|Compliant|Failed to Fix|Not Measured",
#                     "statusMessage": "Human-readable description of the result",
#                     "recommendation": "Next steps or maintenance advice",
#                     "complianceDetails": "Detailed information about actions taken"
#                 }
#             }
#         )
#
#     except Exception as e:
#         logger.error(f"Error getting supported fix policies: {str(e)}")
#         return GraphApiResponse(
#             status_code=500,
#             data={},
#             error=f"Failed to retrieve supported policies: {str(e)}"
#         )
#post endpoint admin mfa
# POST operation for Admin MFA
# @router.post("/EnableMFAForAllAdmins", response_model=GraphApiResponse, summary="Enable MFA for All Administrators")
# async def enable_mfa_for_all_admins(credentials: tuple = Depends(get_client_credentials)):
#     """
#     Checks admin MFA status and creates Conditional Access policy
#     to require MFA for all administrative roles.
#     """
#     try:
#         # Extract client_id from credentials
#         identifier, identifier_type = credentials
#         if identifier_type == "ninjaone_org_id":
#             from app.core.database.supabase_services import supabase
#             response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
#             if not response.data or len(response.data) == 0:
#                 raise Exception(f"No client_id found for ninjaone_org_id: {identifier}")
#             client_id = response.data[0]['client_id']
#             if client_id is None:
#                 raise Exception(f"client_id is NULL for ninjaone_org_id: {identifier}")
#         else:
#             client_id = identifier
#             if client_id is None:
#                 raise Exception(f"client_id parameter is NULL")
#
#         # 1. Get current admin MFA status using existing function
#         admin_mfa_response = await get_admin_mfa_status(client_id)
#         if admin_mfa_response.status_code != 200:
#             return GraphApiResponse(
#                 status_code=admin_mfa_response.status_code,
#                 data={
#                     "complianceStatus": "Not Measured",
#                     "statusMessage": "Unable to retrieve admin MFA status",
#                     "recommendation": "Check system configuration and try again",
#                     "complianceDetails": None,
#                     "reportGeneratedAt": datetime.now().isoformat() + "Z"
#                 },
#                 error=f"Failed to retrieve admin MFA data: {admin_mfa_response.error}"
#             )
#
#         # Extract admin details from the compliance response
#         compliance_details = admin_mfa_response.data.get("complianceDetails", {})
#         admin_details = compliance_details.get("administratorDetails", [])
#         compliance_summary = compliance_details.get("complianceSummary", {})
#
#         # 2. Identify administrators without MFA
#         admins_without_mfa = [
#             admin for admin in admin_details
#             if not admin.get("hasMfaEnabled", False)
#         ]
#
#         total_admins = compliance_summary.get("totalAdministrators", len(admin_details))
#         non_compliant_count = len(admins_without_mfa)
#
#         # 3. If all admins already have MFA enabled
#         if not admins_without_mfa:
#             return GraphApiResponse(
#                 status_code=200,
#                 data={
#                     "complianceStatus": "Compliant",
#                     "statusMessage": f"All {total_admins} administrative accounts already have MFA enabled",
#                     "recommendation": "Current status is optimal. Continue monitoring admin accounts for MFA compliance",
#                     "complianceDetails": {
#                         "actionsTaken": ["No action needed - all administrators already compliant"],
#                         "totalAdministrators": total_admins,
#                         "administratorsFixed": 0,
#                         "administratorDetails": admin_details,
#                         "policyStatus": "No new policy required"
#                     },
#                     "reportGeneratedAt": datetime.now().isoformat() + "Z"
#                 }
#             )
#
#         # 4. Create Conditional Access policy for admin MFA
#         identifier, identifier_type = credentials
#
#         # Convert ninjaone_org_id to client_id for backward compatibility
#         if identifier_type == "ninjaone_org_id":
#             from app.core.database.supabase_services import supabase
#             response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
#             if not response.data or len(response.data) == 0:
#                 raise Exception(f"No client_id found for ninjaone_org_id: {identifier}")
#             client_id = response.data[0]['client_id']
#             if client_id is None:
#                 raise Exception(f"client_id is NULL for ninjaone_org_id: {identifier}")
#         else:
#             client_id = identifier
#             if client_id is None:
#                 raise Exception(f"client_id parameter is NULL")
#
#         token = await get_access_token(client_id)
#         headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
#
#         # Microsoft's built-in administrative role template IDs
#         CRITICAL_ADMIN_ROLE_IDS = [
#             "62e90394-69f5-4237-9190-012177145e10",  # Global Administrator
#             "194ae4cb-b126-40b2-bd5b-6091b380977d",  # Security Administrator
#             "e8611ab8-c189-46e8-94e1-60213ab1f814",  # Privileged Role Administrator
#             "c4e39bd9-1100-46d3-8c65-fb160da0071f",  # Authentication Administrator
#             "b1be1c3e-b65d-4f19-8427-f6fa0d97feb9",  # Conditional Access Administrator
#             "fe930be7-5e62-47db-91af-98c3a49a38b1",  # User Administrator
#             "29232cdf-9323-42fd-ade2-1d097af3e4de",  # Exchange Administrator
#             "f28a1f50-f6e7-4571-818b-6a12f2af6b6c",  # SharePoint Administrator
#             "729827e3-9c14-49f7-bb1b-9608f156bbb8",  # Helpdesk Administrator
#             "966707d0-3269-4727-9be2-8c3a10f19b9d"  # Password Administrator
#         ]
#
#         ca_policy_url = f"{GRAPH_BETA_URL}/identity/conditionalAccess/policies"
#
#         # 5. Check if admin MFA policy already exists
#         existing_policies_url = f"{GRAPH_BETA_URL}/identity/conditionalAccess/policies"
#         async with httpx.AsyncClient() as client:
#             existing_response = await client.get(existing_policies_url, headers=headers, timeout=30.0)
#             existing_response.raise_for_status()
#             existing_policies = existing_response.json().get("value", [])
#
#         # Look for existing admin MFA policies
#         admin_mfa_policy_exists = any(
#             "admin" in policy.get("displayName", "").lower() and "mfa" in policy.get("displayName", "").lower()
#             for policy in existing_policies
#         )
#
#         policy_action = "Updated existing policy" if admin_mfa_policy_exists else "Created new policy"
#
#         # 6. Create the Conditional Access policy
#         policy_body = {
#             "displayName": "Require MFA for Administrators - AutoCreated",
#             "state": "enabled",
#             "conditions": {
#                 "users": {
#                     "includeRoles": CRITICAL_ADMIN_ROLE_IDS
#                 },
#                 "applications": {
#                     "includeApplications": ["All"]
#                 },
#                 "platforms": {
#                     "includePlatforms": ["All"]
#                 }
#             },
#             "grantControls": {
#                 "operator": "OR",
#                 "builtInControls": ["mfa"]
#             },
#             "sessionControls": None
#         }
#
#         async with httpx.AsyncClient() as client:
#             ca_response = await client.post(ca_policy_url, headers=headers, json=policy_body, timeout=30.0)
#             ca_response.raise_for_status()
#             created_policy = ca_response.json()
#
#         # 7. Build success response
#         return GraphApiResponse(
#             status_code=200,
#             data={
#                 "complianceStatus": "Fixed",
#                 "statusMessage": f"MFA requirement enabled for all {total_admins} administrators via Conditional Access policy",
#                 "recommendation": "Administrators will be prompted to register MFA on their next sign-in. Monitor compliance over the next 24-48 hours",
#                 "complianceDetails": {
#                     "actionsTaken": [
#                         f"{policy_action}: 'Require MFA for Administrators'",
#                         f"Applied MFA requirement to {total_admins} administrator accounts",
#                         f"Targeted {non_compliant_count} non-compliant administrators"
#                     ],
#                     "totalAdministrators": total_admins,
#                     "administratorsFixed": non_compliant_count,
#                     "nonCompliantAdmins": [
#                         {
#                             "userPrincipalName": admin["userPrincipalName"],
#                             "displayName": admin["displayName"],
#                             "roles": admin["administrativeRoles"]
#                         }
#                         for admin in admins_without_mfa
#                     ],
#                     "policyDetails": {
#                         "policyId": created_policy.get("id"),
#                         "policyName": created_policy.get("displayName"),
#                         "state": created_policy.get("state"),
#                         "targetedRoles": len(CRITICAL_ADMIN_ROLE_IDS)
#                     }
#                 },
#                 "reportGeneratedAt": datetime.now().isoformat() + "Z"
#             }
#         )
#
#     except httpx.HTTPStatusError as exc:
#         logger.error(f"Graph API HTTP error: {exc.response.status_code} - {exc.response.text}")
#         return GraphApiResponse(
#             status_code=exc.response.status_code,
#             data={
#                 "complianceStatus": "Failed to Fix",
#                 "statusMessage": f"Unable to create admin MFA policy: HTTP {exc.response.status_code}",
#                 "recommendation": "Check Conditional Access permissions and try again",
#                 "complianceDetails": None,
#                 "reportGeneratedAt": datetime.now().isoformat() + "Z"
#             },
#             error=f"Graph API error: {exc.response.text}"
#         )
#     except Exception as e:
#         logger.error(f"Error enabling admin MFA: {str(e)}")
#         return GraphApiResponse(
#             status_code=500,
#             data={
#                 "complianceStatus": "Failed to Fix",
#                 "statusMessage": "Unable to enable MFA for administrators due to system error",
#                 "recommendation": "Check system configuration and try again",
#                 "complianceDetails": None,
#                 "reportGeneratedAt": datetime.now().isoformat() + "Z"
#             },
#             error=f"Failed to enable admin MFA: {str(e)}"
#         )
# # POST operation for User MFA
# @router.post("/EnableMFAForAllUsers", response_model=GraphApiResponse, summary="Enable MFA for All Users")
# async def enable_mfa_for_all_users(credentials: tuple = Depends(get_client_credentials)):
#     """
#     Checks user MFA status and creates Conditional Access policy
#     to require MFA for all users in the organization.
#     """
#     try:
#         # Extract client_id from credentials
#         identifier, identifier_type = credentials
#         if identifier_type == "ninjaone_org_id":
#             from app.core.database.supabase_services import supabase
#             response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
#             if not response.data or len(response.data) == 0:
#                 raise Exception(f"No client_id found for ninjaone_org_id: {identifier}")
#             client_id = response.data[0]['client_id']
#             if client_id is None:
#                 raise Exception(f"client_id is NULL for ninjaone_org_id: {identifier}")
#         else:
#             client_id = identifier
#             if client_id is None:
#                 raise Exception(f"client_id parameter is NULL")
#
#         # 1. Get current user MFA status using existing function
#         user_mfa_response = await get_user_mfa_status(client_id)
#         if user_mfa_response.status_code != 200:
#             return GraphApiResponse(
#                 status_code=user_mfa_response.status_code,
#                 data={
#                     "complianceStatus": "Not Measured",
#                     "statusMessage": "Unable to retrieve user MFA status",
#                     "recommendation": "Check system configuration and try again",
#                     "complianceDetails": None,
#                     "reportGeneratedAt": datetime.now().isoformat() + "Z"
#                 },
#                 error=f"Failed to retrieve user MFA data: {user_mfa_response.error}"
#             )
#
#         # Extract user details from the compliance response
#         compliance_details = user_mfa_response.data.get("complianceDetails", {})
#         user_details = compliance_details.get("user_details", [])
#
#         total_users = compliance_details.get("total_users", len(user_details))
#         mfa_enabled_users = compliance_details.get("mfa_enabled", 0)
#         mfa_disabled_users = compliance_details.get("mfa_disabled", 0)
#
#         # 2. Identify users without MFA
#         users_without_mfa = [
#             user for user in user_details
#             if not (
#                     user.get("isMfaRegistered", False) or
#                     user.get("conditionalAccessCovered", False) or
#                     user.get("securityDefaultsEnabled", False) or
#                     user.get("perUserMfaState", "").lower() in ["enabled", "enforced"]
#             )
#         ]
#
#         non_compliant_count = len(users_without_mfa)
#
#         # 3. If all users already have MFA enabled
#         if not users_without_mfa:
#             return GraphApiResponse(
#                 status_code=200,
#                 data={
#                     "complianceStatus": "Compliant",
#                     "statusMessage": f"All {total_users} users already have MFA enabled",
#                     "recommendation": "Current status is optimal. Continue monitoring user accounts for MFA compliance",
#                     "complianceDetails": {
#                         "actionsTaken": ["No action needed - all users already compliant"],
#                         "totalUsers": total_users,
#                         "usersFixed": 0,
#                         "userDetails": user_details,
#                         "policyStatus": "No new policy required"
#                     },
#                     "reportGeneratedAt": datetime.now().isoformat() + "Z"
#                 }
#             )
#
#         # 4. Create Conditional Access policy for user MFA
#         identifier, identifier_type = credentials
#
#         # Convert ninjaone_org_id to client_id for backward compatibility
#         if identifier_type == "ninjaone_org_id":
#             from app.core.database.supabase_services import supabase
#             response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
#             if not response.data or len(response.data) == 0:
#                 raise Exception(f"No client_id found for ninjaone_org_id: {identifier}")
#             client_id = response.data[0]['client_id']
#             if client_id is None:
#                 raise Exception(f"client_id is NULL for ninjaone_org_id: {identifier}")
#         else:
#             client_id = identifier
#             if client_id is None:
#                 raise Exception(f"client_id parameter is NULL")
#
#         token = await get_access_token(client_id)
#         headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
#
#         ca_policy_url = f"{GRAPH_BETA_URL}/identity/conditionalAccess/policies"
#
#         # 5. Check if user MFA policy already exists
#         existing_policies_url = f"{GRAPH_BETA_URL}/identity/conditionalAccess/policies"
#         async with httpx.AsyncClient() as client:
#             existing_response = await client.get(existing_policies_url, headers=headers, timeout=30.0)
#             existing_response.raise_for_status()
#             existing_policies = existing_response.json().get("value", [])
#
#         # Look for existing user MFA policies
#         user_mfa_policy_exists = any(
#             "all users" in policy.get("displayName", "").lower() and "mfa" in policy.get("displayName", "").lower()
#             for policy in existing_policies
#         )
#
#         policy_action = "Updated existing policy" if user_mfa_policy_exists else "Created new policy"
#
#         # 6. Create the Conditional Access policy
#         policy_body = {
#             "displayName": "Require MFA for All Users - AutoCreated",
#             "state": "enabled",
#             "conditions": {
#                 "users": {
#                     "includeUsers": ["All"]
#                 },
#                 "applications": {
#                     "includeApplications": ["All"]
#                 },
#                 "platforms": {
#                     "includePlatforms": ["All"]
#                 }
#             },
#             "grantControls": {
#                 "operator": "OR",
#                 "builtInControls": ["mfa"]
#             },
#             "sessionControls": None
#         }
#
#         async with httpx.AsyncClient() as client:
#             ca_response = await client.post(ca_policy_url, headers=headers, json=policy_body, timeout=30.0)
#             ca_response.raise_for_status()
#             created_policy = ca_response.json()
#
#         # 7. Build success response
#         return GraphApiResponse(
#             status_code=200,
#             data={
#                 "complianceStatus": "Fixed",
#                 "statusMessage": f"MFA requirement enabled for all {total_users} users via Conditional Access policy",
#                 "recommendation": "Users will be prompted to register MFA on their next sign-in. Monitor compliance over the next 24-48 hours",
#                 "complianceDetails": {
#                     "actionsTaken": [
#                         f"{policy_action}: 'Require MFA for All Users'",
#                         f"Applied MFA requirement to {total_users} user accounts",
#                         f"Targeted {non_compliant_count} non-compliant users"
#                     ],
#                     "totalUsers": total_users,
#                     "usersFixed": non_compliant_count,
#                     "nonCompliantUsers": [
#                         {
#                             "userPrincipalName": user["userPrincipalName"],
#                             "displayName": user["displayName"],
#                             "currentMfaStatus": {
#                                 "isMfaRegistered": user.get("isMfaRegistered", False),
#                                 "conditionalAccessCovered": user.get("conditionalAccessCovered", False),
#                                 "securityDefaultsEnabled": user.get("securityDefaultsEnabled", False)
#                             }
#                         }
#                         for user in users_without_mfa[:10]  # Limit to first 10 for brevity
#                     ],
#                     "policyDetails": {
#                         "policyId": created_policy.get("id"),
#                         "policyName": created_policy.get("displayName"),
#                         "state": created_policy.get("state"),
#                         "targetedUsers": "All users"
#                     },
#                     "summary": {
#                         "totalUsersTargeted": total_users,
#                         "previouslyCompliantUsers": mfa_enabled_users,
#                         "newlyProtectedUsers": non_compliant_count
#                     }
#                 },
#                 "reportGeneratedAt": datetime.now().isoformat() + "Z"
#             }
#         )
#
#     except httpx.HTTPStatusError as exc:
#         logger.error(f"Graph API HTTP error: {exc.response.status_code} - {exc.response.text}")
#         return GraphApiResponse(
#             status_code=exc.response.status_code,
#             data={
#                 "complianceStatus": "Failed to Fix",
#                 "statusMessage": f"Unable to create user MFA policy: HTTP {exc.response.status_code}",
#                 "recommendation": "Check Conditional Access permissions and try again",
#                 "complianceDetails": None,
#                 "reportGeneratedAt": datetime.now().isoformat() + "Z"
#             },
#             error=f"Graph API error: {exc.response.text}"
#         )
#     except Exception as e:
#         logger.error(f"Error enabling user MFA: {str(e)}")
#         return GraphApiResponse(
#             status_code=500,
#             data={
#                 "complianceStatus": "Failed to Fix",
#                 "statusMessage": "Unable to enable MFA for users due to system error",
#                 "recommendation": "Check system configuration and try again",
#                 "complianceDetails": None,
#                 "reportGeneratedAt": datetime.now().isoformat() + "Z"
#             },
#             error=f"Failed to enable user MFA: {str(e)}"
#         )


# POST operation for SharePoint External Resharing
@router.post("/FixSharePointExternalResharing", summary="Fix SharePoint External Resharing Policy")
async def fix_sharepoint_external_resharing(credentials: tuple = Depends(get_client_credentials)):
    """
    Fixes SharePoint external resharing compliance by applying security restrictions
    based on current compliance status. Handles Not Compliant and Partially Compliant scenarios.
    """
    try:
        # Extract client_id from credentials
        identifier, identifier_type = credentials
        # TODO: migrate to SQLAlchemy — organization_mapping table not in schema.sql, confirm model before replacing
        if identifier_type == "ninjaone_org_id":
            from app.core.database.supabase_services import supabase
            response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
            if not response.data or len(response.data) == 0:
                raise Exception(f"No client_id found for ninjaone_org_id: {identifier}")
            client_id = response.data[0]['client_id']
            if client_id is None:
                raise Exception(f"client_id is NULL for ninjaone_org_id: {identifier}")
        else:
            client_id = identifier
            if client_id is None:
                raise Exception(f"client_id parameter is NULL")

        # 1. Get current SharePoint external resharing status
        current_status_response = await list_sharepoint_external_resharing_status(client_id)
        if current_status_response.status_code != 200:
            return {
                "status_code": current_status_response.status_code,
                "data": {
                    "complianceStatus": "Not Measured",
                    "statusMessage": "Unable to retrieve SharePoint external resharing status",
                    "recommendation": "Check SharePoint admin permissions and try again",
                    "complianceDetails": {
                        "actionsTaken": [],
                        "summary": {},
                        "userDetails": [],
                        "policyDetails": {}
                    },
                    "reportGeneratedAt": datetime.now().isoformat() + "Z"
                },
                "error": f"Failed to retrieve SharePoint status: {current_status_response.error}"
            }

        # Extract current settings from response
        compliance_details = current_status_response.data.get("complianceDetails", {})
        current_settings = compliance_details.get("sharepointExternalResharingSettings", {})
        current_status = current_status_response.data.get("complianceStatus", "")

        is_resharing_enabled = current_settings.get("isResharingByExternalUsersEnabled")
        sharing_capability = current_settings.get("sharingCapability")
        domain_restriction_mode = current_settings.get("sharingDomainRestrictionMode")
        allowed_domains = current_settings.get("sharingAllowedDomainList", [])

        # 2. If already compliant, no action needed
        if current_status == "Compliant":
            return {
                "status_code": 200,
                "data": {
                    "complianceStatus": "Compliant",
                    "statusMessage": "SharePoint external sharing is already properly configured",
                    "recommendation": "Continue monitoring sharing settings and review periodically",
                    "complianceDetails": {
                        "actionsTaken": [
                            {
                                "action": "No action needed - already compliant",
                                "status": "completed",
                                "details": "SharePoint external sharing configuration meets compliance requirements",
                                "timestamp": datetime.now().isoformat() + "Z"
                            }
                        ],
                        "summary": {
                            "previousStatus": "Compliant",
                            "currentStatus": "Compliant",
                            "settingsChanged": 0,
                            "totalActionsAttempted": 0,
                            "successfulActions": 0
                        },
                        "userDetails": [],
                        "policyDetails": current_settings
                    },
                    "reportGeneratedAt": datetime.now().isoformat() + "Z"
                },
                "error": None
            }

        # 3. Prepare for remediation
        identifier, identifier_type = credentials

        # Convert ninjaone_org_id to client_id for backward compatibility
        # TODO: migrate to SQLAlchemy — organization_mapping table not in schema.sql, confirm model before replacing
        if identifier_type == "ninjaone_org_id":
            from app.core.database.supabase_services import supabase
            response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
            if not response.data or len(response.data) == 0:
                raise Exception(f"No client_id found for ninjaone_org_id: {identifier}")
            client_id = response.data[0]['client_id']
            if client_id is None:
                raise Exception(f"client_id is NULL for ninjaone_org_id: {identifier}")
        else:
            client_id = identifier
            if client_id is None:
                raise Exception(f"client_id parameter is NULL")

        token = await get_access_token(client_id)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        sharepoint_settings_url = f"{GRAPH_BETA_URL}/admin/sharepoint/settings"
        actions_taken = []
        settings_to_update = {}

        # 4. Apply fixes based on current compliance issues

        # Handle "Not Compliant" - External sharing enabled without restrictions
        if (is_resharing_enabled and
                (domain_restriction_mode is None or
                 domain_restriction_mode == "" or
                 domain_restriction_mode.lower() in ["none", "null"])):
            # Disable external resharing completely
            settings_to_update["isResharingByExternalUsersEnabled"] = False
            actions_taken.append({
                "action": "Disable external resharing",
                "status": "planned",
                "details": "Disabled external resharing by external users",
                "timestamp": datetime.now().isoformat() + "Z"
            })

        # Handle "Not Compliant" - Anonymous sharing capability
        if sharing_capability in ["Anyone", "AnonymousAndExternalUserSharing"]:
            # Change to more restrictive sharing
            settings_to_update["sharingCapability"] = "ExistingExternalUserSharingOnly"
            actions_taken.append({
                "action": "Restrict sharing capability",
                "status": "planned",
                "details": f"Changed sharing capability from '{sharing_capability}' to 'ExistingExternalUserSharingOnly'",
                "timestamp": datetime.now().isoformat() + "Z"
            })

        # Handle "Partially Compliant" scenarios
        if current_status == "Partially Compliant":

            # Too many allowed domains (>5) - Don't remove domains, apply stricter controls
            if (isinstance(allowed_domains, list) and len(allowed_domains) > 5 and
                    domain_restriction_mode and domain_restriction_mode.lower() == "allowlist"):

                # Keep domains but disable anonymous sharing if not already done
                if sharing_capability not in ["ExistingExternalUserSharingOnly",
                                              "ExistingExternalUserSharingOnlyWithAccess"]:
                    settings_to_update["sharingCapability"] = "ExistingExternalUserSharingOnly"
                    actions_taken.append({
                        "action": "Apply stricter sharing controls",
                        "status": "planned",
                        "details": "Applied stricter sharing controls (existing external users only)",
                        "timestamp": datetime.now().isoformat() + "Z"
                    })

                actions_taken.append({
                    "action": "Flag domains for review",
                    "status": "completed",
                    "details": f"Flagged {len(allowed_domains)} domains for manual review (recommended max: 5)",
                    "timestamp": datetime.now().isoformat() + "Z"
                })

        # 5. Apply the settings changes if any
        if settings_to_update:
            async with httpx.AsyncClient() as client:
                patch_response = await client.patch(
                    sharepoint_settings_url,
                    headers=headers,
                    json=settings_to_update,
                    timeout=30.0
                )
                patch_response.raise_for_status()
                updated_settings = patch_response.json()

            # Update action statuses to success
            for action in actions_taken:
                if action.get("status") == "planned":
                    action["status"] = "success"

            # 6. Determine final status
            final_status = "Compliant"  # Changed from "Fixed"
            status_message = f"SharePoint external sharing restrictions applied successfully"
            recommendation = "Monitor sharing activities and review settings monthly"

            # Special handling for partially compliant with too many domains
            if len(allowed_domains) > 5 and domain_restriction_mode and domain_restriction_mode.lower() == "allowlist":
                final_status = "Partially Compliant"  # Changed from "Partially Fixed"
                status_message = f"Applied security restrictions but {len(allowed_domains)} domains require manual review"
                recommendation = "Review and reduce allowed domains to 3-5 most critical business partners"

        else:
            # No settings to update (shouldn't happen, but handle gracefully)
            final_status = "Failed to Fix"
            status_message = "No applicable fixes found for current configuration"
            recommendation = "Manual review required for this specific configuration"
            actions_taken.append({
                "action": "Analyze configuration",
                "status": "failed",
                "details": "No automatic fixes available for current settings",
                "timestamp": datetime.now().isoformat() + "Z"
            })

        # 7. Build success response
        return {
            "status_code": 200,
            "data": {
                "complianceStatus": final_status,
                "statusMessage": status_message,
                "recommendation": recommendation,
                "complianceDetails": {
                    "actionsTaken": actions_taken,
                    "summary": {
                        "previousStatus": current_status,
                        "currentStatus": final_status,
                        "settingsChanged": len(settings_to_update),
                        "totalActionsAttempted": len(actions_taken),
                        "successfulActions": len([a for a in actions_taken if a.get("status") == "success"]),
                        "failedActions": len([a for a in actions_taken if a.get("status") == "failed"])
                    },
                    "userDetails": [],
                    "policyDetails": {
                        "originalSettings": current_settings,
                        "updatedSettings": settings_to_update,
                        "domainReviewRequired": len(allowed_domains) > 5 if isinstance(allowed_domains, list) else False,
                        "domainCount": len(allowed_domains) if isinstance(allowed_domains, list) else 0
                    }
                },
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            },
            "error": None
        }

    except httpx.HTTPStatusError as exc:
        logger.error(f"Graph API HTTP error: {exc.response.status_code} - {exc.response.text}")
        return {
            "status_code": exc.response.status_code,
            "data": {
                "complianceStatus": "Failed to Fix",
                "statusMessage": f"Unable to update SharePoint settings: HTTP {exc.response.status_code}",
                "recommendation": "Check SharePoint admin permissions and try again",
                "complianceDetails": {
                    "actionsTaken": [
                        {
                            "action": "Update SharePoint settings",
                            "status": "failed",
                            "details": f"HTTP {exc.response.status_code}: {exc.response.text}",
                            "timestamp": datetime.now().isoformat() + "Z"
                        }
                    ],
                    "summary": {"error": f"HTTP {exc.response.status_code}"},
                    "userDetails": [],
                    "policyDetails": {}
                },
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            },
            "error": f"Graph API error: {exc.response.text}"
        }
    except Exception as e:
        logger.error(f"Error fixing SharePoint external resharing: {str(e)}")
        return {
            "status_code": 500,
            "data": {
                "complianceStatus": "Failed to Fix",
                "statusMessage": "Internal error occurred while fixing SharePoint external sharing",
                "recommendation": "Check system logs and contact administrator if issue persists",
                "complianceDetails": {
                    "actionsTaken": [
                        {
                            "action": "Fix SharePoint external resharing",
                            "status": "failed",
                            "details": f"Internal error: {str(e)}",
                            "timestamp": datetime.now().isoformat() + "Z"
                        }
                    ],
                    "summary": {"error": str(e)},
                    "userDetails": [],
                    "policyDetails": {}
                },
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            },
            "error": f"Failed to fix SharePoint external resharing: {str(e)}"
        }


@router.post("/FixUnifiedAuditingStatus", summary="Fix Unified Auditing Compliance Issues")
async def fix_unified_auditing_status(credentials: tuple = Depends(get_client_credentials)):
    """
    Attempts to remediate unified auditing compliance issues using Graph API only.
    Limited by Business Basic license - cannot access audit logs or modify audit configuration.
    """
    actions_taken = []

    try:
        identifier, identifier_type = credentials

        # Convert ninjaone_org_id to client_id for backward compatibility
        # TODO: migrate to SQLAlchemy — organization_mapping table not in schema.sql, confirm model before replacing
        if identifier_type == "ninjaone_org_id":
            from app.core.database.supabase_services import supabase
            response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
            if not response.data or len(response.data) == 0:
                raise Exception(f"No client_id found for ninjaone_org_id: {identifier}")
            client_id = response.data[0]['client_id']
            if client_id is None:
                raise Exception(f"client_id is NULL for ninjaone_org_id: {identifier}")
        else:
            client_id = identifier
            if client_id is None:
                raise Exception(f"client_id parameter is NULL")

        token = await get_access_token(client_id)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        # Check if we can access basic organization info (Business Basic compatible)
        org_access_result = await test_organization_access(token, headers, actions_taken)

        if org_access_result["has_access"]:
            result = {
                "status": "Partially Compliant",
                "message": "Basic Graph API access confirmed but audit logs require E3+ license",
                "recommendation": "Upgrade to Microsoft 365 E3 or higher for unified audit logging capabilities"
            }
        else:
            result = {
                "status": "Failed to Fix",
                "message": "Unable to access Graph API endpoints for audit verification",
                "recommendation": "Check Graph API permissions and try again"
            }

        return {
            "status_code": 200,
            "data": {
                "complianceStatus": result["status"],
                "statusMessage": result["message"],
                "recommendation": result["recommendation"],
                "complianceDetails": {
                    "actionsTaken": actions_taken,
                    "summary": {
                        "totalActionsAttempted": len(actions_taken),
                        "successfulActions": len([a for a in actions_taken if a.get("status") == "success"]),
                        "businessBasicLimitation": "Audit logs require Microsoft 365 E3+ license",
                        "graphApiLimitations": "Cannot modify audit configuration via Graph API"
                    },
                    "userDetails": [],
                    "policyDetails": {
                        "auditingRequirement": "Microsoft 365 E3+ license",
                        "currentLicenseCapability": "Business Basic - no audit log access",
                        "upgradeRecommendation": "E3+ for unified audit logging"
                    }
                },
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            },
            "error": None
        }

    except Exception as e:
        logger.error(f"Error fixing unified auditing: {str(e)}")
        return {
            "status_code": 200,
            "data": {
                "complianceStatus": "Failed to Fix",
                "statusMessage": f"Error: {str(e)}",
                "recommendation": "Check Graph API permissions and try again",
                "complianceDetails": {
                    "actionsTaken": actions_taken,
                    "summary": {"error": str(e)},
                    "userDetails": [],
                    "policyDetails": {}
                },
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            },
            "error": str(e)
        }


async def test_organization_access(token: str, headers: dict, actions_taken: list) -> dict:
    """Test basic Graph API access that works with Business Basic license"""

    actions_taken.append({
        "action": "Test basic Graph API access",
        "status": "started",
        "details": "Testing access to basic Graph API endpoints",
        "timestamp": datetime.now().isoformat() + "Z"
    })

    # Test Business Basic compatible endpoints only
    basic_endpoints = [
        {"name": "Current user", "url": f"{GRAPH_V1_URL}/me"},
        {"name": "Organization info", "url": f"{GRAPH_V1_URL}/organization"},
        {"name": "Users list", "url": f"{GRAPH_V1_URL}/users", "params": {"$top": 1}},
    ]

    successful_calls = 0

    async with httpx.AsyncClient() as client:
        for endpoint in basic_endpoints:
            try:
                response = await client.get(
                    endpoint["url"],
                    headers=headers,
                    params=endpoint.get("params", {}),
                    timeout=30.0
                )
                response.raise_for_status()
                successful_calls += 1

                actions_taken.append({
                    "action": f"Test {endpoint['name']} access",
                    "status": "success",
                    "details": f"Successfully accessed {endpoint['name']} endpoint",
                    "timestamp": datetime.now().isoformat() + "Z"
                })

                await asyncio.sleep(1)  # Small delay between calls

            except Exception as e:
                actions_taken.append({
                    "action": f"Test {endpoint['name']} access",
                    "status": "failed",
                    "details": f"Failed to access {endpoint['name']}: {str(e)}",
                    "timestamp": datetime.now().isoformat() + "Z"
                })

    # Test audit log access (will likely fail with Business Basic but document the limitation)
    actions_taken.append({
        "action": "Test audit log access",
        "status": "started",
        "details": "Testing audit log endpoint (requires E3+ license)",
        "timestamp": datetime.now().isoformat() + "Z"
    })

    try:
        audit_url = f"{GRAPH_V1_URL}/auditLogs/directoryAudits"
        async with httpx.AsyncClient() as client:
            response = await client.get(
                audit_url,
                headers=headers,
                params={"$top": 1},
                timeout=30.0
            )
            response.raise_for_status()

        actions_taken.append({
            "action": "Test audit log access",
            "status": "success",
            "details": "Audit logs accessible - license supports unified auditing",
            "timestamp": datetime.now().isoformat() + "Z"
        })

    except Exception as e:
        actions_taken.append({
            "action": "Test audit log access",
            "status": "failed",
            "details": f"Audit logs not accessible - likely due to license limitation: {str(e)}",
            "timestamp": datetime.now().isoformat() + "Z"
        })

    actions_taken.append({
        "action": "Complete Graph API access test",
        "status": "completed",
        "details": f"Successfully accessed {successful_calls}/{len(basic_endpoints)} basic endpoints",
        "timestamp": datetime.now().isoformat() + "Z"
    })

    return {
        "has_access": successful_calls > 0,
        "successful_endpoints": successful_calls,
        "total_endpoints": len(basic_endpoints)
    }

@router.post("/FixHighRiskUsersPolicies", summary="Fix High Risk Users Policy Compliance Issues")
async def fix_high_risk_users_policies(credentials: tuple = Depends(get_client_credentials)):
    """
    Attempts to remediate high-risk users policy compliance by enabling Security Defaults.
    Limited to Business Basic license capabilities - no Conditional Access policy creation.
    """
    actions_taken = []

    try:
        identifier, identifier_type = credentials

        # Convert ninjaone_org_id to client_id for backward compatibility
        # TODO: migrate to SQLAlchemy — organization_mapping table not in schema.sql, confirm model before replacing
        if identifier_type == "ninjaone_org_id":
            from app.core.database.supabase_services import supabase
            response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
            if not response.data or len(response.data) == 0:
                raise Exception(f"No client_id found for ninjaone_org_id: {identifier}")
            client_id = response.data[0]['client_id']
            if client_id is None:
                raise Exception(f"client_id is NULL for ninjaone_org_id: {identifier}")
        else:
            client_id = identifier
            if client_id is None:
                raise Exception(f"client_id parameter is NULL")

        token = await get_access_token(client_id)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "application/json"}

        # Get current Security Defaults status (skip CA policies - requires Business Premium)
        current_status = await get_current_security_defaults_status(token, headers)

        if current_status["security_defaults_enabled"]:
            result = {
                "status": "Compliant",
                "message": "Security Defaults enabled - provides basic high-risk user protection",
                "recommendation": "Consider upgrading to Business Premium for advanced Conditional Access policies"
            }
        else:
            # Try to enable Security Defaults
            result = await fix_high_risk_with_security_defaults(token, headers, actions_taken)

        return {
            "status_code": 200,
            "data": {
                "complianceStatus": result["status"],
                "statusMessage": result["message"],
                "recommendation": result["recommendation"],
                "complianceDetails": {
                    "actionsTaken": actions_taken,
                    "summary": {
                        "totalActionsAttempted": len(actions_taken),
                        "successfulActions": len([a for a in actions_taken if a.get("status") == "success"]),
                        "businessBasicLimitation": "Conditional Access policies require Business Premium or E3+ license"
                    },
                    "userDetails": [],
                    "policyDetails": {
                        "availableProtection": "Security Defaults (Basic MFA and security protection)",
                        "unavailableFeatures": "Conditional Access policies for specific high-risk users",
                        "upgradeRecommendation": "Business Premium or E3+ for advanced high-risk user controls"
                    }
                },
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            },
            "error": None
        }

    except Exception as e:
        logger.error(f"Error fixing high-risk user policies: {str(e)}")
        return {
            "status_code": 200,
            "data": {
                "complianceStatus": "Failed to Fix",
                "statusMessage": f"Error: {str(e)}",
                "recommendation": "Check permissions and try again",
                "complianceDetails": {
                    "actionsTaken": actions_taken,
                    "summary": {"error": str(e)},
                    "userDetails": [],
                    "policyDetails": {}
                },
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            },
            "error": str(e)
        }


async def fix_high_risk_with_security_defaults(token: str, headers: dict, actions_taken: list) -> dict:
    """Fix high-risk user compliance using only Security Defaults (Business Basic compatible)"""

    actions_taken.append({
        "action": "Enable Security Defaults for high-risk user protection",
        "status": "started",
        "details": "Attempting to enable Security Defaults to provide basic protection for high-risk users",
        "timestamp": datetime.now().isoformat() + "Z"
    })

    # Try to enable Security Defaults
    sd_result = await enable_security_defaults(token, headers)

    if sd_result["success"]:
        actions_taken.append({
            "action": "Enable Security Defaults",
            "status": "success",
            "details": "Successfully enabled Security Defaults - provides MFA requirements and basic security protection",
            "timestamp": datetime.now().isoformat() + "Z"
        })

        return {
            "status": "Compliant",
            "message": "Enabled Security Defaults for basic high-risk user protection",
            "recommendation": "Security Defaults provides basic protection. Upgrade to Business Premium for advanced high-risk user policies"
        }
    else:
        actions_taken.append({
            "action": "Enable Security Defaults",
            "status": "failed",
            "details": f"Failed to enable Security Defaults: {sd_result['message']}",
            "timestamp": datetime.now().isoformat() + "Z"
        })

        return {
            "status": "Failed to Fix",
            "message": "Unable to enable Security Defaults for high-risk user protection",
            "recommendation": "Check Policy.ReadWrite.SecurityDefaults permission or manually enable in Azure AD portal"
        }


async def enable_security_defaults(token: str, headers: dict) -> dict:
    """Enable Security Defaults - compatible with Business Basic license"""

    try:
        sd_url = f"{GRAPH_BETA_URL}/policies/identitySecurityDefaultsEnforcementPolicy"

        async with httpx.AsyncClient() as client:
            response = await client.patch(
                sd_url,
                headers=headers,
                json={"isEnabled": True},
                timeout=30.0
            )
            response.raise_for_status()

        return {
            "success": True,
            "message": "Security Defaults enabled successfully"
        }

    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }


async def get_current_security_defaults_status(token: str, headers: dict) -> dict:
    """Get current Security Defaults status - compatible with Business Basic license"""

    try:
        # Only check Security Defaults (skip CA policies - requires Business Premium)
        sd_url = f"{GRAPH_BETA_URL}/policies/identitySecurityDefaultsEnforcementPolicy"
        sd_params = {"$select": "isEnabled"}

        async with httpx.AsyncClient() as client:
            sd_response = await client.get(sd_url, headers=headers, params=sd_params, timeout=30.0)
            sd_response.raise_for_status()
            sd_data = sd_response.json()

        security_defaults_enabled = sd_data.get("isEnabled", False)

        return {
            "security_defaults_enabled": security_defaults_enabled,
            "status_message": "Security Defaults enabled" if security_defaults_enabled else "Security Defaults disabled"
        }

    except Exception as e:
        return {
            "security_defaults_enabled": False,
            "status_message": f"Error checking Security Defaults: {str(e)}"
        }


@router.post("/FixRiskySignInPolicies", summary="Fix Risky Sign-In Policy Compliance Issues")
async def fix_risky_signin_policies(credentials: tuple = Depends(get_client_credentials)):
    """
    Attempts to remediate risky sign-in policy compliance by enabling Security Defaults.
    Limited to Business Basic license capabilities - no Conditional Access policy creation.
    """
    actions_taken = []

    try:
        # Extract client_id from credentials
        identifier, identifier_type = credentials
        # TODO: migrate to SQLAlchemy — organization_mapping table not in schema.sql, confirm model before replacing
        if identifier_type == "ninjaone_org_id":
            from app.core.database.supabase_services import supabase
            response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
            if not response.data or len(response.data) == 0:
                raise Exception(f"No client_id found for ninjaone_org_id: {identifier}")
            client_id = response.data[0]['client_id']
            if client_id is None:
                raise Exception(f"client_id is NULL for ninjaone_org_id: {identifier}")
        else:
            client_id = identifier
            if client_id is None:
                raise Exception(f"client_id parameter is NULL")

        token = await get_access_token(client_id)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "application/json"}

        # Get current Security Defaults status (skip CA policies - requires Business Premium)
        current_status = await get_current_security_defaults_status(token, headers)

        if current_status["security_defaults_enabled"]:
            result = {
                "status": "Compliant",
                "message": "Security Defaults enabled - provides basic risky sign-in protection",
                "recommendation": "Consider upgrading to Business Premium for advanced Conditional Access policies"
            }
        else:
            # Try to enable Security Defaults
            result = await fix_risky_signin_with_security_defaults(token, headers, actions_taken)

        return {
            "status_code": 200,
            "data": {
                "complianceStatus": result["status"],
                "statusMessage": result["message"],
                "recommendation": result["recommendation"],
                "complianceDetails": {
                    "actionsTaken": actions_taken,
                    "summary": {
                        "totalActionsAttempted": len(actions_taken),
                        "successfulActions": len([a for a in actions_taken if a.get("status") == "success"]),
                        "businessBasicLimitation": "Conditional Access policies require Business Premium or E3+ license"
                    },
                    "userDetails": [],
                    "policyDetails": {
                        "availableProtection": "Security Defaults (Basic MFA and security protection)",
                        "unavailableFeatures": "Conditional Access policies for specific sign-in risk levels",
                        "upgradeRecommendation": "Business Premium or E3+ for advanced risky sign-in controls"
                    }
                },
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            },
            "error": None
        }

    except Exception as e:
        logger.error(f"Error fixing risky sign-in policies: {str(e)}")
        return {
            "status_code": 200,
            "data": {
                "complianceStatus": "Failed to Fix",
                "statusMessage": f"Error: {str(e)}",
                "recommendation": "Check permissions and try again",
                "complianceDetails": {
                    "actionsTaken": actions_taken,
                    "summary": {"error": str(e)},
                    "userDetails": [],
                    "policyDetails": {}
                },
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            },
            "error": str(e)
        }


async def fix_risky_signin_with_security_defaults(token: str, headers: dict, actions_taken: list) -> dict:
    """Fix risky sign-in compliance using only Security Defaults (Business Basic compatible)"""

    actions_taken.append({
        "action": "Enable Security Defaults for risky sign-in protection",
        "status": "started",
        "details": "Attempting to enable Security Defaults to provide basic protection against risky sign-ins",
        "timestamp": datetime.now().isoformat() + "Z"
    })

    # Try to enable Security Defaults
    sd_result = await enable_security_defaults(token, headers)

    if sd_result["success"]:
        actions_taken.append({
            "action": "Enable Security Defaults",
            "status": "success",
            "details": "Successfully enabled Security Defaults - provides MFA requirements and basic security protection",
            "timestamp": datetime.now().isoformat() + "Z"
        })

        return {
            "status": "Compliant",
            "message": "Enabled Security Defaults for basic risky sign-in protection",
            "recommendation": "Security Defaults provides basic protection. Upgrade to Business Premium for advanced risky sign-in policies"
        }
    else:
        actions_taken.append({
            "action": "Enable Security Defaults",
            "status": "failed",
            "details": f"Failed to enable Security Defaults: {sd_result['message']}",
            "timestamp": datetime.now().isoformat() + "Z"
        })

        return {
            "status": "Failed to Fix",
            "message": "Unable to enable Security Defaults for risky sign-in protection",
            "recommendation": "Check Policy.ReadWrite.SecurityDefaults permission or manually enable in Azure AD portal"
        }


async def enable_security_defaults(token: str, headers: dict) -> dict:
    """Enable Security Defaults - compatible with Business Basic license"""

    try:
        sd_url = f"{GRAPH_BETA_URL}/policies/identitySecurityDefaultsEnforcementPolicy"

        async with httpx.AsyncClient() as client:
            response = await client.patch(
                sd_url,
                headers=headers,
                json={"isEnabled": True},
                timeout=30.0
            )
            response.raise_for_status()

        return {
            "success": True,
            "message": "Security Defaults enabled successfully"
        }

    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }


async def get_current_security_defaults_status(token: str, headers: dict) -> dict:
    """Get current Security Defaults status - compatible with Business Basic license"""

    try:
        # Only check Security Defaults (skip CA policies - requires Business Premium)
        sd_url = f"{GRAPH_BETA_URL}/policies/identitySecurityDefaultsEnforcementPolicy"
        sd_params = {"$select": "isEnabled"}

        async with httpx.AsyncClient() as client:
            sd_response = await client.get(sd_url, headers=headers, params=sd_params, timeout=30.0)
            sd_response.raise_for_status()
            sd_data = sd_response.json()

        security_defaults_enabled = sd_data.get("isEnabled", False)

        return {
            "security_defaults_enabled": security_defaults_enabled,
            "status_message": "Security Defaults enabled" if security_defaults_enabled else "Security Defaults disabled"
        }

    except Exception as e:
        return {
            "security_defaults_enabled": False,
            "status_message": f"Error checking Security Defaults: {str(e)}"
        }


@router.post("/FixSharedMailboxSignInStatus", summary="Fix Shared Mailbox Sign-In Compliance Issues")
async def fix_shared_mailbox_signin_status(credentials: tuple = Depends(get_client_credentials)):
    """
    Simplified logic: Disable sign-in for unlicensed users (treated as shared mailboxes).
    Works with Microsoft 365 Business Basic.
    """
    actions_taken = []
    try:
        identifier, identifier_type = credentials

        # Convert ninjaone_org_id to client_id for backward compatibility
        # TODO: migrate to SQLAlchemy — organization_mapping table not in schema.sql, confirm model before replacing
        if identifier_type == "ninjaone_org_id":
            from app.core.database.supabase_services import supabase
            response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
            if not response.data or len(response.data) == 0:
                raise Exception(f"No client_id found for ninjaone_org_id: {identifier}")
            client_id = response.data[0]['client_id']
            if client_id is None:
                raise Exception(f"client_id is NULL for ninjaone_org_id: {identifier}")
        else:
            client_id = identifier
            if client_id is None:
                raise Exception(f"client_id parameter is NULL")

        token = await get_access_token(client_id)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # Step 1: Get all users
        users_url = f"{GRAPH_V1_URL}/users"
        params = {"$select": "id,userPrincipalName,accountEnabled,assignedLicenses,displayName", "$top": 999}

        async with httpx.AsyncClient() as client:
            resp = await client.get(users_url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            users = resp.json().get("value", [])

        # Step 2: Identify unlicensed users = shared mailboxes
        shared_mailboxes = [u for u in users if len(u.get("assignedLicenses", [])) == 0]
        if not shared_mailboxes:
            return {
                "status_code": 200,
                "data": {
                    "complianceStatus": "Not Measured",
                    "statusMessage": "No shared mailboxes found to configure",
                    "recommendation": "Ensure shared mailboxes are properly set up if needed",
                    "complianceDetails": {
                        "actionsTaken": [],
                        "summary": {
                            "totalActionsAttempted": 0,
                            "successfulActions": 0,
                            "failedActions": 0,
                            "totalSharedMailboxes": 0,
                            "signInDisabled": 0
                        },
                        "userDetails": [],
                        "policyDetails": {
                            "securityRequirement": "Shared mailboxes should have sign-in disabled",
                            "complianceTarget": "All shared mailboxes with accountEnabled = false",
                            "exchangeOnlineRequired": "This feature requires Exchange Online licensing"
                        }
                    },
                    "reportGeneratedAt": datetime.now().isoformat() + "Z"
                },
                "error": None
            }

        # Step 3: Disable sign-in where enabled
        successes, failures = 0, 0
        for mb in shared_mailboxes:
            if mb.get("accountEnabled", True):  # still enabled
                try:
                    patch_url = f"{GRAPH_V1_URL}/users/{mb['id']}"
                    payload = {"accountEnabled": False}
                    async with httpx.AsyncClient() as client:
                        r = await client.patch(patch_url, headers=headers, json=payload)
                        if r.status_code == 204:
                            actions_taken.append({"action": f"Disable {mb['userPrincipalName']}", "status": "success"})
                            successes += 1
                        else:
                            actions_taken.append({"action": f"Disable {mb['userPrincipalName']}", "status": "failed"})
                            failures += 1
                except Exception as e:
                    actions_taken.append(
                        {"action": f"Disable {mb['userPrincipalName']}", "status": "failed", "details": str(e)})
                    failures += 1

        # Step 4: Build result
        compliance_status = (
            "Compliant" if failures == 0 and successes > 0
            else "Partially Compliant" if successes > 0
            else "Failed to Fix"
        )
        message = f"Disabled sign-in for {successes} mailbox(es), {failures} failed"

        return {
            "status_code": 200,
            "data": {
                "complianceStatus": compliance_status,
                "statusMessage": message,
                "recommendation": "Monitor shared mailboxes and manually fix failed ones if needed",
                "complianceDetails": {
                    "actionsTaken": actions_taken,
                    "summary": {
                        "totalActionsAttempted": successes + failures,
                        "successfulActions": successes,
                        "failedActions": failures,
                        "totalSharedMailboxes": len(shared_mailboxes),
                        "signInDisabled": successes
                    },
                    "userDetails": shared_mailboxes,
                    "policyDetails": {
                        "securityRequirement": "Shared mailboxes should have sign-in disabled",
                        "complianceTarget": "All shared mailboxes with accountEnabled = false",
                        "exchangeOnlineRequired": "Works with Business Basic (no premium endpoints used)"
                    }
                },
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            },
            "error": None
        }

    except Exception as e:
        return {
            "status_code": 200,
            "data": {
                "complianceStatus": "Failed to Fix",
                "statusMessage": f"Error: {str(e)}",
                "recommendation": "Check Graph API permissions",
                "complianceDetails": {"actionsTaken": actions_taken},
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            },
            "error": str(e)
        }


@router.post("/FixGuestUserAccessPermissions", summary="Fix Guest User Access Compliance Issues")
async def fix_guest_user_access_permissions(credentials: tuple = Depends(get_client_credentials)):
    """
    Attempts to remediate guest user access compliance by restricting invitation policies
    and guest permissions. Works with Business Basic license.
    """
    actions_taken = []

    try:
        identifier, identifier_type = credentials

        # Convert ninjaone_org_id to client_id for backward compatibility
        # TODO: migrate to SQLAlchemy — organization_mapping table not in schema.sql, confirm model before replacing
        if identifier_type == "ninjaone_org_id":
            from app.core.database.supabase_services import supabase
            response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
            if not response.data or len(response.data) == 0:
                raise Exception(f"No client_id found for ninjaone_org_id: {identifier}")
            client_id = response.data[0]['client_id']
            if client_id is None:
                raise Exception(f"client_id is NULL for ninjaone_org_id: {identifier}")
        else:
            client_id = identifier
            if client_id is None:
                raise Exception(f"client_id parameter is NULL")

        token = await get_access_token(client_id)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "application/json"}

        # Get current guest user access status
        current_status = await get_current_guest_user_status(token, headers)

        if current_status["complianceStatus"] == "Compliant":
            result = {
                "status": "Compliant",
                "message": "Guest user access policies are already compliant",
                "recommendation": "Continue monitoring guest access policies and permissions"
            }

        elif current_status["complianceStatus"] in ["Not Compliant", "Partially Compliant"]:
            result = await fix_guest_user_compliance(token, headers, current_status, actions_taken)

        else:
            result = {
                "status": "Not Measured",
                "message": "Unable to determine guest user access compliance",
                "recommendation": "Check authorization policy permissions and try again"
            }

        return {
            "status_code": 200,
            "data": {
                "complianceStatus": result["status"],
                "statusMessage": result["message"],
                "recommendation": result["recommendation"],
                "complianceDetails": {
                    "actionsTaken": actions_taken,
                    "summary": {
                        "totalActionsAttempted": len(actions_taken),
                        "successfulActions": len([a for a in actions_taken if a.get("status") == "success"]),
                        "failedActions": len([a for a in actions_taken if a.get("status") == "failed"]),
                        "totalGuestUsers": current_status.get("total_guests", 0),
                        "policyChangesApplied": len(
                            [a for a in actions_taken if "policy" in a.get("action", "").lower()])
                    },
                    "userDetails": current_status.get("guest_users", []),
                    "policyDetails": {
                        "securityRequirement": "Restrict guest invitation and access permissions",
                        "complianceTarget": "Admins-only guest invitations and limited guest permissions",
                        "policyScope": "Organization-wide authorization policy"
                    }
                },
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            },
            "error": None
        }

    except Exception as e:
        logger.error(f"Error fixing guest user access: {str(e)}")
        return {
            "status_code": 200,
            "data": {
                "complianceStatus": "Failed to Fix",
                "statusMessage": f"Error: {str(e)}",
                "recommendation": "Check Policy.ReadWrite.Authorization permission and try again",
                "complianceDetails": {
                    "actionsTaken": actions_taken,
                    "summary": {"error": str(e)},
                    "userDetails": [],
                    "policyDetails": {}
                },
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            },
            "error": str(e)
        }


async def fix_guest_user_compliance(token: str, headers: dict, current_status: dict, actions_taken: list) -> dict:
    """Fix guest user compliance by restricting authorization policies"""

    auth_policy = current_status.get("auth_policy", {})

    # Check what needs to be fixed
    needs_invite_restriction = auth_policy.get("allowInvitesFrom") == "everyone"
    needs_self_join_restriction = auth_policy.get("allowEmailVerifiedUsersToJoinOrganization", False)
    needs_user_permission_restriction = auth_policy.get("defaultUserRolePermissions", {}).get("allowedToReadOtherUsers",
                                                                                              False)

    if not needs_invite_restriction and not needs_self_join_restriction and not needs_user_permission_restriction:
        return {
            "status": "Compliant",
            "message": "Guest access policies are already properly configured",
            "recommendation": "Continue monitoring guest user permissions"
        }

    # Prepare policy updates
    policy_updates = {}

    # Fix invitation policy
    if needs_invite_restriction:
        actions_taken.append({
            "action": "Restrict guest invitations to admins only",
            "status": "started",
            "details": "Changing allowInvitesFrom from 'everyone' to 'adminsAndGuestInviters'",
            "timestamp": datetime.now().isoformat() + "Z"
        })
        policy_updates["allowInvitesFrom"] = "adminsAndGuestInviters"

    # Fix self-join policy
    if needs_self_join_restriction:
        actions_taken.append({
            "action": "Disable email verified user self-join",
            "status": "started",
            "details": "Setting allowEmailVerifiedUsersToJoinOrganization to false",
            "timestamp": datetime.now().isoformat() + "Z"
        })
        policy_updates["allowEmailVerifiedUsersToJoinOrganization"] = False

    # Fix default user permissions
    if needs_user_permission_restriction:
        actions_taken.append({
            "action": "Restrict default user permissions",
            "status": "started",
            "details": "Limiting default user role permissions",
            "timestamp": datetime.now().isoformat() + "Z"
        })

        # Update default user role permissions
        default_permissions = auth_policy.get("defaultUserRolePermissions", {})
        restricted_permissions = {
            **default_permissions,
            "allowedToReadOtherUsers": False,
            "allowedToCreateApps": False,
            "allowedToCreateSecurityGroups": False,
            "allowedToCreateTenants": False
        }
        policy_updates["defaultUserRolePermissions"] = restricted_permissions

    # Apply the policy updates
    if policy_updates:
        update_result = await update_authorization_policy(token, headers, policy_updates)

        if update_result["success"]:
            # Update all action statuses to success
            for action in actions_taken:
                if action.get("status") == "started":
                    action["status"] = "success"
                    action["details"] += " - Successfully applied"

            # Determine final compliance status
            if needs_invite_restriction and needs_self_join_restriction:
                return {
                    "status": "Compliant",  # Changed from "Fixed"
                    "message": "Successfully restricted guest invitation policies and disabled self-join",
                    "recommendation": "Monitor guest user additions and review permissions periodically"
                }
            elif needs_invite_restriction or needs_self_join_restriction:
                return {
                    "status": "Compliant",  # Changed from "Fixed"
                    "message": "Successfully applied guest access restrictions",
                    "recommendation": "Continue monitoring guest access policies"
                }
            else:
                return {
                    "status": "Compliant",  # Changed from "Fixed"
                    "message": "Guest access policies updated successfully",
                    "recommendation": "Review guest user permissions regularly"
                }
        else:
            # Update action statuses to failed
            for action in actions_taken:
                if action.get("status") == "started":
                    action["status"] = "failed"
                    action["details"] += f" - Failed: {update_result['error']}"

            return {
                "status": "Failed to Fix",
                "message": "Unable to update authorization policies",
                "recommendation": "Check Policy.ReadWrite.Authorization permission and try manually via Azure AD portal"
            }

    return {
        "status": "Failed to Fix",
        "message": "No applicable policy updates identified",
        "recommendation": "Manual review of guest access configuration required"
    }


async def update_authorization_policy(token: str, headers: dict, policy_updates: dict) -> dict:
    """Update the organization's authorization policy"""

    try:
        auth_policy_url = f"{GRAPH_V1_URL}/policies/authorizationPolicy"

        async with httpx.AsyncClient() as client:
            response = await client.patch(
                auth_policy_url,
                headers=headers,
                json=policy_updates,
                timeout=30.0
            )
            response.raise_for_status()

        return {
            "success": True,
            "message": "Authorization policy updated successfully"
        }

    except httpx.HTTPStatusError as e:
        error_detail = "Unknown error"
        try:
            error_detail = e.response.json().get("error", {}).get("message", str(e))
        except:
            error_detail = f"HTTP {e.response.status_code}"

        return {
            "success": False,
            "error": error_detail
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


async def get_current_guest_user_status(token: str, headers: dict) -> dict:
    """Get current guest user compliance status using GET endpoint logic"""

    try:
        # Get authorization policy
        auth_policy_url = f"{GRAPH_V1_URL}/policies/authorizationPolicy"

        async with httpx.AsyncClient() as client:
            auth_response = await client.get(auth_policy_url, headers=headers, timeout=30.0)
            auth_response.raise_for_status()
            auth_data = auth_response.json()

        # Get guest users (simplified - just count them)
        guest_users_url = f"{GRAPH_V1_URL}/users"
        guest_params = {
            "$filter": "userType eq 'Guest'",
            "$select": "id,userPrincipalName,displayName,userType",
            "$top": 100
        }

        async with httpx.AsyncClient() as client:
            guests_response = await client.get(guest_users_url, headers=headers, params=guest_params, timeout=30.0)
            guests_response.raise_for_status()
            guests_data = guests_response.json()

        guest_users = guests_data.get("value", [])

        # Simplified compliance determination (focus on policies only for Business Basic)
        compliance_info = determine_simplified_guest_compliance(auth_data, guest_users)

        return {
            "complianceStatus": compliance_info["status"],
            "statusMessage": compliance_info["message"],
            "auth_policy": auth_data,
            "guest_users": guest_users,
            "total_guests": len(guest_users)
        }

    except Exception as e:
        return {
            "complianceStatus": "Not Measured",
            "statusMessage": f"Error: {str(e)}",
            "auth_policy": {},
            "guest_users": [],
            "total_guests": 0
        }


def determine_simplified_guest_compliance(auth_data: dict, guest_users: list) -> dict:
    """Simplified compliance determination focusing on authorization policies only"""

    # Check key policy settings
    allow_invites_from = auth_data.get("allowInvitesFrom", "")
    allow_email_verified_join = auth_data.get("allowEmailVerifiedUsersToJoinOrganization", False)
    default_permissions = auth_data.get("defaultUserRolePermissions", {})
    allow_read_other_users = default_permissions.get("allowedToReadOtherUsers", False)

    total_guests = len(guest_users)

    # Identify policy issues
    policy_issues = []

    if allow_invites_from == "everyone":
        policy_issues.append("anyone can invite guest users")

    if allow_email_verified_join:
        policy_issues.append("email verified users can self-join organization")

    if allow_read_other_users:
        policy_issues.append("default users can read other user information")

    # Determine compliance status
    if not policy_issues:
        if total_guests == 0:
            return {
                "status": "Compliant",
                "message": "Guest access policies are restrictive and no guest users exist",
                "recommendation": "Continue monitoring guest access policies"
            }
        else:
            return {
                "status": "Compliant",
                "message": f"Guest access policies are restrictive with {total_guests} guest users",
                "recommendation": "Continue monitoring guest user permissions"
            }

    elif len(policy_issues) == 1:
        return {
            "status": "Partially Compliant",
            "message": f"Guest access requires review: {policy_issues[0]}",
            "recommendation": "Restrict guest invitation policies and review access settings"
        }

    else:
        return {
            "status": "Not Compliant",
            "message": f"Multiple guest access concerns: {', '.join(policy_issues)}",
            "recommendation": "Implement restrictive guest invitation policies immediately"
        }

@router.post("/FixSharePointSiteCreationStatus", summary="Fix SharePoint Site Creation Compliance Issues")
async def fix_sharepoint_site_creation_status(credentials: tuple = Depends(get_client_credentials)):
    """
    Attempts to remediate SharePoint site creation compliance by disabling unrestricted site creation.
    Simple logic: If site creation is enabled for all users, disable it to require admin approval.
    """
    actions_taken = []

    try:
        identifier, identifier_type = credentials

        # Convert ninjaone_org_id to client_id for backward compatibility
        # TODO: migrate to SQLAlchemy — organization_mapping table not in schema.sql, confirm model before replacing
        if identifier_type == "ninjaone_org_id":
            from app.core.database.supabase_services import supabase
            response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
            if not response.data or len(response.data) == 0:
                raise Exception(f"No client_id found for ninjaone_org_id: {identifier}")
            client_id = response.data[0]['client_id']
            if client_id is None:
                raise Exception(f"client_id is NULL for ninjaone_org_id: {identifier}")
        else:
            client_id = identifier
            if client_id is None:
                raise Exception(f"client_id parameter is NULL")

        token = await get_access_token(client_id)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "application/json"}

        # Get current SharePoint site creation status
        current_status = await get_current_sharepoint_site_creation_status(token, headers)

        if current_status["complianceStatus"] == "Compliant":
            result = {
                "status": "Compliant",
                "message": "SharePoint site creation is already restricted and requires approval",
                "recommendation": "Continue monitoring site creation settings and review approval processes"
            }

        elif current_status["complianceStatus"] == "Not Compliant":
            result = await fix_sharepoint_site_creation(token, headers, current_status, actions_taken)

        else:
            result = {
                "status": "Not Measured",
                "message": "Unable to determine SharePoint site creation compliance",
                "recommendation": "Check SharePoint admin permissions and try again"
            }

        return {
            "status_code": 200,
            "data": {
                "complianceStatus": result["status"],
                "statusMessage": result["message"],
                "recommendation": result["recommendation"],
                "complianceDetails": {
                    "actionsTaken": actions_taken,
                    "summary": {
                        "totalActionsAttempted": len(actions_taken),
                        "successfulActions": len([a for a in actions_taken if a.get("status") == "success"]),
                        "failedActions": len([a for a in actions_taken if a.get("status") == "failed"]),
                        "settingChanged": "isSiteCreationEnabled" if any(
                            "site creation" in a.get("action", "").lower() for a in actions_taken) else None
                    },
                    "userDetails": [],
                    "policyDetails": {
                        "securityRequirement": "Restrict SharePoint site creation to authorized users only",
                        "complianceTarget": "Site creation disabled for standard users",
                        "adminApprovalRequired": "True after fix is applied"
                    }
                },
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            },
            "error": None
        }

    except Exception as e:
        logger.error(f"Error fixing SharePoint site creation: {str(e)}")
        return {
            "status_code": 200,
            "data": {
                "complianceStatus": "Not Compliant",
                "statusMessage": f"Error: {str(e)}",
                "recommendation": "Check SharePoint admin permissions and try again",
                "complianceDetails": {
                    "actionsTaken": actions_taken,
                    "summary": {"error": str(e)},
                    "userDetails": [],
                    "policyDetails": {}
                },
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            },
            "error": str(e)
        }


async def fix_sharepoint_site_creation(token: str, headers: dict, current_status: dict, actions_taken: list) -> dict:
    """Fix SharePoint site creation compliance by disabling unrestricted site creation"""

    # Simple logic: If site creation is enabled, disable it
    actions_taken.append({
        "action": "Disable unrestricted SharePoint site creation",
        "status": "started",
        "details": "Changing isSiteCreationEnabled from true to false to require admin approval",
        "timestamp": datetime.now().isoformat() + "Z"
    })

    # Disable site creation for standard users
    disable_result = await disable_site_creation(token, headers)

    if disable_result["success"]:
        actions_taken.append({
            "action": "Update SharePoint site creation setting",
            "status": "success",
            "details": "Successfully disabled site creation for standard users - now requires admin approval",
            "timestamp": datetime.now().isoformat() + "Z"
        })

        return {
            "status": "Compliant",  # Changed from "Fixed"
            "message": "SharePoint site creation restricted successfully - now requires admin approval",
            "recommendation": "Monitor site creation requests and ensure proper approval process is in place"
        }
    else:
        actions_taken.append({
            "action": "Update SharePoint site creation setting",
            "status": "failed",
            "details": f"Failed to disable site creation: {disable_result['error']}",
            "timestamp": datetime.now().isoformat() + "Z"
        })

        return {
            "status": "Failed to Fix",
            "message": "Unable to restrict SharePoint site creation",
            "recommendation": "Check SharePoint admin permissions or manually configure in SharePoint admin center"
        }


async def disable_site_creation(token: str, headers: dict) -> dict:
    """Disable SharePoint site creation for standard users"""

    try:
        sharepoint_settings_url = f"{GRAPH_V1_URL}/admin/sharepoint/settings"

        # Simple update: set isSiteCreationEnabled to false
        update_payload = {
            "isSiteCreationEnabled": False
        }

        async with httpx.AsyncClient() as client:
            response = await client.patch(
                sharepoint_settings_url,
                headers=headers,
                json=update_payload,
                timeout=30.0
            )
            response.raise_for_status()

        return {
            "success": True,
            "message": "Site creation disabled successfully"
        }

    except httpx.HTTPStatusError as e:
        error_detail = "Unknown error"
        try:
            error_detail = e.response.json().get("error", {}).get("message", str(e))
        except:
            error_detail = f"HTTP {e.response.status_code}"

        return {
            "success": False,
            "error": error_detail
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


async def get_current_sharepoint_site_creation_status(token: str, headers: dict) -> dict:
    """Get current SharePoint site creation compliance status using GET endpoint logic"""

    try:
        # Get SharePoint settings (same as GET endpoint)
        sharepoint_settings_url = f"{GRAPH_V1_URL}/admin/sharepoint/settings"
        params = {
            "$select": "siteCreationDefaultManagedPath,siteCreationDefaultStorageLimitInMB,isSiteCreationEnabled"
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(sharepoint_settings_url, headers=headers, params=params, timeout=30.0)
            response.raise_for_status()
            settings_data = response.json()

        # Use existing compliance determination logic
        compliance_info = determine_sharepoint_site_creation_compliance_status(settings_data)

        return {
            "complianceStatus": compliance_info["status"],
            "statusMessage": compliance_info["message"],
            "settings": settings_data
        }

    except Exception as e:
        return {
            "complianceStatus": "Not Measured",
            "statusMessage": f"Error: {str(e)}",
            "settings": {}
        }


@router.post("/FixWeakAuthenticatorStatus", summary="Fix Weak Authenticator Compliance Issues")
async def fix_weak_authenticator_status(credentials: tuple = Depends(get_client_credentials)):
    """
    Attempts to remediate weak authenticator compliance by disabling SMS and Voice authentication methods.
    Simple logic: Disable any enabled weak authentication methods (SMS and Voice).
    """
    actions_taken = []

    try:
        identifier, identifier_type = credentials

        # Convert ninjaone_org_id to client_id for backward compatibility
        # TODO: migrate to SQLAlchemy — organization_mapping table not in schema.sql, confirm model before replacing
        if identifier_type == "ninjaone_org_id":
            from app.core.database.supabase_services import supabase
            response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
            if not response.data or len(response.data) == 0:
                raise Exception(f"No client_id found for ninjaone_org_id: {identifier}")
            client_id = response.data[0]['client_id']
            if client_id is None:
                raise Exception(f"client_id is NULL for ninjaone_org_id: {identifier}")
        else:
            client_id = identifier
            if client_id is None:
                raise Exception(f"client_id parameter is NULL")

        token = await get_access_token(client_id)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "application/json"}

        # Get current weak authenticator status
        current_status = await get_current_weak_authenticator_status(token, headers)

        if current_status["complianceStatus"] == "Compliant":
            result = {
                "status": "Compliant",
                "message": "SMS and voice authentication methods are already disabled",
                "recommendation": "Current status is good. Continue promoting stronger authentication methods"
            }

        elif current_status["complianceStatus"] in ["Not Compliant", "Partially Compliant"]:
            result = await fix_weak_authenticator_methods(token, headers, current_status, actions_taken)

        else:
            result = {
                "status": "Not Measured",
                "message": "Unable to determine weak authenticator compliance",
                "recommendation": "Check authentication method policy permissions and try again"
            }

        return {
            "status_code": 200,
            "data": {
                "complianceStatus": result["status"],
                "statusMessage": result["message"],
                "recommendation": result["recommendation"],
                "complianceDetails": {
                    "actionsTaken": actions_taken,
                    "summary": {
                        "totalActionsAttempted": len(actions_taken),
                        "successfulActions": len([a for a in actions_taken if a.get("status") == "success"]),
                        "failedActions": len([a for a in actions_taken if a.get("status") == "failed"]),
                        "methodsDisabled": len([a for a in actions_taken if
                                                "disable" in a.get("action", "").lower() and a.get(
                                                    "status") == "success"])
                    },
                    "userDetails": [],
                    "policyDetails": {
                        "securityRequirement": "Disable weak 2FA authentication methods (SMS and Voice)",
                        "complianceTarget": "Both SMS and Voice authentication disabled",
                        "recommendedAlternatives": "Authenticator apps, FIDO2 keys, or Windows Hello"
                    }
                },
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            },
            "error": None
        }

    except Exception as e:
        logger.error(f"Error fixing weak authenticator: {str(e)}")
        return {
            "status_code": 200,
            "data": {
                "complianceStatus": "Not Compliant",
                "statusMessage": f"Error: {str(e)}",
                "recommendation": "Check authentication method policy permissions and try again",
                "complianceDetails": {
                    "actionsTaken": actions_taken,
                    "summary": {"error": str(e)},
                    "userDetails": [],
                    "policyDetails": {}
                },
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            },
            "error": str(e)
        }


async def fix_weak_authenticator_methods(token: str, headers: dict, current_status: dict, actions_taken: list) -> dict:
    """Fix weak authenticator compliance by disabling SMS and/or Voice authentication"""

    sms_status = current_status.get("sms_status", "")
    voice_status = current_status.get("voice_status", "")

    successful_fixes = 0
    failed_fixes = 0

    # Fix SMS authentication if enabled
    if sms_status.lower() == "enabled":
        actions_taken.append({
            "action": "Disable SMS authentication method",
            "status": "started",
            "details": "Disabling SMS as a 2FA authentication method",
            "timestamp": datetime.now().isoformat() + "Z"
        })

        sms_result = await disable_authentication_method(token, headers, "Sms")

        if sms_result["success"]:
            actions_taken.append({
                "action": "Disable SMS authentication",
                "status": "success",
                "details": "Successfully disabled SMS authentication method",
                "timestamp": datetime.now().isoformat() + "Z"
            })
            successful_fixes += 1
        else:
            actions_taken.append({
                "action": "Disable SMS authentication",
                "status": "failed",
                "details": f"Failed to disable SMS: {sms_result['error']}",
                "timestamp": datetime.now().isoformat() + "Z"
            })
            failed_fixes += 1

    # Fix Voice authentication if enabled
    if voice_status.lower() == "enabled":
        actions_taken.append({
            "action": "Disable Voice authentication method",
            "status": "started",
            "details": "Disabling Voice as a 2FA authentication method",
            "timestamp": datetime.now().isoformat() + "Z"
        })

        voice_result = await disable_authentication_method(token, headers, "Voice")

        if voice_result["success"]:
            actions_taken.append({
                "action": "Disable Voice authentication",
                "status": "success",
                "details": "Successfully disabled Voice authentication method",
                "timestamp": datetime.now().isoformat() + "Z"
            })
            successful_fixes += 1
        else:
            actions_taken.append({
                "action": "Disable Voice authentication",
                "status": "failed",
                "details": f"Failed to disable Voice: {voice_result['error']}",
                "timestamp": datetime.now().isoformat() + "Z"
            })
            failed_fixes += 1

    # Determine final result
    total_methods_to_fix = (1 if sms_status.lower() == "enabled" else 0) + (
        1 if voice_status.lower() == "enabled" else 0)

    if successful_fixes == total_methods_to_fix:
        return {
            "status": "Compliant",  # Changed from "Fixed"
            "message": f"Successfully disabled {successful_fixes} weak authentication method(s)",
            "recommendation": "Promote stronger authentication methods like authenticator apps or FIDO2 keys"
        }
    elif successful_fixes > 0:
        return {
            "status": "Partially Compliant",  # Some methods fixed, some failed
            "message": f"Disabled {successful_fixes} of {total_methods_to_fix} weak authentication methods",
            "recommendation": f"Manually disable remaining {failed_fixes} authentication method(s) via Azure AD portal"
        }
    else:
        return {
            "status": "Not Compliant",
            "message": "Unable to disable any weak authentication methods",
            "recommendation": "Check Policy.ReadWrite.AuthenticationMethod permission or configure manually"
        }


async def disable_authentication_method(token: str, headers: dict, method_type: str) -> dict:
    """Disable a specific authentication method (SMS or Voice)"""

    try:
        auth_method_url = f"{GRAPH_V1_URL}/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/{method_type}"

        # Simple update: set state to disabled
        update_payload = {
            "state": "disabled"
        }

        async with httpx.AsyncClient() as client:
            response = await client.patch(
                auth_method_url,
                headers=headers,
                json=update_payload,
                timeout=30.0
            )
            response.raise_for_status()

        return {
            "success": True,
            "message": f"{method_type} authentication disabled successfully"
        }

    except httpx.HTTPStatusError as e:
        error_detail = "Unknown error"
        try:
            error_detail = e.response.json().get("error", {}).get("message", str(e))
        except:
            error_detail = f"HTTP {e.response.status_code}"

        return {
            "success": False,
            "error": error_detail
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


async def get_current_weak_authenticator_status(token: str, headers: dict) -> dict:
    """Get current weak authenticator compliance status using GET endpoint logic"""

    try:
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

        # Use existing compliance determination logic
        compliance_info = determine_weak_authenticator_compliance_status(sms_data, voice_data)

        return {
            "complianceStatus": compliance_info["status"],
            "statusMessage": compliance_info["message"],
            "sms_status": sms_data.get("state", ""),
            "voice_status": voice_data.get("state", ""),
            "sms_data": sms_data,
            "voice_data": voice_data
        }

    except Exception as e:
        return {
            "complianceStatus": "Not Measured",
            "statusMessage": f"Error: {str(e)}",
            "sms_status": "",
            "voice_status": "",
            "sms_data": {},
            "voice_data": {}
        }
# Endpoint for Fixing Password Expiration Policy (write operation)
@router.post("/FixPasswordExpirationPolicy", response_model=GraphApiResponse,
             summary="Fix Password Expiration Policy for All Domains (Simplified)")
async def fix_password_expiration_policy(credentials: tuple = Depends(get_client_credentials)):
    """
    Attempts to remediate password expiration compliance issues.

    Logic:
    - NOT COMPLIANT cases to fix:
        * null/unconfigured → set to 2147483647 (never expires, NIST-compliant)
        * invalid values    → set to 2147483647 (never expires, NIST-compliant)
    - COMPLIANT cases: no action required
    - Final complianceStatus can only be: Compliant | Not Compliant | Not Measured

    Compatible with Microsoft 365 Business Basic.
    """

    actions_taken = []

    try:
        identifier, identifier_type = credentials

        # Convert ninjaone_org_id to client_id for backward compatibility
        # TODO: migrate to SQLAlchemy — organization_mapping table not in schema.sql, confirm model before replacing
        if identifier_type == "ninjaone_org_id":
            from app.core.database.supabase_services import supabase
            response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
            if not response.data or len(response.data) == 0:
                raise Exception(f"No client_id found for ninjaone_org_id: {identifier}")
            client_id = response.data[0]['client_id']
            if client_id is None:
                raise Exception(f"client_id is NULL for ninjaone_org_id: {identifier}")
        else:
            client_id = identifier
            if client_id is None:
                raise Exception(f"client_id parameter is NULL")

        token = await get_access_token(client_id)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # Step 1: Get all domains
        domains_url = f"{GRAPH_V1_URL}/domains"

        async with httpx.AsyncClient() as client:
            resp = await client.get(domains_url, headers=headers, timeout=30.0)
            resp.raise_for_status()
            domains = resp.json().get("value", [])

        compliant, fixed, failed, non_compliant = [], [], [], []

        # Step 2: Iterate domains
        for domain in domains:
            domain_id = domain.get("id")
            auth_type = domain.get("authenticationType")
            current_validity = domain.get("passwordValidityPeriodInDays")

            # Skip federated domains
            if auth_type != "Managed":
                actions_taken.append({
                    "action": f"Skip domain {domain_id}",
                    "status": "skipped",
                    "details": f"Federated domain ({auth_type}), managed externally"
                })
                continue

            # If compliant → no fix needed
            if current_validity == 2147483647 or (current_validity and 1 <= current_validity <= 999999):
                compliant.append(domain_id)
                actions_taken.append({
                    "action": f"Check domain {domain_id}",
                    "status": "no_action",
                    "details": "Already compliant"
                })
                continue

            # Non-compliant → attempt fix
            update_url = f"{GRAPH_V1_URL}/domains/{domain_id}"
            payload = {"passwordValidityPeriodInDays": 2147483647}

            try:
                async with httpx.AsyncClient() as client:
                    patch_resp = await client.patch(update_url, headers=headers, json=payload, timeout=30.0)
                    if patch_resp.status_code in [200, 204]:
                        fixed.append(domain_id)
                        actions_taken.append({
                            "action": f"Fix domain {domain_id}",
                            "status": "success",
                            "details": "Set passwordValidityPeriodInDays to 2147483647 (never expires)"
                        })
                    else:
                        failed.append(domain_id)
                        actions_taken.append({
                            "action": f"Fix domain {domain_id}",
                            "status": "failed",
                            "details": f"Graph API returned {patch_resp.status_code}"
                        })
            except Exception as e:
                failed.append(domain_id)
                actions_taken.append({
                    "action": f"Fix domain {domain_id}",
                    "status": "failed",
                    "details": str(e)
                })

        # Step 3: Determine final compliance status
        if not domains:
            compliance_status = "Not Measured"
            status_message = "No domains found to evaluate"
            recommendation = "Check tenant configuration"
        elif failed or (not compliant and not fixed):
            compliance_status = "Not Compliant"
            status_message = f"{len(failed)} domains failed to fix, {len(non_compliant)} remain non-compliant"
            recommendation = "Retry or manually configure password policy in Microsoft 365 Admin Center"
        else:
            compliance_status = "Compliant"
            total = len(compliant) + len(fixed)
            status_message = f"All {total} managed domains are compliant"
            recommendation = "Maintain current configuration"

        # Step 4: Build response
        result_data = {
            "complianceStatus": compliance_status,
            "statusMessage": status_message,
            "recommendation": recommendation,
            "complianceDetails": {
                "actionsTaken": actions_taken,
                "summary": {
                    "totalDomains": len(domains),
                    "compliantDomains": len(compliant),
                    "fixedDomains": len(fixed),
                    "failedDomains": len(failed),
                },
                "userDetails": [],
                "policyDetails": {
                    "fixApplied": "passwordValidityPeriodInDays set to 2147483647 for non-compliant domains",
                    "securityRequirement": "Passwords should never expire per NIST guidelines",
                    "scope": "All managed domains"
                }
            },
            "reportGeneratedAt": datetime.now().isoformat() + "Z"
        }

        return GraphApiResponse(status_code=200, data=result_data)

    except Exception as e:
        logger.error(f"Error fixing password expiration policy: {str(e)}")
        return GraphApiResponse(
            status_code=200,
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": f"Error: {str(e)}",
                "recommendation": "Check Graph API permissions and try again",
                "complianceDetails": {"actionsTaken": actions_taken},
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            },
            error=str(e)
        )
# Endpoint for fixing Teams External Access Policy (POST)
@router.post("/FixTeamsExternalAccess", response_model=GraphApiResponse,
             summary="Fix Teams External Access Policy by Blocking External Access")
async def fix_teams_external_access(credentials: tuple = Depends(get_client_credentials)):
    """
    Fixes Teams external access policy by blocking both inbound and outbound external access.
    Changes accessType from 'allowed' to 'blocked' for AllUsers in both b2bCollaborationInbound
    and b2bCollaborationOutbound configurations.
    """
    try:
        identifier, identifier_type = credentials

        # Convert ninjaone_org_id to client_id for backward compatibility
        # TODO: migrate to SQLAlchemy — organization_mapping table not in schema.sql, confirm model before replacing
        if identifier_type == "ninjaone_org_id":
            from app.core.database.supabase_services import supabase
            response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
            if not response.data or len(response.data) == 0:
                raise Exception(f"No client_id found for ninjaone_org_id: {identifier}")
            client_id = response.data[0]['client_id']
            if client_id is None:
                raise Exception(f"client_id is NULL for ninjaone_org_id: {identifier}")
        else:
            client_id = identifier
            if client_id is None:
                raise Exception(f"client_id parameter is NULL")

        token = await get_access_token(client_id)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        # Step 1: Get current configuration to check compliance status
        cross_tenant_url = f"{GRAPH_V1_URL}/policies/crossTenantAccessPolicy/default"

        async with httpx.AsyncClient() as client:
            # Get current configuration
            current_response = await client.get(cross_tenant_url, headers=headers, timeout=30.0)
            current_response.raise_for_status()
            current_data = current_response.json()

        # Check current compliance status
        b2b_inbound = current_data.get("b2bCollaborationInbound", {})
        b2b_outbound = current_data.get("b2bCollaborationOutbound", {})

        inbound_users_groups = b2b_inbound.get("usersAndGroups", {})
        outbound_users_groups = b2b_outbound.get("usersAndGroups", {})

        inbound_access_type = inbound_users_groups.get("accessType", "")
        outbound_access_type = outbound_users_groups.get("accessType", "")

        inbound_targets = inbound_users_groups.get("targets", [])
        outbound_targets = outbound_users_groups.get("targets", [])

        # Check if inbound allows all external access
        inbound_allows_all = (
                inbound_access_type == "allowed" and
                len(inbound_targets) == 1 and
                inbound_targets[0].get("target") == "AllUsers" and
                inbound_targets[0].get("targetType") == "user"
        )

        # Check if outbound allows all external access
        outbound_allows_all = (
                outbound_access_type == "allowed" and
                len(outbound_targets) == 1 and
                outbound_targets[0].get("target") == "AllUsers" and
                outbound_targets[0].get("targetType") == "user"
        )

        actions_taken = []

        # Determine if fix is needed
        if not inbound_allows_all and not outbound_allows_all:
            # Already compliant - no action needed
            result_data = {
                "complianceStatus": "Compliant",
                "statusMessage": "Teams external access is already properly restricted",
                "recommendation": "No changes needed. Continue monitoring external access settings",
                "complianceDetails": {
                    "actionsTaken": ["No action needed - policy already compliant"],
                    "summary": {
                        "inboundExternalAccess": "Blocked",
                        "outboundExternalAccess": "Blocked",
                        "policyFixed": False,
                        "alreadyCompliant": True
                    },
                    "userDetails": [],
                    "policyDetails": {
                        "beforeFix": {
                            "inboundAccessType": inbound_access_type,
                            "outboundAccessType": outbound_access_type
                        },
                        "afterFix": {
                            "inboundAccessType": inbound_access_type,
                            "outboundAccessType": outbound_access_type
                        }
                    }
                },
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
            return GraphApiResponse(status_code=200, data=result_data)

        # Step 2: Apply fix - Block external access for both inbound and outbound
        patch_data = {
            "b2bCollaborationInbound": {
                "usersAndGroups": {
                    "accessType": "blocked",
                    "targets": [
                        {
                            "target": "AllUsers",
                            "targetType": "user"
                        }
                    ]
                }
            },
            "b2bCollaborationOutbound": {
                "usersAndGroups": {
                    "accessType": "blocked",
                    "targets": [
                        {
                            "target": "AllUsers",
                            "targetType": "user"
                        }
                    ]
                }
            }
        }

        async with httpx.AsyncClient() as client:
            # Apply the fix
            patch_response = await client.patch(
                cross_tenant_url,
                headers={**headers, "Content-Type": "application/json"},
                json=patch_data,
                timeout=30.0
            )
            patch_response.raise_for_status()

        # Track what was fixed
        if inbound_allows_all:
            actions_taken.append("Blocked inbound external access for all users")
        if outbound_allows_all:
            actions_taken.append("Blocked outbound external access for all users")

        # Step 3: Verify the fix by getting updated configuration
        async with httpx.AsyncClient() as client:
            verify_response = await client.get(cross_tenant_url, headers=headers, timeout=30.0)
            verify_response.raise_for_status()
            updated_data = verify_response.json()

        # Check if fix was successful
        updated_inbound = updated_data.get("b2bCollaborationInbound", {})
        updated_outbound = updated_data.get("b2bCollaborationOutbound", {})

        updated_inbound_access = updated_inbound.get("usersAndGroups", {}).get("accessType", "")
        updated_outbound_access = updated_outbound.get("usersAndGroups", {}).get("accessType", "")

        # Determine final compliance status
        if updated_inbound_access == "blocked" and updated_outbound_access == "blocked":
            compliance_status = "Compliant"
            status_message = "Teams external access successfully restricted - both inbound and outbound blocked"
            recommendation = "External access is now secure. Monitor settings regularly to ensure they remain restricted"
        else:
            compliance_status = "Not Compliant"
            status_message = "Failed to properly restrict Teams external access"
            recommendation = "Review cross-tenant access policy permissions and try again"
            actions_taken.append("Fix verification failed - policy may not have been updated correctly")

        # Build response
        result_data = {
            "complianceStatus": compliance_status,
            "statusMessage": status_message,
            "recommendation": recommendation,
            "complianceDetails": {
                "actionsTaken": actions_taken,
                "summary": {
                    "inboundExternalAccess": "Blocked" if updated_inbound_access == "blocked" else "Allowed",
                    "outboundExternalAccess": "Blocked" if updated_outbound_access == "blocked" else "Allowed",
                    "policyFixed": True,
                    "totalChanges": len(actions_taken)
                },
                "userDetails": [],
                "policyDetails": {
                    "beforeFix": {
                        "inboundAccessType": inbound_access_type,
                        "outboundAccessType": outbound_access_type,
                        "inboundAllowedAllUsers": inbound_allows_all,
                        "outboundAllowedAllUsers": outbound_allows_all
                    },
                    "afterFix": {
                        "inboundAccessType": updated_inbound_access,
                        "outboundAccessType": updated_outbound_access,
                        "inboundAllowedAllUsers": False,
                        "outboundAllowedAllUsers": False
                    }
                }
            },
            "reportGeneratedAt": datetime.now().isoformat() + "Z"
        }

        return GraphApiResponse(status_code=200, data=result_data)

    except httpx.HTTPStatusError as exc:
        logger.error(
            f"Graph API HTTP error during Teams external access fix: {exc.response.status_code} - {exc.response.text}")
        return GraphApiResponse(
            status_code=200,
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to fix Teams external access policy due to API error",
                "recommendation": "Check permissions for Policy.ReadWrite.CrossTenantAccess and try again",
                "complianceDetails": {
                    "actionsTaken": ["Failed to apply fix due to API error"],
                    "summary": {},
                    "userDetails": [],
                    "policyDetails": {}
                },
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )
    except Exception as e:
        logger.error(f"Error fixing Teams external access policy: {str(e)}")
        return GraphApiResponse(
            status_code=200,
            data={
                "complianceStatus": "Not Measured",
                "statusMessage": "Unable to fix Teams external access policy due to system error",
                "recommendation": "Check system configuration and try again",
                "complianceDetails": {
                    "actionsTaken": ["Failed to apply fix due to system error"],
                    "summary": {},
                    "userDetails": [],
                    "policyDetails": {}
                },
                "reportGeneratedAt": datetime.now().isoformat() + "Z"
            }
        )