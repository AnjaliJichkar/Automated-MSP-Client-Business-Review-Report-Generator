"""
Complete Pydantic schemas for data validation across all Microsoft Graph API endpoints.
This file contains all the request/response models for proper input validation.
"""

from pydantic import BaseModel, Field, validator, EmailStr
from typing import List, Dict, Any, Optional, Union
from enum import Enum
import re
from datetime import datetime


# =============================================================================
# GENERIC API RESPONSE MODEL
# =============================================================================

class GraphApiResponse(BaseModel):
    """A generic response model for Graph API data."""
    status_code: int = Field(..., description="The HTTP status code from the Graph API call.")
    data: Optional[Union[List[dict], dict]] = Field(
        None, description="The JSON data returned from the Graph API as a list or a single object."
    )
    error: Optional[str] = Field(None, description="An error message if the call failed.")


# =============================================================================
# ENUMS FOR CONTROLLED VALUES
# =============================================================================

class ConditionalAccessState(str, Enum):
    """Conditional Access policy states"""
    enabled = "enabled"
    disabled = "disabled"
    enabledForReportingButNotEnforced = "enabledForReportingButNotEnforced"


class UserRiskLevel(str, Enum):
    """User risk levels for conditional access"""
    low = "low"
    medium = "medium"
    high = "high"


class SignInRiskLevel(str, Enum):
    """Sign-in risk levels for conditional access"""
    low = "low"
    medium = "medium"
    high = "high"


class GrantControlType(str, Enum):
    """Built-in grant controls for conditional access"""
    block = "block"
    mfa = "mfa"
    compliantDevice = "compliantDevice"
    domainJoinedDevice = "domainJoinedDevice"
    approvedApplication = "approvedApplication"
    compliantApplication = "compliantApplication"


class PolicyIdEnum(str, Enum):
    """Supported policy IDs for automated fixing"""
    ADMIN_MFA = "policy-adminmfastatus"
    USER_MFA = "policy-usermfastatus"
    SHAREPOINT_RESHARING = "policy-sharepointexternalresharing"
    UNIFIED_AUDITING = "policy-unifiedauditingstatus"
    HIGH_RISK_USERS = "policy-highriskuserspolicy"
    RISKY_SIGNIN = "policy-riskysigninpolicies"
    SHARED_MAILBOX = "policy-sharedmailboxsignin"
    GUEST_ACCESS = "policy-guestuseraccesspermissions"
    SHAREPOINT_CREATION = "policy-sharepointsitecreation"
    WEAK_AUTHENTICATOR = "policy-weakauthenticatorstatus"
    PASSWORD_EXPIRATION = "policy-passwordexpirationpolicy"
    TEAMS_EXTERNAL = "policy-teamsexternalaccess"


# =============================================================================
# INTEGRATION PLATFORM CREDENTIALS
# =============================================================================

class SavePlatformCredentialsRequest(BaseModel):
    """Request model for saving single platform credentials and chart selections"""
    uuid: str = Field(..., description="User UUID from auth.users")
    platform_id: int = Field(..., description="Platform ID from integrations table")
    platform_name: Optional[str] = Field(None, description="Platform display name")
    status: Optional[str] = Field(None, description="Platform status")
    credentials: Dict[str, str] = Field(..., description="Platform credentials as key-value pairs")
    chartlist_selected_by_user: List[Dict[str, Any]] = Field(..., description="List of selected charts")

    @validator('uuid')
    def validate_uuid(cls, v):
        if not v or not v.strip():
            raise ValueError('UUID is required')
        return v.strip()

    @validator('chartlist_selected_by_user')
    def validate_chartlist(cls, v):
        if v is None:
            return []
        for chart in v:
            if 'chart_id' not in chart:
                raise ValueError('Each chart must have chart_id')
        return v


# =============================================================================
# COMPLIANCE FIX OPERATION SCHEMAS
# =============================================================================

