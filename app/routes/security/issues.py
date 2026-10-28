import logging
import httpx
from fastapi import APIRouter
from app.core.auth.middleware import get_access_token
from app.schemas.api import GraphApiResponse
from app.schemas.api import (
    BulkUserOperationRequest,
    RiskyUserRemediationRequest,
    RiskDetectionReviewRequest,
    PasswordResetRequest
)
# Create router for security endpoints
router = APIRouter()
logger = logging.getLogger(__name__)

#------------Security Issues------------
#Risky users (403 error) (Your tenant is not licensed for this feature)

@router.get("/ListHighRiskUsers", response_model=GraphApiResponse, summary="List High Risk Users")
async def list_high_risk_users():
    """
    Fetches high-risk users from Microsoft Graph API (Identity Protection).
    Returns a dictionary where each key is the userPrincipalName and value is their risk details.
    """
    try:
        token = get_access_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        results = {}

        async with httpx.AsyncClient() as client:
            risky_users_url = "https://graph.microsoft.com/v1.0/identityProtection/riskyUsers"
            risky_users_response = await client.get(risky_users_url, headers=headers, timeout=30.0)
            risky_users_response.raise_for_status()

            items = risky_users_response.json().get("value", [])

            for user in items:
                user_id = user.get("id")  # ← CAPTURE USER ID
                upn = user.get("userPrincipalName") or user_id

                results[upn] = {
                    "UserId": user_id,  # ← ADD USER ID TO RESPONSE
                    "DisplayName": user.get("userDisplayName"),
                    "RiskLevel": user.get("riskLevel"),
                    "RiskState": user.get("riskState"),
                    "RiskDetail": user.get("riskDetail"),
                    "RiskLastUpdated": user.get("riskLastUpdatedDateTime"),
                    "IsDeleted": user.get("isDeleted", False),
                    "IsProcessing": user.get("isProcessing", False),
                    "UserPrincipalName": user.get("userPrincipalName")  # ← KEEP UPN FOR REFERENCE
                }

        return GraphApiResponse(status_code=200, data=results)

    except httpx.HTTPStatusError as exc:
        return GraphApiResponse(
            status_code=exc.response.status_code,
            data={},
            error=f"Graph API error: {exc.response.text}"
        )
    except Exception as e:
        return GraphApiResponse(
            status_code=500,
            data={},
            error=f"Failed to get high risk users: {str(e)}"
        )


#Rsky Sign-Ins (403 error) (Your tenant is not licensed for this feature)
@router.get("/ListRiskySignInEvents", response_model=GraphApiResponse, summary="List Risky Sign-In Events")
async def list_risky_signin_events():
    """
    Fetches risky sign-in events from Microsoft Graph API.
    Returns a dictionary where each key is the event ID and value is the sign-in event details.
    """
    try:
        token = get_access_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        results = {}

        async with httpx.AsyncClient() as client:
            filter_param = "riskState eq 'atRisk' or riskState eq 'confirmedCompromised'"
            signin_url = f"https://graph.microsoft.com/v1.0/auditLogs/signIns?$filter={filter_param}"
            signin_response = await client.get(signin_url, headers=headers, timeout=30.0)
            signin_response.raise_for_status()

            items = signin_response.json().get("value", [])

            for event in items:
                location_info = event.get("location", {})
                location_data = {
                    "city": location_info.get("city"),
                    "countryOrRegion": location_info.get("countryOrRegion"),
                    "state": location_info.get("state"),
                    "geoCoordinates": location_info.get("geoCoordinates")
                }

                event_id = event.get("id")
                results[event_id] = {
                    "UserDisplayName": event.get("userDisplayName"),
                    "UserId": event.get("userId"),
                    "UserPrincipalName": event.get("userPrincipalName"),
                    "IPAddress": event.get("ipAddress"),
                    "ClientAppUsed": event.get("clientAppUsed"),
                    "CorrelationId": event.get("correlationId"),
                    "ConditionalAccessStatus": event.get("conditionalAccessStatus"),
                    "AppliedConditionalAccessPolicies": event.get("appliedConditionalAccessPolicies"),
                    "IsInteractive": event.get("isInteractive"),
                    "DeviceDetail": event.get("deviceDetail"),
                    "Location": location_data,
                    "RiskDetail": event.get("riskDetail"),
                    "RiskLevelAggregated": event.get("riskLevelAggregated"),
                    "RiskLevelDuringSignIn": event.get("riskLevelDuringSignIn"),
                    "RiskState": event.get("riskState"),
                    "RiskEventTypes": event.get("riskEventTypes"),
                    "RiskEventTypes_v2": event.get("riskEventTypes_v2"),
                    "ResourceDisplayName": event.get("resourceDisplayName"),
                    "ResourceId": event.get("resourceId"),
                    "Status": event.get("status"),
                    "AppDisplayName": event.get("appDisplayName"),
                    "AppId": event.get("appId"),
                    "CreatedDateTime": event.get("createdDateTime")
                }

        return GraphApiResponse(status_code=200, data=results)

    except httpx.HTTPStatusError as exc:
        return GraphApiResponse(
            status_code=exc.response.status_code,
            data={},
            error=f"Graph API error: {exc.response.text}"
        )
    except Exception as e:
        return GraphApiResponse(
            status_code=500,
            data={},
            error=f"Failed to get risky sign-in events: {str(e)}"
        )




