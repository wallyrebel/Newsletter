"""
Weather provider for the Newsletter Digest system.
Fetches forecasts from the National Weather Service (NWS) API.
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import requests

logger = logging.getLogger(__name__)

# NWS API base URL
NWS_API_BASE = "https://api.weather.gov"

REQUEST_TIMEOUT = 15

USER_AGENT = (
    "(MNG-Digest-Newsletter, contact@msnewsgroup.com)"
)


@dataclass
class WeatherForecast:
    """Represents a weather forecast for a location."""
    location_name: str
    high_temp: Optional[int]
    low_temp: Optional[int]
    precip_chance: Optional[int]
    summary: str
    forecast_url: str
    detailed_forecast: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for template rendering."""
        return {
            'location_name': self.location_name,
            'high_temp': self.high_temp,
            'low_temp': self.low_temp,
            'precip_chance': self.precip_chance,
            'summary': self.summary,
            'forecast_url': self.forecast_url,
            'detailed_forecast': self.detailed_forecast
        }


@dataclass
class WeatherLocation:
    """Weather location configuration."""
    name: str
    lat: float
    lon: float


def get_nws_session() -> requests.Session:
    """Create a session with NWS-required headers."""
    session = requests.Session()
    session.headers.update({
        'User-Agent': USER_AGENT,
        'Accept': 'application/geo+json'
    })
    return session


def get_forecast_office(lat: float, lon: float, session: requests.Session) -> Optional[Dict]:
    """
    Get the NWS forecast office information for coordinates.
    
    Args:
        lat: Latitude
        lon: Longitude
        session: Requests session
        
    Returns:
        Dict with forecast URLs or None
    """
    try:
        # Get the metadata for the point
        url = f"{NWS_API_BASE}/points/{lat},{lon}"
        response = session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        
        data = response.json()
        properties = data.get('properties', {})
        
        return {
            'forecast_url': properties.get('forecast'),
            'forecast_hourly_url': properties.get('forecastHourly'),
            'forecast_grid_data': properties.get('forecastGridData'),
            'city': properties.get('relativeLocation', {}).get('properties', {}).get('city', ''),
            'state': properties.get('relativeLocation', {}).get('properties', {}).get('state', ''),
        }
    except requests.RequestException as e:
        logger.error(f"Error getting NWS point data for ({lat}, {lon}): {e}")
        return None


def fetch_forecast(location: WeatherLocation, session: requests.Session) -> Optional[WeatherForecast]:
    """
    Fetch the weather forecast for a location.
    
    Args:
        location: Weather location configuration
        session: Requests session
        
    Returns:
        WeatherForecast object or None
    """
    try:
        # Get forecast office data
        office_data = get_forecast_office(location.lat, location.lon, session)
        if not office_data or not office_data.get('forecast_url'):
            logger.error(f"Could not get forecast URL for {location.name}")
            return None
        
        forecast_url = office_data['forecast_url']
        
        # Fetch the forecast
        response = session.get(forecast_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        
        data = response.json()
        periods = data.get('properties', {}).get('periods', [])
        
        if not periods:
            logger.warning(f"No forecast periods for {location.name}")
            return None
        
        # Get today's forecast (first period is usually "This Afternoon" or "Tonight")
        high_temp = None
        low_temp = None
        precip_chance = None
        summary_parts = []
        detailed = ""
        
        # Look at first two periods for high/low
        for i, period in enumerate(periods[:2]):
            temp = period.get('temperature')
            is_daytime = period.get('isDaytime', True)
            
            if is_daytime and temp is not None:
                high_temp = temp
            elif not is_daytime and temp is not None:
                low_temp = temp
            
            # Get precipitation probability
            if period.get('probabilityOfPrecipitation'):
                prob = period['probabilityOfPrecipitation'].get('value')
                if prob is not None and (precip_chance is None or prob > precip_chance):
                    precip_chance = prob
            
            # Get short forecast
            short = period.get('shortForecast', '')
            if short and i == 0:
                summary_parts.append(short)
            
            # Get detailed forecast for first period
            if i == 0:
                detailed = period.get('detailedForecast', '')
        
        # If we only got one temp, try to get the other from next period
        if len(periods) > 1:
            if high_temp is None:
                for period in periods[1:4]:
                    if period.get('isDaytime') and period.get('temperature') is not None:
                        high_temp = period['temperature']
                        break
            if low_temp is None:
                for period in periods[1:4]:
                    if not period.get('isDaytime') and period.get('temperature') is not None:
                        low_temp = period['temperature']
                        break
        
        # Build summary
        summary = " ".join(summary_parts) if summary_parts else "Forecast unavailable"
        
        # Truncate detailed forecast if too long
        if len(detailed) > 200:
            detailed = detailed[:197] + "..."
        
        # Build public forecast URL for the location
        city = office_data.get('city', '')
        state = office_data.get('state', '')
        if city and state:
            public_url = f"https://forecast.weather.gov/MapClick.php?lat={location.lat}&lon={location.lon}"
        else:
            public_url = f"https://weather.gov"
        
        return WeatherForecast(
            location_name=location.name,
            high_temp=high_temp,
            low_temp=low_temp,
            precip_chance=precip_chance,
            summary=summary,
            forecast_url=public_url,
            detailed_forecast=detailed
        )
        
    except requests.RequestException as e:
        logger.error(f"Error fetching forecast for {location.name}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error parsing forecast for {location.name}: {e}")
        return None


def fetch_all_weather(locations: List[WeatherLocation]) -> tuple[List[WeatherForecast], str]:
    """
    Fetch weather forecasts for all configured locations.
    
    Args:
        locations: List of weather locations
        
    Returns:
        Tuple of (list of forecasts, source URL)
    """
    forecasts = []
    session = get_nws_session()
    
    for location in locations:
        try:
            forecast = fetch_forecast(location, session)
            if forecast:
                forecasts.append(forecast)
            else:
                # Add a placeholder forecast for failed locations
                forecasts.append(WeatherForecast(
                    location_name=location.name,
                    high_temp=None,
                    low_temp=None,
                    precip_chance=None,
                    summary="Forecast temporarily unavailable",
                    forecast_url="https://weather.gov"
                ))
        except Exception as e:
            logger.error(f"Failed to fetch weather for {location.name}: {e}")
            forecasts.append(WeatherForecast(
                location_name=location.name,
                high_temp=None,
                low_temp=None,
                precip_chance=None,
                summary="Forecast temporarily unavailable",
                forecast_url="https://weather.gov"
            ))
    
    source_url = "https://www.weather.gov"
    return forecasts, source_url
