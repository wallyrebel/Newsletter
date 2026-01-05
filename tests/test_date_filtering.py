"""
Tests for date filtering functions.
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.helpers import parse_rss_date, is_within_hours


class TestParseRssDate:
    """Tests for the parse_rss_date function."""
    
    def test_rfc822_format(self):
        """Test parsing RFC 822 format (common in RSS)."""
        date_str = "Mon, 05 Jan 2026 12:00:00 GMT"
        result = parse_rss_date(date_str)
        
        assert result is not None
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 5
        assert result.hour == 12
    
    def test_iso8601_format(self):
        """Test parsing ISO 8601 format."""
        date_str = "2026-01-05T12:00:00Z"
        result = parse_rss_date(date_str)
        
        assert result is not None
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 5
    
    def test_iso8601_with_offset(self):
        """Test parsing ISO 8601 with timezone offset."""
        date_str = "2026-01-05T12:00:00-06:00"
        result = parse_rss_date(date_str)
        
        assert result is not None
        assert result.year == 2026
        assert result.tzinfo is not None
    
    def test_simple_date(self):
        """Test parsing simple date format."""
        date_str = "January 5, 2026"
        result = parse_rss_date(date_str)
        
        assert result is not None
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 5
    
    def test_empty_string(self):
        """Test handling of empty string."""
        assert parse_rss_date("") is None
    
    def test_none_input(self):
        """Test handling of None input."""
        assert parse_rss_date(None) is None
    
    def test_invalid_date(self):
        """Test handling of invalid date string."""
        assert parse_rss_date("not a date") is None
    
    def test_adds_default_timezone(self):
        """Test that default timezone is added to naive dates."""
        date_str = "2026-01-05 12:00:00"
        default_tz = ZoneInfo("America/Chicago")
        result = parse_rss_date(date_str, default_tz)
        
        assert result is not None
        assert result.tzinfo is not None
    
    def test_various_rss_formats(self):
        """Test various real-world RSS date formats."""
        formats = [
            "Mon, 05 Jan 2026 12:00:00 +0000",
            "Mon, 05 Jan 2026 12:00:00 CST",
            "2026-01-05T12:00:00.000Z",
            "05 Jan 2026 12:00:00 GMT",
        ]
        
        for date_str in formats:
            result = parse_rss_date(date_str)
            assert result is not None, f"Failed to parse: {date_str}"
            assert result.year == 2026


class TestIsWithinHours:
    """Tests for the is_within_hours function."""
    
    def test_recent_datetime(self):
        """Test that a recent datetime passes the check."""
        now = datetime.now(ZoneInfo("UTC"))
        recent = now - timedelta(hours=1)
        
        assert is_within_hours(recent, hours=24) is True
    
    def test_old_datetime(self):
        """Test that an old datetime fails the check."""
        now = datetime.now(ZoneInfo("UTC"))
        old = now - timedelta(hours=48)
        
        assert is_within_hours(old, hours=24) is False
    
    def test_edge_case_exactly_24_hours(self):
        """Test datetime exactly at the 24-hour boundary."""
        now = datetime.now(ZoneInfo("UTC"))
        exactly_24 = now - timedelta(hours=24)
        
        # Should be exactly at the cutoff (inclusive)
        assert is_within_hours(exactly_24, hours=24) is True
    
    def test_just_over_24_hours(self):
        """Test datetime just over 24 hours ago."""
        now = datetime.now(ZoneInfo("UTC"))
        just_over = now - timedelta(hours=24, minutes=1)
        
        assert is_within_hours(just_over, hours=24) is False
    
    def test_none_datetime(self):
        """Test handling of None datetime."""
        assert is_within_hours(None, hours=24) is False
    
    def test_different_hour_values(self):
        """Test with different hour thresholds."""
        now = datetime.now(ZoneInfo("UTC"))
        six_hours_ago = now - timedelta(hours=6)
        
        assert is_within_hours(six_hours_ago, hours=12) is True
        assert is_within_hours(six_hours_ago, hours=4) is False
    
    def test_different_timezone(self):
        """Test with datetime in different timezone."""
        chicago_tz = ZoneInfo("America/Chicago")
        now_chicago = datetime.now(chicago_tz)
        recent_chicago = now_chicago - timedelta(hours=1)
        
        assert is_within_hours(recent_chicago, hours=24) is True
    
    def test_future_datetime(self):
        """Test that future datetime passes the check."""
        now = datetime.now(ZoneInfo("UTC"))
        future = now + timedelta(hours=1)
        
        assert is_within_hours(future, hours=24) is True
