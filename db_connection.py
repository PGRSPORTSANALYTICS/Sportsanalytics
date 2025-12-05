import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
import os
import logging
from contextlib import contextmanager
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

logger = logging.getLogger(__name__)

def clean_database_url(url):
    """Clean DATABASE_URL to fix SSL mode issues across different environments"""
    if not url:
        return url
    
    try:
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        
        if 'sslmode' in query_params:
            sslmode_val = query_params['sslmode'][0] if query_params['sslmode'] else 'require'
            sslmode_val = sslmode_val.strip('"').strip("'")
            query_params['sslmode'] = [sslmode_val]
        
        new_query = urlencode({k: v[0] for k, v in query_params.items()})
        cleaned = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment
        ))
        return cleaned
    except Exception as e:
        logger.warning(f"Could not parse DATABASE_URL, using as-is: {e}")
        return url

class DatabaseConnection:
    _connection_pool = None
    
    @classmethod
    def initialize_pool(cls, minconn=5, maxconn=20):
        """Initialize connection pool for concurrent access with TCP keepalives"""
        if cls._connection_pool is None:
            try:
                db_url = clean_database_url(os.environ.get('DATABASE_URL'))
                cls._connection_pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn,
                    maxconn,
                    db_url,
                    keepalives=1,           # Enable TCP keepalives
                    keepalives_idle=30,     # Start keepalives after 30s idle
                    keepalives_interval=10, # Keepalive interval 10s
                    keepalives_count=3      # Max 3 keepalive probes
                )
                logger.info(f"✅ PostgreSQL connection pool initialized ({minconn}-{maxconn} connections, keepalives enabled)")
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
        connection_is_bad = False
        
        try:
            cursor_factory = RealDictCursor if dict_cursor else None
            cursor = conn.cursor(cursor_factory=cursor_factory)
            yield cursor
            conn.commit()
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            # Connection dropped (SSL error, timeout, etc.) - mark for disposal
            connection_is_bad = True
            if conn and not conn.closed:
                conn.rollback()
            logger.warning(f"⚠️ Connection error, will discard: {e}")
            raise
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
            
            # Return connection to pool (or discard if bad)
            if conn:
                try:
                    if connection_is_bad:
                        # Close broken connection manually, don't return to pool
                        try:
                            conn.close()
                            logger.info("🔄 Closed broken connection")
                        except Exception:
                            pass
                    elif not conn.closed:
                        # Return healthy connection to pool
                        cls._connection_pool.putconn(conn)
                except Exception as e:
                    # Log but don't crash
                    logger.warning(f"⚠️ Could not return connection to pool: {e}")
    
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
    def reset_pool(cls):
        """Reset connection pool by closing and reinitializing (for stale connections)"""
        if cls._connection_pool:
            try:
                cls._connection_pool.closeall()
                cls._connection_pool = None
                logger.info("🔄 PostgreSQL connection pool reset")
            except Exception as e:
                logger.error(f"❌ Error resetting connection pool: {e}")
                cls._connection_pool = None
    
    @classmethod
    def close_pool(cls):
        """Close all connections in the pool"""
        if cls._connection_pool:
            cls._connection_pool.closeall()
            logger.info("🔌 PostgreSQL connection pool closed")

db = DatabaseConnection()


def get_db_conn():
    """
    Backwards-compatible helper for scripts (e.g. settlement.py)
    that expect a plain psycopg2 connection object.
    Uses the shared DatabaseConnection pool.
    """
    if DatabaseConnection._connection_pool is None:
        DatabaseConnection.initialize_pool()

    return DatabaseConnection._connection_pool.getconn()
