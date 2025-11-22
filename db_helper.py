import re
import os
import logging
from db_connection import DatabaseConnection

logger = logging.getLogger(__name__)

class DatabaseHelper:
    """Compatibility layer for migrating from SQLite to PostgreSQL with connection pooling"""
    
    @staticmethod
    def translate_sql(sql_query):
        """Translate SQLite SQL to PostgreSQL SQL"""
        query = sql_query
        
        query = re.sub(r'\?', '%s', query)
        
        query = re.sub(r"datetime\('now'\)", "NOW()", query, flags=re.IGNORECASE)
        query = re.sub(r"strftime\('%s',\s*'now'\)", "EXTRACT(EPOCH FROM NOW())::BIGINT", query, flags=re.IGNORECASE)
        query = re.sub(r"DATE\('now'\)", "CURRENT_DATE", query, flags=re.IGNORECASE)
        
        query = re.sub(r'AUTOINCREMENT', 'SERIAL', query, flags=re.IGNORECASE)
        
        return query
    
    @staticmethod
    def execute(query, params=None, fetch=None, max_retries=3):
        """Execute a query using connection pool with automatic SQL translation and retry logic
        
        Args:
            query: SQL query (SQLite or PostgreSQL syntax)
            params: Query parameters (tuple or list)
            fetch: 'one', 'all', or None for execute only
            max_retries: Maximum retry attempts on connection errors
        
        Returns:
            Query result if fetch is specified, None otherwise
        """
        import psycopg2
        import time
        
        translated_query = DatabaseHelper.translate_sql(query)
        
        for attempt in range(max_retries):
            try:
                with DatabaseConnection.get_cursor() as cursor:
                    cursor.execute(translated_query, params or ())
                    
                    if fetch == 'one':
                        return cursor.fetchone()
                    elif fetch == 'all':
                        return cursor.fetchall()
                    return None
                    
            except (psycopg2.OperationalError, psycopg2.InterfaceError, psycopg2.DatabaseError) as e:
                # Connection dropped - retry (get_cursor will discard the bad connection)
                error_msg = str(e).lower()
                if 'ssl' in error_msg or 'closed' in error_msg or 'terminated' in error_msg:
                    # SSL/connection issue - reset pool
                    logger.warning(f"Connection dropped (SSL/termination), resetting pool: {e}")
                    DatabaseConnection.reset_pool()
                
                if attempt < max_retries - 1:
                    logger.warning(f"Database connection error (attempt {attempt + 1}/{max_retries}): {e}")
                    time.sleep(0.5 * (attempt + 1))  # Exponential backoff
                    continue
                else:
                    logger.error(f"Database connection failed after {max_retries} attempts: {e}")
                    raise
            except Exception as e:
                logger.error(f"Database error: {e}")
                raise
    
    @staticmethod
    def execute_many(query, params_list):
        """Execute query multiple times with different parameters using connection pool"""
        translated_query = DatabaseHelper.translate_sql(query)
        
        with DatabaseConnection.get_cursor() as cursor:
            cursor.executemany(translated_query, params_list)

db_helper = DatabaseHelper()
