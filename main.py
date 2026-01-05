#!/usr/bin/env python3
"""
Mississippi News Group Daily Digest - Main Entry Point

Generates and emails a nightly newsletter digest with:
- Local Mississippi news from RSS feeds
- National headlines
- Weather outlook
- Gas prices
- Holidays and observances
- This Day in History

Usage:
    python main.py              # Run normally
    python main.py --dry-run    # Generate output without sending email
    python main.py --force      # Ignore "already sent today" check
"""

import argparse
import logging
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader

from config import load_config, validate_config, RSSSource, WeatherLocation
from storage.state import StateManager
from providers.rss import fetch_all_feeds, RSSSource as RSSSourceProvider
from providers.national_news import fetch_national_news
from providers.weather import fetch_all_weather, WeatherLocation as WeatherLocationProvider
from providers.gas import fetch_gas_prices
from providers.holidays import fetch_holidays
from providers.history import fetch_this_day_in_history
from email_sender.sender import send_email, EmailConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def should_run_now(config, force: bool = False) -> tuple[bool, str]:
    """
    Check if the digest should run now based on time and state.
    
    Args:
        config: Application configuration
        force: If True, ignore time and state checks
        
    Returns:
        Tuple of (should_run, reason)
    """
    if force:
        return True, "Force flag set"
    
    # Get current time in configured timezone
    now = datetime.now(config.timezone)
    current_hour = now.hour
    
    # Check if it's the scheduled hour
    if current_hour != config.run_hour:
        return False, f"Not scheduled hour (current: {current_hour}, scheduled: {config.run_hour})"
    
    # Check if already sent today
    state = StateManager(config.database_path)
    if state.was_sent_today(now.date()):
        return False, "Already sent today"
    
    return True, "Scheduled time and not yet sent"


