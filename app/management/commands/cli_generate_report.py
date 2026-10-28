#!/usr/bin/env python3
"""
CLI Tool for Security Report Generation
Extracted from: security_reporting_system/src/main.py (lines 596-848)

Command-line interface for generating security assessment reports.
Supports multiple output formats (JSON, PDF, frontend-optimized).

Usage Examples:
    # Generate PDF report for an organization
    python -m app.management.commands.cli_generate_report --account-id 1 --org-id 123 --output pdf --month "december_2024"

    # Test all API connections
    python -m app.management.commands.cli_generate_report --account-id 1 --org-id 123 --test-connections

    # List available months for reporting
    python -m app.management.commands.cli_generate_report --list-months

    # Generate frontend-optimized JSON
    python -m app.management.commands.cli_generate_report --account-id 1 --org-id 123 --output frontend

    # Generate both JSON and PDF
    python -m app.management.commands.cli_generate_report --account-id 1 --org-id 123 --output both
"""

import json
import logging
import asyncio
import argparse
import os
from datetime import datetime
from typing import Dict, Any, Optional

# Import orchestrator from new structure
from app.services.integrations.orchestrator import SecurityAssessmentOrchestrator
from app.utils.frontend_transformer import FrontendTransformer
from app.utils.month_selector import MonthSelector

# Try to import PDF report generator
try:
    from app.reports.pdf_report_generator import generate_security_report
    PDF_AVAILABLE = True
except ImportError as e:
    PDF_AVAILABLE = False
    # PDF generator not available - will show warning if PDF output requested

