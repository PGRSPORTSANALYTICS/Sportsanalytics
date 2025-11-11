import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
import os
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class DatabaseConnection:
    _connection_pool = None
    
    @classmethod
    def initialize_pool(cls, minconn=5, maxconn=20):
        """Initialize connection pool for concurrent access"""
        if cls._connection_pool is None:
            try:
                cls._connection_pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn,
                    maxconn,
                    os.environ.get('DATABASE_URL')
                )
                logger.info(f"✅ PostgreSQL connection pool initialized ({minconn}-{maxconn} connections)")
            except Exception as e:
                logger.error(f"❌ Failed to initialize connection pool: {e}")
                raise
    
    @classmethod
    @contextmanager
    def get_cursor(cls, dict_cursor=False):
        """Get a cursor from the connection pool (context manager for auto-cleanup)
        
        Args:
            dict_cursor: If True, returns dict rows. Default False for tuple compatibility.
        """
        if cls._connection_pool is None:
            cls.initialize_pool()
        
        conn = cls._connection_pool.getconn()
        cursor = None
        try:
            cursor_factory = RealDictCursor if dict_cursor else None
            cursor = conn.cursor(cursor_factory=cursor_factory)
            yield cursor
            conn.commit()
        except Exception as e:
            if conn and not conn.closed:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass  # Cursor already closed
            
            # Try to return connection to pool, handle errors gracefully
            try:
                if conn and not conn.closed:
                    cls._connection_pool.putconn(conn)
            except Exception as e:
                # Connection can't be returned - log and continue
                logger.warning(f"⚠️ Could not return connection to pool: {e}")
                # Don't raise - this prevents dashboard crashes
    
    @classmethod
    @contextmanager
    def get_connection(cls):
        """Get a connection from the pool (for transactions)"""
        if cls._connection_pool is None:
            cls.initialize_pool()
        
        conn = cls._connection_pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            if conn and not conn.closed:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            # Try to return connection to pool, handle errors gracefully
            try:
                if conn and not conn.closed:
                    cls._connection_pool.putconn(conn)
            except Exception as e:
                # Connection can't be returned - log and continue
                logger.warning(f"⚠️ Could not return connection to pool: {e}")
                # Don't raise - this prevents dashboard crashes
    
    @classmethod
    def close_pool(cls):
        """Close all connections in the pool"""
        if cls._connection_pool:
            cls._connection_pool.closeall()
            logger.info("🔌 PostgreSQL connection pool closed")

db = DatabaseConnection()
