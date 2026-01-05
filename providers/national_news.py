"""
National news provider for the Newsletter Digest system.
Fetches top headlines from Google News RSS or NewsAPI.
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import feedparser
import requests

from utils.helpers import strip_html, truncate_text, parse_rss_date

logger = logging.getLogger(__name__)

# Google News RSS URL for US top stories
GOOGLE_NEWS_RSS = "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"

# NewsAPI endpoint
NEWS_API_URL = "https://newsapi.org/v2/top-headlines"

REQUEST_TIMEOUT = 15

USER_AGENT = (
    "Mozilla/5.0 (compatible; MNG-Digest-Bot/1.0; "
    "+https://github.com/msnewsgroup/newsletter)"
)


@dataclass
class NationalHeadline:
    """Represents a national news headline."""
    title: str
    url: str
    source: str
    published: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for template rendering."""
        return {
            'title': self.title,
            'url': self.url,
            'source': self.source,
            'published': self.published
        }


def fetch_google_news(max_headlines: int = 3) -> List[NationalHeadline]:
    """
    Fetch top headlines from Google News RSS.
    
    Args:
        max_headlines: Maximum headlines to return
        
    Returns:
        List of NationalHeadline objects
    """
    headlines = []
    
    try:
        session = requests.Session()
        session.headers.update({'User-Agent': USER_AGENT})
        
        response = session.get(GOOGLE_NEWS_RSS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        
        feed = feedparser.parse(response.text)
        
        for entry in feed.entries[:max_headlines]:
            title = strip_html(entry.get('title', ''))
            
            # Google News includes source in title like "Title - Source Name"
            source = "Google News"
            if ' - ' in title:
                parts = title.rsplit(' - ', 1)
                if len(parts) == 2:
                    title = parts[0].strip()
                    source = parts[1].strip()
            
            url = entry.get('link', '')
            
            # Parse date
            pub_date = None
            if 'published' in entry:
                pub_date = parse_rss_date(entry['published'])
            
            if title and url:
                headlines.append(NationalHeadline(
                    title=title,
                    url=url,
                    source=source,
                    published=pub_date
                ))
        
        logger.info(f"Fetched {len(headlines)} headlines from Google News")
        return headlines
        
    except requests.RequestException as e:
        logger.error(f"Error fetching Google News: {e}")
        return []
    except Exception as e:
        logger.error(f"Error parsing Google News feed: {e}")
        return []


def fetch_newsapi(api_key: str, max_headlines: int = 3) -> List[NationalHeadline]:
    """
    Fetch top headlines from NewsAPI.
    
    Args:
        api_key: NewsAPI API key
        max_headlines: Maximum headlines to return
        
    Returns:
        List of NationalHeadline objects
    """
    if not api_key:
        logger.warning("NewsAPI key not provided, skipping")
        return []
    
    headlines = []
    
    try:
        response = requests.get(
            NEWS_API_URL,
            params={
                'country': 'us',
                'pageSize': max_headlines,
                'apiKey': api_key
            },
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('status') != 'ok':
            logger.error(f"NewsAPI error: {data.get('message', 'Unknown error')}")
            return []
        
        for article in data.get('articles', []):
            title = article.get('title', '')
            url = article.get('url', '')
            source = article.get('source', {}).get('name', 'Unknown')
            
            # Parse date
            pub_date = None
            if article.get('publishedAt'):
                pub_date = parse_rss_date(article['publishedAt'])
            
            if title and url:
                headlines.append(NationalHeadline(
                    title=strip_html(title),
                    url=url,
                    source=source,
                    published=pub_date
                ))
        
        logger.info(f"Fetched {len(headlines)} headlines from NewsAPI")
        return headlines
        
    except requests.RequestException as e:
        logger.error(f"Error fetching NewsAPI: {e}")
        return []


def fetch_national_news(
    api_key: Optional[str] = None,
    max_headlines: int = 3,
    prefer_newsapi: bool = False
) -> List[NationalHeadline]:
    """
    Fetch top national news headlines.
    
    Uses Google News RSS by default, or NewsAPI if configured and preferred.
    
    Args:
        api_key: Optional NewsAPI key
        max_headlines: Maximum headlines to return
        prefer_newsapi: If True and API key is available, use NewsAPI first
        
    Returns:
        List of NationalHeadline objects
    """
    # Try NewsAPI first if preferred and available
    if prefer_newsapi and api_key:
        headlines = fetch_newsapi(api_key, max_headlines)
        if headlines:
            return headlines
    
    # Default to Google News RSS
    headlines = fetch_google_news(max_headlines)
    
    # Fall back to NewsAPI if Google News fails
    if not headlines and api_key:
        headlines = fetch_newsapi(api_key, max_headlines)
    
    return headlines
