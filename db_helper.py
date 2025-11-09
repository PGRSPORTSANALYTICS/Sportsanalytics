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
    def execute(query, params=None, fetch=None):
        """Execute a query using connection pool with automatic SQL translation
        
        Args:
            query: SQL query (SQLite or PostgreSQL syntax)
            params: Query parameters (tuple or list)
            fetch: 'one', 'all', or None for execute only
        
        Returns:
            Query result if fetch is specified, None otherwise
        """
        translated_query = DatabaseHelper.translate_sql(query)
        
        with DatabaseConnection.get_cursor() as cursor:
            cursor.execute(translated_query, params or ())
            
            if fetch == 'one':
                return cursor.fetchone()
            elif fetch == 'all':
                return cursor.fetchall()
            return None
    
    @staticmethod
    def execute_many(query, params_list):
        """Execute query multiple times with different parameters using connection pool"""
        translated_query = DatabaseHelper.translate_sql(query)
        
        with DatabaseConnection.get_cursor() as cursor:
            cursor.executemany(translated_query, params_list)

db_helper = DatabaseHelper()
