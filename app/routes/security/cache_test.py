"""
TEST ENDPOINTS for Supabase Cache READ functionality.
These endpoints test reading data from cache tables and transforming to frontend JSON.
"""

import logging
from datetime import datetime
from fastapi import APIRouter, Query, Path
from app.schemas.api import GraphApiResponse

from app.services.cache.cache_services import (
    get_cached_compliance,
    get_cached_mfa,
    get_cached_licenses,
    get_cached_secure_score,
    get_cached_users_list,
    get_cached_user_details,
    get_cached_clients
)

# Create router for cache test endpoints
router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/test-cache-read-compliance", response_model=GraphApiResponse, summary="[TEST] Read Compliance from Cache")
async def test_cache_read_compliance(clientId: int = Query(..., description="Client ID (org_id)")):
    """
    TEST ENDPOINT: Read compliance data from m365_compliance_snapshots and return exact /api/GetAllComplianceStatus format.

    Args:
        clientId: Client ID (org_id from organizations table)

    Returns:
        GraphApiResponse with compliance data from cache or error if not found/expired
    """
    try:
        org_id = clientId  # Extract clientId and use as org_id
        logger.info(f"TEST: Reading compliance cache for org_id: {org_id}")

        cached_data = await get_cached_compliance(org_id)

        if cached_data is None:
            return GraphApiResponse(
                status_code=404,
                data=None,
                error=f"No valid compliance cache found for org_id: {org_id}. Cache may be missing or expired."
            )

        return GraphApiResponse(
            status_code=200,
            data=cached_data,
            error=None
        )

    except Exception as e:
        logger.error(f"TEST ERROR: {e}")
        return GraphApiResponse(
            status_code=500,
            data=None,
            error=f"Test failed: {str(e)}"
        )


@router.get("/test-cache-read-mfa", response_model=GraphApiResponse, summary="[TEST] Read MFA from Cache")
async def test_cache_read_mfa(clientId: int = Query(..., description="Client ID (org_id)")):
    """
    TEST ENDPOINT: Read MFA data from m365_mfa_snapshots and return exact /api/GetMFAComplianceReport format.

    Args:
        clientId: Client ID (org_id from organizations table)

    Returns:
        GraphApiResponse with MFA data from cache or error if not found/expired
    """
    try:
        org_id = clientId  # Extract clientId and use as org_id
        logger.info(f" TEST: Reading MFA cache for org_id: {org_id}")

        cached_data = await get_cached_mfa(org_id)

        if cached_data is None:
            return GraphApiResponse(
                status_code=404,
                data=None,
                error=f"No valid MFA cache found for org_id: {org_id}. Cache may be missing or expired."
            )

        return GraphApiResponse(
            status_code=200,
            data=cached_data,
            error=None
        )

    except Exception as e:
        logger.error(f" TEST ERROR: {e}")
        return GraphApiResponse(
            status_code=500,
            data=None,
            error=f"Test failed: {str(e)}"
        )


@router.get("/test-cache-read-licenses", response_model=GraphApiResponse, summary="[TEST] Read Licenses from Cache")
async def test_cache_read_licenses(clientId: int = Query(..., description="Client ID (org_id)")):
    """
    TEST ENDPOINT: Read license data from m365_license_snapshots and return exact /api/GetLicenseSummary format.

    Args:
        clientId: Client ID (org_id from organizations table)

    Returns:
        GraphApiResponse with license data from cache or error if not found/expired
    """
    try:
        org_id = clientId  # Extract clientId and use as org_id
        logger.info(f"TEST: Reading license cache for org_id: {org_id}")

        cached_data = await get_cached_licenses(org_id)

        if cached_data is None:
            return GraphApiResponse(
                status_code=404,
                data=None,
                error=f"No valid license cache found for org_id: {org_id}. Cache may be missing or expired."
            )

        return GraphApiResponse(
            status_code=200,
            data=cached_data,
            error=None
        )

    except Exception as e:
        logger.error(f"TEST ERROR: {e}")
        return GraphApiResponse(
            status_code=500,
            data=None,
            error=f"Test failed: {str(e)}"
        )


