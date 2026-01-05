"""
Holidays and observances provider for the Newsletter Digest system.
Fetches official holidays from Nager.Date and fun observances from Calendarific.
"""

import logging
from datetime import datetime, date
from typing import Optional, List, Tuple
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

# API URLs
NAGER_DATE_API = "https://date.nager.at/api/v3"
CALENDARIFIC_API = "https://calendarific.com/api/v2"
CHECKIDAY_API = "https://www.checkiday.com/api/3"

REQUEST_TIMEOUT = 15


@dataclass
class HolidayResult:
    """Result from holiday provider."""
    major_holidays: List[str]
    fun_observances: List[str]
    source_links: List[str]
    error_message: Optional[str] = None


def fetch_nager_holidays(check_date: date) -> Tuple[List[str], str]:
    """
    Fetch official US public holidays from Nager.Date API.
    
    Args:
        check_date: Date to check for holidays
        
    Returns:
        Tuple of (list of holiday names, source URL)
    """
    holidays = []
    source_url = "https://date.nager.at"
    
    try:
        url = f"{NAGER_DATE_API}/PublicHolidays/{check_date.year}/US"
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        
        data = response.json()
        
        for holiday in data:
            holiday_date = holiday.get('date', '')
            if holiday_date == check_date.isoformat():
                name = holiday.get('name', '')
                if name:
                    holidays.append(name)
        
        logger.info(f"Found {len(holidays)} official holidays from Nager.Date")
        return holidays, source_url
        
    except requests.RequestException as e:
        logger.error(f"Error fetching Nager.Date holidays: {e}")
        return [], source_url


