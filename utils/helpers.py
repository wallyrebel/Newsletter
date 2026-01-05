"""
Utility functions for the Newsletter Digest system.
Includes URL normalization, date parsing, HTML cleaning, and text helpers.
"""

import re
import html
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from zoneinfo import ZoneInfo

from dateutil import parser as dateutil_parser
from bs4 import BeautifulSoup


# Tracking parameters to strip from URLs
TRACKING_PARAMS = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'utm_id', 'utm_cid', 'utm_reader', 'utm_name', 'utm_pubreferrer',
    'fbclid', 'gclid', 'gclsrc', 'dclid', 'msclkid',
    'mc_cid', 'mc_eid',  # Mailchimp
    'ref', 'ref_src', 'ref_url',
    '_ga', '_gl',  # Google Analytics
    'ncid', 'sr_share',
    'igshid',  # Instagram
    'twclid',  # Twitter
}


def normalize_url(url: str) -> str:
    """
    Normalize a URL by:
    - Converting to lowercase scheme and host
    - Removing tracking parameters
    - Removing trailing slashes from path
    - Removing fragments
    
    Args:
        url: The URL to normalize
        
    Returns:
        Normalized URL string
    """
    if not url:
        return ""
    
    try:
        parsed = urlparse(url)
        
        # Parse query parameters and filter out tracking ones
        query_params = parse_qs(parsed.query, keep_blank_values=False)
        filtered_params = {
            k: v for k, v in query_params.items()
            if k.lower() not in TRACKING_PARAMS
        }
        
        # Rebuild query string
        new_query = urlencode(filtered_params, doseq=True) if filtered_params else ""
        
        # Normalize path (remove trailing slash unless it's just "/")
        path = parsed.path.rstrip('/') if parsed.path != '/' else parsed.path
        
        # Rebuild URL without fragment
        normalized = urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            parsed.params,
            new_query,
            ""  # Remove fragment
        ))
        
        return normalized
    except Exception:
        return url


def parse_rss_date(date_str: str, default_tz: ZoneInfo = ZoneInfo("UTC")) -> Optional[datetime]:
    """
    Parse various RSS date formats into a timezone-aware datetime.
    
    Handles formats like:
    - RFC 822: "Mon, 05 Jan 2026 12:00:00 GMT"
    - ISO 8601: "2026-01-05T12:00:00Z"
    - Various other formats via dateutil
    
    Args:
        date_str: Date string to parse
        default_tz: Default timezone if none specified in the string
        
    Returns:
        Timezone-aware datetime or None if parsing fails
    """
    if not date_str:
        return None
    
    try:
        parsed = dateutil_parser.parse(date_str)
        
        # Make timezone-aware if naive
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=default_tz)
        
        return parsed
    except (ValueError, TypeError):
        return None


def is_within_hours(dt: datetime, hours: int = 24) -> bool:
    """
    Check if a datetime is within the specified hours from now.
    
    Args:
        dt: Datetime to check (must be timezone-aware)
        hours: Number of hours to look back
        
    Returns:
        True if within the time window
    """
    if dt is None:
        return False
    
    now = datetime.now(ZoneInfo("UTC"))
    cutoff = now - timedelta(hours=hours)
    
    return dt >= cutoff


def strip_html(text: str) -> str:
    """
    Remove HTML tags and decode entities from text.
    
    Args:
        text: HTML text to clean
        
    Returns:
        Plain text string
    """
    if not text:
        return ""
    
    # Parse with BeautifulSoup
    soup = BeautifulSoup(text, 'html.parser')
    
    # Get text content
    plain_text = soup.get_text(separator=' ')
    
    # Decode HTML entities
    plain_text = html.unescape(plain_text)
    
    # Normalize whitespace
    plain_text = re.sub(r'\s+', ' ', plain_text).strip()
    
    return plain_text


def truncate_text(text: str, max_length: int = 200, ellipsis: str = "...") -> str:
    """
    Truncate text to a maximum length, breaking at word boundaries.
    
    Args:
        text: Text to truncate
        max_length: Maximum length (including ellipsis)
        ellipsis: String to append if truncated
        
    Returns:
        Truncated text
    """
    if not text:
        return ""
    
    # Clean the text first
    text = strip_html(text)
    
    if len(text) <= max_length:
        return text
    
    # Find a good break point
    truncated = text[:max_length - len(ellipsis)]
    
    # Try to break at word boundary
    last_space = truncated.rfind(' ')
    if last_space > max_length * 0.5:  # Only if we're not losing too much
        truncated = truncated[:last_space]
    
    return truncated.rstrip() + ellipsis


def extract_domain(url: str) -> str:
    """
    Extract the domain name from a URL.
    
    Args:
        url: URL to extract domain from
        
    Returns:
        Domain name (e.g., "example.com")
    """
    if not url:
        return ""
    
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Remove www. prefix
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def format_date_for_display(dt: datetime, format_str: str = "%B %d, %Y") -> str:
    """
    Format a datetime for display in the email.
    
    Args:
        dt: Datetime to format
        format_str: strftime format string
        
    Returns:
        Formatted date string
    """
    if dt is None:
        return ""
    return dt.strftime(format_str)


def safe_get(data: dict, *keys, default=None):
    """
    Safely get nested dictionary values.
    
    Args:
        data: Dictionary to traverse
        *keys: Keys to access
        default: Default value if key not found
        
    Returns:
        Value at the nested key or default
    """
    result = data
    for key in keys:
        try:
            result = result[key]
        except (KeyError, TypeError, IndexError):
            return default
    return result


def clean_image_url(url: str) -> Optional[str]:
    """
    Clean and validate an image URL.
    
    Args:
        url: Image URL to clean
        
    Returns:
        Cleaned URL or None if invalid
    """
    if not url:
        return None
    
    url = url.strip()
    
    # Must be HTTP(S)
    if not url.startswith(('http://', 'https://')):
        return None
    
    # Basic validation - check for common image extensions or known CDN patterns
    parsed = urlparse(url)
    path = parsed.path.lower()
    
    # Common image extensions
    image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg')
    
    # Check if it looks like an image URL
    if any(path.endswith(ext) for ext in image_extensions):
        return url
    
    # Also accept URLs from known image CDNs/services even without extension
    cdn_patterns = ['wp-content', 'uploads', 'images', 'img', 'media', 'cdn']
    if any(pattern in path for pattern in cdn_patterns):
        return url
    
    # Default: return the URL anyway (might be a dynamic image service)
    return url
