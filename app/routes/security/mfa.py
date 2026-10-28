import logging
import httpx
from datetime import datetime
from typing import Optional
from fastapi import APIRouter,Depends,HTTPException,Query
from app.core.auth.dependencies import get_client_id, get_client_credentials
from app.core.auth.middleware import get_access_token
from app.schemas.api import GraphApiResponse
from app.core.config.settings import GRAPH_V1_URL, GRAPH_BETA_URL
import asyncio
from app.core.database.supabase_services import get_organization_credentials
from app.schemas.api import (
    ConditionalAccessPolicyRequest,
    AuthenticationMethodConfigRequest
)
# Create router for MFA endpoints
router = APIRouter()
logger = logging.getLogger(__name__)

#---------------MFA USERS AND REPORT-----------------

@router.get("/ListMFAUsers", response_model=GraphApiResponse, summary="List MFA Users")
async def list_mfa_users(clientId: Optional[str] = Query(None),org_id: Optional[int] = Query(None)):
    """
    Lists users with MFA information using only /users and /users/{id}/authentication/methods.
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
            # Old method: use clientId directly
            client_id = str(clientId).strip()
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

                        #  Only true if methods beyond "password" exist
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
        results = await asyncio.gather(*(fetch_user_mfa(user) for user in users))

        # 3. Return list of users
        return GraphApiResponse(status_code=200, data=results)

    except httpx.HTTPStatusError as exc:
        logger.error(f"Graph API HTTP error: {exc.response.status_code} - {exc.response.text}")
        return GraphApiResponse(
            status_code=exc.response.status_code,
            data=[],
            error=f"Graph API error: {exc.response.text}"
        )

    except Exception as e:
        logger.error(f"Error listing MFA users: {str(e)}")
        return GraphApiResponse(
            status_code=500,
            data=[],
            error=f"Failed to list MFA users: {str(e)}"
        )


@router.get("/GetMFAComplianceReport", response_model=GraphApiResponse, summary="Get MFA Compliance Report")
async def get_mfa_compliance_report(clientId: Optional[str] = Query(None),org_id: Optional[int] = Query(None)):
    """
    Gets MFA compliance summary report showing percentage of users with MFA enabled.
    Uses only /users and /users/{id}/authentication/methods.
    Returns compliance status, percentages, and counts.
    """
    try:
        # Handle both clientId (old) and org_id (new) parameters
        if not clientId and not org_id:
            raise HTTPException(
                status_code=400,
                detail="Either clientId or org_id query parameter is required"
            )

        if clientId:
            # Old method: use clientId directly
            client_id = str(clientId).strip()
        else:

            creds = await get_organization_credentials(org_id)
            if not creds:
                raise HTTPException(
                    status_code=404,
                    detail=f"No credentials found for org_id: {org_id}"
                )
            client_id = creds['client_id']
        # 1. Call list_mfa_users() internally to get detailed user data
        mfa_users_response = await list_mfa_users(clientId=client_id, org_id=None)

        if mfa_users_response.status_code != 200:
            return GraphApiResponse(
                status_code=mfa_users_response.status_code,
                data=[],
                error=f"Failed to retrieve MFA user data: {mfa_users_response.error}"
            )

        users_data = mfa_users_response.data
        total_users = len(users_data)

        if total_users == 0:
            return GraphApiResponse(
                status_code=200,
                data=[{
                    "percentage": "0%",
                    "status": "Not Measured",
                    "target": "100%",
                    "total_users": 0,
                    "mfa_enabled": 0,
                    "mfa_disabled": 0,
                    "enabled_by_method": {
                        "mfa_registered": 0,
                        "conditional_access": 0,
                        "security_defaults": 0,
                        "per_user_mfa": 0
                    }
                }]
            )

        # 2. Count MFA-enabled users (based only on isMfaRegistered)
        mfa_enabled_count = sum(1 for user in users_data if user.get("isMfaRegistered", False))
        mfa_disabled_count = total_users - mfa_enabled_count

        enabled_by_method = {
            "mfa_registered": mfa_enabled_count,
            "conditional_access": 0,   # kept for response structure
            "security_defaults": 0,    # kept for response structure
            "per_user_mfa": 0          # kept for response structure
        }

        # 3. Calculate percentage
        percentage = (mfa_enabled_count / total_users) * 100

        if percentage.is_integer():
            percentage_str = f"{int(percentage)}%"
        else:
            percentage_str = f"{round(percentage, 1)}%"

        # 4. Compliance status
        if percentage == 100:
            status = "Compliant"
            recommendation = "Current status is good. Continue to monitor MFA compliance."
        elif percentage > 0:
            status = "Partially Compliant"
            recommendation = "Enable MFA for remaining users to achieve full compliance."
        else:
            status = "Not Compliant"
            recommendation = "URGENT: Enable MFA for all users immediately."

        compliance_report = {
            "percentage": percentage_str,
            "status": status,
            "target": "100%",
            "total_users": total_users,
            "mfa_enabled": mfa_enabled_count,
            "mfa_disabled": mfa_disabled_count,
            "enabled_by_method": enabled_by_method,
            "recommendation": recommendation,
            "details": {
                "description": "Percentage of users with MFA enabled (methods beyond password)",
                "measurement_date": datetime.now().isoformat() + "Z"
            }
        }

        return GraphApiResponse(status_code=200, data=[compliance_report])

    except Exception as e:
        logger.error(f"Error generating MFA compliance report: {str(e)}")
        return GraphApiResponse(
            status_code=500,
            data=[],
            error=f"Failed to generate MFA compliance report: {str(e)}"
        )
