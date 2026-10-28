# This file contains the wrapper endpoint implementations
# that will be added to the main compliance file

ENDPOINT_WRAPPERS = '''

# =========================
# EXTERNAL ENDPOINT WRAPPERS (Individual access - each gets own token)
# =========================

@router.get("/ListSharePointExternalResharingStatus", response_model=GraphApiResponse, summary="Check SharePoint External Resharing Policy")
async def list_sharepoint_external_resharing_status_endpoint(credentials: tuple = Depends(get_client_credentials)):
    """External endpoint for SharePoint External Resharing Status"""
    identifier, identifier_type = credentials
    if identifier_type == "ninjaone_org_id":
        from app.core.database.supabase_services import supabase
        response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
        client_id = response.data[0]['client_id']
    else:
        client_id = identifier
    token = await get_access_token_by_identifier(identifier, identifier_type)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    return await list_sharepoint_external_resharing_status(headers, client_id)

@router.get("/ListUnifiedAuditingStatus", response_model=GraphApiResponse, summary="Check Unified Auditing Logs Status")
async def list_unified_auditing_status_endpoint(credentials: tuple = Depends(get_client_credentials)):
    """External endpoint for Unified Auditing Status"""
    identifier, identifier_type = credentials
    if identifier_type == "ninjaone_org_id":
        from app.core.database.supabase_services import supabase
        response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
        client_id = response.data[0]['client_id']
    else:
        client_id = identifier
    token = await get_access_token_by_identifier(identifier, identifier_type)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    return await list_unified_auditing_status(headers, client_id)

@router.get("/ListHighRiskUsersPolicies", response_model=GraphApiResponse, summary="Check High Risk Users Policies")
async def list_high_risk_users_signin_policies_endpoint(credentials: tuple = Depends(get_client_credentials)):
    """External endpoint for High Risk Users Policies"""
    identifier, identifier_type = credentials
    if identifier_type == "ninjaone_org_id":
        from app.core.database.supabase_services import supabase
        response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
        client_id = response.data[0]['client_id']
    else:
        client_id = identifier
    token = await get_access_token_by_identifier(identifier, identifier_type)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    return await list_high_risk_users_signin_policies(headers, client_id)

@router.get("/ListRiskySignInPolicies", response_model=GraphApiResponse, summary="Check Block Risky Sign-In Policies")
async def list_risky_signin_policies_endpoint(credentials: tuple = Depends(get_client_credentials)):
    """External endpoint for Risky Sign-In Policies"""
    identifier, identifier_type = credentials
    if identifier_type == "ninjaone_org_id":
        from app.core.database.supabase_services import supabase
        response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
        client_id = response.data[0]['client_id']
    else:
        client_id = identifier
    token = await get_access_token_by_identifier(identifier, identifier_type)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    return await list_risky_signin_policies(headers, client_id)

@router.get("/ListSharedMailboxSignInStatus", response_model=GraphApiResponse, summary="Check Shared Mailbox Sign-In Status")
async def list_shared_mailbox_signin_status_endpoint(credentials: tuple = Depends(get_client_credentials)):
    """External endpoint for Shared Mailbox Sign-In Status"""
    identifier, identifier_type = credentials
    if identifier_type == "ninjaone_org_id":
        # Pass org_id to the main function
        return await list_shared_mailbox_signin_status(clientId=None, org_id=identifier)
    else:
        # Pass clientId to the main function
        return await list_shared_mailbox_signin_status(clientId=identifier, org_id=None)

@router.get("/ListGuestUserAccessPermissions", response_model=GraphApiResponse, summary="Check Guest User Access Permissions")
async def list_guest_user_access_permissions_endpoint(credentials: tuple = Depends(get_client_credentials)):
    """External endpoint for Guest User Access Permissions"""
    identifier, identifier_type = credentials
    if identifier_type == "ninjaone_org_id":
        from app.core.database.supabase_services import supabase
        response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
        client_id = response.data[0]['client_id']
    else:
        client_id = identifier
    token = await get_access_token_by_identifier(identifier, identifier_type)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    return await list_guest_user_access_permissions(headers, client_id)

@router.get("/ListSharePointSiteCreationStatus", response_model=GraphApiResponse, summary="Check SharePoint Site Creation Status")
async def list_sharepoint_site_creation_status_endpoint(credentials: tuple = Depends(get_client_credentials)):
    """External endpoint for SharePoint Site Creation Status"""
    identifier, identifier_type = credentials
    if identifier_type == "ninjaone_org_id":
        from app.core.database.supabase_services import supabase
        response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
        client_id = response.data[0]['client_id']
    else:
        client_id = identifier
    token = await get_access_token_by_identifier(identifier, identifier_type)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    return await list_sharepoint_site_creation_status(headers, client_id)

@router.get("/ListWeakAuthenticatorStatus", response_model=GraphApiResponse, summary="Check Weak Authenticator Status")
async def list_weak_authenticator_status_endpoint(credentials: tuple = Depends(get_client_credentials)):
    """External endpoint for Weak Authenticator Status"""
    identifier, identifier_type = credentials
    if identifier_type == "ninjaone_org_id":
        from app.core.database.supabase_services import supabase
        response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
        client_id = response.data[0]['client_id']
    else:
        client_id = identifier
    token = await get_access_token_by_identifier(identifier, identifier_type)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    return await list_weak_authenticator_status(headers, client_id)

@router.get("/ListGlobalAdmins", response_model=GraphApiResponse, summary="List Global Administrators")
async def list_global_admins_endpoint(credentials: tuple = Depends(get_client_credentials)):
    """External endpoint for Global Admins"""
    identifier, identifier_type = credentials
    if identifier_type == "ninjaone_org_id":
        from app.core.database.supabase_services import supabase
        response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
        client_id = response.data[0]['client_id']
    else:
        client_id = identifier
    token = await get_access_token_by_identifier(identifier, identifier_type)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    return await list_global_admins(headers, client_id)

@router.get("/CheckPasswordExpirationPolicy", response_model=GraphApiResponse, summary="Check Password Expiration Policy")
async def check_password_expiration_policy_endpoint(credentials: tuple = Depends(get_client_credentials)):
    """External endpoint for Password Expiration Policy"""
    identifier, identifier_type = credentials
    if identifier_type == "ninjaone_org_id":
        from app.core.database.supabase_services import supabase
        response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
        client_id = response.data[0]['client_id']
    else:
        client_id = identifier
    token = await get_access_token_by_identifier(identifier, identifier_type)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    return await check_password_expiration_policy(headers, client_id)

@router.get("/ListSPFPolicyStatus", response_model=GraphApiResponse, summary="Check SPF Policy Configuration")
async def list_spf_policy_status_endpoint(credentials: tuple = Depends(get_client_credentials)):
    """External endpoint for SPF Policy Status"""
    identifier, identifier_type = credentials
    if identifier_type == "ninjaone_org_id":
        from app.core.database.supabase_services import supabase
        response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
        client_id = response.data[0]['client_id']
    else:
        client_id = identifier
    token = await get_access_token_by_identifier(identifier, identifier_type)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    return await list_spf_policy_status(headers, client_id)

@router.get("/CheckTeamsExternalAccess", response_model=GraphApiResponse, summary="Check Teams External Access")
async def check_teams_external_access_endpoint(credentials: tuple = Depends(get_client_credentials)):
    """External endpoint for Teams External Access"""
    identifier, identifier_type = credentials
    if identifier_type == "ninjaone_org_id":
        from app.core.database.supabase_services import supabase
        response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
        client_id = response.data[0]['client_id']
    else:
        client_id = identifier
    token = await get_access_token_by_identifier(identifier, identifier_type)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    return await check_teams_external_access(headers, client_id)

@router.get("/ListRiskyCountryLocations", response_model=GraphApiResponse, summary="Check Risky Country Locations")
async def list_risky_country_locations_endpoint(credentials: tuple = Depends(get_client_credentials)):
    """External endpoint for Risky Country Locations"""
    identifier, identifier_type = credentials
    if identifier_type == "ninjaone_org_id":
        from app.core.database.supabase_services import supabase
        response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
        client_id = response.data[0]['client_id']
    else:
        client_id = identifier
    token = await get_access_token_by_identifier(identifier, identifier_type)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    return await list_risky_country_locations(headers, client_id)

@router.get("/ListConnectedAppsUserConsents", response_model=GraphApiResponse, summary="Check Connected Apps User Consents")
async def list_connected_apps_user_consents_endpoint(credentials: tuple = Depends(get_client_credentials)):
    """External endpoint for Connected Apps User Consents"""
    identifier, identifier_type = credentials
    if identifier_type == "ninjaone_org_id":
        from app.core.database.supabase_services import supabase
        response = supabase.table('organization_mapping').select('client_id').eq('ninjaone_org_id', identifier).execute()
        client_id = response.data[0]['client_id']
    else:
        client_id = identifier
    token = await get_access_token_by_identifier(identifier, identifier_type)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    return await list_connected_apps_user_consents(headers, client_id)

'''