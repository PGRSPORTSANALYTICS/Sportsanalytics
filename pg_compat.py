#!/usr/bin/env python3
"""
PostgreSQL Compatibility Layer for SQLite code
Provides a drop-in replacement for sqlite3.connect() that uses PostgreSQL instead
"""

from db_connection import DatabaseConnection
import re

class PostgreSQLCursor:
    """Cursor wrapper that uses connection pool properly"""
    def __init__(self):
        self._results = []
        self._result_index = 0
        
    def execute(self, query, params=()):
        """Execute query with parameter translation"""
        # Translate SQLite placeholders to PostgreSQL
        pg_query = re.sub(r'\?', '%s', query)
        
        # Translate SQLite date functions
        # match_date is stored as TEXT (ISO format), need to cast to timestamp for TO_CHAR
        pg_query = re.sub(r"strftime\('%Y-%m',\s*match_date\)", "TO_CHAR(CAST(match_date AS TIMESTAMP), 'YYYY-MM')", pg_query)
        pg_query = re.sub(r"date\(settled_timestamp,\s*'unixepoch'\)", "TO_TIMESTAMP(settled_timestamp)::DATE", pg_query, flags=re.IGNORECASE)
        pg_query = re.sub(r"datetime\('now'\)", "NOW()", pg_query, flags=re.IGNORECASE)
        
        # Execute using connection pool properly
        with DatabaseConnection.get_cursor() as cursor:
            cursor.execute(pg_query, params)
            try:
                self._results = cursor.fetchall()
            except:
                self._results = []
        
        self._result_index = 0
        
    def fetchone(self):
        """Fetch one row from results"""
        if self._result_index < len(self._results):
            row = self._results[self._result_index]
            self._result_index += 1
            return row
        return None
        
    def fetchall(self):
        """Fetch all remaining rows"""
        remaining = self._results[self._result_index:]
        self._result_index = len(self._results)
        return remaining
    
    def close(self):
        """Close cursor"""
        self._results = []
        self._result_index = 0

class PostgreSQLConnection:
    """Connection wrapper that mimics sqlite3.Connection"""
    def __init__(self, db_path=None):
        pass
    
    def cursor(self):
        """Return a PostgreSQL cursor"""
        return PostgreSQLCursor()
    
    def commit(self):
        """Commit (handled automatically by connection pool)"""
        pass
    
    def close(self):
        """Close (no-op, connection pool manages this)"""
        pass

def connect(database):
    """Drop-in replacement for sqlite3.connect()"""
    return PostgreSQLConnection(database)
