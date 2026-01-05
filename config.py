"""
Configuration module for the Newsletter Digest system.
Loads settings from environment variables and feeds.yaml.
"""

import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv


# Load environment variables from .env file
load_dotenv()


@dataclass
class SMTPConfig:
    """SMTP email configuration."""
    host: str
    port: int
    user: str
    password: str
    use_tls: bool = True


@dataclass
class EmailConfig:
    """Email settings."""
    to_address: str
    from_address: str
    smtp: Optional[SMTPConfig] = None
    sendgrid_api_key: Optional[str] = None
    mailgun_api_key: Optional[str] = None
    mailgun_domain: Optional[str] = None


@dataclass
class RSSSource:
    """RSS feed source configuration."""
    name: str
    base_url: str
    feed_url: Optional[str] = None


@dataclass
class WeatherLocation:
    """Weather location with coordinates."""
    name: str
    lat: float
    lon: float


@dataclass
class Config:
    """Main configuration container."""
    # Email settings
    email: EmailConfig
    
    # Timezone
    timezone: ZoneInfo
    run_hour: int
    
    # Database
    database_path: Path
    
    # RSS sources
    rss_sources: list[RSSSource] = field(default_factory=list)
    national_sources: list[RSSSource] = field(default_factory=list)
    
    # Weather
    weather_locations: list[WeatherLocation] = field(default_factory=list)
    
    # Gas cities
    gas_cities: list[str] = field(default_factory=list)
    
    # API Keys
    calendarific_api_key: Optional[str] = None
    checkiday_api_key: Optional[str] = None
    news_api_key: Optional[str] = None
    gas_api_key: Optional[str] = None
    
    # Paths
    project_root: Path = field(default_factory=lambda: Path(__file__).parent)
    output_dir: Path = field(default_factory=lambda: Path(__file__).parent / "output")
    template_dir: Path = field(default_factory=lambda: Path(__file__).parent / "renderer")


def load_config() -> Config:
    """Load configuration from environment and feeds.yaml."""
    project_root = Path(__file__).parent
    
    # Load feeds.yaml
    feeds_path = project_root / "feeds.yaml"
    if feeds_path.exists():
        with open(feeds_path, 'r', encoding='utf-8') as f:
            feeds_data = yaml.safe_load(f)
    else:
        feeds_data = {"sources": [], "national_sources": [], "weather_locations": [], "gas_cities": []}
    
    # Parse RSS sources
    rss_sources = [
        RSSSource(
            name=s.get("name", "Unknown"),
            base_url=s.get("base_url", ""),
            feed_url=s.get("feed_url")
        )
        for s in feeds_data.get("sources", [])
    ]
    
    # Parse national sources
    national_sources = [
        RSSSource(
            name=s.get("name", "Unknown"),
            base_url=s.get("base_url", ""),
            feed_url=s.get("feed_url")
        )
        for s in feeds_data.get("national_sources", [])
    ]
    
    # Parse weather locations
    weather_locations = [
        WeatherLocation(
            name=w.get("name", "Unknown"),
            lat=w.get("lat", 0.0),
            lon=w.get("lon", 0.0)
        )
        for w in feeds_data.get("weather_locations", [])
    ]
    
    # Parse gas cities
    gas_cities = feeds_data.get("gas_cities", [])
    
    # Build SMTP config if credentials provided
    smtp_config = None
    smtp_host = os.getenv("SMTP_HOST")
    if smtp_host:
        smtp_config = SMTPConfig(
            host=smtp_host,
            port=int(os.getenv("SMTP_PORT", "587")),
            user=os.getenv("SMTP_USER", ""),
            password=os.getenv("SMTP_PASS", ""),
            use_tls=True
        )
    
    # Build email config
    email_config = EmailConfig(
        to_address=os.getenv("EMAIL_TO", ""),
        from_address=os.getenv("EMAIL_FROM", ""),
        smtp=smtp_config,
        sendgrid_api_key=os.getenv("SENDGRID_API_KEY"),
        mailgun_api_key=os.getenv("MAILGUN_API_KEY"),
        mailgun_domain=os.getenv("MAILGUN_DOMAIN")
    )
    
    # Timezone
    tz_name = os.getenv("TIMEZONE", "America/Chicago")
    timezone = ZoneInfo(tz_name)
    
    # Run hour
    run_hour = int(os.getenv("RUN_HOUR", "19"))
    
    # Database path
    db_path_str = os.getenv("DATABASE_PATH", "data/newsletter.db")
    database_path = project_root / db_path_str
    
    # Ensure directories exist
    database_path.parent.mkdir(parents=True, exist_ok=True)
    output_dir = project_root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    return Config(
        email=email_config,
        timezone=timezone,
        run_hour=run_hour,
        database_path=database_path,
        rss_sources=rss_sources,
        national_sources=national_sources,
        weather_locations=weather_locations,
        gas_cities=gas_cities,
        calendarific_api_key=os.getenv("CALENDARIFIC_API_KEY"),
        checkiday_api_key=os.getenv("CHECKIDAY_API_KEY"),
        news_api_key=os.getenv("NEWS_API_KEY"),
        gas_api_key=os.getenv("GAS_API_KEY"),
        project_root=project_root,
        output_dir=output_dir,
        template_dir=project_root / "renderer"
    )


def validate_config(config: Config) -> list[str]:
    """Validate configuration and return list of errors."""
    errors = []
    
    if not config.email.to_address:
        errors.append("EMAIL_TO is required")
    
    if not config.email.from_address:
        errors.append("EMAIL_FROM is required")
    
    # Check that at least one email method is configured
    has_email_method = (
        config.email.smtp is not None or
        config.email.sendgrid_api_key is not None or
        config.email.mailgun_api_key is not None
    )
    if not has_email_method:
        errors.append("No email delivery method configured (SMTP, SendGrid, or Mailgun)")
    
    if not config.rss_sources:
        errors.append("No RSS sources configured in feeds.yaml")
    
    return errors
