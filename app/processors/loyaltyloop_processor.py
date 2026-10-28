"""
LoyaltyLoop Data Processor
Handles data fetching and processing for LoyaltyLoop testimonials and ratings
"""

import logging
from typing import Dict, Any, Optional

from app.clients.loyaltyloop_client import LoyaltyLoopClient

logger = logging.getLogger(__name__)


class LoyaltyLoopProcessor:
    """Processes LoyaltyLoop testimonial and rating data for security reporting"""

    def __init__(self, account_id: int = None):
        """
        Initialize LoyaltyLoopProcessor

        Args:
            account_id: Account ID for fetching credentials from integration_credentials table
        """
        self.account_id = account_id

        api_token = self._get_loyaltyloop_credentials()

        self.client = LoyaltyLoopClient(api_token)

        logger.info(f"LoyaltyLoopProcessor initialized for account_id={account_id}")

    def _get_loyaltyloop_credentials(self) -> tuple:
        """
        Fetch and decrypt LoyaltyLoop credentials from integration_credentials table.

        Returns:
            Tuple of (api_token, base_url). base_url is None if not set, letting
            LoyaltyLoopClient fall back to its own default.

        Raises:
            ValueError if credentials not found
        """
        try:
            from app.core.database.engine import SessionLocal
            from app.models.credentials import IntegrationCredential
            from app.services.encryption.manager import EncryptionManager
            
            encryption_manager = EncryptionManager()
            
            db = SessionLocal()
            try:
                row = db.query(IntegrationCredential).filter(
                    IntegrationCredential.account_id == self.account_id,
                    IntegrationCredential.is_active == True
                ).first()
                encrypted_blob = row.credentials if row else None
            finally:
                db.close()
            
            if not encrypted_blob:
                raise ValueError(f"No credentials found for account_id={self.account_id}")
            
            decrypted_creds = encryption_manager.decrypt_integration_credentials(encrypted_blob)
            
            loyaltyloop_creds = decrypted_creds.get('loyaltyloop', {})
            api_token = loyaltyloop_creds.get('loyaltyloop_api_token')
            if not api_token:
                raise ValueError(f"LoyaltyLoop API token not found for account_id={self.account_id}")
            
            logger.info(f"Successfully retrieved LoyaltyLoop credentials for account_id={self.account_id}")
            return api_token
        
        except Exception as e:
            logger.error(f"Failed to retrieve LoyaltyLoop credentials: {e}")
            raise

    def test_connection(self) -> bool:
        """
        Lightweight connectivity check used by SecurityAssessmentOrchestrator.test_all_connections().

        Returns:
            True if the API token is valid and the stats endpoint responds, False otherwise.
        """
        try:
            stats = self.client.get_testimonial_stats()
            return isinstance(stats, dict)
        except Exception as e:
            logger.error(f"LoyaltyLoop connection test failed: {e}")
            return False

    def fetch_all_data(self, month_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Fetch LoyaltyLoop data from API. This integration only surfaces NPS and
        loyalty score, so only the stats endpoint is called -- no testimonial
        content/list is fetched.

        Args:
            month_name: Optional month filter (accepted for caller compatibility, not used by LoyaltyLoop)

        Returns:
            Dict with raw API response
        """
        logger.info(f"Fetching LoyaltyLoop data (month_name={month_name})")
        
        raw_data = {
            "testimonial_stats": self.client.get_testimonial_stats()
        }
        
        logger.info(f"Fetched LoyaltyLoop data successfully")
        return raw_data

    def process_all_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process raw LoyaltyLoop data into chart format.

        Args:
            raw_data: Raw data from fetch_all_data()

        Returns:
            Processed data with separate nps_score and loyalty_score charts
        """
        logger.info("Processing LoyaltyLoop data...")
        
        processed = {
            "loyaltyloop_metrics": {
                "charts": {}
            }
        }
        
        testimonial_stats = raw_data.get("testimonial_stats", {})
        
        # Process NPS and loyalty scores as separate charts.
        scores = self._process_scores(testimonial_stats)
        processed["loyaltyloop_metrics"]["charts"].update(scores)
        
        logger.info("LoyaltyLoop data processed successfully")
        return processed

    def _process_scores(self, stats: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process NPS and Loyalty scores from testimonial stats

        Args:
            stats: Testimonial statistics from API

        Returns:
            Dict containing separate NPS and loyalty score chart values
        """
        result = {
            "nps_score": round(stats.get("nps_score") or 0, 2),
            "loyalty_score": round(stats.get("loyalty_score") or 0, 2)
        }
        
        logger.info(f"Testimonial scores - NPS: {result['nps_score']}, Loyalty: {result['loyalty_score']}")
        return result
