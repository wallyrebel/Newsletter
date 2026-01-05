"""
This Day in History provider for the Newsletter Digest system.
Fetches historical events for a given date from Wikipedia.
"""

import logging
import re
from datetime import datetime, date, timedelta
from typing import Optional, List
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15

USER_AGENT = (
    "Mozilla/5.0 (compatible; MNG-Digest-Bot/1.0; "
    "+https://github.com/msnewsgroup/newsletter)"
)

# Wikipedia API for "On This Day"
WIKIPEDIA_API = "https://en.wikipedia.org/api/rest_v1"


@dataclass
class HistoricalEvent:
    """Represents a historical event."""
    year: str
    event: str
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            'year': self.year,
            'event': self.event
        }


def fetch_wikipedia_on_this_day(check_date: date, max_events: int = 8) -> tuple[List[HistoricalEvent], str]:
    """
    Fetch historical events from Wikipedia's "On This Day" API.
    
    Args:
        check_date: Date to fetch history for
        max_events: Maximum events to return
        
    Returns:
        Tuple of (list of events, source URL)
    """
    events = []
    month = check_date.month
    day = check_date.day
    
    source_url = f"https://en.wikipedia.org/wiki/{check_date.strftime('%B')}_{day}"
    
    try:
        # Wikipedia's On This Day API endpoint
        url = f"{WIKIPEDIA_API}/feed/onthisday/events/{month}/{day}"
        
        headers = {
            'User-Agent': USER_AGENT,
            'Accept': 'application/json'
        }
        
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        
        data = response.json()
        
        wiki_events = data.get('events', [])
        
        # Sort by year (most recent first) and select notable ones
        wiki_events.sort(key=lambda x: x.get('year', 0), reverse=True)
        
        # Select a mix of events from different eras
        selected = []
        eras = {
            'recent': [],      # 2000+
            'modern': [],      # 1950-1999
            'mid_century': [], # 1900-1949
            'historical': []   # Before 1900
        }
        
        for event in wiki_events:
            year = event.get('year', 0)
            text = event.get('text', '')
            
            if not text or not year:
                continue
            
            # Clean up the text
            text = text.strip()
            if len(text) > 200:
                text = text[:197] + "..."
            
            evt = HistoricalEvent(year=str(year), event=text)
            
            if year >= 2000:
                eras['recent'].append(evt)
            elif year >= 1950:
                eras['modern'].append(evt)
            elif year >= 1900:
                eras['mid_century'].append(evt)
            else:
                eras['historical'].append(evt)
        
        # Take a balanced selection from each era
        per_era = max(1, max_events // 4)
        for era_name in ['recent', 'modern', 'mid_century', 'historical']:
            selected.extend(eras[era_name][:per_era])
        
        # Fill remaining slots from any era
        if len(selected) < max_events:
            all_events = (
                eras['recent'] + eras['modern'] + 
                eras['mid_century'] + eras['historical']
            )
            for evt in all_events:
                if evt not in selected:
                    selected.append(evt)
                    if len(selected) >= max_events:
                        break
        
        # Sort final selection by year (chronological)
        selected.sort(key=lambda x: int(x.year) if x.year.lstrip('-').isdigit() else 0)
        
        events = selected[:max_events]
        logger.info(f"Found {len(events)} historical events for {month}/{day}")
        
        return events, source_url
        
    except requests.RequestException as e:
        logger.error(f"Error fetching Wikipedia On This Day: {e}")
        return [], source_url
    except Exception as e:
        logger.error(f"Error parsing Wikipedia data: {e}")
        return [], source_url


def fetch_history_fallback(check_date: date, max_events: int = 8) -> tuple[List[HistoricalEvent], str]:
    """
    Fallback: Scrape Wikipedia's "On This Day" page directly.
    
    Args:
        check_date: Date to fetch history for
        max_events: Maximum events to return
        
    Returns:
        Tuple of (list of events, source URL)
    """
    events = []
    month_name = check_date.strftime('%B')
    day = check_date.day
    
    source_url = f"https://en.wikipedia.org/wiki/{month_name}_{day}"
    
    try:
        headers = {'User-Agent': USER_AGENT}
        response = requests.get(source_url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the Events section
        events_heading = None
        for heading in soup.find_all(['h2', 'h3']):
            span = heading.find('span', class_='mw-headline')
            if span and 'Events' in span.get_text():
                events_heading = heading
                break
        
        if not events_heading:
            logger.warning("Could not find Events section on Wikipedia page")
            return [], source_url
        
        # Get the list after the Events heading
        ul = events_heading.find_next('ul')
        if ul:
            for li in ul.find_all('li', recursive=False)[:max_events * 2]:
                text = li.get_text(strip=True)
                
                # Parse year and event
                # Format is usually "Year – Event description"
                match = re.match(r'^(\d+)\s*[–\-—]\s*(.+)$', text)
                if match:
                    year = match.group(1)
                    event_text = match.group(2)
                    
                    # Clean up the event text
                    if len(event_text) > 200:
                        event_text = event_text[:197] + "..."
                    
                    events.append(HistoricalEvent(year=year, event=event_text))
                    
                    if len(events) >= max_events:
                        break
        
        logger.info(f"Scraped {len(events)} events from Wikipedia")
        return events, source_url
        
    except requests.RequestException as e:
        logger.error(f"Error scraping Wikipedia: {e}")
        return [], source_url
    except Exception as e:
        logger.error(f"Error parsing Wikipedia page: {e}")
        return [], source_url


def fetch_this_day_in_history(
    target_date: Optional[date] = None,
    max_events: int = 8
) -> tuple[List[HistoricalEvent], str, str]:
    """
    Fetch historical events for "This Day in History".
    
    By default, fetches for the NEXT day's date (e.g., if run on Jan 5,
    returns events for Jan 6).
    
    Args:
        target_date: Specific date to fetch (defaults to tomorrow)
        max_events: Maximum events to return (4-8 recommended)
        
    Returns:
        Tuple of (list of events, formatted date string, source URL)
    """
    # Default to next day
    if target_date is None:
        target_date = date.today() + timedelta(days=1)
    
    date_str = target_date.strftime("%B %d")
    
    # Try the API first
    events, source_url = fetch_wikipedia_on_this_day(target_date, max_events)
    
    # Fall back to scraping if API fails
    if not events:
        events, source_url = fetch_history_fallback(target_date, max_events)
    
    return events, date_str, source_url
