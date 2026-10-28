"""
Outlook Email Service (Microsoft Graph API)
==========================================
Sends emails with PDF attachments via Microsoft Graph API using MSAL.
Uses Client Credentials Flow (app-only access, no user interaction).

NEW ARCHITECTURE (Single Sender):
- All credentials loaded from .env file
- Single fixed sender mailbox (e.g., reports@company.com)
- No per-account credential storage
- No database lookups for SMTP credentials
"""

import os
import logging
import aiohttp
import base64
from msal import ConfidentialClientApplication
from typing import Optional

logger = logging.getLogger(__name__)


class OutlookEmailSender:
    """
    Sends emails via Microsoft Graph API with PDF attachments.
    Uses MSAL Client Credentials Flow for app-only access.

    All credentials are loaded from environment variables:
    - MS_TENANT_ID: Azure AD tenant ID
    - MS_CLIENT_ID: Azure AD application client ID
    - MS_CLIENT_SECRET: Azure AD application client secret
    - MS_SENDER_EMAIL: Fixed sender email (e.g., reports@company.com)
    """

    def __init__(self):
        """
        Initialize email sender with credentials from environment variables.
        No parameters needed - all config comes from .env file.

        Required ENV variables:
            MS_TENANT_ID: Azure AD tenant ID (UUID)
            MS_CLIENT_ID: Azure AD application client ID (UUID)
            MS_CLIENT_SECRET: Azure AD application client secret
            MS_SENDER_EMAIL: Sender email address (e.g., reports@company.com)
        """
        # Load credentials from environment
        self.tenant_id = os.getenv('MS_TENANT_ID')
        self.client_id = os.getenv('MS_CLIENT_ID')
        self.client_secret = os.getenv('MS_CLIENT_SECRET')
        self.smtp_email = os.getenv('MS_SENDER_EMAIL')

        # Validate required credentials
        missing = []
        if not self.tenant_id:
            missing.append('MS_TENANT_ID')
        if not self.client_id:
            missing.append('MS_CLIENT_ID')
        if not self.client_secret:
            missing.append('MS_CLIENT_SECRET')
        if not self.smtp_email:
            missing.append('MS_SENDER_EMAIL')

        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

        # Microsoft Graph API endpoints
        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        self.graph_url = "https://graph.microsoft.com/v1.0"
        self.scope = ["https://graph.microsoft.com/.default"]

        logger.info(f"OutlookEmailSender initialized (Graph API) for: {self.smtp_email}")

    async def _get_access_token(self) -> str:
        """
        Get access token using MSAL Client Credentials Flow.
        Uses same pattern as middleware.py get_access_token_from_credentials().

        Returns:
            Access token string

        Raises:
            Exception: If token acquisition fails
        """
        try:
            # Create MSAL app
            msal_app = ConfidentialClientApplication(
                client_id=self.client_id,
                client_credential=self.client_secret,
                authority=self.authority,
            )

            # Try silent acquisition first
            result = msal_app.acquire_token_silent(scopes=self.scope, account=None)

            # If silent fails, acquire new token
            if not result:
                logger.info(f"Acquiring new access token for {self.client_id}...")
                result = msal_app.acquire_token_for_client(scopes=self.scope)

            # Check for errors
            if not result or 'access_token' not in result:
                error = result.get('error_description', result.get('error', 'Unknown error'))
                logger.error(f"Token acquisition failed: {error}")
                raise Exception(f"Failed to acquire access token: {error}")

            logger.info("Successfully acquired access token")
            return result['access_token']

        except Exception as e:
            logger.error(f"Error getting access token: {e}")
            raise

    async def send_report_email(
        self,
        recipient_email: str,
        organization_name: str,
        report_month: str,
        report_year: int,
        pdf_bytes: bytes,
        sender_name: Optional[str] = "InputIV Security Reports"
    ) -> bool:
        """
        Send security report email with PDF attachment via Graph API.

        Args:
            recipient_email: POC email address
            organization_name: Organization name for email content
            report_month: Month name (e.g., "November")
            report_year: Year (e.g., 2024)
            pdf_bytes: PDF file as bytes
            sender_name: Display name for sender

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Sending report email to: {recipient_email}")

            # Step 1: Get access token
            access_token = await self._get_access_token()

            # Step 2: Prepare email content
            subject = f"{organization_name} - {report_month} {report_year} Security Report"

            html_body = f"""
            <html>
              <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                  <h2 style="color: #2563eb;">Monthly Security Report</h2>

                  <p>Dear {organization_name} Team,</p>

                  <p>Please find attached your <strong>{report_month} {report_year}</strong> security assessment report.</p>


                  <p>If you have any questions or concerns about the report, please don't hesitate to reach out to your account manager.</p>

                  <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;">

                  <p style="color: #6b7280; font-size: 0.9em;">
                    Best regards,<br>
                    <strong>Inputiv Security Team</strong><br>
                    <a href="mailto:{self.smtp_email}">{self.smtp_email}</a>
                  </p>

                  <p style="color: #9ca3af; font-size: 0.8em; margin-top: 20px;">
                    This is an automated email. Please do not reply directly to this message.
                  </p>
                </div>
              </body>
            </html>
            """

            # Step 3: Prepare PDF attachment
            pdf_filename = f"{organization_name.replace(' ', '_')}_{report_month}_{report_year}_Report.pdf"
            pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')

            # Step 4: Build Graph API message
            message = {
                "message": {
                    "subject": subject,
                    "body": {
                        "contentType": "HTML",
                        "content": html_body
                    },
                    "toRecipients": [
                        {
                            "emailAddress": {
                                "address": recipient_email
                            }
                        }
                    ],
                    "from": {
                        "emailAddress": {
                            "address": self.smtp_email,
                            "name": sender_name
                        }
                    },
                    "attachments": [
                        {
                            "@odata.type": "#microsoft.graph.fileAttachment",
                            "name": pdf_filename,
                            "contentType": "application/pdf",
                            "contentBytes": pdf_base64
                        }
                    ]
                },
                "saveToSentItems": "true"
            }

            # Step 5: Send email via Graph API
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            send_mail_url = f"{self.graph_url}/users/{self.smtp_email}/sendMail"

            async with aiohttp.ClientSession() as session:
                async with session.post(send_mail_url, headers=headers, json=message) as response:
                    if response.status in [200, 202]:
                        logger.info(f"✓ Email sent successfully to {recipient_email}")
                        logger.info(f"  PDF attached: {pdf_filename} ({len(pdf_bytes)} bytes)")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"✗ Graph API error (status {response.status}): {error_text}")
                        return False

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