class OptionalFixParameters(BaseModel):
    """Optional parameters that can be added to any fix endpoint"""
    dry_run: bool = Field(default=False, description="Simulate without applying changes")
    force: bool = Field(default=False, description="Force fix even if compliant")
    backup_first: bool = Field(default=True, description="Create backup before changes")
    notification_email: Optional[str] = Field(None, description="Email for notifications")
    custom_policy_prefix: Optional[str] = Field(None, max_length=50, description="Custom policy prefix")

    @validator('notification_email')
    def validate_email(cls, v):
        if v:
            email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
            if not email_pattern.match(v.strip()):
                raise ValueError(f'Invalid email format: {v}')
            return v.strip().lower()
        return v


class MFAFixRequest(BaseModel):
    """Request model for MFA compliance fixes"""
    target_users: Optional[List[str]] = Field(
        None,
        description="Specific user IDs to target (if empty, applies to all)"
    )
    policy_name_suffix: Optional[str] = Field(
        None,
        max_length=50,
        description="Custom suffix for policy name"
    )
    exclude_emergency_accounts: bool = Field(
        default=True,
        description="Exclude emergency access accounts from MFA requirement"
    )

    @validator('target_users')
    def validate_user_ids(cls, v):
        if v:
            guid_pattern = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
            valid_ids = []
            for user_id in v:
                if user_id.strip() and guid_pattern.match(user_id.strip()):
                    valid_ids.append(user_id.strip())
                else:
                    raise ValueError(f'Invalid user ID format: {user_id}')
            return valid_ids
        return v


class SharePointFixRequest(BaseModel):
    """Request model for SharePoint compliance fixes"""
    sharing_capability: Optional[str] = Field(
        None,
        pattern="^(Disabled|ExistingExternalUserSharingOnly|ExternalUserAndGuestSharing|ExternalUserSharingOnly)$",
        description="Desired sharing capability level"
    )
    allowed_domains: Optional[List[str]] = Field(
        None,
        max_items=10,
        description="Allowed domains for external sharing (max 10)"
    )
    disable_anonymous_links: bool = Field(
        default=True,
        description="Disable anonymous sharing links"
    )

    @validator('allowed_domains')
    def validate_domains(cls, v):
        if v:
            domain_pattern = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9-]{1,61}[a-zA-Z0-9]\.[a-zA-Z]{2,}$')
            valid_domains = []
            for domain in v:
                domain = domain.strip().lower()
                if domain and domain_pattern.match(domain):
                    valid_domains.append(domain)
                elif domain:  # non-empty but invalid
                    raise ValueError(f'Invalid domain format: {domain}')
            return valid_domains
        return v


class GuestAccessFixRequest(BaseModel):
    """Request model for guest access compliance fixes"""
    allow_invites_from: Optional[str] = Field(
        None,
        pattern="^(none|adminsAndGuestInvitors|adminsGuestInvitersAndAllMembers|everyone)$",
        description="Who can invite guest users"
    )
    block_external_signup: bool = Field(
        default=True,
        description="Block external users from signing up"
    )
    remove_existing_guests: bool = Field(
        default=False,
        description="Remove existing guest users (destructive operation)"
    )

    @validator('remove_existing_guests')
    def validate_destructive_operation(cls, v):
        if v:
            # This is a destructive operation that should be explicitly confirmed
            pass  # Could add additional validation logic here
        return v


# =============================================================================
# CONDITIONAL ACCESS POLICY SCHEMAS
# =============================================================================

