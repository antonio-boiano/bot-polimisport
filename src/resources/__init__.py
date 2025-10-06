"""
Resources Package - Website interaction layer
- Session management and browser control
- Web scraping and data extraction
"""

from .session_manager import SessionManager
from .web_scraper import WebScraper, parse_weekly_pattern_from_html

__all__ = ['SessionManager', 'WebScraper', 'parse_weekly_pattern_from_html']