@router.post("/RemediateRiskyUser", response_model=GraphApiResponse, summary="Remediate Risky User")
async def remediate_risky_user(request: RiskyUserRemediationRequest):
    """
    Remediate risky users with actions: dismiss risk, confirm compromised, or block user.
    """
    try:
        token = get_access_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        results = []

        for user_id in request.user_ids:
            try:
                if request.action == "dismiss":
                    # Dismiss user risk
                    dismiss_url = f"https://graph.microsoft.com/v1.0/identityProtection/riskyUsers/dismiss"
                    dismiss_payload = {"userIds": [user_id]}

                    async with httpx.AsyncClient() as client:
                        response = await client.post(dismiss_url, headers=headers, json=dismiss_payload, timeout=30.0)
                        response.raise_for_status()

                    results.append({
                        "userId": user_id,
                        "action": "dismissed",
                        "status": "success",
                        "message": "User risk dismissed successfully"
                    })

                elif request.action == "confirm_compromised":
                    # Confirm user compromised
                    confirm_url = f"https://graph.microsoft.com/v1.0/identityProtection/riskyUsers/confirmCompromised"
                    confirm_payload = {"userIds": [user_id]}

                    async with httpx.AsyncClient() as client:
                        response = await client.post(confirm_url, headers=headers, json=confirm_payload, timeout=30.0)
                        response.raise_for_status()

                    results.append({
                        "userId": user_id,
                        "action": "confirmed_compromised",
                        "status": "success",
                        "message": "User confirmed as compromised"
                    })

                elif request.action == "block_user":
                    # Block user account
                    block_url = f"https://graph.microsoft.com/v1.0/users/{user_id}"
                    block_payload = {"accountEnabled": False}

                    async with httpx.AsyncClient() as client:
                        response = await client.patch(block_url, headers=headers, json=block_payload, timeout=30.0)
                        response.raise_for_status()

                    results.append({
                        "userId": user_id,
                        "action": "blocked",
                        "status": "success",
                        "message": "User account blocked successfully"
                    })

            except httpx.HTTPStatusError as user_exc:
                results.append({
                    "userId": user_id,
                    "action": request.action,
                    "status": "failed",
                    "error": f"HTTP {user_exc.response.status_code}: {user_exc.response.text}"
                })
            except Exception as user_e:
                results.append({
                    "userId": user_id,
                    "action": request.action,
                    "status": "failed",
                    "error": str(user_e)
                })

        return GraphApiResponse(
            status_code=200,
            data={"remediation_results": results}
        )

    except Exception as e:
        logger.error(f"Error remediating risky users: {str(e)}")
        return GraphApiResponse(
            status_code=500,
            data={},
            error=f"Failed to remediate risky users: {str(e)}"
        )


# ================== REVIEW BUTTON ENDPOINTS ==================