class ConditionalAccessPolicyRequest(BaseModel):
    """Request model for creating conditional access policies"""
    displayName: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Display name for the conditional access policy"
    )
    state: ConditionalAccessState = Field(
        default=ConditionalAccessState.enabled,
        description="State of the conditional access policy"
    )
    users_include: List[str] = Field(
        default_factory=lambda: ["All"],
        description="Users or groups to include in the policy"
    )
    users_exclude: List[str] = Field(
        default_factory=list,
        description="Users or groups to exclude from the policy"
    )
    applications_include: List[str] = Field(
        default_factory=lambda: ["All"],
        description="Applications to include in the policy"
    )
    user_risk_levels: List[UserRiskLevel] = Field(
        default_factory=list,
        description="User risk levels to target"
    )
    sign_in_risk_levels: List[SignInRiskLevel] = Field(
        default_factory=list,
        description="Sign-in risk levels to target"
    )
    grant_controls: List[GrantControlType] = Field(
        ...,
        min_items=1,
        description="Grant controls to apply"
    )

    @validator('displayName')
    def validate_display_name(cls, v):
        """Validate policy display name"""
        cleaned_name = v.strip()
        if not cleaned_name:
            raise ValueError('Policy display name cannot be empty')

        # Prevent potentially confusing names
        forbidden_patterns = ['test', 'temp', 'delete']
        if any(pattern in cleaned_name.lower() for pattern in forbidden_patterns):
            raise ValueError('Policy name should not contain temporary or test-related terms')

        return cleaned_name

    @validator('users_exclude')
    def validate_user_exclusions(cls, v, values):
        """Ensure no user is both included and excluded"""
        included = values.get('users_include', [])
        if included and v:
            overlap = set(v) & set(included)
            if overlap:
                raise ValueError(f'Users cannot be both included and excluded: {overlap}')
        return v


# =============================================================================
# AUTHENTICATION METHOD SCHEMAS
# =============================================================================

class AuthenticationMethodConfigRequest(BaseModel):
    """Request model for configuring authentication methods"""
    sms_enabled: bool = Field(
        default=False,
        description="Enable or disable SMS authentication"
    )
    voice_enabled: bool = Field(
        default=False,
        description="Enable or disable voice authentication"
    )
    microsoft_authenticator_enabled: bool = Field(
        default=True,
        description="Enable or disable Microsoft Authenticator"
    )
    fido2_enabled: bool = Field(
        default=True,
        description="Enable or disable FIDO2 security keys"
    )


# =============================================================================
# SECURITY REMEDIATION SCHEMAS
# =============================================================================

class RiskyUserRemediationRequest(BaseModel):
    """Request model for remediating risky users"""
    user_ids: List[str] = Field(
        ...,
        min_items=1,
        max_items=50,
        description="List of user IDs to remediate"
    )
    action: str = Field(
        ...,
        pattern="^(dismiss|confirm_compromised|block_user)$",
        description="Remediation action: dismiss, confirm_compromised, or block_user"
    )

    @validator('user_ids')
    def validate_user_ids(cls, v):
        """Validate user IDs format and uniqueness"""
        if not v:
            raise ValueError('At least one user ID must be provided')

        # Remove duplicates and empty values
        cleaned_ids = list(set([uid.strip() for uid in v if uid.strip()]))

        if not cleaned_ids:
            raise ValueError('No valid user IDs provided')

        # Basic GUID format validation for Azure AD user IDs
        guid_pattern = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
        for user_id in cleaned_ids:
            if not guid_pattern.match(user_id):
                raise ValueError(f'Invalid user ID format: {user_id}')

        return cleaned_ids


class RiskDetectionReviewRequest(BaseModel):
    """Request model for reviewing risk detections"""
    detection_ids: List[str] = Field(
        ...,
        min_items=1,
        max_items=50,
        description="List of risk detection IDs to review"
    )
    action: str = Field(
        ...,
        pattern="^(dismiss|confirm_compromised)$",
        description="Review action: dismiss or confirm_compromised"
    )

    @validator('detection_ids')
    def validate_detection_ids(cls, v):
        """Validate detection IDs format and uniqueness"""
        if not v:
            raise ValueError('At least one detection ID must be provided')

        # Remove duplicates and empty values
        cleaned_ids = list(set([did.strip() for did in v if did.strip()]))

        if not cleaned_ids:
            raise ValueError('No valid detection IDs provided')

        # Basic GUID format validation for detection IDs
        guid_pattern = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
        for detection_id in cleaned_ids:
            if not guid_pattern.match(detection_id):
                raise ValueError(f'Invalid detection ID format: {detection_id}')

        return cleaned_ids


