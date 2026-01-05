"""
Gas prices provider for the Newsletter Digest system.
Fetches gas price data for Mississippi cities.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from pathlib import Path
import json

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# AAA Gas Prices page for Mississippi
AAA_MS_URL = "https://gasprices.aaa.com/?state=MS"

# Cache file for gas prices (to avoid excessive requests)
CACHE_FILE = Path(__file__).parent.parent / "data" / "gas_prices_cache.json"
CACHE_DURATION_HOURS = 4


@dataclass
class GasPrice:
    """Represents gas price data for a city or state."""
    location: str
    regular: Optional[float]
    midgrade: Optional[float] = None
    premium: Optional[float] = None
    diesel: Optional[float] = None
    as_of: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for template rendering."""
        return {
            'location': self.location,
            'regular': self.regular,
            'midgrade': self.midgrade,
            'premium': self.premium,
            'diesel': self.diesel,
            'as_of': self.as_of.isoformat() if self.as_of else None
        }


def load_cache() -> Optional[Dict]:
    """Load cached gas prices if still valid."""
    try:
        if CACHE_FILE.exists():
            with open(CACHE_FILE, 'r') as f:
                data = json.load(f)
            
            cached_time = datetime.fromisoformat(data.get('timestamp', '2000-01-01'))
            if datetime.now() - cached_time < timedelta(hours=CACHE_DURATION_HOURS):
                logger.info("Using cached gas prices")
                return data
    except Exception as e:
        logger.warning(f"Error loading gas price cache: {e}")
    return None


def save_cache(data: Dict):
    """Save gas prices to cache."""
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data['timestamp'] = datetime.now().isoformat()
        with open(CACHE_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning(f"Error saving gas price cache: {e}")


def fetch_aaa_state_average() -> Optional[GasPrice]:
    """
    Fetch the Mississippi statewide gas price average from AAA.
    
    Returns:
        GasPrice object with state average or None
    """
    try:
        session = requests.Session()
        session.headers.update({'User-Agent': USER_AGENT})
        
        response = session.get(AAA_MS_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # AAA displays prices in a table or specific elements
        # The structure varies, so we try multiple approaches
        
        regular_price = None
        
        # Look for the state average price display
        # AAA typically shows it prominently
        price_elements = soup.find_all(['span', 'div', 'td'], class_=lambda x: x and 'price' in x.lower() if x else False)
        
        for elem in price_elements:
            text = elem.get_text(strip=True)
            if text.startswith('$'):
                try:
                    price = float(text.replace('$', '').replace(',', ''))
                    if 1.5 < price < 8.0:  # Reasonable gas price range
                        regular_price = price
                        break
                except ValueError:
                    continue
        
        # Alternative: look for specific data attributes or structured data
        if regular_price is None:
            # Try finding any element with price-like content
            for elem in soup.find_all(string=lambda t: t and '$' in t):
                text = str(elem).strip()
                if text.startswith('$') and len(text) < 10:
                    try:
                        price = float(text.replace('$', '').replace(',', ''))
                        if 1.5 < price < 8.0:
                            regular_price = price
                            break
                    except ValueError:
                        continue
        
        if regular_price:
            return GasPrice(
                location="Mississippi (State Average)",
                regular=regular_price,
                as_of=datetime.now()
            )
        
        return None
        
    except requests.RequestException as e:
        logger.error(f"Error fetching AAA gas prices: {e}")
        return None
    except Exception as e:
        logger.error(f"Error parsing AAA gas prices: {e}")
        return None


def fetch_gas_prices(
    cities: List[str],
    api_key: Optional[str] = None
) -> tuple[List[GasPrice], str, str]:
    """
    Fetch gas prices for the specified cities.
    
    Args:
        cities: List of city names (e.g., "Tupelo, MS")
        api_key: Optional API key for a gas price service
        
    Returns:
        Tuple of (list of prices, status message, source URL)
    """
    prices = []
    status_message = ""
    source_url = "https://gasprices.aaa.com/?state=MS"
    
    # Check cache first
    cached = load_cache()
    if cached and cached.get('prices'):
        prices = [
            GasPrice(
                location=p['location'],
                regular=p.get('regular'),
                midgrade=p.get('midgrade'),
                premium=p.get('premium'),
                diesel=p.get('diesel')
            )
            for p in cached['prices']
        ]
        if cached.get('status_message'):
            status_message = cached['status_message']
        return prices, status_message, source_url
    
    # If API key is provided, try to use a gas price API
    if api_key:
        # TODO: Implement specific API integration if available
        # For now, fall through to state average
        pass
    
    # Fetch state average from AAA
    state_avg = fetch_aaa_state_average()
    
    if state_avg:
        prices.append(state_avg)
        status_message = (
            "City-level gas prices are not available. "
            "Showing Mississippi statewide average from AAA."
        )
    else:
        # Use fallback static data with disclaimer
        prices.append(GasPrice(
            location="Mississippi (State Average)",
            regular=None,
            as_of=datetime.now()
        ))
        status_message = (
            "Gas price data temporarily unavailable. "
            "Visit AAA for current prices."
        )
    
    # Cache the results
    save_cache({
        'prices': [p.to_dict() for p in prices],
        'status_message': status_message
    })
    
    return prices, status_message, source_url
