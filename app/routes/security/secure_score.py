import logging
import httpx
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Body, Depends, Query, HTTPException
from app.core.auth.middleware import get_access_token
from app.schemas.api import GraphApiResponse
from app.core.config.settings import GRAPH_V1_URL, GRAPH_BETA_URL
from app.core.auth.dependencies import get_client_id
from app.core.database.supabase_services import get_organization_credentials

# Create router for license endpoints
router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/GetMicrosoftSecureScore", response_model=GraphApiResponse, summary="Get Microsoft Secure Score")
async def get_microsoft_secure_score(clientId: Optional[str] = Query(None),org_id: Optional[int] = Query(None)):
    """
    Gets Microsoft Secure Score data from Microsoft Graph API.
    Returns current score, max score, percentage, and control scores for improvement actions.
    """

    # Mapping dictionaries for friendly names
    FRIENDLY_NAME_MAPPING = {
        # Improvement Actions
        "meeting_restrictanonymousjoin_v1": "Restrict anonymous users from joining Teams meetings",
        "meeting_autoadmitusers_v1": "Control automatic meeting admittance",
        "meeting_designatedpresenter_v1": "Restrict presentation rights in Teams meetings",
        "OneAdmin": "Add additional global administrators",
        "RoleOverlap": "Assign least privileged administrative roles",
        "spo_idle_session_timeout": "Configure SharePoint idle session timeout",
        "spo_legacy_auth": "Block legacy authentication in SharePoint",
        "AATP_DefenderForIdentityIsNotInstalled": "Install Microsoft Defender for Identity",
        "mdo_atpprotection": "Enable Defender for Office 365 protection",
        "dlp_datalossprevention": "Configure Data Loss Prevention policies",
        "exo_individualsharing": "Restrict calendar sharing with external users",
        "mdo_safedocuments": "Enable Safe Documents scanning",
        "mip_purviewlabelconsent": "Enable Microsoft Purview sensitivity labels",
        "CustomerLockBoxEnabled": "Enable Customer Lockbox approval",
        "exo_mailtipsenabled": "Enable MailTips for end users",
        "mip_search_auditlog": "Enable audit log search",
        "exo_mailboxaudit": "Enable mailbox auditing for all users",
        "exo_storageproviderrestricted": "Restrict additional storage providers",
        "exo_outlookaddins": "Control Outlook add-in installations",
        "mip_sensitivitylabelspolicies": "Publish sensitivity label policies",
        "mip_autosensitivitylabelspolicies": "Configure auto-labeling policies",
        "mdo_highconfidencespamaction": "Set high confidence spam action",
        "mdo_phisspamacation": "Configure phishing detection action",
        "mdo_quarantineretentionperiod": "Set quarantine retention period",
        "mdo_bulkthreshold": "Configure bulk spam threshold",
        "mdo_thresholdreachedaction": "Set outbound spam threshold action",

        # Completed Actions
        "MFARegistrationV2": "Require MFA for all users",
        "AdminMFAV2": "Require MFA for administrators",
        "BlockLegacyAuthentication": "Block legacy authentication",
        "PWAgePolicyNew": "Set password expiration policy",
        "SigninRiskPolicy": "Turn on sign-in risk policy",
        "UserRiskPolicy": "Turn on user risk policy",
        "mdo_safeattachments": "Enable Safe Attachments protection",
        "mdo_safelinksforemail": "Enable Safe Links for email",
        "mdo_enablemailboxintelligence": "Enable mailbox intelligence",
        "mdo_zapmalware": "Enable zero-hour auto purge (malware)",
        "mdo_commonattachmentsfilter": "Enable common attachment filter",
        "mdo_highconfidencephishaction": "Set high confidence phishing action",
        "mdo_safeattachmentpolicy": "Configure Safe Attachments policy",
        "mdo_spamaction": "Configure spam detection action",
        "IntegratedApps": "Control user consent for apps",
        "exo_oauth2clientprofileenabled": "Enable modern authentication",
        "exo_transportrulesallowlistdomains": "Secure transport rule domains",
        "mdo_zapphish": "Enable zero-hour auto purge (phish)",
        "mdo_bulkspamaction": "Configure bulk spam action",
        "mdo_allowedsenderscombined": "Secure allowed senders list"
    }

    # High Impact controls (specific overrides)
    HIGH_IMPACT_CONTROLS = {
        "OneAdmin", "RoleOverlap", "AATP_DefenderForIdentityIsNotInstalled",
        "MFARegistrationV2", "AdminMFAV2", "BlockLegacyAuthentication",
        "PWAgePolicyNew", "SigninRiskPolicy", "UserRiskPolicy", "IntegratedApps",
        "spo_legacy_auth"
    }

    # Potential point values for incomplete actions (based on completed actions analysis)
    POTENTIAL_POINTS = {
        "AdminMFAV2": 10,
        "MFARegistrationV2": 9,
        "PWAgePolicyNew": 8,
        "BlockLegacyAuthentication": 8,
        "mdo_safeattachments": 8,
        "mdo_enablemailboxintelligence": 8,
        "SigninRiskPolicy": 7,
        "UserRiskPolicy": 7,
        "mdo_zapmalware": 6,
        "mdo_commonattachmentsfilter": 5,
        "mdo_highconfidencephishaction": 5,
        "mdo_safeattachmentpolicy": 5,
        "mdo_spamaction": 5,
        "OneAdmin": 5,
        "RoleOverlap": 4,
        "IntegratedApps": 4,
        "AATP_DefenderForIdentityIsNotInstalled": 6,
        "spo_legacy_auth": 5,
        "exo_oauth2clientprofileenabled": 3,
        "exo_transportrulesallowlistdomains": 3,
        "mdo_zapphish": 3,
        "mdo_bulkspamaction": 3,
        "mdo_allowedsenderscombined": 2,
        "SelfServicePasswordReset": 1,
        "default": 3
    }

    def get_impact_level(control_name, control_category):
        if control_name in HIGH_IMPACT_CONTROLS:
            return "High Impact"
        elif control_category == "Identity":
            return "High Impact"
        else:
            return "Medium Impact"

    def get_friendly_name(control_name):
        return FRIENDLY_NAME_MAPPING.get(control_name, control_name.replace('_', ' ').title())

    def get_potential_points(control_name, actual_score):
        if actual_score > 0:
            return actual_score
        else:
            return POTENTIAL_POINTS.get(control_name, POTENTIAL_POINTS["default"])

    try:
        # Handle both clientId (old) and org_id (new) parameters
        if not clientId and not org_id:
            raise HTTPException(
                status_code=400,
                detail="Either clientId or org_id query parameter is required"
            )

        if clientId:
            # Old method: use clientId directly
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

        secure_score_url = f"{GRAPH_V1_URL}/security/secureScores"
        params = {
            "$top": 1,
            "$orderby": "createdDateTime desc"
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(secure_score_url, headers=headers, params=params, timeout=30.0)
            response.raise_for_status()
            score_data = response.json()

        scores = score_data.get("value", [])
        if not scores:
            return GraphApiResponse(
                status_code=404,
                data={},
                error="No secure score data found"
            )

        latest_score = scores[0]

        current_score = latest_score.get("currentScore", 0)
        max_score = latest_score.get("maxScore", 0)
        percentage = round((current_score / max_score) * 100) if max_score > 0 else 0

        control_scores = latest_score.get("controlScores", [])

        all_improvement_actions = []
        completed_actions = []

        for control in control_scores:
            control_name = control.get("controlName", "")
            control_category = control.get("controlCategory", "")
            score = control.get("score", 0)
            score_percentage = control.get("scoreInPercentage", 0)

            potential_points = get_potential_points(control_name, score)

            mapped_control = {
                "controlName": control_name,
                "friendlyName": get_friendly_name(control_name),
                "points": f"+{potential_points} pts",
                "impactLevel": get_impact_level(control_name, control_category),
                "category": control_category,
                "description": control.get("description", ""),
                "score": score,
                "scoreInPercentage": score_percentage,
                "implementationStatus": control.get("implementationStatus", ""),
                "lastSynced": control.get("lastSynced", ""),
                "completed": score_percentage > 0,
                "potentialPoints": potential_points
            }

            if score_percentage == 0:
                all_improvement_actions.append(mapped_control)
            else:
                completed_actions.append(mapped_control)

        #  FIX: Get only top 5 improvement actions by potential points
        top_improvement_actions = sorted(
            all_improvement_actions,
            key=lambda x: x["potentialPoints"],
            reverse=True
        )[:5]

        result_data = {
            "scoreData": {
                "currentScore": current_score,
                "maxScore": max_score,
                "percentage": f"{percentage}%",
                "activeUserCount": latest_score.get("activeUserCount", 0),
                "licensedUserCount": latest_score.get("licensedUserCount", 0),
                "createdDateTime": latest_score.get("createdDateTime", ""),
                "azureTenantId": latest_score.get("azureTenantId", "")
            },
            "topImprovementActions": top_improvement_actions,
            "allImprovementActions": all_improvement_actions,
            "completedActions": completed_actions,
            "summary": {
                "totalControls": len(control_scores),
                "needsImprovement": len(all_improvement_actions),
                "completed": len(completed_actions)
            }
        }

        return GraphApiResponse(status_code=200, data=result_data)

    except httpx.HTTPStatusError as exc:
        logger.error(f"Graph API HTTP error: {exc.response.status_code} - {exc.response.text}")
        return GraphApiResponse(
            status_code=exc.response.status_code,
            data={},
            error=f"Graph API error: {exc.response.text}"
        )
    except Exception as e:
        logger.error(f"Error getting Microsoft Secure Score: {str(e)}")
        return GraphApiResponse(
            status_code=500,
            data={},
            error=f"Failed to get Microsoft Secure Score: {str(e)}"
        )
