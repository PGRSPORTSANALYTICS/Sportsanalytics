"""
Centralized datetime utilities for standardized UTC/epoch handling.

RULES:
1. All kickoff times stored as kickoff_utc (ISO 8601 with Z) and kickoff_epoch (int seconds)
2. All created_at timestamps are UTC
3. Backend logic uses UTC only - no local timezones
4. UI converts to Europe/Stockholm for display only
5. Validation rejects naive datetimes and null epochs

Example:
    Dec 26 20:00 Stockholm time (CET = UTC+1)
    -> kickoff_utc: "2025-12-26T19:00:00Z"
    -> kickoff_epoch: 1735239600
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Union
import calendar


STOCKHOLM_OFFSET_WINTER = 1  # CET = UTC+1 (late Oct - late Mar)
STOCKHOLM_OFFSET_SUMMER = 2  # CEST = UTC+2 (late Mar - late Oct)


def parse_to_utc(dt_input: Union[str, datetime, int, float, None]) -> Optional[datetime]:
    """
    Parse any datetime input to a timezone-aware UTC datetime.
    
    Accepts:
    - ISO 8601 string (with or without timezone)
    - Unix epoch (int or float)
    - datetime object (naive assumed UTC, aware converted to UTC)
    - None returns None
    
    Returns:
    - datetime object with tzinfo=timezone.utc
    - None if input is None or unparseable
    """
    if dt_input is None:
        return None
    
    if isinstance(dt_input, (int, float)):
        return datetime.fromtimestamp(dt_input, tz=timezone.utc)
    
    if isinstance(dt_input, datetime):
        if dt_input.tzinfo is None:
            return dt_input.replace(tzinfo=timezone.utc)
        return dt_input.astimezone(timezone.utc)
    
    if isinstance(dt_input, str):
        dt_str = dt_input.strip()
        if not dt_str:
            return None
        
        try:
            if 'Z' in dt_str:
                dt_str = dt_str.replace('Z', '+00:00')
            
            if '+' in dt_str or (dt_str.count('-') > 2):
                dt = datetime.fromisoformat(dt_str)
                return dt.astimezone(timezone.utc)
            else:
                if 'T' in dt_str:
                    dt = datetime.fromisoformat(dt_str)
                else:
                    dt = datetime.strptime(dt_str, '%Y-%m-%d')
                return dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass
        
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%d/%m/%Y %H:%M']:
            try:
                dt = datetime.strptime(dt_str, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        
        return None
    
    return None


def to_iso_utc(dt: Optional[datetime]) -> Optional[str]:
    """
    Convert datetime to ISO 8601 UTC string with Z suffix.
    
    Example: "2025-12-26T19:00:00Z"
    """
    if dt is None:
        return None
    
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def to_epoch(dt: Optional[datetime]) -> Optional[int]:
    """
    Convert datetime to Unix epoch (seconds since 1970-01-01 UTC).
    
    Returns integer, not float.
    """
    if dt is None:
        return None
    
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    return int(dt.timestamp())


def from_epoch(epoch: Optional[int]) -> Optional[datetime]:
    """
    Convert Unix epoch to timezone-aware UTC datetime.
    """
    if epoch is None:
        return None
    
    return datetime.fromtimestamp(epoch, tz=timezone.utc)


def now_utc() -> datetime:
    """
    Get current time as timezone-aware UTC datetime.
    """
    return datetime.now(timezone.utc)


def now_epoch() -> int:
    """
    Get current time as Unix epoch (seconds).
    """
    return int(datetime.now(timezone.utc).timestamp())


def normalize_kickoff(dt_input: Union[str, datetime, int, float, None]) -> Tuple[Optional[str], Optional[int]]:
    """
    Normalize any kickoff time input to (kickoff_utc, kickoff_epoch).
    
    This is the primary function for standardizing kickoff times.
    
    Args:
        dt_input: Any datetime representation
        
    Returns:
        Tuple of (kickoff_utc ISO string with Z, kickoff_epoch int)
        Both None if input is None or unparseable
        
    Example:
        >>> normalize_kickoff("2025-12-26T20:00:00+01:00")
        ("2025-12-26T19:00:00Z", 1735239600)
    """
    dt = parse_to_utc(dt_input)
    if dt is None:
        return None, None
    
    return to_iso_utc(dt), to_epoch(dt)


def validate_kickoff(kickoff_utc: Optional[str], kickoff_epoch: Optional[int]) -> Tuple[bool, str]:
    """
    Validate kickoff timestamps.
    
    Rules:
    - kickoff_utc must be a valid ISO string with timezone (ends with Z)
    - kickoff_epoch must be a non-null integer
    - Both must represent the same time (within 1 second tolerance)
    
    Returns:
        Tuple of (is_valid: bool, error_message: str)
    """
    if kickoff_utc is None:
        return False, "kickoff_utc is null"
    
    if kickoff_epoch is None:
        return False, "kickoff_epoch is null"
    
    if not isinstance(kickoff_epoch, int):
        return False, f"kickoff_epoch must be int, got {type(kickoff_epoch)}"
    
    if not kickoff_utc.endswith('Z'):
        return False, f"kickoff_utc must end with Z (UTC), got: {kickoff_utc}"
    
    dt_from_iso = parse_to_utc(kickoff_utc)
    dt_from_epoch = from_epoch(kickoff_epoch)
    
    if dt_from_iso is None:
        return False, f"kickoff_utc is not valid ISO format: {kickoff_utc}"
    
    diff = abs((dt_from_iso - dt_from_epoch).total_seconds())
    if diff > 1:
        return False, f"kickoff_utc and kickoff_epoch differ by {diff} seconds"
    
    return True, ""


def utc_to_stockholm_display(dt: Optional[datetime]) -> str:
    """
    Convert UTC datetime to Stockholm local time string for UI display.
    
    This is the ONLY function that should be used for timezone conversion.
    Backend logic must never use local timezones.
    
    Args:
        dt: UTC datetime (must be timezone-aware)
        
    Returns:
        Formatted string like "26 Dec 20:00" in Stockholm time
    """
    if dt is None:
        return "—"
    
    try:
        import pytz
        stockholm_tz = pytz.timezone('Europe/Stockholm')
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_stockholm = dt.astimezone(stockholm_tz)
        return dt_stockholm.strftime('%d %b %H:%M')
    except ImportError:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        offset = timedelta(hours=1)
        dt_local = dt + offset
        return dt_local.strftime('%d %b %H:%M')


def epoch_to_stockholm_display(epoch: Optional[int]) -> str:
    """
    Convert epoch to Stockholm local time string for UI display.
    """
    if epoch is None:
        return "—"
    
    dt = from_epoch(epoch)
    return utc_to_stockholm_display(dt)


def get_clv_capture_epoch(kickoff_epoch: int, minutes_before: int = 5) -> int:
    """
    Calculate the epoch time for CLV capture.
    
    CLV (Closing Line Value) should be captured at kickoff - N minutes.
    
    Args:
        kickoff_epoch: Match kickoff time as Unix epoch
        minutes_before: Minutes before kickoff to capture (default 5)
        
    Returns:
        Epoch time for CLV capture
    """
    return kickoff_epoch - (minutes_before * 60)


def demonstrate_conversion():
    """
    Print before/after examples for Dec 26 20:00 Stockholm time.
    """
    print("=" * 60)
    print("DATETIME STANDARDIZATION EXAMPLE")
    print("=" * 60)
    print()
    print("BEFORE (inconsistent):")
    print("  Input: '2025-12-26 20:00' (assumed Stockholm local time)")
    print("  Problem: Stored as-is without timezone info")
    print("  match_date: '2025-12-26 20:00:00' (naive, no TZ)")
    print("  kickoff_time: '20:00' (local, ambiguous)")
    print()
    
    import pytz
    stockholm_tz = pytz.timezone('Europe/Stockholm')
    local_dt = stockholm_tz.localize(datetime(2025, 12, 26, 20, 0, 0))
    utc_dt = local_dt.astimezone(timezone.utc)
    
    kickoff_utc, kickoff_epoch = normalize_kickoff(utc_dt)
    
    print("AFTER (standardized):")
    print(f"  Input: Stockholm time '2025-12-26 20:00:00+01:00' (CET)")
    print(f"  Converted to UTC: {utc_dt.isoformat()}")
    print()
    print("  Database storage:")
    print(f"    kickoff_utc:   '{kickoff_utc}'")
    print(f"    kickoff_epoch: {kickoff_epoch}")
    print(f"    created_at:    '{to_iso_utc(now_utc())}'")
    print()
    print("  UI Display (Europe/Stockholm):")
    print(f"    Kickoff: {utc_to_stockholm_display(utc_dt)}")
    print()
    print("  CLV Capture (5 min before kickoff):")
    clv_epoch = get_clv_capture_epoch(kickoff_epoch, 5)
    print(f"    clv_capture_epoch: {clv_epoch}")
    print(f"    clv_capture_time:  {epoch_to_stockholm_display(clv_epoch)} (Stockholm)")
    print()
    print("=" * 60)
    
    return {
        'stockholm_input': '2025-12-26 20:00:00 CET',
        'kickoff_utc': kickoff_utc,
        'kickoff_epoch': kickoff_epoch,
        'clv_capture_epoch': clv_epoch,
        'display_stockholm': utc_to_stockholm_display(utc_dt)
    }


if __name__ == '__main__':
    demonstrate_conversion()
