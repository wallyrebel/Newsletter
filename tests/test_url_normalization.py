"""
Tests for URL normalization functions.
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.helpers import normalize_url


class TestNormalizeUrl:
    """Tests for the normalize_url function."""
    
    def test_basic_url(self):
        """Test that a basic URL is returned unchanged."""
        url = "https://example.com/article/123"
        assert normalize_url(url) == "https://example.com/article/123"
    
    def test_removes_utm_source(self):
        """Test removal of utm_source parameter."""
        url = "https://example.com/article?utm_source=twitter"
        assert normalize_url(url) == "https://example.com/article"
    
    def test_removes_utm_medium(self):
        """Test removal of utm_medium parameter."""
        url = "https://example.com/article?utm_medium=social"
        assert normalize_url(url) == "https://example.com/article"
    
    def test_removes_utm_campaign(self):
        """Test removal of utm_campaign parameter."""
        url = "https://example.com/article?utm_campaign=summer2024"
        assert normalize_url(url) == "https://example.com/article"
    
    def test_removes_multiple_utm_params(self):
        """Test removal of multiple utm parameters."""
        url = "https://example.com/article?utm_source=twitter&utm_medium=social&utm_campaign=test"
        assert normalize_url(url) == "https://example.com/article"
    
    def test_removes_fbclid(self):
        """Test removal of Facebook click ID."""
        url = "https://example.com/article?fbclid=IwAR123abc"
        assert normalize_url(url) == "https://example.com/article"
    
    def test_removes_gclid(self):
        """Test removal of Google click ID."""
        url = "https://example.com/article?gclid=abc123"
        assert normalize_url(url) == "https://example.com/article"
    
    def test_preserves_non_tracking_params(self):
        """Test that non-tracking parameters are preserved."""
        url = "https://example.com/article?id=123&page=2"
        assert normalize_url(url) == "https://example.com/article?id=123&page=2"
    
    def test_mixed_params(self):
        """Test mix of tracking and non-tracking parameters."""
        url = "https://example.com/article?id=123&utm_source=twitter&page=2"
        result = normalize_url(url)
        assert "id=123" in result
        assert "page=2" in result
        assert "utm_source" not in result
    
    def test_removes_trailing_slash(self):
        """Test removal of trailing slash."""
        url = "https://example.com/article/"
        assert normalize_url(url) == "https://example.com/article"
    
    def test_preserves_root_slash(self):
        """Test that root path slash is preserved."""
        url = "https://example.com/"
        assert normalize_url(url) == "https://example.com/"
    
    def test_removes_fragment(self):
        """Test removal of URL fragment."""
        url = "https://example.com/article#section1"
        assert normalize_url(url) == "https://example.com/article"
    
    def test_lowercases_scheme(self):
        """Test that scheme is lowercased."""
        url = "HTTPS://example.com/article"
        assert normalize_url(url).startswith("https://")
    
    def test_lowercases_host(self):
        """Test that host is lowercased."""
        url = "https://EXAMPLE.COM/article"
        assert "example.com" in normalize_url(url)
    
    def test_empty_url(self):
        """Test handling of empty URL."""
        assert normalize_url("") == ""
    
    def test_none_url(self):
        """Test handling of None URL."""
        assert normalize_url(None) == ""
    
    def test_removes_ga_params(self):
        """Test removal of Google Analytics params."""
        url = "https://example.com/article?_ga=123&_gl=456"
        assert normalize_url(url) == "https://example.com/article"
    
    def test_removes_msclkid(self):
        """Test removal of Microsoft click ID."""
        url = "https://example.com/article?msclkid=abc123"
        assert normalize_url(url) == "https://example.com/article"
    
    def test_removes_mailchimp_params(self):
        """Test removal of Mailchimp parameters."""
        url = "https://example.com/article?mc_cid=123&mc_eid=456"
        assert normalize_url(url) == "https://example.com/article"
    
    def test_complex_url(self):
        """Test a complex URL with various parameters."""
        url = (
            "https://www.example.com/news/article-title/"
            "?id=123&utm_source=newsletter&utm_medium=email"
            "&fbclid=abc&ref=homepage#comments"
        )
        result = normalize_url(url)
        
        assert "example.com" in result
        assert "id=123" in result
        assert "utm_source" not in result
        assert "fbclid" not in result
        assert "#comments" not in result
        assert not result.endswith("/")
