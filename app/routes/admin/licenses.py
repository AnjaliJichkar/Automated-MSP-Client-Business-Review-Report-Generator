import logging
import httpx
import asyncio
from fastapi import APIRouter,Depends
from app.core.auth.dependencies import get_client_id, get_client_credentials
from app.core.auth.middleware import get_access_token, get_access_token_by_identifier
from app.schemas.api import GraphApiResponse
from app.core.config.settings import GRAPH_V1_URL, GRAPH_BETA_URL

# Create router for license endpoints
router = APIRouter()
logger = logging.getLogger(__name__)

# ------Helper Functions---------

def lookup_friendly_name_from_db(service_plan_name: str) -> str:
    """
    Lookup friendly name from database license_sku_mappings table.

    Args:
        service_plan_name: SKU identifier (e.g., ENTERPRISEPREMIUM, O365_BUSINESS_PREMIUM)

    Returns:
        Product display name from database, or None if not found
    """
    try:
        from app.core.database.engine import SessionLocal
        from app.models.misc import LicenseSkuMapping

        db = SessionLocal()
        try:
            row = db.query(LicenseSkuMapping).filter(
                LicenseSkuMapping.service_plan_name == service_plan_name
            ).first()
            return row.product_display_name if row else None
        finally:
            db.close()

    except Exception as e:
        logger.warning(f"Database lookup failed for SKU '{service_plan_name}': {str(e)}")
        return None


def get_friendly_name(sku_part_number):
    """
    Map SKU part number to friendly name using 2-tier fallback:
    1. Database lookup (606 SKUs from Microsoft official CSV)
    2. Format fallback (auto-format unknown SKUs)

    Args:
        sku_part_number: SKU identifier from Microsoft Graph API

    Returns:
        Human-readable friendly name for the license
    """
    # Tier 1: Database lookup (606 SKUs from Microsoft)
    db_name = lookup_friendly_name_from_db(sku_part_number)
    if db_name:
        return db_name

    # Tier 2: Format fallback (converts service_plan_name to friendly format)
    return format_sku_name(sku_part_number)


def format_sku_name(sku_part_number):
    """Format unknown SKU names to be more readable"""
    formatted = sku_part_number.replace("_", " ").replace("O365", "Office 365")
    return " ".join(word.capitalize() for word in formatted.split())


def categorize_license(sku_part_number, service_plans=None):
    """Categorize license based on SKU and service plans"""
    sku_upper = sku_part_number.upper()

    # Premium indicators
    premium_indicators = ["E5", "PREMIUM", "ENTERPRISEPREMIUM", "POWER_BI_PRO", "PROJECT"]
    if any(indicator in sku_upper for indicator in premium_indicators):
        return "Premium"

    # Standard indicators
    standard_indicators = ["E3", "STANDARD", "ENTERPRISEPACK", "EXCHANGEENTERPRISE"]
    if any(indicator in sku_upper for indicator in standard_indicators):
        return "Standard"

    # Basic indicators
    basic_indicators = ["BASIC", "ESSENTIALS", "E1", "STANDARDPACK"]
    if any(indicator in sku_upper for indicator in basic_indicators):
        return "Basic"

    return "Others"


def create_license_detail(sku, user_counts, tenant_data):
    """Create license detail object for response - keeping same fields, improved values"""
    consumed = tenant_data[sku]["consumed"]
    available = tenant_data[sku]["available"]

    # Handle unlimited/very large license pools (common with user-based licensing)
    UNLIMITED_THRESHOLD = 10000
    is_unlimited = available >= UNLIMITED_THRESHOLD

    if is_unlimited:
        # For unlimited licenses, show "Unlimited" and 0% utilization
        return {
            "skuPartNumber": sku,
            "friendlyName": get_friendly_name(sku),
            "category": categorize_license(sku, tenant_data[sku]["servicePlans"]),
            "assigned": consumed,
            "available": "Unlimited",
            "utilization": 0
        }

    # Calculate utilization percentage - NO CAPPING, show actual percentage
    actual_utilization = round((consumed / available * 100), 0) if available > 0 else 0

    return {
        "skuPartNumber": sku,
        "friendlyName": get_friendly_name(sku),
        "category": categorize_license(sku, tenant_data[sku]["servicePlans"]),
        "assigned": consumed,
        "available": str(available),  # Convert to string
        "utilization": actual_utilization  # Can exceed 100% (e.g., 150%)
    }