class PasswordResetRequest(BaseModel):
    """Request model for forcing password reset"""
    user_ids: List[str] = Field(
        ...,
        min_items=1,
        max_items=50,
        description="List of user IDs to force password reset"
    )

    @validator('user_ids')
    def validate_user_ids(cls, v):
        """Validate user IDs format and uniqueness"""
        if not v:
            raise ValueError('At least one user ID must be provided')

        # Remove duplicates and empty values
        cleaned_ids = list(set([uid.strip() for uid in v if uid.strip()]))

        if not cleaned_ids:
            raise ValueError('No valid user IDs provided')

        # Basic GUID format validation
        guid_pattern = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
        for user_id in cleaned_ids:
            if not guid_pattern.match(user_id):
                raise ValueError(f'Invalid user ID format: {user_id}')

        return cleaned_ids


# =============================================================================
# BULK OPERATION SCHEMAS
# =============================================================================

class BulkUserOperationRequest(BaseModel):
    """Request model for bulk user operations"""
    user_ids: List[str] = Field(
        ...,
        min_items=1,
        max_items=100,
        description="List of user IDs for bulk operation"
    )
    operation: str = Field(
        ...,
        pattern="^(enable|disable|delete|reset_password)$",
        description="Operation to perform on users"
    )
    confirm_destructive: bool = Field(
        default=False,
        description="Confirmation for destructive operations"
    )

    @validator('confirm_destructive')
    def validate_destructive_confirmation(cls, v, values):
        """Require confirmation for destructive operations"""
        operation = values.get('operation', '')
        if operation in ['disable', 'delete'] and not v:
            raise ValueError('Confirmation required for destructive operations')
        return v


# =============================================================================
# VALIDATION SCHEMAS FOR EXISTING ENDPOINTS
# =============================================================================

class PolicyIdValidation(BaseModel):
    """Validation model for policy ID path parameter"""
    policy_id: PolicyIdEnum

    @classmethod
    def validate_policy_id(cls, policy_id: str) -> str:
        """Validate and normalize policy ID"""
        try:
            # Try to convert to enum to validate
            normalized = PolicyIdEnum(policy_id.lower().strip())
            return normalized.value
        except ValueError:
            valid_policies = [p.value for p in PolicyIdEnum]
            raise ValueError(f'Invalid policy ID: {policy_id}. Valid options: {valid_policies}')


# =============================================================================
# UTILITY FUNCTIONS FOR VALIDATION
# =============================================================================

def validate_and_sanitize_policy_id(policy_id: str) -> str:
    """Utility function to validate and sanitize policy IDs"""
    try:
        return PolicyIdValidation.validate_policy_id(policy_id)
    except ValueError as e:
        raise ValueError(str(e))


# =============================================================================
# ACCOUNT ALLOCATION SCHEMAS
# =============================================================================

class AccountAllocationRequest(BaseModel):
    """Request model for account allocation endpoint"""
    companyName: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="Company name for the new account"
    )
    userId: str = Field(
        ...,
        description="User UUID (auth_user_id) from Supabase Auth"
    )
    userEmail: EmailStr = Field(
        ...,
        description="User email address"
    )

    @validator('companyName')
    def validate_company_name(cls, v):
        """Validate and clean company name"""
        cleaned_name = v.strip()
        if not cleaned_name:
            raise ValueError('Company name cannot be empty')
        return cleaned_name

    @validator('userId')
    def validate_user_id(cls, v):
        """Validate user ID is a valid UUID"""
        cleaned_id = v.strip()
        guid_pattern = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
        if not guid_pattern.match(cleaned_id):
            raise ValueError(f'Invalid user ID format: {v}. Must be a valid UUID.')
        return cleaned_id


# =============================================================================
# DELETE INTEGRATION CREDENTIALS SCHEMA
# =============================================================================

class DeleteIntegrationCredentialsRequest(BaseModel):
    """Request model for deleting a single integration's credentials"""
    uuid: str = Field(..., description="User UUID from auth.users")
    integration_key: str = Field(..., description="Integration key e.g. ninjaone, autotask, bitdefender")


