# organization_matcher.py
"""
Utility for matching organizations across multiple platforms (NinjaOne, Autotask, ConnectSecure)
Uses fuzzy name matching and source_id references for cross-platform organization mapping
"""

import re
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class OrganizationMatcher:
    """Handles fuzzy matching and mapping of organizations across platforms"""

    def __init__(self):
        self.match_confidence_threshold = 0.7  # Minimum confidence for name-based matches

    def normalize_company_name(self, name: str) -> str:
        """
        Normalize company name for matching by removing common variations

        Args:
            name: Raw company name from platform

        Returns:
            Normalized lowercase name without special chars, numbers, and suffixes
        """
        if not name:
            return ""

        # Convert to lowercase
        cleaned = name.lower().strip()

        # Remove common business suffixes (case-insensitive)
        cleaned = re.sub(r'\s+(inc|llc|ltd|corp|corporation|pllc|co|company|limited)\\.?$', '', cleaned)

        # Remove location indicators like "#64325"
        cleaned = re.sub(r'\s*#\d+', '', cleaned)

        # Remove numbers at the end
        cleaned = re.sub(r'\s*\d+$', '', cleaned)

        # Remove punctuation and special characters
        cleaned = re.sub(r'[^\w\s]', '', cleaned)

        # Normalize whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned)

        return cleaned.strip()

    def calculate_match_confidence(self, name1: str, name2: str) -> float:
        """
        Calculate confidence score for name match (0.0 to 1.0)

        Args:
            name1: First company name (normalized)
            name2: Second company name (normalized)

        Returns:
            Confidence score between 0.0 and 1.0
        """
        if not name1 or not name2:
            return 0.0

        # Exact match after normalization
        if name1 == name2:
            return 1.0

        # Check if one contains the other
        if name1 in name2 or name2 in name1:
            shorter = min(len(name1), len(name2))
            longer = max(len(name1), len(name2))
            return shorter / longer if longer > 0 else 0.0

        # Character overlap ratio (simple similarity)
        set1 = set(name1.replace(' ', ''))
        set2 = set(name2.replace(' ', ''))

        if not set1 or not set2:
            return 0.0

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0

    def find_best_name_match(self, target_name: str, candidates: List[Dict],
                            name_field: str = 'name') -> Tuple[Optional[Dict], float]:
        """
        Find best matching organization by name from candidate list

        Args:
            target_name: Name to match against
            candidates: List of candidate organization dicts
            name_field: Field name containing the organization name

        Returns:
            Tuple of (best_match_dict, confidence_score)
        """
        if not target_name or not candidates:
            return None, 0.0

        normalized_target = self.normalize_company_name(target_name)

        best_match = None
        best_confidence = 0.0

        for candidate in candidates:
            candidate_name = candidate.get(name_field) or candidate.get('companyName')

            if not candidate_name:
                continue

            normalized_candidate = self.normalize_company_name(candidate_name)
            confidence = self.calculate_match_confidence(normalized_target, normalized_candidate)

            if confidence > best_confidence:
                best_confidence = confidence
                best_match = candidate

        # Only return match if confidence exceeds threshold
        if best_confidence >= self.match_confidence_threshold:
            return best_match, best_confidence

        return None, 0.0

    def match_organizations(self, ninjaone_orgs: List[Dict],
                          autotask_companies: List[Dict],
                          connectsecure_companies: List[Dict]) -> List[Dict]:
        """
        Create organization mappings across all platforms

        Matching strategy:
        1. Use NinjaOne name as primary organization name
        2. Match ConnectSecure by name first
        3. Use ConnectSecure source_id to find Autotask ID (most reliable)
        4. Fallback to direct name matching for Autotask
        5. Create entries for all organizations found

        Args:
            ninjaone_orgs: List of NinjaOne organizations
            autotask_companies: List of Autotask companies
            connectsecure_companies: List of ConnectSecure companies

        Returns:
            List of organization mapping dicts ready for database insertion
        """
        mappings = []

        # Handle edge cases
        if not isinstance(ninjaone_orgs, list):
            ninjaone_orgs = []
        if not isinstance(autotask_companies, list):
            autotask_companies = []
        if not isinstance(connectsecure_companies, list):
            connectsecure_companies = []

        logger.info(f"Matching {len(ninjaone_orgs)} NinjaOne orgs with "
                   f"{len(autotask_companies)} Autotask and "
                   f"{len(connectsecure_companies)} ConnectSecure companies")

        # Track used IDs to avoid duplicates
        used_autotask_ids = set()
        used_connectsecure_ids = set()

        for ninja_org in ninjaone_orgs:
            mapping = self._create_single_mapping(
                ninja_org,
                autotask_companies,
                connectsecure_companies,
                used_autotask_ids,
                used_connectsecure_ids
            )
            mappings.append(mapping)

        logger.info(f"Created {len(mappings)} organization mappings")
        return mappings

    def _create_single_mapping(self, ninja_org: Dict,
                              autotask_companies: List[Dict],
                              connectsecure_companies: List[Dict],
                              used_autotask_ids: set,
                              used_connectsecure_ids: set) -> Dict:
        """
        Create mapping for a single NinjaOne organization

        Args:
            ninja_org: NinjaOne organization dict
            autotask_companies: Available Autotask companies
            connectsecure_companies: Available ConnectSecure companies
            used_autotask_ids: Set of already-matched Autotask IDs
            used_connectsecure_ids: Set of already-matched ConnectSecure IDs

        Returns:
            Organization mapping dict
        """
        ninja_name = ninja_org.get('name', 'Unknown')
        ninja_id = str(ninja_org.get('id', ''))

        # Initialize mapping with NinjaOne name as primary
        mapping = {
            'organization_name': ninja_name,
            'ninjaone_org_id': ninja_id,
            'autotask_id': None,
            'connect_secure_id': None,
            'match_confidence': 0.0,
            'match_method': 'ninjaone_primary',
            'last_synced': datetime.now().isoformat()
        }

        # STEP 1: Find ConnectSecure match by name
        cs_match, cs_confidence = self.find_best_name_match(
            ninja_name,
            connectsecure_companies,
            name_field='name'
        )

        if cs_match and cs_match.get('id') not in used_connectsecure_ids:
            mapping['connect_secure_id'] = cs_match['id']
            mapping['match_confidence'] = cs_confidence
            used_connectsecure_ids.add(cs_match['id'])

            # STEP 2: Use source_id for Autotask match (MOST RELIABLE)
            source_id = cs_match.get('source_id')
            if source_id:
                # Look for Autotask company with matching ID
                autotask_match = next(
                    (company for company in autotask_companies
                     if str(company.get('id')) == str(source_id)
                     and str(company.get('id')) not in used_autotask_ids),
                    None
                )

                if autotask_match:
                    mapping['autotask_id'] = autotask_match['id']
                    mapping['match_method'] = 'source_id'
                    mapping['match_confidence'] = 1.0  # Source ID is exact match
                    used_autotask_ids.add(str(autotask_match['id']))

                    logger.info(f"✓ SOURCE_ID match: {ninja_name} → "
                              f"Autotask ID {source_id}, ConnectSecure ID {cs_match['id']}")
                    return mapping

        # STEP 3: Fallback - Direct name matching for Autotask
        if not mapping['autotask_id']:
            at_match, at_confidence = self.find_best_name_match(
                ninja_name,
                autotask_companies,
                name_field='companyName'
            )

            if at_match and str(at_match.get('id')) not in used_autotask_ids:
                mapping['autotask_id'] = at_match['id']
                mapping['match_confidence'] = max(mapping['match_confidence'], at_confidence)
                mapping['match_method'] = 'name_match'
                used_autotask_ids.add(str(at_match['id']))

                logger.info(f"✓ NAME match: {ninja_name} → Autotask (confidence: {at_confidence:.2f})")

        # STEP 4: If no ConnectSecure found yet, try direct name match
        if not mapping['connect_secure_id']:
            cs_direct_match, cs_direct_confidence = self.find_best_name_match(
                ninja_name,
                connectsecure_companies,
                name_field='name'
            )

            if cs_direct_match and cs_direct_match.get('id') not in used_connectsecure_ids:
                mapping['connect_secure_id'] = cs_direct_match['id']
                mapping['match_confidence'] = max(mapping['match_confidence'], cs_direct_confidence)
                used_connectsecure_ids.add(cs_direct_match['id'])

                logger.info(f"✓ NAME match: {ninja_name} → ConnectSecure (confidence: {cs_direct_confidence:.2f})")

        # Log if only NinjaOne found
        if not mapping['autotask_id'] and not mapping['connect_secure_id']:
            logger.info(f"⚠ NinjaOne only: {ninja_name} (no matches in other platforms)")
            mapping['match_method'] = 'ninjaone_only'

        return mapping

    def get_primary_organization_name(self, ninjaone_name: Optional[str] = None,
                                     autotask_name: Optional[str] = None,
                                     connectsecure_name: Optional[str] = None) -> str:
        """
        Determine the cleanest organization name to use as primary

        Priority:
        1. NinjaOne name (if available)
        2. Autotask name (if NinjaOne missing)
        3. ConnectSecure name (fallback)

        Args:
            ninjaone_name: Name from NinjaOne
            autotask_name: Name from Autotask
            connectsecure_name: Name from ConnectSecure

        Returns:
            Best primary name
        """
        # Priority order: NinjaOne > Autotask > ConnectSecure
        if ninjaone_name:
            return ninjaone_name.strip()
        elif autotask_name:
            return autotask_name.strip()
        elif connectsecure_name:
            return connectsecure_name.strip()

        return "Unknown Organization"