# Note: This replaces the existing create_license_detail function in your code
# The changes:
# 1. available: Shows "Unlimited" when >= 100,000
# 2. utilization: Capped at 100% (so 150% becomes 100%)
# 3. Same exact fields as before - no new fields added


def map_to_distribution(license_details):
    """Map license details to distribution categories"""
    distribution = {}
    for license in license_details:
        category = license["category"]
        distribution[category] = distribution.get(category, 0) + license["assigned"]
    return distribution


async def get_user_licenses(client, headers):
    """Fetch all user license assignments"""
    results = {}

    # Get all users
    users_url = "https://graph.microsoft.com/v1.0/users?$select=userPrincipalName"
    users_response = await client.get(users_url, headers=headers, timeout=30.0)
    users_response.raise_for_status()
    users = users_response.json().get("value", [])

    # Fetch license details for each user
    for user in users:
        upn = user.get("userPrincipalName")
        if not upn:
            continue

        license_url = f"https://graph.microsoft.com/v1.0/users/{upn}/licenseDetails"
        license_response = await client.get(license_url, headers=headers, timeout=30.0)

        if license_response.status_code != 200:
            results[upn] = {"error": f"Failed to fetch license details (status {license_response.status_code})"}
            continue

        license_data = license_response.json()
        results[upn] = license_data

    return results


async def get_tenant_licenses(client, headers):
    """Fetch tenant subscription details"""
    tenant_url = "https://graph.microsoft.com/v1.0/subscribedSkus"
    tenant_response = await client.get(tenant_url, headers=headers, timeout=30.0)
    tenant_response.raise_for_status()
    return tenant_response.json()


def process_license_summary(user_licenses, tenant_licenses):
    """Process and combine license data for UI response"""
    # 1. Calculate total users
    total_users = len(user_licenses)

    # 2. Map user licenses to SKU counts (invert structure)
    user_sku_counts = {}
    for user, license_data in user_licenses.items():
        if "error" in license_data:
            continue

        for license_info in license_data.get("value", []):
            sku = license_info.get("skuPartNumber")
            if sku:
                user_sku_counts[sku] = user_sku_counts.get(sku, 0) + 1

    # 3. Map tenant licenses to available counts
    tenant_sku_data = {}
    for item in tenant_licenses.get("value", []):
        if item["capabilityStatus"] == "Enabled":
            sku = item["skuPartNumber"]
            tenant_sku_data[sku] = {
                "available": item["prepaidUnits"]["enabled"],
                "consumed": item["consumedUnits"],
                "status": item["capabilityStatus"],
                "servicePlans": item.get("servicePlans", [])
            }

    # 4. Create license details using map technique
    all_license_details = list(map(
        lambda sku: create_license_detail(sku, user_sku_counts, tenant_sku_data),
        tenant_sku_data.keys()
    ))

    # 5. Calculate distribution (include all categories including "Others")
    license_distribution = map_to_distribution(all_license_details)

    # 6. Sort licenses: Premium/Standard/Basic first, then "Others" at the bottom
    def sort_by_category(license):
        category_order = {"Premium": 1, "Standard": 2, "Basic": 3, "Others": 4}
        return category_order.get(license["category"], 4)

    license_details = sorted(all_license_details, key=sort_by_category)

    return {
        "totalUsers": total_users,
        "licenseDistribution": license_distribution,
        "licenseDetails": license_details
    }


