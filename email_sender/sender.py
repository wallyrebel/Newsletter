"""
Email sender for the Newsletter Digest system.
Supports SMTP, SendGrid, and Mailgun delivery methods.
"""

import logging
import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds


@dataclass
class EmailConfig:
    """Email configuration."""
    to_address: str
    from_address: str
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    sendgrid_api_key: Optional[str] = None
    mailgun_api_key: Optional[str] = None
    mailgun_domain: Optional[str] = None


def create_plaintext_version(html_content: str) -> str:
    """
    Create a plaintext version from HTML content.
    
    Args:
        html_content: HTML email content
        
    Returns:
        Plaintext version
    """
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove style and script tags
    for tag in soup.find_all(['style', 'script']):
        tag.decompose()
    
    # Get text with some formatting
    text = []
    
    # Process headers
    for h in soup.find_all(['h1', 'h2', 'h3', 'h4']):
        heading_text = h.get_text(strip=True)
        if heading_text:
            text.append('\n' + '=' * len(heading_text))
            text.append(heading_text)
            text.append('=' * len(heading_text) + '\n')
    
    # Get all text
    full_text = soup.get_text(separator='\n', strip=True)
    
    # Clean up multiple newlines
    import re
    full_text = re.sub(r'\n{3,}', '\n\n', full_text)
    
    return full_text


def send_via_smtp(
    config: EmailConfig,
    subject: str,
    html_content: str,
    plaintext_content: str
) -> bool:
    """
    Send email via SMTP.
    
    Args:
        config: Email configuration
        subject: Email subject
        html_content: HTML body
        plaintext_content: Plaintext fallback
        
    Returns:
        True if successful
    """
    if not config.smtp_host:
        logger.error("SMTP host not configured")
        return False
    
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = config.from_address
    msg['To'] = config.to_address
    
    # Attach both versions
    part1 = MIMEText(plaintext_content, 'plain', 'utf-8')
    part2 = MIMEText(html_content, 'html', 'utf-8')
    msg.attach(part1)
    msg.attach(part2)
    
    for attempt in range(MAX_RETRIES):
        try:
            with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
                server.starttls()
                if config.smtp_user and config.smtp_password:
                    server.login(config.smtp_user, config.smtp_password)
                server.send_message(msg)
            
            logger.info(f"Email sent successfully via SMTP to {config.to_address}")
            return True
            
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
        except Exception as e:
            logger.error(f"Unexpected error sending email: {e}")
            break
    
    return False


def send_via_sendgrid(
    config: EmailConfig,
    subject: str,
    html_content: str,
    plaintext_content: str
) -> bool:
    """
    Send email via SendGrid API.
    
    Args:
        config: Email configuration
        subject: Email subject
        html_content: HTML body
        plaintext_content: Plaintext fallback
        
    Returns:
        True if successful
    """
    if not config.sendgrid_api_key:
        logger.error("SendGrid API key not configured")
        return False
    
    url = "https://api.sendgrid.com/v3/mail/send"
    
    payload = {
        "personalizations": [{"to": [{"email": config.to_address}]}],
        "from": {"email": config.from_address},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": plaintext_content},
            {"type": "text/html", "value": html_content}
        ]
    }
    
    headers = {
        "Authorization": f"Bearer {config.sendgrid_api_key}",
        "Content-Type": "application/json"
    }
    
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            
            if response.status_code in [200, 201, 202]:
                logger.info(f"Email sent successfully via SendGrid to {config.to_address}")
                return True
            else:
                logger.error(f"SendGrid error: {response.status_code} - {response.text}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    
        except requests.RequestException as e:
            logger.error(f"SendGrid request error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
    
    return False


def send_via_mailgun(
    config: EmailConfig,
    subject: str,
    html_content: str,
    plaintext_content: str
) -> bool:
    """
    Send email via Mailgun API.
    
    Args:
        config: Email configuration
        subject: Email subject
        html_content: HTML body
        plaintext_content: Plaintext fallback
        
    Returns:
        True if successful
    """
    if not config.mailgun_api_key or not config.mailgun_domain:
        logger.error("Mailgun API key or domain not configured")
        return False
    
    url = f"https://api.mailgun.net/v3/{config.mailgun_domain}/messages"
    
    data = {
        "from": config.from_address,
        "to": config.to_address,
        "subject": subject,
        "text": plaintext_content,
        "html": html_content
    }
    
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(
                url,
                auth=("api", config.mailgun_api_key),
                data=data,
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info(f"Email sent successfully via Mailgun to {config.to_address}")
                return True
            else:
                logger.error(f"Mailgun error: {response.status_code} - {response.text}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    
        except requests.RequestException as e:
            logger.error(f"Mailgun request error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
    
    return False


def send_email(
    config: EmailConfig,
    subject: str,
    html_content: str,
    plaintext_content: Optional[str] = None
) -> bool:
    """
    Send an email using the configured delivery method.
    
    Tries methods in order: SMTP, SendGrid, Mailgun
    
    Args:
        config: Email configuration
        subject: Email subject
        html_content: HTML body
        plaintext_content: Optional plaintext fallback (generated if not provided)
        
    Returns:
        True if sent successfully via any method
    """
    if not plaintext_content:
        plaintext_content = create_plaintext_version(html_content)
    
    # Try SMTP first
    if config.smtp_host:
        if send_via_smtp(config, subject, html_content, plaintext_content):
            return True
        logger.warning("SMTP failed, trying alternative methods...")
    
    # Try SendGrid
    if config.sendgrid_api_key:
        if send_via_sendgrid(config, subject, html_content, plaintext_content):
            return True
        logger.warning("SendGrid failed, trying Mailgun...")
    
    # Try Mailgun
    if config.mailgun_api_key and config.mailgun_domain:
        if send_via_mailgun(config, subject, html_content, plaintext_content):
            return True
    
    logger.error("All email delivery methods failed")
    return False
