"""
Email Service

Handles sending emails for OTP verification and invitations.
"""

import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from app.core.config import settings


class EmailService:
    """Service for sending emails."""

    @staticmethod
    async def send_email(
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
    ) -> bool:
        """
        Send an email.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            body: Plain text body
            html_body: Optional HTML body
        
        Returns:
            bool: True if sent successfully
        """
        if not settings.smtp_user or not settings.smtp_password:
            # In development, just log the email
            if settings.is_development:
                print(f"[DEV EMAIL] To: {to_email}")
                print(f"[DEV EMAIL] Subject: {subject}")
                print(f"[DEV EMAIL] Body: {body}")
                return True
            return False

        message = MIMEMultipart("alternative")
        message["From"] = f"{settings.email_from_name} <{settings.email_from}>"
        message["To"] = to_email
        message["Subject"] = subject

        # Add plain text part
        message.attach(MIMEText(body, "plain"))

        # Add HTML part if provided
        if html_body:
            message.attach(MIMEText(html_body, "html"))

        try:
            await aiosmtplib.send(
                message,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_user,
                password=settings.smtp_password,
                start_tls=True,
            )
            return True
        except Exception as e:
            print(f"Email sending failed: {e}")
            if settings.is_development:
                print(f"[DEV FALLBACK] To: {to_email}")
                print(f"[DEV FALLBACK] Subject: {subject}")
                print(f"[DEV FALLBACK] Body: {body}")
            return False

    @classmethod
    async def send_otp_email(cls, to_email: str, otp: str) -> bool:
        """
        Send OTP verification email.
        
        Args:
            to_email: Recipient email
            otp: OTP code
        
        Returns:
            bool: True if sent successfully
        """
        subject = f"Your MiniMart Verification Code: {otp}"
        body = f"""
Hello,

Your verification code is: {otp}

This code will expire in {settings.otp_expire_minutes} minutes.

If you didn't request this code, please ignore this email.

Best regards,
The MiniMart Team
        """.strip()

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        .container {{ font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }}
        .otp {{ font-size: 32px; font-weight: bold; color: #4F46E5; letter-spacing: 8px; text-align: center; padding: 20px; background: #F3F4F6; border-radius: 8px; margin: 20px 0; }}
        .footer {{ color: #6B7280; font-size: 14px; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Verify Your Email</h1>
        <p>Hello,</p>
        <p>Your verification code is:</p>
        <div class="otp">{otp}</div>
        <p>This code will expire in {settings.otp_expire_minutes} minutes.</p>
        <p class="footer">If you didn't request this code, please ignore this email.</p>
    </div>
</body>
</html>
        """.strip()

        return await cls.send_email(to_email, subject, body, html_body)

    @classmethod
    async def send_invitation_email(
        cls,
        to_email: str,
        inviter_name: str,
        list_name: str,
        accept_url: str,
        reject_url: str,
    ) -> bool:
        """
        Send shopping list invitation email.
        
        Args:
            to_email: Recipient email
            inviter_name: Name of the person who invited
            list_name: Name of the shopping list
            accept_url: URL to accept the invitation
            reject_url: URL to reject the invitation
        
        Returns:
            bool: True if sent successfully
        """
        subject = f"{inviter_name} invited you to collaborate on '{list_name}'"
        body = f"""
Hello,

{inviter_name} has invited you to collaborate on the shopping list "{list_name}" in MiniMart.

To accept this invitation, click here:
{accept_url}

To reject this invitation, click here:
{reject_url}

This invitation will expire in {settings.invitation_token_expire_hours} hours.

Best regards,
The MiniMart Team
        """.strip()

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        .container {{ font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }}
        .button {{ display: inline-block; padding: 12px 24px; margin: 10px 5px; border-radius: 6px; text-decoration: none; font-weight: bold; }}
        .accept {{ background: #10B981; color: white; }}
        .reject {{ background: #EF4444; color: white; }}
        .list-name {{ background: #F3F4F6; padding: 10px 15px; border-radius: 6px; display: inline-block; }}
        .footer {{ color: #6B7280; font-size: 14px; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>You're Invited! 🛒</h1>
        <p><strong>{inviter_name}</strong> has invited you to collaborate on:</p>
        <p class="list-name">📝 {list_name}</p>
        <p>Join them to add items, mark purchases, and keep your shopping synchronized in real-time!</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{accept_url}" class="button accept">✓ Accept Invitation</a>
            <a href="{reject_url}" class="button reject">✗ Decline</a>
        </div>
        <p class="footer">This invitation will expire in {settings.invitation_token_expire_hours} hours.</p>
    </div>
</body>
</html>
        """.strip()

        return await cls.send_email(to_email, subject, body, html_body)