def generate_digest(config, dry_run: bool = False) -> tuple[bool, str]:
    """
    Generate and optionally send the newsletter digest.
    
    Args:
        config: Application configuration
        dry_run: If True, write to files instead of sending email
        
    Returns:
        Tuple of (success, message)
    """
    now = datetime.now(config.timezone)
    today = now.date()
    
    logger.info(f"Generating digest for {today}")
    
    # Initialize state manager
    state = StateManager(config.database_path)
    sent_urls = state.get_sent_urls()
    
    # Collect data from all providers
    errors = []
    
    # 1. Fetch local RSS articles
    logger.info("Fetching local RSS articles...")
    try:
        rss_sources = [
            RSSSourceProvider(
                name=s.name,
                base_url=s.base_url,
                feed_url=s.feed_url
            )
            for s in config.rss_sources
        ]
        articles = fetch_all_feeds(
            sources=rss_sources,
            sent_urls=sent_urls,
            hours=24,
            max_per_source=6,
            max_total=24
        )
        logger.info(f"Found {len(articles)} local articles")
    except Exception as e:
        logger.error(f"Error fetching RSS feeds: {e}")
        articles = []
        errors.append(f"RSS feeds: {e}")
    
    # 2. Fetch national news
    logger.info("Fetching national news...")
    try:
        national_news = fetch_national_news(
            api_key=config.news_api_key,
            max_headlines=3
        )
        logger.info(f"Found {len(national_news)} national headlines")
    except Exception as e:
        logger.error(f"Error fetching national news: {e}")
        national_news = []
        errors.append(f"National news: {e}")
    
    # 3. Fetch weather
    logger.info("Fetching weather forecasts...")
    try:
        weather_locations = [
            WeatherLocationProvider(
                name=w.name,
                lat=w.lat,
                lon=w.lon
            )
            for w in config.weather_locations
        ]
        weather_forecasts, weather_source_url = fetch_all_weather(weather_locations)
        logger.info(f"Fetched weather for {len(weather_forecasts)} locations")
    except Exception as e:
        logger.error(f"Error fetching weather: {e}")
        weather_forecasts = []
        weather_source_url = "https://weather.gov"
        errors.append(f"Weather: {e}")
    
    # 4. Fetch gas prices
    logger.info("Fetching gas prices...")
    try:
        gas_prices, gas_status_message, gas_source_url = fetch_gas_prices(
            cities=config.gas_cities,
            api_key=config.gas_api_key
        )
        logger.info(f"Fetched {len(gas_prices)} gas price entries")
    except Exception as e:
        logger.error(f"Error fetching gas prices: {e}")
        gas_prices = []
        gas_status_message = "Gas prices temporarily unavailable."
        gas_source_url = "https://gasprices.aaa.com/?state=MS"
        errors.append(f"Gas prices: {e}")
    
    # 5. Fetch holidays (for today)
    logger.info("Fetching holidays and observances...")
    try:
        holidays = fetch_holidays(
            check_date=today,
            calendarific_api_key=config.calendarific_api_key,
            checkiday_api_key=config.checkiday_api_key
        )
        logger.info(f"Found {len(holidays.major_holidays)} holidays, {len(holidays.fun_observances)} observances")
    except Exception as e:
        logger.error(f"Error fetching holidays: {e}")
        from providers.holidays import HolidayResult
        holidays = HolidayResult(
            major_holidays=[],
            fun_observances=[],
            source_links=[],
            error_message=f"Holidays unavailable: {e}"
        )
        errors.append(f"Holidays: {e}")
    
    # 6. Fetch "This Day in History" (for NEXT day)
    logger.info("Fetching This Day in History...")
    try:
        tomorrow = today + timedelta(days=1)
        history_events, history_date, history_source_url = fetch_this_day_in_history(
            target_date=tomorrow,
            max_events=8
        )
        logger.info(f"Found {len(history_events)} historical events for {history_date}")
    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        history_events = []
        history_date = (today + timedelta(days=1)).strftime("%B %d")
        history_source_url = "https://en.wikipedia.org"
        errors.append(f"History: {e}")
    
    # Prepare template data
    template_data = {
        'date_str': today.isoformat(),
        'date_display': today.strftime('%A, %B %d, %Y'),
        'articles': [a.to_dict() for a in articles],
        'national_news': [n.to_dict() for n in national_news],
        'weather_forecasts': [w.to_dict() for w in weather_forecasts],
        'weather_source_url': weather_source_url,
        'gas_prices': [g.to_dict() for g in gas_prices],
        'gas_status_message': gas_status_message,
        'gas_source_url': gas_source_url,
        'holidays': {
            'major_holidays': holidays.major_holidays,
            'fun_observances': holidays.fun_observances,
            'source_links': holidays.source_links,
            'error_message': holidays.error_message
        },
        'history_events': [e.to_dict() for e in history_events],
        'history_date': history_date,
        'history_source_url': history_source_url,
        'generated_timestamp': now.strftime('%Y-%m-%d %H:%M:%S %Z')
    }
    
    # Render HTML template
    logger.info("Rendering email template...")
    env = Environment(loader=FileSystemLoader(config.template_dir))
    template = env.get_template('template.html.j2')
    html_content = template.render(**template_data)
    
    # Ensure output directory exists
    config.output_dir.mkdir(parents=True, exist_ok=True)
    
    # Write HTML output
    html_path = config.output_dir / 'draft.html'
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    logger.info(f"Wrote HTML to {html_path}")
    
    # Generate and write plaintext version
    from email_sender.sender import create_plaintext_version
    plaintext_content = create_plaintext_version(html_content)
    
    txt_path = config.output_dir / 'draft.txt'
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(plaintext_content)
    logger.info(f"Wrote plaintext to {txt_path}")
    
    # Generate Markdown version for Substack
    md_content = generate_markdown(template_data)
    md_path = config.output_dir / 'draft.md'
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
    logger.info(f"Wrote Markdown to {md_path}")
    
    if dry_run:
        logger.info("Dry run mode - skipping email send")
        return True, f"Dry run complete. Files saved to {config.output_dir}"
    
    # Send email
    logger.info("Sending email...")
    subject = f"MNG Daily Digest — {today.isoformat()}"
    
    email_config = EmailConfig(
        to_address=config.email.to_address,
        from_address=config.email.from_address,
        smtp_host=config.email.smtp.host if config.email.smtp else None,
        smtp_port=config.email.smtp.port if config.email.smtp else 587,
        smtp_user=config.email.smtp.user if config.email.smtp else None,
        smtp_password=config.email.smtp.password if config.email.smtp else None,
        sendgrid_api_key=config.email.sendgrid_api_key,
        mailgun_api_key=config.email.mailgun_api_key,
        mailgun_domain=config.email.mailgun_domain
    )
    
    success = send_email(
        config=email_config,
        subject=subject,
        html_content=html_content,
        plaintext_content=plaintext_content
    )
    
    if success:
        # Mark articles as sent
        state.mark_articles_sent([
            {'url': a.url, 'title': a.title, 'source_name': a.source_name}
            for a in articles
        ])
        
        # Record successful run
        state.record_successful_run(len(articles), today)
        
        # Cleanup old records periodically
        state.cleanup_old_articles(days=90)
        
        logger.info("Digest sent successfully!")
        return True, f"Digest sent to {config.email.to_address}"
    else:
        state.record_failed_run("Email delivery failed", today)
        logger.error("Failed to send digest email")
        return False, "Email delivery failed"


