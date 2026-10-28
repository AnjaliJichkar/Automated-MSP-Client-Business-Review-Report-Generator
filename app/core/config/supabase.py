"""
Supabase client for credential management.
Active methods (get_credentials_by_account_id, get_organization_by_id) now use SQLAlchemy.
self.supabase client is kept alive for legacy callers (e.g. frontend_transformer.py RPC calls)
that have not been migrated yet.
"""
import os
import logging
from supabase import create_client, Client
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from datetime import datetime
from app.core.database.engine import SessionLocal
from app.models.credentials import IntegrationCredential
from app.models.organizations import Organization, OrganizationIntegration
from app.models.integrations import Integration

logger = logging.getLogger(__name__)

class SupabaseCredentialManager:
    def __init__(self):
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_key = os.getenv('SUPABASE_KEY')

        if not self.supabase_url or not self.supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment")

        # Kept for legacy callers that access self.supabase directly (e.g. frontend_transformer.py)
        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)

    def get_credentials_by_account_id(self, account_id: int) -> Optional[Dict[str, Any]]:
        """
        Get integration credentials by account_id from integration_credentials table.
        Returns decrypted credentials ready to use.

        Args:
            account_id: Account ID (integer)

        Returns:
            Dict with decrypted autotask, ninjaone, connectsecure credentials
        """
        db: Session = SessionLocal()
        try:
            from app.services.encryption.manager import EncryptionManager

            row = db.query(IntegrationCredential).filter(
                IntegrationCredential.account_id == account_id,
                IntegrationCredential.is_active == True
            ).first()

            if not row:
                logger.error(f"No credentials found for account_id: {account_id}")
                return None

            encryption_manager = EncryptionManager()
            credentials = encryption_manager.decrypt_integration_credentials(row.credentials)

            logger.info(f"Successfully retrieved and decrypted credentials for account_id: {account_id}")
            return credentials

        except Exception as e:
            logger.error(f"Failed to fetch/decrypt credentials for account_id {account_id}: {e}")
            return None
        finally:
            db.close()

    def get_organization_by_id(self, org_id: int) -> Optional[Dict[str, Any]]:
        """
        Get organization-specific platform IDs using organization_integrations table.

        Args:
            org_id: Organization ID (integer)

        Returns:
            Dict with ninjaone_org_id, autotask_id, connectsecure_id, account_id, organization_name
        """
        db: Session = SessionLocal()
        try:
            # JOIN organization_integrations → integrations to get integration_key
            rows = db.query(
                OrganizationIntegration.platform_organization_id,
                Integration.integration_key
            ).join(
                Integration, OrganizationIntegration.integration_id == Integration.id
            ).filter(
                OrganizationIntegration.organization_id == org_id
            ).all()

            logger.info(f"=== INTEGRATIONS QUERY RESPONSE FOR ORG {org_id}: {rows} ===")

            if not rows:
                logger.error(f"No integrations found for org_id: {org_id}")
                return None

            # Get organization basic info
            org = db.query(Organization).filter(Organization.id == org_id).first()

            if not org:
                logger.error(f"No organization found for org_id: {org_id}")
                return None

            # Build org_data with platform IDs from integrations
            org_data = {
                'id': org.id,
                'account_id': org.account_id,
                'organization_name': org.organization_name,
                'name': org.organization_name,  # Backward compatibility
            }

            # Map integration_key to expected field names
            platform_mapping = {
                'ninjaone': 'ninjaone_org_id',
                'autotask': 'autotask_id',
                'connectsecure': 'connectsecure_id',
                'bitdefender': 'bitdefender_company_id',
                'cove': 'cove_customer_id',
                'sentinelone': 'sentinelone_site_id',
                'nodeware': 'nodeware_customer_token',
                'dnsfilter': 'dnsfilter_org_id',
                'dropsuite': 'dropsuite_org_id',
                'blackpoint': 'blackpoint_tenant_id',
                'axcient': 'axcient_client_id',
                'infima': 'infima_client_id',
            }

            for row in rows:
                integration_key = row.integration_key
                platform_id = row.platform_organization_id

                logger.info(f"=== PROCESSING INTEGRATION: key={integration_key}, platform_id={platform_id} ===")

                if integration_key in platform_mapping:
                    field_name = platform_mapping[integration_key]
                    org_data[field_name] = platform_id
                    logger.info(f"=== MAPPED {integration_key} -> {field_name} = {platform_id} ===")

                    if integration_key == 'connectsecure':
                        org_data['connect_secure_id'] = platform_id

            logger.info(f"=== FINAL ORG_DATA KEYS: {list(org_data.keys())} ===")
            logger.info(f"=== BITDEFENDER_COMPANY_ID IN ORG_DATA: {org_data.get('bitdefender_company_id')} ===")

            logger.info(f"Successfully retrieved organization data for org_id: {org_id} - {org_data.get('organization_name')}")
            logger.info(f"  Platform IDs: NinjaOne={org_data.get('ninjaone_org_id')}, Autotask={org_data.get('autotask_id')}, ConnectSecure={org_data.get('connectsecure_id')}, Bitdefender={org_data.get('bitdefender_company_id')}")

            return org_data

        except Exception as e:
            logger.error(f"Failed to fetch organization for org_id {org_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
        finally:
            db.close()

    # get_credentials_by_id() and save_credentials() removed.
    # Both queried the old user_credentials table which no longer exists in the DB schema.
    # Processors now use get_credentials_by_account_id() via the account_id path.