# =============================================================================
# INTEGRATION CREDENTIALS SCHEMAS
# =============================================================================

class NinjaOneConfig(BaseModel):
    """NinjaOne platform configuration - flexible validation"""
    ninjaone_client_id: Optional[str] = None
    ninjaone_client_secret: Optional[str] = None
    ninjaone_instance_url: Optional[str] = None
    ninjaone_scopes: Optional[str] = "monitoring management"

    class Config:
        extra = "allow"  # Allow additional fields


class AutotaskConfig(BaseModel):
    """Autotask platform configuration - flexible validation"""
    autotask_username: Optional[str] = None
    autotask_secret: Optional[str] = None
    autotask_integration_code: Optional[str] = None
    autotask_base_url: Optional[str] = "https://webservices.autotask.net/atservicesrest/v1.0/"

    class Config:
        extra = "allow"  # Allow additional fields


class ConnectSecureConfig(BaseModel):
    """ConnectSecure platform configuration - flexible validation"""
    connectsecure_tenant_name: Optional[str] = None
    connectsecure_base_url: Optional[str] = None
    connectsecure_client_id: Optional[str] = None
    connectsecure_client_secret_b64: Optional[str] = None

    class Config:
        extra = "allow"  # Allow additional fields


class DNSFilterConfig(BaseModel):
    """DNSFilter platform configuration"""
    dnsfilter_api_key: Optional[str] = None

    class Config:
        extra = "allow"

class BlackpointConfig(BaseModel):
    """Blackpoint platform configuration"""
    blackpoint: Optional[Dict[str, Any]] = None

    class Config:
        extra = "allow"

class AxcientConfig(BaseModel):
    """Axcient platform configuration"""
    axcient_api_key: Optional[str] = None

    class Config:
        extra = "allow"


class PlatformItem(BaseModel):
    """Single platform with its configuration"""
    platform: str = Field(..., description="Platform name: ninjaone, autotask, connectsecure, dnsfilter, etc.")
    configuration: Union[NinjaOneConfig, AutotaskConfig, ConnectSecureConfig, DNSFilterConfig, BlackpointConfig, AxcientConfig, Dict[str, Any]] = Field(
        ...,
        description="Platform-specific configuration"
    )

    @validator('platform')
    def validate_platform(cls, v):
        """Validate platform name"""
        allowed_platforms = [
            'ninjaone', 'autotask', 'connectsecure', 'bitdefender',
            'cove', 'sentinelone', 'nodeware', 'dnsfilter', 'dropsuite', 'blackpoint', 'axcient'
        ]
        platform_lower = v.lower().strip()
        if platform_lower not in allowed_platforms:
            raise ValueError(f'Platform must be one of: {", ".join(allowed_platforms)}')
        return platform_lower


class SaveIntegrationCredentialsRequest(BaseModel):
    """Request model for saving integration credentials - flexible validation"""
    companyId: int = Field(..., description="Account ID from database", gt=0)
    companyName: str = Field(..., min_length=1, max_length=255, description="Company name")
    userId: str = Field(..., description="User UUID (auth_user_id)")
    platforms: List[PlatformItem] = Field(..., min_items=1, description="At least one platform required")

    @validator('companyName')
    def validate_company_name(cls, v):
        """Validate and clean company name"""
        cleaned_name = v.strip()
        if not cleaned_name:
            raise ValueError('Company name cannot be empty')
        return cleaned_name

    @validator('userId')
    def validate_user_id(cls, v):
        """Validate user ID is a valid UUID"""
        cleaned_id = v.strip()
        guid_pattern = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
        if not guid_pattern.match(cleaned_id):
            raise ValueError(f'Invalid user ID format: {v}. Must be a valid UUID.')
        return cleaned_id

    @validator('platforms')
    def validate_unique_platforms(cls, v):
        """Ensure no duplicate platforms"""
        platform_names = [item.platform for item in v]
        if len(platform_names) != len(set(platform_names)):
            raise ValueError('Duplicate platforms not allowed')
        return v

    class Config:
        extra = "forbid"  # Strict on root level but flexible on configurations