@router.get("/test-cache-read-secure-score", response_model=GraphApiResponse, summary="[TEST] Read Secure Score from Cache")
async def test_cache_read_secure_score(clientId: int = Query(..., description="Client ID (org_id)")):
    """
    TEST ENDPOINT: Read secure score data from m365_secure_score_history and return exact /api/GetMicrosoftSecureScore format.

    Args:
        clientId: Client ID (org_id from organizations table)

    Returns:
        GraphApiResponse with secure score data from cache or error if not found/expired
    """
    try:
        org_id = clientId  # Extract clientId and use as org_id
        logger.info(f"TEST: Reading secure score cache for org_id: {org_id}")

        cached_data = await get_cached_secure_score(org_id)

        if cached_data is None:
            return GraphApiResponse(
                status_code=404,
                data=None,
                error=f"No valid secure score cache found for org_id: {org_id}. Cache may be missing or expired."
            )

        return GraphApiResponse(
            status_code=200,
            data=cached_data,
            error=None
        )

    except Exception as e:
        logger.error(f"TEST ERROR: {e}")
        return GraphApiResponse(
            status_code=500,
            data=None,
            error=f"Test failed: {str(e)}"
        )


@router.get("/test-cache-read-users-list", response_model=GraphApiResponse, summary="[TEST] Read Users List from Cache")
async def test_cache_read_users_list(clientId: int = Query(..., description="Client ID (org_id)")):
    """
    TEST ENDPOINT: Read ALL users from m365_users and return exact /api/ListUsers format.

    Args:
        clientId: Client ID (org_id from organizations table)

    Returns:
        GraphApiResponse with all users data from cache or error if not found/expired
    """
    try:
        org_id = clientId  # Extract clientId and use as org_id
        logger.info(f"TEST: Reading users list cache for org_id: {org_id}")

        cached_data = await get_cached_users_list(org_id)

        if cached_data is None:
            return GraphApiResponse(
                status_code=404,
                data=None,
                error=f"No valid users list cache found for org_id: {org_id}. Cache may be missing or expired."
            )

        return GraphApiResponse(
            status_code=200,
            data=cached_data,
            error=None
        )

    except Exception as e:
        logger.error(f"TEST ERROR: {e}")
        return GraphApiResponse(
            status_code=500,
            data=None,
            error=f"Test failed: {str(e)}"
        )


@router.get("/test-cache-read-user-details/{user_id}", response_model=GraphApiResponse, summary="[TEST] Read Single User Details from Cache")
async def test_cache_read_user_details(
    user_id: str = Path(..., description="User ID (Graph API user_id)"),
    clientId: int = Query(..., description="Client ID (org_id)")
):
    """
    TEST ENDPOINT: Read ONE user's complete details from m365_users + m365_user_details + m365_user_devices.
    Returns exact /api/UserDetails/{user_id} format.

    Args:
        user_id: Graph API user ID (from m365_users.user_id column)
        clientId: Client ID (org_id from organizations table)

    Returns:
        GraphApiResponse with user details from cache or error if not found/expired
    """
    try:
        org_id = clientId  # Extract clientId and use as org_id
        logger.info(f"TEST: Reading user details cache for user_id: {user_id}, org_id: {org_id}")

        cached_data = await get_cached_user_details(user_id, org_id)

        if cached_data is None:
            return GraphApiResponse(
                status_code=404,
                data=None,
                error=f"No valid user details cache found for user_id: {user_id}. Cache may be missing or expired."
            )

        return GraphApiResponse(
            status_code=200,
            data=cached_data,
            error=None
        )

    except Exception as e:
        logger.error(f"TEST ERROR: {e}")
        return GraphApiResponse(
            status_code=500,
            data=None,
            error=f"Test failed: {str(e)}"
        )