# Configure logging for production use
logging.basicConfig(
    level=logging.WARNING,  # Only show warnings and errors
    format='%(levelname)s: %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Main execution function with command-line arguments."""
    parser = argparse.ArgumentParser(description='IT Security Assessment Data Collection and Reporting')
    parser.add_argument('--output', choices=['json', 'pdf', 'both', 'frontend'], default='json',
                        help='Output format: json (full), frontend (optimized), pdf, both (default: json)')
    parser.add_argument('--account-id', type=int,
                        help='NEW: Account ID for fetching credentials from integration_credentials table')
    parser.add_argument('--org-id', type=int,
                        help='NEW: Organization ID for fetching org-specific IDs from organizations table')
    parser.add_argument('--credential-id', type=str,
                        help='[LEGACY] Legacy credential ID from old user_credentials table (deprecated, use --account-id and --org-id)')
    parser.add_argument('--ninjaone-org-id', type=str, default='41',
                        help='[DEPRECATED] NinjaOne Organization ID for report generation. Use --org-id instead.')
    parser.add_argument('--company-id', type=int, default=625,
                        help='[DEPRECATED] Autotask company ID for filtering (use --org-id instead)')
    parser.add_argument('--filename', type=str,
                        help='Custom filename for PDF output')
    parser.add_argument('--month', type=str,
                        help='Specific month for report generation in month_year format (e.g., "november_2024", "december_2024"). Defaults to previous month')
    parser.add_argument('--list-months', action='store_true',
                        help='List available months for report generation and exit')
    parser.add_argument('--test-connections', action='store_true',
                        help='Test connectivity to all data sources and exit')

    args = parser.parse_args()

    # Handle month listing
    if args.list_months:
        month_selector = MonthSelector()
        available_months = month_selector.list_available_months()

        print("\n=== Available Months for Report Generation ===")
        for month in available_months:
            month_lowercase = month['name'].lower()
            month_year_format = f"{month_lowercase}_{month['year']}"
            print(f"  • {month['display_name']} (use --month \"{month_year_format}\")")
        print("\nExample usage:")
        print("  python -m app.management.commands.cli_generate_report --account-id 1 --org-id 123 --month \"november_2024\" --output pdf")
        return

    # Handle connection testing
    if args.test_connections:
        try:
            # Initialize orchestrator with account_id/org_id or credential_id
            orchestrator = SecurityAssessmentOrchestrator(
                account_id=args.account_id,
                org_id=args.org_id,
                credential_id=args.credential_id
            )

            logger.info("Testing connections to all data sources...")
            results = await orchestrator.test_all_connections()

            print("\n=== Connection Test Results ===")
            for service, status in results.items():
                status_icon = "✅" if status else "❌"
                print(f"{status_icon} {service.title()}: {'Connected' if status else 'Failed'}")

            overall_status = all(results.values())
            print(f"\n Overall Status: {'All systems operational' if overall_status else 'Some connections failed'}")

            # Provide specific guidance for failed connections
            if not overall_status:
                print("\n Troubleshooting failed connections:")
                if not results.get('ninjaone', True):
                    print("   • NinjaOne: Check credentials in Supabase for account_id:", args.account_id)
                if not results.get('autotask', True):
                    print("   • Autotask: Verify credentials in Supabase for account_id:", args.account_id)
                if not results.get('connectsecure', True):
                    print("   • ConnectSecure: Check credentials in Supabase for account_id:", args.account_id)
                if not results.get('bitdefender', True):
                    print("   • Bitdefender: Check credentials in Supabase for account_id:", args.account_id)
                if not results.get('cove', True):
                    print("   • Cove: Check credentials in Supabase for account_id:", args.account_id)

            return

        except ValueError as e:
            print(f"Configuration Error: {e}")
            print("Please ensure both account_id and org_id are provided")
            return
        except Exception as e:
            print(f"Connection test failed: {e}")
            return

    try:
        # Initialize orchestrator with account_id/org_id or credential_id
        try:
            orchestrator = SecurityAssessmentOrchestrator(
                account_id=args.account_id,
                org_id=args.org_id,
                credential_id=args.credential_id
            )
        except ValueError as e:
            print(f"Configuration Error: {e}")
            if args.account_id or args.org_id:
                print("Please ensure both account_id and org_id are provided, or use credential_id for legacy mode")
            else:
                print("Please ensure credentials exist in Supabase for ID:", args.credential_id)
            return
        except Exception as e:
            print(f"Initialization Error: {e}")
            return

        # Collect all data
        logger.info("Starting comprehensive security assessment data collection...")
        start_time = datetime.now()

        # NEW: Use account_id and org_id if both are provided
        if args.account_id and args.org_id:
            logger.info(f"✓ Using NEW credential system: account_id={args.account_id}, org_id={args.org_id}")
            final_output = await orchestrator.collect_all_data_with_org_id(args.month)
        # OLD: Fallback to ninjaone_org_id method
        else:
            logger.warning("Using DEPRECATED ninjaone_org_id method. Please migrate to --account-id and --org-id.")
            final_output = await orchestrator.collect_all_data_for_org(args.ninjaone_org_id, args.month)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # Add execution metadata
        final_output["execution_info"]["duration_seconds"] = round(duration, 2)
        final_output["execution_info"]["start_time"] = start_time.isoformat()
        final_output["execution_info"]["end_time"] = end_time.isoformat()

        # Output based on requested format
        if args.output in ['json', 'both']:
            json_output = json.dumps(final_output, indent=2, default=str)
            print(json_output)  # Still print to console

            # Save JSON to file in output directory
            os.makedirs('output', exist_ok=True)

            # Generate JSON filename with timestamp and organization
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            org_identifier = f"org{args.org_id}" if args.org_id else args.ninjaone_org_id
            json_filename = f"output/security_report_{org_identifier}_{timestamp}.json"

            with open(json_filename, 'w', encoding='utf-8') as f:
                f.write(json_output)

            print(f"\n✓ JSON report saved: {json_filename}")

        if args.output == 'frontend':
            logger.info("Generating frontend-optimized JSON...")

            # Convert month parameter to "November 2024" format for reporting_period
            reporting_period = None
            if args.month:
                try:
                    parts = args.month.split('_')
                    month_name = parts[0].capitalize()
                    year = parts[1]
                    reporting_period = f"{month_name} {year}"
                except:
                    pass

            transformer = FrontendTransformer()
            frontend_json = transformer.transform_to_frontend_json(
                final_output,
                reporting_period=reporting_period
            )
            frontend_output = json.dumps(frontend_json, indent=2, default=str)

            # Save frontend JSON to file
            os.makedirs('output', exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            org_identifier = f"org{args.org_id}" if args.org_id else args.ninjaone_org_id
            frontend_filename = f"output/frontend_report_{org_identifier}_{timestamp}.json"

            with open(frontend_filename, 'w', encoding='utf-8') as f:
                f.write(frontend_output)

            print(f"\n✓ Frontend JSON report saved: {frontend_filename}")

            # Print summary statistics
            print(f"Data sources included: {', '.join(frontend_json.get('summary', {}).get('data_sources', []))}")
            print(f"Total devices: {frontend_json.get('summary', {}).get('total_devices', 0)}")
            print(f"Security risk score: {frontend_json.get('summary', {}).get('security_risk_score', 0)}")
            print(f"Patch compliance: {frontend_json.get('summary', {}).get('patch_compliance_percentage', 0)}%")

        if args.output in ['pdf', 'both'] and PDF_AVAILABLE:
            logger.info("Generating comprehensive PDF report...")
            # Pass account_id if available, otherwise fall back to credential_id
            filename = await generate_security_report(
                ninjaone_org_id=args.ninjaone_org_id,
                filename=args.filename,
                account_id=args.account_id,
                credential_id=args.credential_id,
                month_name=args.month
            )
            print(f"\n✓ PDF report generated: {filename}")

            # Print summary of data included
            data_sources = final_output.get("execution_info", {}).get("data_sources", [])
            print(f"Data sources included: {', '.join(data_sources)}")

            if 'connectsecure_metrics' in final_output:
                cs_summary = final_output['connectsecure_metrics'].get('summary', {})
                total_assets = cs_summary.get('total_assets', 0)
                total_vulns = cs_summary.get('total_vulnerabilities', 0)
                risk_score = cs_summary.get('risk_score', 'N/A')
                print(f"ConnectSecure: {total_assets} assets, {total_vulns} vulnerabilities, Risk Score: {risk_score}")
            elif 'ConnectSecure' not in data_sources:
                print("ConnectSecure: No data available - API endpoints may not be accessible")

        elif args.output in ['pdf', 'both'] and not PDF_AVAILABLE:
            print("\n⚠ PDF generation not available. Please install required dependencies:")
            print("pip install reportlab plotly pandas")

        # Print execution summary
        print(f"\n✓ Execution completed in {duration:.1f} seconds")
        data_sources = final_output.get("execution_info", {}).get("data_sources", [])
        print(f"✓ Data sources processed: {len(data_sources)}")
        for source in data_sources:
            print(f"   ✓ {source}")

    except ValueError as e:
        error_result = {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
            "account_id": args.account_id,
            "org_id": args.org_id,
            "troubleshooting": {
                "check_credentials": f"Verify credentials exist in Supabase for account_id: {args.account_id}",
                "check_organization": f"Verify organization exists for org_id: {args.org_id}",
                "check_network": "Ensure network connectivity to API endpoints",
                "check_logs": "Review console output for specific error details"
            }
        }
        print(json.dumps(error_result, indent=2))
        logger.error(f"Security assessment failed: {e}")

    except Exception as e:
        error_result = {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
            "account_id": args.account_id,
            "org_id": args.org_id,
            "troubleshooting": {
                "check_credentials": f"Verify credentials exist in Supabase for account_id: {args.account_id}",
                "check_organization": f"Verify organization exists for org_id: {args.org_id}",
                "check_network": "Ensure network connectivity to API endpoints",
                "check_logs": "Review console output for specific error details"
            }
        }
        print(json.dumps(error_result, indent=2))
        logger.error(f"Security assessment failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
