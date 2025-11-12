"""
Persistent API Cache Manager
Shares cache across all workflows via PostgreSQL to prevent quota exhaustion
"""

import json
import logging
from datetime import datetime, timedelta, date
from typing import Optional, Dict, Any
from db_helper import db_helper

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class APICacheManager:
    """Manages persistent API cache and request quota across all workflows"""
    
    def __init__(self, api_name: str, quota_limit: int):
        """
        Initialize cache manager for a specific API
        
        Args:
            api_name: Name of API (e.g., 'api_football', 'odds_api')
            quota_limit: Daily request limit
        """
        self.api_name = api_name
        self.quota_limit = quota_limit
        self.cache_table = f"{api_name}_cache"
        
        self._ensure_quota_initialized()
    
    def _ensure_quota_initialized(self):
        """Ensure this API has a quota counter entry"""
        db_helper.execute('''
            INSERT INTO api_request_counter (api_name, request_count, quota_limit)
            VALUES (%s, 0, %s)
            ON CONFLICT (api_name) DO NOTHING
        ''', (self.api_name, self.quota_limit), fetch=None)
    
    def _reset_if_new_day(self):
        """Reset quota counter if it's a new day"""
        result = db_helper.execute('''
            SELECT last_reset_date FROM api_request_counter
            WHERE api_name = %s
        ''', (self.api_name,), fetch='one')
        
        if result:
            last_reset = result[0]
            today = date.today()
            
            if last_reset != today:
                logger.info(f"🔄 New day detected - resetting {self.api_name} quota counter")
                db_helper.execute('''
                    UPDATE api_request_counter
                    SET request_count = 0, last_reset_date = CURRENT_DATE
                    WHERE api_name = %s
                ''', (self.api_name,), fetch=None)
    
    def check_quota_available(self) -> bool:
        """
        Check if we have quota available for another request
        
        Returns:
            bool: True if quota available, False if exhausted
        """
        self._reset_if_new_day()
        
        result = db_helper.execute('''
            SELECT request_count, quota_limit FROM api_request_counter
            WHERE api_name = %s
        ''', (self.api_name,), fetch='one')
        
        if not result:
            return True
        
        request_count, quota_limit = result
        return request_count < quota_limit
    
    def increment_request_count(self):
        """Increment the request counter after making an API call"""
        db_helper.execute('''
            UPDATE api_request_counter
            SET request_count = request_count + 1,
                last_request_time = CURRENT_TIMESTAMP
            WHERE api_name = %s
        ''', (self.api_name,), fetch=None)
        
        result = db_helper.execute('''
            SELECT request_count, quota_limit FROM api_request_counter
            WHERE api_name = %s
        ''', (self.api_name,), fetch='one')
        
        if result:
            request_count, quota_limit = result
            if request_count % 10 == 0:
                logger.info(f"📊 {self.api_name}: {request_count}/{quota_limit} requests today")
    
    def get_cached_response(self, cache_key: str, endpoint: str) -> Optional[Dict]:
        """
        Get cached API response if available and not expired
        
        Args:
            cache_key: Unique cache key for this request
            endpoint: API endpoint (for logging)
            
        Returns:
            Cached response data or None if not found/expired
        """
        # Clean expired cache entries first
        db_helper.execute(f'''
            DELETE FROM {self.cache_table}
            WHERE expires_at < CURRENT_TIMESTAMP
        ''', fetch=None)
        
        # Try to get cached response
        result = db_helper.execute(f'''
            SELECT response_data, expires_at FROM {self.cache_table}
            WHERE cache_key = %s
        ''', (cache_key,), fetch='one')
        
        if result:
            response_data, expires_at = result
            
            # Check if still valid
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at)
            
            if datetime.now() < expires_at:
                # Update hit count
                db_helper.execute(f'''
                    UPDATE {self.cache_table}
                    SET hit_count = hit_count + 1
                    WHERE cache_key = %s
                ''', (cache_key,), fetch=None)
                
                logger.info(f"📦 CACHE HIT: {endpoint} ({cache_key[:30]}...)")
                return json.loads(response_data)
        
        return None
    
    def cache_response(self, cache_key: str, endpoint: str, response_data: Any, ttl_hours: int = 24):
        """
        Cache an API response
        
        Args:
            cache_key: Unique cache key
            endpoint: API endpoint
            response_data: Response to cache (will be JSON serialized)
            ttl_hours: Time to live in hours (default 24)
        """
        # ⚠️ VALIDATION: Don't cache empty or None responses
        if response_data is None or (isinstance(response_data, (list, dict)) and len(response_data) == 0):
            logger.warning(f"⚠️ SKIPPED CACHING: Empty response for {endpoint} ({cache_key[:30]}...)")
            return
        
        expires_at = datetime.now() + timedelta(hours=ttl_hours)
        
        db_helper.execute(f'''
            INSERT INTO {self.cache_table} (cache_key, response_data, api_endpoint, expires_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (cache_key) DO UPDATE SET
                response_data = EXCLUDED.response_data,
                expires_at = EXCLUDED.expires_at,
                hit_count = 0
        ''', (cache_key, json.dumps(response_data), endpoint, expires_at), fetch=None)
        
        logger.info(f"💾 CACHED: {endpoint} ({cache_key[:30]}...) expires in {ttl_hours}h")
    
    def get_quota_stats(self) -> Dict:
        """Get current quota usage statistics"""
        result = db_helper.execute('''
            SELECT request_count, quota_limit, last_reset_date, last_request_time
            FROM api_request_counter
            WHERE api_name = %s
        ''', (self.api_name,), fetch='one')
        
        if result:
            request_count, quota_limit, last_reset, last_request = result
            return {
                'api_name': self.api_name,
                'request_count': request_count,
                'quota_limit': quota_limit,
                'remaining': quota_limit - request_count,
                'last_reset_date': str(last_reset),
                'last_request_time': str(last_request) if last_request else None
            }
        return {}