@router.get("/test-cache-read-clients", response_model=GraphApiResponse, summary="[TEST] Read Clients from Cache")
async def test_cache_read_clients(u_id: str = Query(..., description="User UUID (auth_user_id)")):
    """
    TEST ENDPOINT: Read clients/organizations from organizations table filtered by user's account.

    Flow:
        1. Accept u_id (user UUID) as query parameter
        2. Resolve u_id → account_id using SQL function
        3. Query organizations WHERE account_id = X
        4. Return organizations for that user's account only

    Args:
        u_id: User UUID from auth.users.id / platform_users.auth_user_id

    Returns:
        GraphApiResponse with clients/organizations for user's account or error if not found/expired
    """
    try:
        logger.info(f"TEST: Reading clients from organizations table for u_id: {u_id}")

        cached_data = await get_cached_clients(u_id)

        if cached_data is None:
            return GraphApiResponse(
                status_code=404,
                data=None,
                error=f"No valid clients cache found for u_id: {u_id}. Cache may be missing or expired."
            )

        return GraphApiResponse(
            status_code=200,
            data=cached_data,
            error=None
        )

    except Exception as e:
        logger.error(f"TEST ERROR: {e}")
        return GraphApiResponse(
            status_code=500,
            data=None,
            error=f"Test failed: {str(e)}"
        )


@router.get("/test-cache-read-all", response_model=GraphApiResponse, summary="[TEST] Read All Cache Types")
async def test_cache_read_all(clientId: int = Query(..., description="Client ID (org_id)")):
    """
    TEST ENDPOINT: Read ALL cache types at once for comprehensive testing.

    Args:
        clientId: Client ID (org_id from organizations table)

    Returns:
        GraphApiResponse with all cached data or errors for each endpoint
    """
    try:
        org_id = clientId  # Extract clientId and use as org_id
        logger.info(f"TEST: Reading ALL caches for org_id: {org_id}")

        # Fetch all cache types concurrently
        compliance_data = await get_cached_compliance(org_id)
        mfa_data = await get_cached_mfa(org_id)
        license_data = await get_cached_licenses(org_id)
        secure_score_data = await get_cached_secure_score(org_id)
        users_list_data = await get_cached_users_list(org_id)

        # Build comprehensive response
        result = {
            "test_org_id": org_id,
            "test_timestamp": datetime.now().isoformat() + "Z",
            "cache_results": {
                "compliance": {
                    "status": "found" if compliance_data else "not_found",
                    "data": compliance_data,
                    "endpoint": "/api/GetAllComplianceStatus"
                },
                "mfa": {
                    "status": "found" if mfa_data else "not_found",
                    "data": mfa_data,
                    "endpoint": "/api/GetMFAComplianceReport"
                },
                "licenses": {
                    "status": "found" if license_data else "not_found",
                    "data": license_data,
                    "endpoint": "/api/GetLicenseSummary"
                },
                "secure_score": {
                    "status": "found" if secure_score_data else "not_found",
                    "data": secure_score_data,
                    "endpoint": "/api/GetMicrosoftSecureScore"
                },
                "users_list": {
                    "status": "found" if users_list_data else "not_found",
                    "data": users_list_data,
                    "endpoint": "/api/ListUsers",
                    "count": len(users_list_data.get("users", [])) if users_list_data else 0
                }
            },
            "summary": {
                "total_endpoints": 5,
                "found": sum([
                    1 if compliance_data else 0,
                    1 if mfa_data else 0,
                    1 if license_data else 0,
                    1 if secure_score_data else 0,
                    1 if users_list_data else 0
                ]),
                "not_found": sum([
                    1 if not compliance_data else 0,
                    1 if not mfa_data else 0,
                    1 if not license_data else 0,
                    1 if not secure_score_data else 0,
                    1 if not users_list_data else 0
                ])
            }
        }

        return GraphApiResponse(
            status_code=200,
            data=result,
            error=None
        )

    except Exception as e:
        logger.error(f" TEST ERROR: {e}")
        return GraphApiResponse(
            status_code=500,
            data=None,
            error=f"Test failed: {str(e)}"
        )