@router.post("/ReviewRiskDetection", response_model=GraphApiResponse, summary="Review Risk Detection")
async def review_risk_detection(request: RiskDetectionReviewRequest):
    """
    Review risky sign-in detections with actions: dismiss risk or confirm compromised.
    """
    try:
        token = get_access_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        results = []

        if request.action == "dismiss":
            # Dismiss risk detections
            dismiss_url = f"https://graph.microsoft.com/v1.0/identityProtection/riskDetections/dismiss"
            dismiss_payload = {"riskDetectionIds": request.detection_ids}

            async with httpx.AsyncClient() as client:
                response = await client.post(dismiss_url, headers=headers, json=dismiss_payload, timeout=30.0)
                response.raise_for_status()

            for detection_id in request.detection_ids:
                results.append({
                    "detectionId": detection_id,
                    "action": "dismissed",
                    "status": "success",
                    "message": "Risk detection dismissed successfully"
                })

        elif request.action == "confirm_compromised":
            # Confirm risk detections as compromised
            confirm_url = f"https://graph.microsoft.com/v1.0/identityProtection/riskDetections/confirmCompromised"
            confirm_payload = {"riskDetectionIds": request.detection_ids}

            async with httpx.AsyncClient() as client:
                response = await client.post(confirm_url, headers=headers, json=confirm_payload, timeout=30.0)
                response.raise_for_status()

            for detection_id in request.detection_ids:
                results.append({
                    "detectionId": detection_id,
                    "action": "confirmed_compromised",
                    "status": "success",
                    "message": "Risk detection confirmed as compromised"
                })

        return GraphApiResponse(
            status_code=200,
            data={"review_results": results}
        )

    except httpx.HTTPStatusError as exc:
        logger.error(f"Graph API HTTP error: {exc.response.status_code} - {exc.response.text}")
        return GraphApiResponse(
            status_code=exc.response.status_code,
            data={},
            error=f"Graph API error: {exc.response.text}"
        )
    except Exception as e:
        logger.error(f"Error reviewing risk detections: {str(e)}")
        return GraphApiResponse(
            status_code=500,
            data={},
            error=f"Failed to review risk detections: {str(e)}"
        )


# ================== ADDITIONAL HELPER ENDPOINTS ==================

@router.post("/ForcePasswordReset", response_model=GraphApiResponse, summary="Force Password Reset for User")
async def force_password_reset(request: PasswordResetRequest):
    """
    Force password reset for risky users.
    """
    try:
        token = get_access_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        results = []

        for user_id in request.user_ids:
            try:
                reset_url = f"https://graph.microsoft.com/v1.0/users/{user_id}"
                reset_payload = {
                    "passwordProfile": {
                        "forceChangePasswordNextSignIn": True
                    }
                }

                async with httpx.AsyncClient() as client:
                    response = await client.patch(reset_url, headers=headers, json=reset_payload, timeout=30.0)
                    response.raise_for_status()

                results.append({
                    "userId": user_id,
                    "action": "password_reset_forced",
                    "status": "success",
                    "message": "Password reset will be required at next sign-in"
                })

            except Exception as user_e:
                results.append({
                    "userId": user_id,
                    "action": "password_reset_forced",
                    "status": "failed",
                    "error": str(user_e)
                })

        return GraphApiResponse(
            status_code=200,
            data={"password_reset_results": results}
        )

    except Exception as e:
        logger.error(f"Error forcing password reset: {str(e)}")
        return GraphApiResponse(
            status_code=500,
            data={},
            error=f"Failed to force password reset: {str(e)}"
        )


# -----------Security Alerts------------ (403 ERROR) (Your tenant is not licensed for this feature)
@router.get("/ListSecurityAlertsComprehensive", response_model=GraphApiResponse,
            summary="List Comprehensive Security Alerts")