def fetch_calendarific_holidays(
    api_key: str,
    check_date: date,
    include_observances: bool = True
) -> Tuple[List[str], List[str], str]:
    """
    Fetch holidays and observances from Calendarific API.
    
    Args:
        api_key: Calendarific API key
        check_date: Date to check
        include_observances: Whether to include observances
        
    Returns:
        Tuple of (official holidays, fun observances, source URL)
    """
    official = []
    fun = []
    source_url = "https://calendarific.com"
    
    if not api_key:
        logger.warning("Calendarific API key not provided")
        return [], [], source_url
    
    try:
        # Request with type=observance to get more fun holidays
        params = {
            'api_key': api_key,
            'country': 'US',
            'year': check_date.year,
            'month': check_date.month,
            'day': check_date.day,
            'type': 'observance,local,religious,national'  # Get all types
        }
        
        response = requests.get(
            f"{CALENDARIFIC_API}/holidays",
            params=params,
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('meta', {}).get('code') != 200:
            logger.error(f"Calendarific API error: {data.get('meta', {})}")
            return [], [], source_url
        
        # Handle different response formats
        response_data = data.get('response', {})
        if isinstance(response_data, dict):
            holidays = response_data.get('holidays', [])
        elif isinstance(response_data, list):
            holidays = response_data
        else:
            holidays = []
        
        logger.debug(f"Calendarific raw response: {len(holidays)} holidays")
        
        for holiday in holidays:
            name = holiday.get('name', '')
            if not name:
                continue
            
            holiday_type = holiday.get('type', [])
            
            # Categorize by type
            if 'National holiday' in holiday_type or 'Federal holiday' in holiday_type:
                official.append(name)
            else:
                # All other types go to fun observances
                fun.append(name)
        
        # Remove duplicates while preserving order
        official = list(dict.fromkeys(official))
        fun = list(dict.fromkeys(fun))
        
        logger.info(f"Calendarific: {len(official)} official, {len(fun)} observances")
        return official, fun, source_url
        
    except requests.RequestException as e:
        logger.error(f"Error fetching Calendarific holidays: {e}")
        return [], [], source_url


def fetch_checkiday_holidays(api_key: str, check_date: date) -> Tuple[List[str], str]:
    """
    Fetch fun observances from Checkiday API.
    
    Args:
        api_key: Checkiday API key
        check_date: Date to check
        
    Returns:
        Tuple of (list of observance names, source URL)
    """
    observances = []
    source_url = "https://www.checkiday.com"
    
    if not api_key:
        logger.warning("Checkiday API key not provided")
        return [], source_url
    
    try:
        params = {
            'apiKey': api_key,
            'date': check_date.strftime('%Y-%m-%d')  # Format: YYYY-MM-DD
        }
        
        response = requests.get(
            f"{CHECKIDAY_API}/",
            params=params,
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        
        data = response.json()
        
        if not data.get('ok'):
            logger.error(f"Checkiday API error: {data.get('error', 'Unknown')}")
            return [], source_url
        
        for holiday in data.get('holidays', []):
            name = holiday.get('name', '')
            if name:
                observances.append(name)
        
        logger.info(f"Found {len(observances)} observances from Checkiday")
        return observances, source_url
        
    except requests.RequestException as e:
        logger.error(f"Error fetching Checkiday holidays: {e}")
        return [], source_url


def fetch_wikipedia_holidays(check_date: date) -> Tuple[List[str], str]:
    """
    Fallback: Fetch observances from Wikipedia's page for the date.
    
    Args:
        check_date: Date to check
        
    Returns:
        Tuple of (list of observance names, source URL)
    """
    from bs4 import BeautifulSoup
    
    observances = []
    month_name = check_date.strftime('%B')
    day = check_date.day
    source_url = f"https://en.wikipedia.org/wiki/{month_name}_{day}"
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; MNG-Digest-Bot/1.0)'
        }
        response = requests.get(source_url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the "Holidays and observances" section - try multiple approaches
        holidays_section = None
        
        # Approach 1: Look for h2 with text containing "observances"
        for h in soup.find_all('h2'):
            if 'observances' in h.get_text().lower() or 'holidays' in h.get_text().lower():
                holidays_section = h
                break
        
        # Approach 2: Look for mw-headline span
        if not holidays_section:
            for heading in soup.find_all(['h2', 'h3']):
                span = heading.find('span', class_='mw-headline')
                if span and 'observances' in span.get_text().lower():
                    holidays_section = heading
                    break
        
        if holidays_section:
            # Get the list items after this heading
            next_elem = holidays_section.find_next_sibling()
            while next_elem and next_elem.name not in ['h2']:
                if next_elem.name == 'ul':
                    for li in next_elem.find_all('li', recursive=False):
                        text = li.get_text(strip=True)
                        # Clean up the text - take first line, remove citations
                        text = text.split('\n')[0]
                        text = text.split('[')[0].strip()
                        
                        if text and len(text) < 100 and len(text) > 3:
                            # Skip sub-items that are just names
                            if ':' in text:
                                # Headers like "Christian Feast day:" - skip
                                continue
                            observances.append(text)
                next_elem = next_elem.find_next_sibling()
        
        # Also search for nested observances (common for holidays)
        if holidays_section and len(observances) == 0:
            section = holidays_section.find_next('ul')
            if section:
                for li in section.find_all('li'):
                    text = li.get_text(strip=True)
                    text = text.split('[')[0].strip()
                    if text and 'day' in text.lower() and len(text) < 80:
                        observances.append(text)
        
        # Remove duplicates
        observances = list(dict.fromkeys(observances))
        
        logger.info(f"Found {len(observances)} observances from Wikipedia")
        return observances[:15], source_url
        
    except Exception as e:
        logger.error(f"Error fetching Wikipedia holidays: {e}")
        return [], source_url


def curate_observances(observances: List[str], max_count: int = 12) -> List[str]:
    """
    Curate and filter observances to keep the most interesting ones.
    
    Args:
        observances: Raw list of observances
        max_count: Maximum number to return
        
    Returns:
        Curated list of observances
    """
    # Keywords that indicate more interesting/recognizable observances
    priority_keywords = [
        'National', 'World', 'International', 'Day', 'Week', 'Month',
        'Awareness', 'Appreciation', 'Celebration'
    ]
    
    # Keywords to filter out (usually too obscure or commercial)
    filter_keywords = [
        'sponsored', 'trademark', '®', '™'
    ]
    
    # Score and filter
    scored = []
    for obs in observances:
        # Skip filtered items
        obs_lower = obs.lower()
        if any(kw.lower() in obs_lower for kw in filter_keywords):
            continue
        
        # Score based on priority keywords
        score = sum(1 for kw in priority_keywords if kw.lower() in obs_lower)
        
        # Boost "National ___ Day" patterns
        if 'national' in obs_lower and 'day' in obs_lower:
            score += 2
        
        scored.append((score, obs))
    
    # Sort by score (descending) and take top items
    scored.sort(key=lambda x: x[0], reverse=True)
    
    # Remove duplicates (case-insensitive)
    seen = set()
    result = []
    for _, obs in scored:
        key = obs.lower().strip()
        if key not in seen:
            seen.add(key)
            result.append(obs)
            if len(result) >= max_count:
                break
    
    return result


def fetch_holidays(
    check_date: date,
    calendarific_api_key: Optional[str] = None,
    checkiday_api_key: Optional[str] = None
) -> HolidayResult:
    """
    Fetch all holidays and observances for a given date.
    
    Args:
        check_date: Date to fetch holidays for
        calendarific_api_key: Optional Calendarific API key
        checkiday_api_key: Optional Checkiday API key
        
    Returns:
        HolidayResult with official holidays and fun observances
    """
    major_holidays = []
    fun_observances = []
    source_links = []
    error_message = None
    
    # 1. Fetch official holidays from Nager.Date (free, no API key)
    nager_holidays, nager_url = fetch_nager_holidays(check_date)
    major_holidays.extend(nager_holidays)
    if nager_url:
        source_links.append(nager_url)
    
    # 2. Try Calendarific for more official holidays + observances
    if calendarific_api_key:
        cal_official, cal_fun, cal_url = fetch_calendarific_holidays(
            calendarific_api_key, check_date
        )
        
        # Add any official holidays we didn't already have
        for h in cal_official:
            if h.lower() not in [x.lower() for x in major_holidays]:
                major_holidays.append(h)
        
        fun_observances.extend(cal_fun)
        if cal_url and cal_url not in source_links:
            source_links.append(cal_url)
    
    # 3. Try Checkiday for fun observances (primary source)
    if checkiday_api_key:
        checkiday_obs, checkiday_url = fetch_checkiday_holidays(
            checkiday_api_key, check_date
        )
        fun_observances.extend(checkiday_obs)
        if checkiday_url and checkiday_url not in source_links:
            source_links.append(checkiday_url)
    
    # 4. Wikipedia fallback if we still have no observances
    if not fun_observances:
        wiki_obs, wiki_url = fetch_wikipedia_holidays(check_date)
        fun_observances.extend(wiki_obs)
        if wiki_obs and wiki_url and wiki_url not in source_links:
            source_links.append(wiki_url)
    
    # If no fun observances found after all attempts
    if not calendarific_api_key and not checkiday_api_key:
        error_message = (
            "Fun observances unavailable today (missing API key or provider error). "
            "Configure CALENDARIFIC_API_KEY or CHECKIDAY_API_KEY to enable."
        )
        logger.warning("No holiday API keys configured for fun observances")
    elif not fun_observances:
        # APIs configured but no observances found anywhere
        error_message = "No fun observances found for today."
    
    # Curate and deduplicate observances
    fun_observances = curate_observances(fun_observances, max_count=12)
    
    # Ensure we have at least something for major holidays
    if not major_holidays:
        major_holidays = []  # Will display "No official public holidays today"
    
    return HolidayResult(
        major_holidays=major_holidays,
        fun_observances=fun_observances,
        source_links=source_links,
        error_message=error_message
    )
