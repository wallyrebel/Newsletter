"""
RSS feed provider for the Newsletter Digest system.
Handles feed discovery, parsing, and article extraction with image support.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Set
from dataclasses import dataclass, field
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import feedparser
import requests
from bs4 import BeautifulSoup

from utils.helpers import (
    normalize_url,
    parse_rss_date,
    is_within_hours,
    strip_html,
    truncate_text,
    clean_image_url
)

logger = logging.getLogger(__name__)

# Common RSS feed paths to try during discovery
FEED_PATHS = [
    '/feed/',
    '/feed',
    '/rss/',
    '/rss',
    '/?feed=rss2',
    '/atom/',
    '/atom',
    '/index.xml',
    '/rss.xml',
    '/feed.xml',
    '/atom.xml',
]

# Request timeout in seconds
REQUEST_TIMEOUT = 15

# User agent for requests
USER_AGENT = (
    "Mozilla/5.0 (compatible; MNG-Digest-Bot/1.0; "
    "+https://github.com/msnewsgroup/newsletter)"
)


@dataclass
class Article:
    """Represents a parsed article."""
    title: str
    url: str
    description: str
    image_url: Optional[str]
    published: Optional[datetime]
    source_name: str
    source_url: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for template rendering."""
        return {
            'title': self.title,
            'url': self.url,
            'description': self.description,
            'image_url': self.image_url,
            'published': self.published,
            'source_name': self.source_name,
            'source_url': self.source_url
        }


@dataclass
class RSSSource:
    """RSS source configuration."""
    name: str
    base_url: str
    feed_url: Optional[str] = None


def get_session() -> requests.Session:
    """Create a requests session with appropriate headers."""
    session = requests.Session()
    session.headers.update({
        'User-Agent': USER_AGENT,
        'Accept': 'application/rss+xml, application/xml, text/xml, */*'
    })
    return session


def discover_feed_url(base_url: str, session: requests.Session) -> Optional[str]:
    """
    Attempt to discover the RSS feed URL for a website.
    
    Args:
        base_url: The website's base URL
        session: Requests session to use
        
    Returns:
        Discovered feed URL or None
    """
    # Normalize base URL
    if not base_url.startswith(('http://', 'https://')):
        base_url = 'https://' + base_url
    base_url = base_url.rstrip('/')
    
    # Try common feed paths
    for path in FEED_PATHS:
        feed_url = base_url + path
        try:
            response = session.head(feed_url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            if response.status_code == 200:
                # Verify it's actually a feed
                content_type = response.headers.get('content-type', '').lower()
                if any(ct in content_type for ct in ['xml', 'rss', 'atom']):
                    logger.info(f"Discovered feed at {feed_url}")
                    return feed_url
                
                # Try GET to verify content
                get_response = session.get(feed_url, timeout=REQUEST_TIMEOUT)
                if get_response.status_code == 200:
                    content = get_response.text[:500].lower()
                    if '<rss' in content or '<feed' in content or '<channel>' in content:
                        logger.info(f"Discovered feed at {feed_url}")
                        return feed_url
        except requests.RequestException:
            continue
    
    # Try to find feed link in HTML head
    try:
        response = session.get(base_url, timeout=REQUEST_TIMEOUT)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for RSS/Atom link tags
            for link in soup.find_all('link', rel='alternate'):
                link_type = link.get('type', '').lower()
                if 'rss' in link_type or 'atom' in link_type or 'xml' in link_type:
                    href = link.get('href')
                    if href:
                        feed_url = urljoin(base_url, href)
                        logger.info(f"Discovered feed from HTML: {feed_url}")
                        return feed_url
    except requests.RequestException as e:
        logger.warning(f"Error fetching {base_url} for feed discovery: {e}")
    
    logger.warning(f"Could not discover feed for {base_url}")
    return None


def extract_image_from_entry(entry: dict, session: requests.Session) -> Optional[str]:
    """
    Extract the best available image URL from an RSS entry.
    
    Tries in order:
    1. enclosure (type image/*)
    2. media:content
    3. media:thumbnail
    4. image tag
    5. og:image from the article page (fallback)
    
    Args:
        entry: Parsed feedparser entry
        session: Requests session
        
    Returns:
        Image URL or None
    """
    # Try enclosure
    enclosures = entry.get('enclosures', [])
    for enc in enclosures:
        if enc.get('type', '').startswith('image/'):
            url = clean_image_url(enc.get('href') or enc.get('url'))
            if url:
                return url
    
    # Try media:content
    media_content = entry.get('media_content', [])
    for media in media_content:
        if media.get('medium') == 'image' or media.get('type', '').startswith('image/'):
            url = clean_image_url(media.get('url'))
            if url:
                return url
        # Some feeds have media:content without type
        url = clean_image_url(media.get('url'))
        if url and any(ext in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
            return url
    
    # Try media:thumbnail
    media_thumbnail = entry.get('media_thumbnail', [])
    for thumb in media_thumbnail:
        url = clean_image_url(thumb.get('url'))
        if url:
            return url
    
    # Try image tag (some feeds put it here)
    if 'image' in entry:
        img = entry['image']
        if isinstance(img, dict):
            url = clean_image_url(img.get('href') or img.get('url'))
            if url:
                return url
        elif isinstance(img, str):
            url = clean_image_url(img)
            if url:
                return url
    
    # Try content (some blogs embed images in content)
    content_blocks = entry.get('content', [])
    if content_blocks:
        for content in content_blocks:
            html_content = content.get('value', '')
            if html_content:
                soup = BeautifulSoup(html_content, 'html.parser')
                img = soup.find('img')
                if img:
                    url = clean_image_url(img.get('src'))
                    if url:
                        return url
    
    # Try summary/description for embedded images
    summary = entry.get('summary', '')
    if summary and '<img' in summary:
        soup = BeautifulSoup(summary, 'html.parser')
        img = soup.find('img')
        if img:
            url = clean_image_url(img.get('src'))
            if url:
                return url
    
    # Fallback: fetch the article page and get og:image
    link = entry.get('link')
    if link:
        try:
            response = session.get(link, timeout=5)  # Short timeout for fallback
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Try og:image
                og_image = soup.find('meta', property='og:image')
                if og_image:
                    url = clean_image_url(og_image.get('content'))
                    if url:
                        return urljoin(link, url)
                
                # Try twitter:image
                twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})
                if twitter_image:
                    url = clean_image_url(twitter_image.get('content'))
                    if url:
                        return urljoin(link, url)
        except requests.RequestException:
            pass  # Silently fail on og:image fallback
    
    return None