def generate_markdown(data: dict) -> str:
    """
    Generate a Markdown version for Substack copy/paste.
    
    Args:
        data: Template data dictionary
        
    Returns:
        Markdown content string
    """
    lines = []
    
    lines.append(f"# Mississippi News Group Daily Digest")
    lines.append(f"**{data['date_display']}**\n")
    
    # Local News
    lines.append("## 📰 Local News Digest\n")
    if data['articles']:
        for article in data['articles']:
            lines.append(f"### [{article['title']}]({article['url']})")
            if article.get('image_url'):
                lines.append(f"![{article['title']}]({article['image_url']})")
            if article.get('description') and article['description'] != article['title']:
                lines.append(f"{article['description']}")
            lines.append(f"*{article['source_name']}*\n")
    else:
        lines.append("*No local articles found in the last 24 hours.*\n")
    
    # National News
    lines.append("## 🌐 Major National News\n")
    if data['national_news']:
        for headline in data['national_news']:
            lines.append(f"- [{headline['title']}]({headline['url']}) — *{headline['source']}*")
    else:
        lines.append("*National news temporarily unavailable.*")
    lines.append("")
    
    # Weather
    lines.append("## 🌤️ Weather Outlook\n")
    for forecast in data['weather_forecasts']:
        temps = []
        if forecast.get('high_temp') is not None:
            temps.append(f"High: {forecast['high_temp']}°F")
        if forecast.get('low_temp') is not None:
            temps.append(f"Low: {forecast['low_temp']}°F")
        temp_str = " / ".join(temps) if temps else "Temperature unavailable"
        
        lines.append(f"**{forecast['location_name']}**: {temp_str}")
        lines.append(f"*{forecast['summary']}*")
        if forecast.get('precip_chance') and forecast['precip_chance'] > 0:
            lines.append(f"💧 {forecast['precip_chance']}% chance of precipitation")
        lines.append("")
    
    # Gas Prices
    lines.append("## ⛽ Gas Prices\n")
    if data['gas_prices']:
        for price in data['gas_prices']:
            price_str = f"${price['regular']:.2f}" if price.get('regular') else "N/A"
            lines.append(f"- **{price['location']}**: {price_str}")
    if data.get('gas_status_message'):
        lines.append(f"\n*{data['gas_status_message']}*")
    lines.append("")
    
    # Holidays
    lines.append("## 🎉 Today's Holidays & Observances\n")
    lines.append("### Official Holidays")
    if data['holidays']['major_holidays']:
        for holiday in data['holidays']['major_holidays']:
            lines.append(f"- 🏛️ {holiday}")
    else:
        lines.append("*No official public holidays today.*")
    lines.append("")
    
    lines.append("### Fun Observances")
    if data['holidays']['fun_observances']:
        for obs in data['holidays']['fun_observances']:
            lines.append(f"- 🎈 {obs}")
    elif data['holidays'].get('error_message'):
        lines.append(f"*{data['holidays']['error_message']}*")
    else:
        lines.append("*No fun observances found for today.*")
    lines.append("")
    
    # History
    lines.append(f"## 📜 This Day in History — {data['history_date']}\n")
    if data['history_events']:
        for event in data['history_events']:
            lines.append(f"- **{event['year']}**: {event['event']}")
    else:
        lines.append("*Historical events temporarily unavailable.*")
    lines.append("")
    
    # Footer
    lines.append("---")
    lines.append(f"*Generated on {data['generated_timestamp']}*")
    lines.append("*This is an automated digest. Headlines and links only.*")
    
    return "\n".join(lines)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate and email the MNG Daily Digest newsletter"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Generate output files without sending email"
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help="Ignore scheduling and 'already sent' checks"
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Load configuration
    logger.info("Loading configuration...")
    config = load_config()
    
    # Validate configuration
    validation_errors = validate_config(config)
    if validation_errors and not args.dry_run:
        logger.error("Configuration errors:")
        for error in validation_errors:
            logger.error(f"  - {error}")
        sys.exit(1)
    
    # Check if we should run
    if not args.force and not args.dry_run:
        should_run, reason = should_run_now(config, args.force)
        if not should_run:
            logger.info(f"Not running: {reason}")
            sys.exit(0)
    
    # Generate digest
    success, message = generate_digest(config, dry_run=args.dry_run)
    
    if success:
        logger.info(message)
        sys.exit(0)
    else:
        logger.error(message)
        sys.exit(1)


if __name__ == '__main__':
    main()