async def list_security_alerts_comprehensive():
    """
    Lists comprehensive security alerts from multiple endpoints including modern alerts,
    identity risk detections, and security incidents. Returns all key fields for security monitoring.
    """
    try:
        token = get_access_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        # Step 1: Get modern security alerts (alerts_v2)
        alerts_v2_url = f"https://graph.microsoft.com/v1.0/security/alerts_v2"
        alerts_params = {
            "$select": "id,title,description,severity,status,category,createdDateTime,lastUpdateDateTime,serviceSource,actorDisplayName,alertWebUrl",
            "$top": 50,
            "$orderby": "createdDateTime desc"
        }

        async with httpx.AsyncClient() as client:
            alerts_response = await client.get(alerts_v2_url, headers=headers, params=alerts_params, timeout=30.0)
            alerts_response.raise_for_status()
            alerts_data = alerts_response.json()

        security_alerts = alerts_data.get("value", [])

        # Step 2: Get identity protection risk detections
        risk_detections_url = f"https://graph.microsoft.com/v1.0/identityProtection/riskDetections"
        risk_params = {
            "$select": "id,riskEventType,riskLevel,riskState,detectedDateTime,activityDateTime,userPrincipalName,userDisplayName,ipAddress,location",
            "$top": 50,
            "$orderby": "detectedDateTime desc"
        }

        async with httpx.AsyncClient() as client:
            risk_response = await client.get(risk_detections_url, headers=headers, params=risk_params, timeout=30.0)
            risk_response.raise_for_status()
            risk_data = risk_response.json()

        risk_detections = risk_data.get("value", [])

        # Step 3: Get security incidents
        incidents_url = f"https://graph.microsoft.com/beta/security/incidents"
        incidents_params = {
            "$select": "id,displayName,description,severity,status,classification,createdDateTime,lastUpdateDateTime,assignedTo,incidentWebUrl",
            "$top": 50,
            "$orderby": "createdDateTime desc"
        }

        async with httpx.AsyncClient() as client:
            incidents_response = await client.get(incidents_url, headers=headers, params=incidents_params, timeout=30.0)
            incidents_response.raise_for_status()
            incidents_data = incidents_response.json()

        security_incidents = incidents_data.get("value", [])

        # ===== NEW PROCESSING LOGIC =====

        # 1. Alert Count - Calculate totals
        total_alerts = len(security_alerts) + len(risk_detections) + len(security_incidents)

        # 4. Additional Processing - Merge all alerts into single array
        all_alerts = []

        # Process Security Alerts v2
        for alert in security_alerts:
            standardized_alert = {
                "id": alert.get("id"),
                "title": alert.get("title"),
                "description": alert.get("description", ""),
                "severity": alert.get("severity"),
                "status": alert.get("status"),
                "category": alert.get("category"),
                "alertDateTime": alert.get("createdDateTime"),  # Standardized date field
                "lastUpdated": alert.get("lastUpdateDateTime"),
                "alertType": "SecurityAlert",
                "serviceSource": alert.get("serviceSource"),
                "actorDisplayName": alert.get("actorDisplayName"),
                "alertWebUrl": alert.get("alertWebUrl"),
                "affectedUser": None  # Security alerts may not have user context
            }
            all_alerts.append(standardized_alert)

        # Process Risk Detections with User Context Enhancement
        for risk in risk_detections:
            # 3. User Context Enhancement - Combine user info
            user_context = ""
            affected_user = None
            if risk.get("userPrincipalName") or risk.get("userDisplayName"):
                user_name = risk.get("userDisplayName") or "Unknown User"
                user_email = risk.get("userPrincipalName") or "No email"
                affected_user = f"{user_name} ({user_email})"
                user_context = f" for user {user_email}"

            # Enhanced description with user context
            base_description = risk.get("riskEventType", "Risk detection")
            enhanced_description = f"{base_description}{user_context}"
            if risk.get("location"):
                location_info = risk.get("location", {})
                if location_info.get("city") or location_info.get("countryOrRegion"):
                    location_str = f"{location_info.get('city', '')}, {location_info.get('countryOrRegion', '')}".strip(
                        ', ')
                    enhanced_description += f" from {location_str}"

            standardized_alert = {
                "id": risk.get("id"),
                "title": risk.get("riskEventType"),
                "description": enhanced_description,
                "severity": risk.get("riskLevel"),
                "status": risk.get("riskState"),
                "category": "Identity",
                "alertDateTime": risk.get("detectedDateTime"),  # Standardized date field
                "lastUpdated": risk.get("activityDateTime"),
                "alertType": "RiskDetection",
                "serviceSource": "Identity Protection",
                "actorDisplayName": affected_user,
                "alertWebUrl": None,
                "affectedUser": affected_user,  # 3. User Context Enhancement
                "ipAddress": risk.get("ipAddress"),
                "location": risk.get("location")
            }
            all_alerts.append(standardized_alert)

        # Process Security Incidents
        for incident in security_incidents:
            standardized_alert = {
                "id": incident.get("id"),
                "title": incident.get("displayName"),
                "description": incident.get("description", ""),
                "severity": incident.get("severity"),
                "status": incident.get("status"),
                "category": incident.get("classification"),
                "alertDateTime": incident.get("createdDateTime"),  # Standardized date field
                "lastUpdated": incident.get("lastUpdateDateTime"),
                "alertType": "SecurityIncident",
                "serviceSource": "Security Center",
                "actorDisplayName": None,
                "alertWebUrl": incident.get("incidentWebUrl"),
                "affectedUser": None,
                "assignedTo": incident.get("assignedTo")
            }
            all_alerts.append(standardized_alert)

        # 4. Sort by date - Most recent first
        all_alerts.sort(key=lambda x: x.get("alertDateTime") or "", reverse=True)

        # 1. Calculate summary statistics
        summary_stats = {
            "totalAlerts": total_alerts,
            "byType": {
                "securityAlerts": len(security_alerts),
                "riskDetections": len(risk_detections),
                "securityIncidents": len(security_incidents)
            },
            "bySeverity": {},
            "byStatus": {}
        }

        # Count by severity and status
        for alert in all_alerts:
            severity = alert.get("severity", "unknown")
            status = alert.get("status", "unknown")

            summary_stats["bySeverity"][severity] = summary_stats["bySeverity"].get(severity, 0) + 1
            summary_stats["byStatus"][status] = summary_stats["byStatus"].get(status, 0) + 1

        # 5. Response Structure Change - New format
        result_data = {
            "allAlerts": all_alerts,  # Merged and sorted alerts
            "summary": summary_stats,  # Alert count and statistics
            "originalData": {  # Keep original structure for reference
                "securityAlertsV2": security_alerts,
                "identityProtectionRiskDetections": risk_detections,
                "securityIncidents": security_incidents
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
        logger.error(f"Error listing comprehensive security alerts: {str(e)}")
        return GraphApiResponse(
            status_code=500,
            data={},
            error=f"Failed to list comprehensive security alerts: {str(e)}"
        )


@router.get("/ViewAlertDetails/{alert_type}/{alert_id}", response_model=GraphApiResponse, summary="View Alert Details")
async def view_alert_details(alert_type: str, alert_id: str):
    """
    Gets detailed information for a specific alert based on its type and ID.
    Routes to appropriate Microsoft Graph endpoint based on alert type.
    """
    try:
        token = get_access_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        # Validate alert type
        valid_types = ["SecurityAlert", "RiskDetection", "SecurityIncident"]
        if alert_type not in valid_types:
            return GraphApiResponse(
                status_code=400,
                data={},
                error=f"Invalid alert type. Must be one of: {', '.join(valid_types)}"
            )

        detail_data = {}

        async with httpx.AsyncClient() as client:
            if alert_type == "SecurityAlert":
                # Get Security Alert v2 details
                alert_detail_url = f"https://graph.microsoft.com/v1.0/security/alerts_v2/{alert_id}"
                detail_response = await client.get(alert_detail_url, headers=headers, timeout=30.0)
                detail_response.raise_for_status()
                alert_detail = detail_response.json()

                # Get evidence if available
                try:
                    evidence_url = f"https://graph.microsoft.com/v1.0/security/alerts_v2/{alert_id}/evidence"
                    evidence_response = await client.get(evidence_url, headers=headers, timeout=30.0)
                    if evidence_response.status_code == 200:
                        evidence_data = evidence_response.json().get("value", [])
                    else:
                        evidence_data = []
                except:
                    evidence_data = []

                # Get comments if available
                try:
                    comments_url = f"https://graph.microsoft.com/v1.0/security/alerts_v2/{alert_id}/comments"
                    comments_response = await client.get(comments_url, headers=headers, timeout=30.0)
                    if comments_response.status_code == 200:
                        comments_data = comments_response.json().get("value", [])
                    else:
                        comments_data = []
                except:
                    comments_data = []

                detail_data = {
                    "alertType": "SecurityAlert",
                    "alertDetails": alert_detail,
                    "evidence": evidence_data,
                    "comments": comments_data,
                    "additionalInfo": {
                        "serviceSource": alert_detail.get("serviceSource"),
                        "detectionSource": alert_detail.get("detectionSource"),
                        "threatFamilyName": alert_detail.get("threatFamilyName"),
                        "mitreTechniques": alert_detail.get("mitreTechniques", [])
                    }
                }

            elif alert_type == "RiskDetection":
                # Get Risk Detection details
                risk_detail_url = f"https://graph.microsoft.com/v1.0/identityProtection/riskDetections/{alert_id}"
                detail_response = await client.get(risk_detail_url, headers=headers, timeout=30.0)
                detail_response.raise_for_status()
                risk_detail = detail_response.json()

                # Get user risk information if user ID is available
                user_risk_data = None
                if risk_detail.get("userId"):
                    try:
                        user_risk_url = f"https://graph.microsoft.com/v1.0/identityProtection/riskyUsers/{risk_detail.get('userId')}"
                        user_risk_response = await client.get(user_risk_url, headers=headers, timeout=30.0)
                        if user_risk_response.status_code == 200:
                            user_risk_data = user_risk_response.json()
                    except:
                        user_risk_data = None

                detail_data = {
                    "alertType": "RiskDetection",
                    "alertDetails": risk_detail,
                    "userRiskInfo": user_risk_data,
                    "additionalInfo": {
                        "riskEventType": risk_detail.get("riskEventType"),
                        "riskLevel": risk_detail.get("riskLevel"),
                        "riskState": risk_detail.get("riskState"),
                        "source": risk_detail.get("source"),
                        "tokenIssuerType": risk_detail.get("tokenIssuerType"),
                        "correlationId": risk_detail.get("correlationId")
                    }
                }

            elif alert_type == "SecurityIncident":
                # Get Security Incident details
                incident_detail_url = f"https://graph.microsoft.com/beta/security/incidents/{alert_id}"
                detail_response = await client.get(incident_detail_url, headers=headers, timeout=30.0)
                detail_response.raise_for_status()
                incident_detail = detail_response.json()

                # Get associated alerts if available
                try:
                    alerts_url = f"https://graph.microsoft.com/beta/security/incidents/{alert_id}/alerts"
                    alerts_response = await client.get(alerts_url, headers=headers, timeout=30.0)
                    if alerts_response.status_code == 200:
                        associated_alerts = alerts_response.json().get("value", [])
                    else:
                        associated_alerts = []
                except:
                    associated_alerts = []

                detail_data = {
                    "alertType": "SecurityIncident",
                    "alertDetails": incident_detail,
                    "associatedAlerts": associated_alerts,
                    "additionalInfo": {
                        "classification": incident_detail.get("classification"),
                        "determination": incident_detail.get("determination"),
                        "assignedTo": incident_detail.get("assignedTo"),
                        "tags": incident_detail.get("tags", []),
                        "comments": incident_detail.get("comments", [])
                    }
                }

        # Build standardized response for UI
        result_data = {
            "alertId": alert_id,
            "alertType": alert_type,
            "detailsData": detail_data,
            "summary": {
                "title": detail_data["alertDetails"].get("title") or detail_data["alertDetails"].get("displayName") or
                         detail_data["alertDetails"].get("riskEventType"),
                "description": detail_data["alertDetails"].get("description", ""),
                "severity": detail_data["alertDetails"].get("severity") or detail_data["alertDetails"].get("riskLevel"),
                "status": detail_data["alertDetails"].get("status") or detail_data["alertDetails"].get("riskState"),
                "createdDateTime": detail_data["alertDetails"].get("createdDateTime") or detail_data[
                    "alertDetails"].get("detectedDateTime"),
                "lastUpdated": detail_data["alertDetails"].get("lastUpdateDateTime") or detail_data["alertDetails"].get(
                    "activityDateTime")
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
        logger.error(f"Error getting alert details: {str(e)}")
        return GraphApiResponse(
            status_code=500,
            data={},
            error=f"Failed to get alert details: {str(e)}"
        )