@router.get("/get-cached-user-ids/{org_id}", response_model=GraphApiResponse, summary="Get Cached User IDs")
async def get_cached_user_ids(org_id: int = Path(..., description="Organization ID")):
    """
    Get list of user IDs from m365_users cache table for a specific organization.
    This endpoint is used by the scheduler to fetch user_ids after writing users to cache.

    Args:
        org_id: Organization ID

    Returns:
        GraphApiResponse with list of user_ids or empty list if no users found
    """
    try:
        from app.core.database.engine import SessionLocal
        from app.models.m365_cache import M365User

        logger.info(f"Fetching cached user IDs for org_id: {org_id}")

        _db = SessionLocal()
        try:
            rows = _db.query(M365User.user_id).filter(M365User.organization_id == org_id).all()
        finally:
            _db.close()

        if not rows:
            logger.warning(f"No cached users found for org_id: {org_id}")
            return GraphApiResponse(
                status_code=200,
                data={"user_ids": [], "count": 0, "org_id": org_id},
                error=None
            )

        # Extract user_ids from response
        user_ids = [row.user_id for row in rows]

        logger.info(f"Found {len(user_ids)} cached user IDs for org_id: {org_id}")

        return GraphApiResponse(
            status_code=200,
            data={"user_ids": user_ids, "count": len(user_ids), "org_id": org_id},
            error=None
        )

    except Exception as e:
        logger.error(f"ERROR fetching cached user IDs: {e}")
        return GraphApiResponse(
            status_code=500,
            data=None,
            error=f"Failed to fetch cached user IDs: {str(e)}"
        )


# ============================================================================
# PHASE 2: WRITE TEST ENDPOINTS
# ============================================================================

from app.services.cache.cache_write_services import (
    write_compliance_to_cache,
    write_mfa_to_cache,
    write_licenses_to_cache,
    write_secure_score_to_cache,
    write_users_to_cache,
    write_user_details_to_cache,
    write_all_caches_to_cache
)


@router.post("/test-cache-write-compliance", response_model=GraphApiResponse, summary="[TEST] Write Compliance to Cache")
async def test_cache_write_compliance(org_id: int = Query(..., description="Organization ID")):
    """
    TEST ENDPOINT: Fetch compliance from existing endpoint and write to m365_compliance_snapshots.
    """
    try:
        logger.info(f" TEST: Writing compliance cache for org_id: {org_id}")
        success = await write_compliance_to_cache(org_id)

        if not success:
            return GraphApiResponse(status_code=500, data=None, error=f"Failed to write compliance cache for org_id: {org_id}")

        return GraphApiResponse(status_code=200, data={"message": "Compliance cache written successfully", "org_id": org_id}, error=None)

    except Exception as e:
        logger.error(f" TEST ERROR: {e}")
        return GraphApiResponse(status_code=500, data=None, error=f"Test failed: {str(e)}")


@router.post("/test-cache-write-mfa", response_model=GraphApiResponse, summary="[TEST] Write MFA to Cache")
async def test_cache_write_mfa(org_id: int = Query(..., description="Organization ID")):
    """
    TEST ENDPOINT: Fetch MFA from existing endpoint and write to m365_mfa_snapshots.
    """
    try:
        logger.info(f" TEST: Writing MFA cache for org_id: {org_id}")
        success = await write_mfa_to_cache(org_id)

        if not success:
            return GraphApiResponse(status_code=500, data=None, error=f"Failed to write MFA cache for org_id: {org_id}")

        return GraphApiResponse(status_code=200, data={"message": "MFA cache written successfully", "org_id": org_id}, error=None)

    except Exception as e:
        logger.error(f"TEST ERROR: {e}")
        return GraphApiResponse(status_code=500, data=None, error=f"Test failed: {str(e)}")


@router.post("/test-cache-write-licenses", response_model=GraphApiResponse, summary="[TEST] Write Licenses to Cache")
async def test_cache_write_licenses(org_id: int = Query(..., description="Organization ID")):
    """
    TEST ENDPOINT: Fetch licenses from existing endpoint and write to m365_license_snapshots.
    """
    try:
        logger.info(f" TEST: Writing licenses cache for org_id: {org_id}")
        success = await write_licenses_to_cache(org_id)

        if not success:
            return GraphApiResponse(status_code=500, data=None, error=f"Failed to write licenses cache for org_id: {org_id}")

        return GraphApiResponse(status_code=200, data={"message": "Licenses cache written successfully", "org_id": org_id}, error=None)

    except Exception as e:
        logger.error(f" TEST ERROR: {e}")
        return GraphApiResponse(status_code=500, data=None, error=f"Test failed: {str(e)}")


