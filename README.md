# Mississippi News Group Daily Digest

A production-ready Python system that generates and emails a nightly newsletter digest featuring Mississippi local news, national headlines, weather, gas prices, holidays, and historical facts.

## Features

- **Local News Digest**: Aggregates from 17+ Mississippi RSS sources
- **National Headlines**: Top 2-3 stories from Google News
- **Weather Outlook**: NWS forecasts for North MS, Central MS, and Gulf Coast
- **Gas Prices**: City averages across Mississippi
- **Holidays & Observances**: Official holidays + fun "National ___ Day" observances
- **This Day in History**: Historical events for the next day

## Quick Start

### 1. Clone and Install

```bash
git clone <repo-url>
cd Newsletter
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your settings
```

Required environment variables:
- `EMAIL_TO` - Recipient email address
- `EMAIL_FROM` - Sender email address
- `SMTP_HOST` - SMTP server hostname
- `SMTP_PORT` - SMTP port (usually 587 for TLS)
- `SMTP_USER` - SMTP username
- `SMTP_PASS` - SMTP password

Optional API keys:
- `CALENDARIFIC_API_KEY` - For fun/observance holidays
- `CHECKIDAY_API_KEY` - Alternative holiday provider
- `GAS_API_KEY` - For city-level gas prices (if available)

### 3. Run Locally

```bash
# Dry run (generates HTML without sending email)
python main.py --dry-run

# Send email
python main.py

# Force send (ignores "already sent today" check)
python main.py --force
```

Output files are saved to `output/`:
- `draft.html` - HTML version for browser preview
- `draft.md` - Markdown version for Substack copy/paste
- `draft.txt` - Plaintext version

## Scheduled Execution

### GitHub Actions (Recommended)

The included workflow runs hourly and sends the digest at 7 PM Central time (DST-aware).

1. Go to repository Settings → Secrets and variables → Actions
2. Add the following secrets:
   - `EMAIL_TO`, `EMAIL_FROM`
   - `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`
   - Optional: `CALENDARIFIC_API_KEY`, `CHECKIDAY_API_KEY`
3. Enable Actions in your repository

### System Cron (Alternative)

```bash
# Edit crontab (ensure server timezone is America/Chicago)
crontab -e

# Add this line for 7 PM daily
0 19 * * * cd /path/to/Newsletter && /path/to/venv/bin/python main.py >> /var/log/newsletter.log 2>&1
```

## Configuration

### RSS Sources (`feeds.yaml`)

The `feeds.yaml` file contains all RSS sources. Each source has:
- `name`: Display name
- `base_url`: Website URL
- `feed_url`: RSS feed URL (auto-discovered if not specified)

```yaml
sources:
  - name: Tupelo News
    base_url: https://newstupelo.com
    feed_url: https://newstupelo.com/feed/
```

### Adding New Sources

1. Add the source to `feeds.yaml`
2. If the feed URL is unknown, leave `feed_url` empty and the system will attempt discovery

## Project Structure

```
Newsletter/
├── main.py                 # CLI entry point
├── config.py               # Configuration loading
├── feeds.yaml              # RSS source configuration
├── providers/
│   ├── rss.py              # RSS feed parsing
│   ├── national_news.py    # Google News integration
│   ├── weather.py          # NWS API
│   ├── gas.py              # Gas prices
│   ├── holidays.py         # Holidays & observances
│   └── history.py          # This Day in History
├── storage/
│   └── state.py            # SQLite state management
├── renderer/
│   └── template.html.j2    # Email template
├── email_sender/
│   └── sender.py           # SMTP delivery
├── utils/
│   └── helpers.py          # URL normalization, etc.
└── tests/                  # Unit tests
```

## State Management

The system uses SQLite (`data/newsletter.db`) to track:
- Previously sent article URLs (prevents duplicates)
- Last successful run timestamp
- Last send date (prevents double sends)

## Manual Substack Posting

If you prefer manual posting:

1. Run `python main.py --dry-run`
2. Open `output/draft.html` in a browser for preview
3. Copy from `output/draft.md` into Substack editor
4. Or copy/paste the HTML directly

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_url_normalization.py -v
```

## Troubleshooting

### No articles found
- Check if RSS feeds are accessible
- Verify feed URLs in `feeds.yaml`
- Run with `--dry-run` to see detailed logs

### Email not sending
- Verify SMTP credentials in `.env`
- Check spam folder
- For Gmail, enable "Less secure app access" or use App Password

### Duplicate emails
- Check `data/newsletter.db` state file
- Use `--force` flag to bypass send checks

## License

MIT License - See LICENSE file for details.