def parse_feed(
    source: RSSSource,
    session: requests.Session,
    hours: int = 24,
    max_articles: int = 6,
    sent_urls: Set[str] = None
) -> List[Article]:
    """
    Parse an RSS feed and extract articles.
    
    Args:
        source: RSS source configuration
        session: Requests session
        hours: Only include articles from the last N hours
        max_articles: Maximum articles to return per feed
        sent_urls: Set of already-sent URLs to exclude
        
    Returns:
        List of Article objects
    """
    if sent_urls is None:
        sent_urls = set()
    
    articles = []
    feed_url = source.feed_url
    
    # Discover feed if not provided
    if not feed_url:
        feed_url = discover_feed_url(source.base_url, session)
        if not feed_url:
            logger.error(f"No feed URL available for {source.name}")
            return []
    
    try:
        # Fetch and parse the feed
        response = session.get(feed_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        
        feed = feedparser.parse(response.text)
        
        if feed.bozo and not feed.entries:
            logger.warning(f"Feed parse error for {source.name}: {feed.bozo_exception}")
            return []
        
        for entry in feed.entries[:max_articles * 2]:  # Fetch extra in case some are filtered
            if len(articles) >= max_articles:
                break
            
            # Get article URL and normalize
            url = entry.get('link', '')
            if not url:
                continue
            
            normalized_url = normalize_url(url)
            
            # Skip if already sent
            if normalized_url in sent_urls:
                logger.debug(f"Skipping already-sent article: {url}")
                continue
            
            # Parse publication date
            pub_date = None
            for date_field in ['published', 'updated', 'created']:
                if date_field in entry:
                    pub_date = parse_rss_date(entry[date_field])
                    if pub_date:
                        break
            
            # Filter by recency
            if pub_date and not is_within_hours(pub_date, hours):
                continue
            
            # Get title
            title = strip_html(entry.get('title', 'Untitled'))
            if not title:
                continue
            
            # Get description
            description = ''
            if entry.get('summary'):
                description = truncate_text(entry['summary'], max_length=200)
            elif entry.get('description'):
                description = truncate_text(entry['description'], max_length=200)
            else:
                description = title  # Fallback to title
            
            # Get image
            image_url = extract_image_from_entry(entry, session)
            
            articles.append(Article(
                title=title,
                url=url,
                description=description,
                image_url=image_url,
                published=pub_date,
                source_name=source.name,
                source_url=source.base_url
            ))
        
        logger.info(f"Parsed {len(articles)} articles from {source.name}")
        return articles
        
    except requests.RequestException as e:
        logger.error(f"Error fetching feed for {source.name}: {e}")
        return []
    except Exception as e:
        logger.error(f"Error parsing feed for {source.name}: {e}")
        return []


def fetch_all_feeds(
    sources: List[RSSSource],
    sent_urls: Set[str] = None,
    hours: int = 24,
    max_per_source: int = 6,
    max_total: int = 24
) -> List[Article]:
    """
    Fetch articles from all configured RSS sources.
    
    Args:
        sources: List of RSS sources
        sent_urls: Set of already-sent URLs to exclude
        hours: Only include articles from the last N hours
        max_per_source: Maximum articles per source
        max_total: Maximum total articles to return
        
    Returns:
        List of Article objects, sorted by publish date (newest first)
    """
    if sent_urls is None:
        sent_urls = set()
    
    all_articles = []
    session = get_session()
    
    for source in sources:
        try:
            articles = parse_feed(
                source=RSSSource(
                    name=source.name,
                    base_url=source.base_url,
                    feed_url=source.feed_url
                ),
                session=session,
                hours=hours,
                max_articles=max_per_source,
                sent_urls=sent_urls
            )
            all_articles.extend(articles)
        except Exception as e:
            logger.error(f"Failed to fetch {source.name}: {e}")
            continue
    
    # Deduplicate by normalized URL
    seen_urls = set()
    unique_articles = []
    for article in all_articles:
        normalized = normalize_url(article.url)
        if normalized not in seen_urls and normalized not in sent_urls:
            seen_urls.add(normalized)
            unique_articles.append(article)
    
    # Sort by publication date (newest first)
    def sort_key(a: Article):
        if a.published:
            return a.published
        return datetime.min.replace(tzinfo=ZoneInfo("UTC"))
    
    unique_articles.sort(key=sort_key, reverse=True)
    
    # Limit to max total
    result = unique_articles[:max_total]
    
    logger.info(f"Total articles after deduplication: {len(result)}")
    return result