@router.post("/test-cache-write-secure-score", response_model=GraphApiResponse, summary="[TEST] Write Secure Score to Cache")
async def test_cache_write_secure_score(org_id: int = Query(..., description="Organization ID")):
    """
    TEST ENDPOINT: Fetch secure score from existing endpoint and write to m365_secure_score_history.
    """
    try:
        logger.info(f"TEST: Writing secure score cache for org_id: {org_id}")
        success = await write_secure_score_to_cache(org_id)

        if not success:
            return GraphApiResponse(status_code=500, data=None, error=f"Failed to write secure score cache for org_id: {org_id}")

        return GraphApiResponse(status_code=200, data={"message": "Secure score cache written successfully", "org_id": org_id}, error=None)

    except Exception as e:
        logger.error(f" TEST ERROR: {e}")
        return GraphApiResponse(status_code=500, data=None, error=f"Test failed: {str(e)}")


@router.post("/test-cache-write-users", response_model=GraphApiResponse, summary="[TEST] Write Users to Cache")
async def test_cache_write_users(org_id: int = Query(..., description="Organization ID")):
    """
    TEST ENDPOINT: Fetch users from existing endpoint and write to m365_users.
    """
    try:
        logger.info(f" TEST: Writing users cache for org_id: {org_id}")
        success = await write_users_to_cache(org_id)

        if not success:
            return GraphApiResponse(status_code=500, data=None, error=f"Failed to write users cache for org_id: {org_id}")

        return GraphApiResponse(status_code=200, data={"message": "Users cache written successfully", "org_id": org_id}, error=None)

    except Exception as e:
        logger.error(f" TEST ERROR: {e}")
        return GraphApiResponse(status_code=500, data=None, error=f"Test failed: {str(e)}")


@router.post("/test-cache-write-user-details/{user_id}", response_model=GraphApiResponse, summary="[TEST] Write User Details to Cache")
async def test_cache_write_user_details(
    user_id: str = Path(..., description="User ID (Graph API user_id)"),
    org_id: int = Query(..., description="Organization ID")
):
    """
    TEST ENDPOINT: Fetch single user details from existing endpoint and write to m365_user_details + m365_user_devices.
    """
    try:
        logger.info(f" TEST: Writing user details cache for user_id: {user_id}, org_id: {org_id}")
        success = await write_user_details_to_cache(user_id, org_id)

        if not success:
            return GraphApiResponse(status_code=500, data=None, error=f"Failed to write user details cache for user_id: {user_id}")

        return GraphApiResponse(status_code=200, data={"message": "User details cache written successfully", "user_id": user_id, "org_id": org_id}, error=None)

    except Exception as e:
        logger.error(f"TEST ERROR: {e}")
        return GraphApiResponse(status_code=500, data=None, error=f"Test failed: {str(e)}")


@router.post("/test-cache-write-all", response_model=GraphApiResponse, summary="[TEST] Write All Caches")
async def test_cache_write_all(org_id: int = Query(..., description="Organization ID")):
    """
    TEST ENDPOINT: Write ALL cache types at once for an organization.
    """
    try:
        logger.info(f" TEST: Writing ALL caches for org_id: {org_id}")
        results = await write_all_caches_to_cache(org_id)

        total_success = sum(1 for v in results.values() if v)
        total_failed = sum(1 for v in results.values() if not v)

        return GraphApiResponse(
            status_code=200,
            data={"org_id": org_id, "results": results, "total_success": total_success, "total_failed": total_failed},
            error=None
        )

    except Exception as e:
        logger.error(f" TEST ERROR: {e}")
        return GraphApiResponse(status_code=500, data=None, error=f"Test failed: {str(e)}")
