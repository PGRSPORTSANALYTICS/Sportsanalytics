#!/usr/bin/env python3
"""
PostgreSQL Compatibility Layer for SQLite code
Provides a drop-in replacement for sqlite3.connect() that uses PostgreSQL instead
"""

from db_helper import db_helper
import re

class PostgreSQLCursor:
    """Cursor wrapper that uses db_helper for query execution"""
    def __init__(self):
        self._last_result = None
        
    def execute(self, query, params=()):
        """Execute query with parameter translation using db_helper"""
        # Translate SQLite placeholders to PostgreSQL (already done by db_helper)
        # But we need to handle SQLite-specific date functions
        pg_query = query
        
        # Translate SQLite date functions
        pg_query = re.sub(r"strftime\('%Y-%m',\s*match_date\)", "TO_CHAR(match_date, 'YYYY-MM')", pg_query)
        pg_query = re.sub(r"date\(settled_timestamp,\s*'unixepoch'\)", "TO_TIMESTAMP(settled_timestamp)::DATE", pg_query, flags=re.IGNORECASE)
        
        # Execute using db_helper which handles connection pooling
        self._last_result = db_helper.execute(pg_query, params, fetch='all')
        
    def fetchone(self):
        """Fetch one row from last result"""
        if self._last_result and len(self._last_result) > 0:
            row = self._last_result[0]
            self._last_result = self._last_result[1:]  # Remove first element
            return row
        return None
        
    def fetchall(self):
        """Fetch all rows from last result"""
        if self._last_result:
            result = self._last_result
            self._last_result = []
            return result
        return []
    
    def close(self):
        """Close cursor (no-op, db_helper manages connections)"""
        self._last_result = None

class PostgreSQLConnection:
    """Connection wrapper that mimics sqlite3.Connection"""
    def __init__(self, db_path=None):
        # Ignore db_path - we use PostgreSQL from environment
        pass
    
    def cursor(self):
        """Return a PostgreSQL cursor"""
        return PostgreSQLCursor()
    
    def commit(self):
        """Commit (handled automatically by db_helper)"""
        pass
    
    def close(self):
        """Close (handled automatically by db_helper)"""
        pass

def connect(database):
    """Drop-in replacement for sqlite3.connect()"""
    return PostgreSQLConnection(database)
