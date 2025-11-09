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
        try:
            cursor_factory = RealDictCursor if dict_cursor else None
            cursor = conn.cursor(cursor_factory=cursor_factory)
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            cursor.close()
            cls._connection_pool.putconn(conn)
    
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
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            cls._connection_pool.putconn(conn)
    
    @classmethod
    def close_pool(cls):
        """Close all connections in the pool"""
        if cls._connection_pool:
            cls._connection_pool.closeall()
            logger.info("🔌 PostgreSQL connection pool closed")

db = DatabaseConnection()