# ------License Management Endpoints---------

# @router.get("/ListLicenses", response_model=GraphApiResponse, summary="List Licenses for All Users")
# async def list_licenses():
#     """
#     Gets license details for all users from Microsoft Graph API.
#     Returns a dictionary with userPrincipalName as the key and their license details as the value.
#     """
#     try:
#         token = get_access_token()
#         headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
#
#         results = {}
#
#         async with httpx.AsyncClient() as client:
#             # Step 1: Get all users (only userPrincipalName)
#             users_url = "https://graph.microsoft.com/v1.0/users?$select=userPrincipalName"
#             users_response = await client.get(users_url, headers=headers, timeout=30.0)
#             users_response.raise_for_status()
#             users = users_response.json().get("value", [])
#
#             # Step 2: Loop over each UPN and fetch their license details
#             for user in users:
#                 upn = user.get("userPrincipalName")
#                 if not upn:
#                     continue
#
#                 license_url = f"https://graph.microsoft.com/v1.0/users/{upn}/licenseDetails"
#                 license_response = await client.get(license_url, headers=headers, timeout=30.0)
#
#                 if license_response.status_code != 200:
#                     results[upn] = {"error": f"Failed to fetch license details (status {license_response.status_code})"}
#                     continue
#
#                 license_data = license_response.json()
#                 results[upn] = license_data  # store full license details for the user
#
#         return GraphApiResponse(status_code=200, data=results)
#
#     except httpx.HTTPStatusError as exc:
#         return GraphApiResponse(
#             status_code=exc.response.status_code,
#             data={},
#             error=f"Graph API error: {exc.response.text}"
#         )
#     except Exception as e:
#         return GraphApiResponse(
#             status_code=500,
#             data={},
#             error=f"Failed to get licenses: {str(e)}"
#         )


@router.get("/GetLicenseSummary", response_model=GraphApiResponse, summary="Get License Summary for UI Dashboard")
async def get_license_summary(credentials: tuple = Depends(get_client_credentials)):
    """
    Enhanced license summary combining user assignments and tenant capacity.
    Returns processed data ready for UI consumption including total users,
    license distribution, and detailed license information.
    Supports clientId, org_id, and ninjaone_org_id parameters.
    """
    try:
        # Extract identifier and type from credentials
        identifier, identifier_type = credentials

        # Get the client_id for backward compatibility with existing Microsoft Graph calls
        if identifier_type == "org_id":
            # NEW: Handle org_id by fetching credentials from m365_credentials
            from app.core.database.supabase_services import get_organization_credentials
            creds = await get_organization_credentials(int(identifier))
            if not creds:
                raise Exception(f"No credentials found for org_id: {identifier}")
            client_id = creds['client_id']
        elif identifier_type == "ninjaone_org_id":
            from app.core.database.engine import SessionLocal
            from app.models.organizations import OrganizationMapping
            db = SessionLocal()
            try:
                mapping = db.query(OrganizationMapping).filter(
                    OrganizationMapping.ninjaone_org_id == identifier
                ).first()
                if not mapping:
                    raise Exception(f"No client_id found for ninjaone_org_id: {identifier}")
                client_id = mapping.client_id
            finally:
                db.close()
        else:
            # client_id type - use directly
            client_id = identifier

        token = await get_access_token(client_id)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        async with httpx.AsyncClient() as client:
            # Fetch both user licenses and tenant subscriptions in parallel
            user_licenses_task = get_user_licenses(client, headers)
            tenant_licenses_task = get_tenant_licenses(client, headers)

            user_licenses, tenant_licenses = await asyncio.gather(
                user_licenses_task, tenant_licenses_task
            )

            # Process data using map techniques
            summary = process_license_summary(user_licenses, tenant_licenses)

        return GraphApiResponse(status_code=200, data=summary)

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
            error=f"Failed to get license summary: {str(e)}"
        )

