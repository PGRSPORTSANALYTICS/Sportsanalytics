"""
Calendar Translation Layer
Converts between sandbox dates (2025) and real-world API dates (2024)
"""
from datetime import datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class CalendarTranslator:
    """
    Translates dates between sandbox environment (2025) and real-world APIs (2024)
    """
    
    def __init__(self, sandbox_year: int = 2025, real_year: int = 2024):
        """
        Initialize calendar translator
        
        Args:
            sandbox_year: Year in sandbox environment (default: 2025)
            real_year: Real-world year for API calls (default: 2024)
        """
        self.sandbox_year = sandbox_year
        self.real_year = real_year
        self.offset_years = sandbox_year - real_year
        logger.info(f"✅ Calendar translator initialized: {sandbox_year} → {real_year} ({self.offset_years} year offset)")
    
    def to_real_world(self, sandbox_date: str) -> str:
        """
        Convert sandbox date to real-world date
        
        Args:
            sandbox_date: Date string in sandbox environment (e.g., "2025-11-02")
        
        Returns:
            Real-world date string (e.g., "2024-11-02")
        """
        try:
            # Parse the sandbox date
            if 'T' in sandbox_date:
                # ISO format with time
                dt = datetime.fromisoformat(sandbox_date.replace('Z', '+00:00'))
                # Subtract the year offset
                real_dt = dt.replace(year=dt.year - self.offset_years)
                # Return in same format
                return real_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
            else:
                # Simple date format
                dt = datetime.strptime(sandbox_date, '%Y-%m-%d')
                real_dt = dt.replace(year=dt.year - self.offset_years)
                return real_dt.strftime('%Y-%m-%d')
        except Exception as e:
            logger.warning(f"⚠️ Error translating date {sandbox_date}: {e}")
            return sandbox_date
    
    def to_sandbox(self, real_date: str) -> str:
        """
        Convert real-world date to sandbox date
        
        Args:
            real_date: Real-world date string (e.g., "2024-11-02")
        
        Returns:
            Sandbox date string (e.g., "2025-11-02")
        """
        try:
            # Parse the real date
            if 'T' in real_date:
                # ISO format with time
                dt = datetime.fromisoformat(real_date.replace('Z', '+00:00'))
                # Add the year offset
                sandbox_dt = dt.replace(year=dt.year + self.offset_years)
                # Return in same format
                return sandbox_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
            else:
                # Simple date format
                dt = datetime.strptime(real_date, '%Y-%m-%d')
                sandbox_dt = dt.replace(year=dt.year + self.offset_years)
                return sandbox_dt.strftime('%Y-%m-%d')
        except Exception as e:
            logger.warning(f"⚠️ Error translating date {real_date}: {e}")
            return real_date
    
    def get_real_today(self) -> str:
        """
        Get today's date in real-world calendar
        
        Returns:
            Today's date in YYYY-MM-DD format (real-world year)
        """
        sandbox_today = datetime.now().strftime('%Y-%m-%d')
        return self.to_real_world(sandbox_today)
    
    def get_sandbox_today(self) -> str:
        """
        Get today's date in sandbox calendar
        
        Returns:
            Today's date in YYYY-MM-DD format (sandbox year)
        """
        return datetime.now().strftime('%Y-%m-%d')


# Global translator instance
translator = CalendarTranslator(sandbox_year=2025, real_year=2024)


if __name__ == "__main__":
    # Test the translator
    print("📅 Calendar Translator Test")
    print("=" * 50)
    
    test_dates = [
        "2025-11-02",
        "2025-11-02T14:00:00Z",
        "2025-11-08T15:00:00Z",
    ]
    
    for date in test_dates:
        real = translator.to_real_world(date)
        back = translator.to_sandbox(real)
        print(f"Sandbox: {date}")
        print(f"  → Real: {real}")
        print(f"  → Back: {back}")
        print()
    
    print(f"Today (sandbox): {translator.get_sandbox_today()}")
    print(f"Today (real):    {translator.get_real_today()}")
