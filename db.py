"""
Database module for Training Catalogue Manager.
Uses PostgreSQL for metadata overlay storage.

IMPORTANT: SharePoint is the source of truth for content.
This DB stores only metadata overlay (decisions, notes, counts).

PRODUCTION: Requires DATABASE_URL environment variable.
"""

import os
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool
import time
import logging
import threading

# Configure logging for instrumentation (server-side only)
_logger = logging.getLogger(__name__)
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter('%(asctime)s [%(name)s] %(message)s'))
    _logger.addHandler(_handler)

# =============================================================================
# CONNECTION POOL (lazy-initialized singleton)
# =============================================================================
_pool: Optional[ThreadedConnectionPool] = None
_pool_lock = threading.Lock()
_init_db_done = False
_init_db_lock = threading.Lock()

# Instrumentation counters (thread-safe)
_stats_lock = threading.Lock()
_pool_stats = {
    "borrows": 0,
    "returns": 0,
    "exhaustions": 0,
    "discards": 0,
    "queries_this_rerun": 0,
}

# =============================================================================
# TTL CACHE (for reference data)
# =============================================================================
_cache: Dict[str, Any] = {}
_cache_expiry: Dict[str, float] = {}
_cache_lock = threading.Lock()
_CACHE_MAX_SIZE = 100  # Prevent unbounded growth


def _make_cache_key(func_name: str, args: tuple, kwargs: dict) -> str:
    """Create a safe, hashable cache key from function call."""
    # Convert args/kwargs to string representation (safe for unhashables)
    try:
        key_parts = [func_name, repr(args), repr(sorted(kwargs.items()))]
    except Exception:
        # Fallback if repr fails
        key_parts = [func_name, str(id(args)), str(id(kwargs))]
    return "|".join(key_parts)


def _purge_expired_cache():
    """Remove expired entries from cache. Called periodically."""
    now = time.time()
    expired_keys = [k for k, exp in _cache_expiry.items() if exp <= now]
    for k in expired_keys:
        _cache.pop(k, None)
        _cache_expiry.pop(k, None)
    if expired_keys:
        _logger.debug(f"Purged {len(expired_keys)} expired cache entries")


def clear_cache():
    """Clear all cached data. Call after Sync or data-changing operations."""
    with _cache_lock:
        _cache.clear()
        _cache_expiry.clear()
    _logger.info("Reference data cache cleared")


def cached(ttl_seconds: int = 30):
    """
    TTL cache decorator for read-only DB functions.
    - Safe for unhashable args
    - Clears expired entries on each call
    - Bounded size
    - Tracks hits/misses
    """
    import functools
    
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = _make_cache_key(func.__name__, args, kwargs)
            now = time.time()
            
            with _cache_lock:
                # Purge expired entries occasionally
                if len(_cache) > 10:
                    _purge_expired_cache()
                
                # Check cache hit
                if key in _cache and _cache_expiry.get(key, 0) > now:
                    with _stats_lock:
                        _pool_stats["cache_hits"] = _pool_stats.get("cache_hits", 0) + 1
                    return _cache[key]
                
                # Prevent unbounded growth
                if len(_cache) >= _CACHE_MAX_SIZE:
                    _purge_expired_cache()
                    if len(_cache) >= _CACHE_MAX_SIZE:
                        # Force clear oldest entries
                        oldest = sorted(_cache_expiry.items(), key=lambda x: x[1])[:10]
                        for k, _ in oldest:
                            _cache.pop(k, None)
                            _cache_expiry.pop(k, None)
            
            # Cache miss - execute function (outside lock)
            with _stats_lock:
                _pool_stats["cache_misses"] = _pool_stats.get("cache_misses", 0) + 1
            result = func(*args, **kwargs)
            
            with _cache_lock:
                _cache[key] = result
                _cache_expiry[key] = now + ttl_seconds
            
            return result
        return wrapper
    return decorator


def _get_pool() -> ThreadedConnectionPool:
    """
    Lazy-initialize and return the connection pool.
    Called on first DB access, not on import.
    """
    global _pool
    if _pool is not None:
        return _pool
    
    with _pool_lock:
        # Double-check inside lock
        if _pool is not None:
            return _pool
        
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL not set. Cannot proceed.")
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        
        _pool = ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            dsn=url,
            cursor_factory=RealDictCursor
        )
        _logger.info("Connection pool initialized (min=2, max=10)")
        return _pool


def get_connection():
    """
    Get a connection from the pool with 2s max wait on exhaustion.
    Returns a pooled connection. Caller MUST return via return_connection().
    """
    pool = _get_pool()
    
    # Explicit 2s wait with retries (pool.getconn can block or raise)
    start = time.time()
    max_wait = 2.0
    attempt = 0
    
    while True:
        try:
            conn = pool.getconn()
            with _stats_lock:
                _pool_stats["borrows"] += 1
            return conn
        except psycopg2.pool.PoolError:
            elapsed = time.time() - start
            if elapsed >= max_wait:
                with _stats_lock:
                    _pool_stats["exhaustions"] += 1
                _logger.warning(f"Pool exhaustion after {elapsed:.2f}s")
                raise RuntimeError("DB pool exhausted. Please retry.")
            # Brief sleep before retry
            time.sleep(0.1)
            attempt += 1


def return_connection(conn, healthy: bool = True):
    """
    Return a connection to the pool.
    If unhealthy (connection error occurred), discard it.
    """
    pool = _get_pool()
    try:
        if healthy:
            pool.putconn(conn)
            with _stats_lock:
                _pool_stats["returns"] += 1
        else:
            # Discard poisoned connection
            pool.putconn(conn, close=True)
            with _stats_lock:
                _pool_stats["discards"] += 1
            _logger.info("Discarded unhealthy connection")
    except Exception as e:
        _logger.warning(f"Error returning connection: {e}")


def get_pool_stats() -> Dict[str, int]:
    """Return current pool instrumentation stats."""
    with _stats_lock:
        return dict(_pool_stats)


def reset_query_counter():
    """Reset the per-request counters. Call at start of each request."""
    with _stats_lock:
        _pool_stats["queries_this_rerun"] = 0
        _pool_stats["total_db_time_ms"] = 0
        _pool_stats["cache_hits"] = 0
        _pool_stats["cache_misses"] = 0
        _pool_stats["borrows"] = 0


def log_rerun_stats(total_ms: float = 0):
    """Log stats for this rerun. Call at end of page render."""
    with _stats_lock:
        db_time = _pool_stats.get('total_db_time_ms', 0)
        cache_hits = _pool_stats.get('cache_hits', 0)
        cache_misses = _pool_stats.get('cache_misses', 0)
        _logger.info(
            f"RERUN STATS: total={total_ms:.0f}ms, queries={_pool_stats['queries_this_rerun']}, "
            f"db_time={db_time:.0f}ms, cache_hits={cache_hits}, cache_misses={cache_misses}, "
            f"pool_borrows={_pool_stats['borrows']}"
        )


from contextlib import contextmanager

@contextmanager
def transaction():
    """
    Transaction context manager for batched operations.
    Commits once on success, rollbacks on exception.
    Only this context manager owns the connection lifecycle.
    """
    conn = get_connection()
    healthy = True
    try:
        yield conn
        conn.commit()
    except Exception:
        healthy = False
        conn.rollback()
        raise
    finally:
        return_connection(conn, healthy=healthy)


def adapt_query(sql: str) -> str:
    """
    Convert SQLite-style '?' placeholders to psycopg2 '%s' placeholders,
    but ONLY when the '?' is outside of:
      - single-quoted strings: '...'
      - double-quoted identifiers: "..."
      - line comments: -- ...
      - block comments: /* ... */
    """
    if not sql:
        return sql

    out = []
    i = 0
    n = len(sql)

    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False

    while i < n:
        ch = sql[i]

        # End line comment
        if in_line_comment:
            out.append(ch)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        # End block comment
        if in_block_comment:
            out.append(ch)
            if ch == "*" and i + 1 < n and sql[i + 1] == "/":
                out.append("/")
                i += 2
                in_block_comment = False
            else:
                i += 1
            continue

        # Start comments (only if not in quotes)
        if not in_single and not in_double:
            if ch == "-" and i + 1 < n and sql[i + 1] == "-":
                out.append(ch)
                out.append("-")
                i += 2
                in_line_comment = True
                continue
            if ch == "/" and i + 1 < n and sql[i + 1] == "*":
                out.append(ch)
                out.append("*")
                i += 2
                in_block_comment = True
                continue

        # Handle quotes
        if ch == "'" and not in_double:
            out.append(ch)
            if in_single:
                if i + 1 < n and sql[i + 1] == "'":
                    out.append("'")
                    i += 2
                    continue
                in_single = False
            else:
                in_single = True
            i += 1
            continue

        if ch == '"' and not in_single:
            out.append(ch)
            if in_double:
                if i + 1 < n and sql[i + 1] == '"':
                    out.append('"')
                    i += 2
                    continue
                in_double = False
            else:
                in_double = True
            i += 1
            continue

        # Replace placeholder only when not in quotes/comments
        if ch == "?" and not in_single and not in_double:
            out.append("%s")
            i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def is_write(sql: str) -> bool:
    """Check if SQL is a write operation. Handles CTE (WITH) queries."""
    if not sql or not sql.strip():
        return False
    s = sql.lstrip()
    token = s.split(None, 1)[0].upper()

    if token == "WITH":
        # CTE query - check for write keywords in body
        upper = s.upper()
        return any(k in upper for k in (
            " INSERT ", " UPDATE ", " DELETE ", " MERGE ",
            " CREATE ", " ALTER ", " DROP ", " TRUNCATE "
        ))
    return token in {
        "INSERT", "UPDATE", "DELETE", "CREATE",
        "ALTER", "DROP", "TRUNCATE", "MERGE"
    }


def execute(sql: str, params=None, *, fetch="none", conn=None):
    """
    Central DB executor using connection pool.
    - fetch: "none" | "one" | "all"
    - Commits only on writes (when caller does not own connection)
    - Returns connection to pool only when caller does not own it
    - Discards connection on connection-level errors
    
    If conn is provided, caller owns the transaction:
    - No autocommit (caller commits via transaction context manager)
    - No pool return (caller returns via transaction context manager)
    """
    query_start = time.time()
    owns_conn = conn is None
    if owns_conn:
        conn = get_connection()
    healthy = True
    row_count = 0
    try:
        with conn.cursor() as cursor:
            cursor.execute(adapt_query(sql), params or ())
            if fetch == "one":
                result = cursor.fetchone()
                row_count = 1 if result else 0
            elif fetch == "all":
                result = cursor.fetchall()
                row_count = len(result) if result else 0
            else:
                result = None
            if is_write(sql) and owns_conn:
                conn.commit()
            
            # Timing and counters
            elapsed_ms = (time.time() - query_start) * 1000
            with _stats_lock:
                _pool_stats["queries_this_rerun"] += 1
                _pool_stats["total_db_time_ms"] = _pool_stats.get("total_db_time_ms", 0) + elapsed_ms
            
            # Log slow queries (>100ms)
            if elapsed_ms > 100:
                query_preview = sql.strip()[:80].replace('\n', ' ')
                _logger.warning(f"SLOW QUERY ({elapsed_ms:.0f}ms, {row_count} rows): {query_preview}...")
            
            return result
    except psycopg2.OperationalError as e:
        # Connection-level error - mark as unhealthy
        healthy = False
        _logger.error(f"Connection error: {e}")
        raise
    except psycopg2.InterfaceError as e:
        # Connection-level error - mark as unhealthy
        healthy = False
        _logger.error(f"Interface error: {e}")
        raise
    finally:
        if owns_conn:
            return_connection(conn, healthy=healthy)


def make_resource_key(
    drive_item_id: str = None,
    relative_path: str = None,
    resource_type: str = None
) -> str:
    """
    Generate deterministic resource key.
    Uses SharePoint ID when available, otherwise hash of path|type.
    """
    if drive_item_id:
        return drive_item_id
    raw = f"{relative_path.lower()}|{resource_type}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def init_db() -> None:
    """
    Initialize database schema (PostgreSQL).
    Creates tables if missing, runs migrations.
    Does NOT import content (that's explicit via Tools page).
    
    Guarded: runs only once per server process.
    """
    global _init_db_done
    
    # Guard: run only once per process
    if _init_db_done:
        return
    
    with _init_db_lock:
        # Double-check inside lock
        if _init_db_done:
            return
        
        _logger.info("init_db() starting (first run this process)")
        
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                # Resources table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS resources (
                        resource_key TEXT PRIMARY KEY,
                        drive_item_id TEXT,
                        
                        relative_path TEXT NOT NULL,
                        bucket TEXT,
                        primary_department TEXT,
                        sub_department TEXT,
                        training_type TEXT,
                        
                        resource_type TEXT NOT NULL,
                        display_name TEXT,
                        web_url TEXT,
                        
                        resource_count INTEGER DEFAULT 1,
                        valid_link_count INTEGER DEFAULT 0,
                        contents_count INTEGER DEFAULT 0,
                        is_placeholder INTEGER DEFAULT 0,
                        
                        scrub_status TEXT DEFAULT 'not_reviewed',
                        scrub_notes TEXT,
                        scrub_owner TEXT,
                        scrub_updated TEXT,
                        
                        invest_decision TEXT,
                        invest_owner TEXT,
                        invest_effort TEXT,
                        invest_notes TEXT,
                        invest_updated TEXT,
                        
                        first_seen TEXT,
                        last_seen TEXT,
                        source TEXT,
                        is_archived INTEGER DEFAULT 0,
                        audience TEXT,
                        approved_for_investment INTEGER DEFAULT 0,
                        scrub_reasons TEXT,
                        sales_stage TEXT
                    )
                """)
                
                # Indexes
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_resources_path 
                    ON resources(relative_path)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_resources_bucket 
                    ON resources(bucket)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_resources_dept 
                    ON resources(primary_department)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_resources_subdept 
                    ON resources(sub_department)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_resources_scrub_status 
                    ON resources(scrub_status)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_resources_active 
                    ON resources(is_archived, is_placeholder)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_resources_approved 
                    ON resources(approved_for_investment)
                """)
                
                # Legacy catalog_items table (for backwards compatibility)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS catalog_items (
                        item_id TEXT PRIMARY KEY,
                        department TEXT NOT NULL,
                        bucket TEXT NOT NULL,
                        functional_area TEXT NOT NULL,
                        training_type TEXT NOT NULL,
                        item_type TEXT NOT NULL,
                        item_identity TEXT NOT NULL UNIQUE,
                        display_name TEXT,
                        size INTEGER,
                        modified TEXT,
                        first_seen TEXT NOT NULL,
                        last_seen TEXT NOT NULL,
                        source TEXT NOT NULL,
                        source_type TEXT DEFAULT 'sharepoint',
                        scrub_status TEXT DEFAULT 'not_reviewed',
                        scrub_notes TEXT,
                        scrub_owner TEXT,
                        scrub_updated TEXT,
                        invest_decision TEXT,
                        invest_owner TEXT,
                        invest_effort TEXT,
                        invest_notes TEXT,
                        invest_updated TEXT
                    )
                """)
                
                # Scan snapshots table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS scan_snapshots (
                        snapshot_id SERIAL PRIMARY KEY,
                        timestamp TEXT NOT NULL,
                        total_items INTEGER NOT NULL,
                        total_files INTEGER NOT NULL,
                        total_links INTEGER NOT NULL,
                        areas_with_training INTEGER NOT NULL,
                        areas_without_training INTEGER NOT NULL,
                        coverage_pct REAL NOT NULL,
                        source TEXT NOT NULL
                    )
                """)
                
                # Sync runs table for CFO metrics
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sync_runs (
                        run_id SERIAL PRIMARY KEY,
                        started_at TEXT NOT NULL,
                        finished_at TEXT,
                        source TEXT NOT NULL,
                        active_total_before INTEGER NOT NULL,
                        added_count INTEGER NOT NULL,
                        archived_count INTEGER NOT NULL,
                        active_total_after INTEGER NOT NULL
                    )
                """)
                
                # Departments table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS departments (
                        department TEXT PRIMARY KEY,
                        last_seen TEXT NOT NULL
                    )
                """)
                
                # Migration: backfill first_seen for rows where it's NULL
                cursor.execute("""
                    UPDATE resources
                    SET first_seen = COALESCE(first_seen, last_seen, NOW()::TEXT)
                    WHERE first_seen IS NULL OR first_seen = ''
                """)
                
                # Normalize legacy statuses to canonical
                cursor.execute("UPDATE resources SET scrub_status = 'Include' WHERE scrub_status = 'PASS'")
                cursor.execute("UPDATE resources SET scrub_status = 'Include' WHERE scrub_status = 'keep'")
                cursor.execute("UPDATE resources SET scrub_status = 'Modify' WHERE scrub_status = 'HOLD'")
                cursor.execute("UPDATE resources SET scrub_status = 'Modify' WHERE scrub_status = 'modify'")
                cursor.execute("UPDATE resources SET scrub_status = 'Modify' WHERE scrub_status = 'gap'")
                cursor.execute("UPDATE resources SET scrub_status = 'Sunset' WHERE scrub_status = 'BLOCK'")
                cursor.execute("UPDATE resources SET scrub_status = 'Sunset' WHERE LOWER(scrub_status) = 'sunset'")
                
                # Force NULL/empty to not_reviewed
                cursor.execute("""
                    UPDATE resources SET scrub_status = 'not_reviewed' 
                    WHERE scrub_status IS NULL OR scrub_status = ''
                """)
                
                # Force any remaining unknown value to not_reviewed
                cursor.execute("""
                    UPDATE resources SET scrub_status = 'not_reviewed' 
                    WHERE scrub_status NOT IN ('not_reviewed', 'Include', 'Modify', 'Sunset')
                """)
                
            conn.commit()
            _logger.info("init_db() completed successfully")
        finally:
            return_connection(conn)
        
        _init_db_done = True


# -----------------------------------------------------------------------------
# Resource CRUD
# -----------------------------------------------------------------------------

def upsert_resource(
    resource_key: str,
    relative_path: str,
    resource_type: str,
    bucket: str = None,
    primary_department: str = None,
    sub_department: str = None,
    training_type: str = None,
    display_name: str = None,
    web_url: str = None,
    resource_count: int = 1,
    valid_link_count: int = 0,
    contents_count: int = 0,
    is_placeholder: bool = False,
    source: str = "zip",
    drive_item_id: str = None,
    last_seen_override: str = None
) -> bool:
    """
    Insert or update a resource.
    
    IDEMPOTENT: Updates metadata but NEVER overwrites scrub/invest fields.
    Returns True if new, False if updated.
    """
    now = last_seen_override or datetime.now(timezone.utc).isoformat()
    
    existing = execute(
        "SELECT resource_key FROM resources WHERE resource_key = ?",
        (resource_key,),
        fetch="one"
    )
    
    if existing:
        # Update metadata only (preserve user decisions)
        # Always set is_archived = 0 (resource is current)
        execute("""
            UPDATE resources SET
                relative_path = ?,
                bucket = ?,
                primary_department = ?,
                sub_department = ?,
                training_type = ?,
                display_name = ?,
                web_url = ?,
                resource_count = ?,
                valid_link_count = ?,
                contents_count = ?,
                is_placeholder = ?,
                last_seen = ?,
                source = ?,
                drive_item_id = ?,
                is_archived = 0
            WHERE resource_key = ?
        """, (
            relative_path, bucket, primary_department, sub_department, training_type,
            display_name, web_url, resource_count, valid_link_count, contents_count,
            int(is_placeholder), now, source, drive_item_id, resource_key
        ))
        return False
    else:
        execute("""
            INSERT INTO resources (
                resource_key, drive_item_id, relative_path, bucket,
                primary_department, sub_department, training_type, resource_type,
                display_name, web_url, resource_count, valid_link_count,
                contents_count, is_placeholder, first_seen, last_seen, source, is_archived
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            resource_key, drive_item_id, relative_path, bucket,
            primary_department, sub_department, training_type, resource_type,
            display_name, web_url, resource_count, valid_link_count,
            contents_count, int(is_placeholder), now, now, source
        ))
        return True


# =============================================================================
# Batched Upsert (Performance Optimization)
# =============================================================================

from psycopg2.extras import execute_values

# Column order for batch upsert (must match tuple order)
_UPSERT_COLUMNS = (
    "resource_key", "drive_item_id", "relative_path", "bucket",
    "primary_department", "sub_department", "training_type", "resource_type",
    "display_name", "web_url", "resource_count", "valid_link_count",
    "contents_count", "is_placeholder", "first_seen", "last_seen", "source", "is_archived"
)

# Required keys that must NOT be None (based on schema NOT NULL constraints)
_REQUIRED_KEYS = frozenset({"resource_key", "relative_path", "resource_type"})

_UPSERT_SQL = f"""
INSERT INTO resources ({', '.join(_UPSERT_COLUMNS)})
VALUES %s
ON CONFLICT (resource_key) DO UPDATE SET
    relative_path = EXCLUDED.relative_path,
    bucket = EXCLUDED.bucket,
    primary_department = EXCLUDED.primary_department,
    sub_department = EXCLUDED.sub_department,
    training_type = EXCLUDED.training_type,
    display_name = EXCLUDED.display_name,
    web_url = EXCLUDED.web_url,
    resource_count = EXCLUDED.resource_count,
    valid_link_count = EXCLUDED.valid_link_count,
    contents_count = EXCLUDED.contents_count,
    is_placeholder = EXCLUDED.is_placeholder,
    last_seen = EXCLUDED.last_seen,
    source = EXCLUDED.source,
    drive_item_id = EXCLUDED.drive_item_id,
    is_archived = 0
"""


def batch_upsert_resources(rows: list, *, conn, chunk_size: int = 500) -> int:
    """
    Batched upsert using INSERT ... ON CONFLICT DO UPDATE.
    
    Args:
        rows: List of dicts with resource data (keys must match _UPSERT_COLUMNS)
        conn: Connection from transaction() context (caller owns commit)
        chunk_size: Max rows per statement to avoid size limits
    
    Returns:
        Total rows processed
        
    Raises:
        ValueError: If required keys are missing or None
    """
    if not rows:
        return 0
    
    # Validate required keys - fail fast with clear error
    for i, row in enumerate(rows):
        for key in _REQUIRED_KEYS:
            if key not in row or row[key] is None:
                resource_id = row.get('resource_key', f'row_index_{i}')
                raise ValueError(
                    f"Missing required key '{key}' in row {i} (resource_key={resource_id})"
                )
    
    # Convert dicts to tuples in deterministic column order
    tuples = []
    for row in rows:
        t = tuple(row.get(col) for col in _UPSERT_COLUMNS)
        tuples.append(t)
    
    query_start = time.time()
    
    with conn.cursor() as cursor:
        for i in range(0, len(tuples), chunk_size):
            chunk = tuples[i:i + chunk_size]
            execute_values(cursor, _UPSERT_SQL, chunk)
    
    elapsed_ms = (time.time() - query_start) * 1000
    _logger.info(f"BATCH UPSERT: {len(rows)} rows in {elapsed_ms:.0f}ms")
    
    return len(rows)


def get_all_resources() -> List[Dict[str, Any]]:
    """Get all resources."""
    rows = execute("SELECT * FROM resources ORDER BY relative_path", fetch="all")
    return [dict(row) for row in rows] if rows else []


def get_resources_by_scrub_status(statuses: List[str]) -> List[Dict[str, Any]]:
    """Get resources filtered by scrub status."""
    placeholders = ",".join("?" * len(statuses))
    rows = execute(
        f"SELECT * FROM resources WHERE scrub_status IN ({placeholders})",
        tuple(statuses),
        fetch="all"
    )
    return [dict(row) for row in rows] if rows else []


def update_resource_scrub(
    resource_key: str,
    decision: str,  # RENAMED from status
    owner: str,
    notes: str = None,
    reasons: list = None,  # NEW: list of reason keys
    resource_count_override: int = None,
    audience: str = None
) -> None:
    """
    Update scrubbing fields for a resource.
    
    Args:
        resource_key: Unique resource identifier
        decision: One of {not_reviewed, Include, Modify, Sunset}
        owner: Who made this decision
        notes: Optional free-text notes
        reasons: DEPRECATED - kept for backwards compatibility, ignored
        resource_count_override: Override count for links resources after review
        audience: Who the training is for
    
    Raises:
        ValueError: If decision is invalid
    """
    import json
    from services.scrub_rules import VALID_SCRUB_DECISIONS
    
    # Validation: decision required and valid
    if decision not in VALID_SCRUB_DECISIONS:
        raise ValueError(f"Invalid scrub decision: {decision}. Must be one of {VALID_SCRUB_DECISIONS}")
    
    # Reasons are deprecated in new workflow, just serialize if provided
    reasons_json = json.dumps(sorted(reasons)) if reasons else None
    now = datetime.now(timezone.utc).isoformat()
    
    # Build update dynamically based on provided values
    updates = [
        "scrub_status = ?",
        "scrub_owner = ?",
        "scrub_notes = ?",
        "scrub_reasons = ?",
        "scrub_updated = ?"
    ]
    params = [decision, owner, notes, reasons_json, now]
    
    if resource_count_override is not None:
        updates.append("resource_count = ?")
        params.append(resource_count_override)
    
    if audience is not None:
        updates.append("audience = ?")
        params.append(audience)
    
    params.append(resource_key)
    
    execute(f"""
        UPDATE resources SET
            {', '.join(updates)}
        WHERE resource_key = ?
    """, tuple(params))


def update_resource_invest(
    resource_key: str,
    decision: str,
    owner: str,
    effort: str = None,
    notes: str = None
) -> None:
    """Update investment fields for a resource."""
    now = datetime.now(timezone.utc).isoformat()
    execute("""
        UPDATE resources SET
            invest_decision = ?, invest_owner = ?, invest_effort = ?,
            invest_notes = ?, invest_updated = ?
        WHERE resource_key = ?
    """, (decision, owner, effort, notes, now, resource_key))


# -----------------------------------------------------------------------------
# Batch Updates (for optimized scrubbing workflow)
# -----------------------------------------------------------------------------

def update_audience_bulk(resource_keys: list, audience: str) -> int:
    """
    Update audience for multiple active resources.
    
    GUARDRAILS:
    - Only updates active, non-placeholder resources
    - Handles empty selection safely (returns 0)
    - Only modifies 'audience' field
    
    Returns: count of rows updated
    """
    if not resource_keys:
        return 0  # Handle empty selection safely
    
    placeholders = ",".join("?" * len(resource_keys))
    
    # Note: We need rowcount, so use manual connection with proper cleanup
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(adapt_query(f"""
                UPDATE resources
                SET audience = ?
                WHERE resource_key IN ({placeholders})
                  AND is_archived = 0 
                  AND is_placeholder = 0
            """), tuple([audience] + list(resource_keys)))
            count = cursor.rowcount
            conn.commit()
            return count
    finally:
        return_connection(conn)


def update_scrub_batch(updates: dict) -> int:
    """
    Batch update scrub fields for multiple resources.
    
    Args:
        updates: Dict of {resource_key: {field: value, ...}}
    
    GUARDRAILS:
    - Only updates whitelisted fields (scrub_status, scrub_owner, scrub_notes, audience)
    - Only updates active, non-placeholder resources
    - Sets scrub_updated timestamp on each update
    
    Returns: count of rows updated
    """
    from services.scrub_rules import SCRUB_FIELD_WHITELIST
    
    if not updates:
        return 0
    
    now = datetime.utcnow().isoformat()
    total_updated = 0
    
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            for resource_key, fields in updates.items():
                # Validate fields against whitelist
                safe_fields = {k: v for k, v in fields.items() if k in SCRUB_FIELD_WHITELIST}
                
                if not safe_fields:
                    continue
                
                # Build parameterized update
                set_clauses = [f"{field} = ?" for field in safe_fields.keys()]
                set_clauses.append("scrub_updated = ?")
                
                params = list(safe_fields.values())
                params.append(now)
                params.append(resource_key)
                
                cursor.execute(adapt_query(f"""
                    UPDATE resources SET
                        {', '.join(set_clauses)}
                    WHERE resource_key = ?
                      AND is_archived = 0
                      AND is_placeholder = 0
                """), tuple(params))
                
                total_updated += cursor.rowcount
            
            conn.commit()
    finally:
        return_connection(conn)
    return total_updated


# -----------------------------------------------------------------------------
# Aggregation (uses SUM(resource_count))
# -----------------------------------------------------------------------------

def get_resource_totals(departments: List[str] = None) -> Dict[str, Any]:
    """
    Get resource totals using SUM(resource_count).
    
    ACTIVE ONLY + NON-PLACEHOLDER: All queries filter to:
      is_archived = 0 AND is_placeholder = 0
    
    This matches Inventory's filtering logic exactly.
    
    - Portfolio totals include not_sure (primary_department IS NULL)
    - Department breakdown excludes not_sure
    """
    base_filter = "is_archived = 0 AND is_placeholder = 0"
    
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # Portfolio totals by bucket
            if departments:
                placeholders = ",".join("?" * len(departments))
                cursor.execute(adapt_query(f"""
                    SELECT bucket, SUM(resource_count) as total
                    FROM resources
                    WHERE {base_filter} AND (primary_department IN ({placeholders}) OR primary_department IS NULL)
                    GROUP BY bucket
                """), tuple(departments))
            else:
                cursor.execute(f"""
                    SELECT bucket, SUM(resource_count) as total
                    FROM resources
                    WHERE {base_filter}
                    GROUP BY bucket
                """)
            bucket_totals = {row['bucket']: row['total'] for row in cursor.fetchall()}
            
            # Department breakdown
            if departments:
                placeholders = ",".join("?" * len(departments))
                cursor.execute(adapt_query(f"""
                    SELECT primary_department, SUM(resource_count) as total
                    FROM resources
                    WHERE {base_filter} AND primary_department IN ({placeholders})
                    GROUP BY primary_department
                """), tuple(departments))
            else:
                cursor.execute(f"""
                    SELECT primary_department, SUM(resource_count) as total
                    FROM resources
                    WHERE {base_filter} AND primary_department IS NOT NULL
                    GROUP BY primary_department
                """)
            dept_totals = {row['primary_department']: row['total'] for row in cursor.fetchall()}
            
            # Not sure backlog
            cursor.execute(f"""
                SELECT COUNT(*) as count, SUM(resource_count) as total
                FROM resources
                WHERE {base_filter} AND primary_department IS NULL
            """)
            not_sure = cursor.fetchone()
            
            # Scrubbing progress
            cursor.execute(f"""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN scrub_status != 'not_reviewed' THEN 1 ELSE 0 END) as reviewed
                FROM resources
                WHERE {base_filter}
            """)
            scrub = cursor.fetchone()
            
            # Investment queue
            cursor.execute(f"""
                SELECT COUNT(*) as count
                FROM resources
                WHERE {base_filter} AND scrub_status IN ('modify', 'gap')
            """)
            invest = cursor.fetchone()
    finally:
        return_connection(conn)
    
    return {
        'onboarding': bucket_totals.get('onboarding', 0) or 0,
        'upskilling': bucket_totals.get('upskilling', 0) or 0,
        'not_sure': not_sure['total'] or 0,
        'not_sure_count': not_sure['count'] or 0,
        'dept_breakdown': dept_totals,
        'total_containers': scrub['total'] or 0,
        'reviewed_containers': scrub['reviewed'] or 0,
        'scrubbing_pct': (scrub['reviewed'] / scrub['total'] * 100) if scrub['total'] else 0,
        'investment_queue': invest['count'] or 0,
    }


def get_latest_snapshot() -> Optional[Dict[str, Any]]:
    """Get most recent scan snapshot."""
    row = execute("""
        SELECT * FROM scan_snapshots ORDER BY timestamp DESC LIMIT 1
    """, fetch="one")
    return dict(row) if row else None


def clear_containers() -> None:
    """Clear all containers. For testing/reset only."""
    execute("DELETE FROM resources")


# -----------------------------------------------------------------------------
# Archive / Reconciliation Functions
# -----------------------------------------------------------------------------

def get_active_resource_count() -> int:
    """Get count of active (non-archived) resources."""
    row = execute("SELECT COUNT(*) as cnt FROM resources WHERE is_archived = 0", fetch="one")
    return row['cnt'] if row else 0


def archive_stale_resources(sync_started_at: str, *, conn=None) -> int:
    """
    Archive resources not seen in current sync.
    
    Rule: Any resource with last_seen < sync_started_at OR last_seen IS NULL
    is considered stale and archived.
    
    Args:
        sync_started_at: ISO timestamp of sync start
        conn: Optional connection from transaction() context (caller owns commit)
    
    Returns: number of rows archived
    """
    owns_conn = conn is None
    if owns_conn:
        conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(adapt_query("""
                UPDATE resources
                SET is_archived = 1
                WHERE
                    is_archived = 0
                    AND (last_seen < ? OR last_seen IS NULL)
            """), (sync_started_at,))
            archived_count = cursor.rowcount
            if owns_conn:
                conn.commit()
            return archived_count
    finally:
        if owns_conn:
            return_connection(conn)


def record_sync_run(
    started_at: str,
    finished_at: str,
    source: str,
    active_total_before: int,
    added_count: int,
    archived_count: int,
    active_total_after: int
) -> None:
    """Record a sync run for CFO metrics."""
    execute("""
        INSERT INTO sync_runs (
            started_at, finished_at, source,
            active_total_before, added_count, archived_count, active_total_after
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        started_at, finished_at, source,
        active_total_before, added_count, archived_count, active_total_after
    ))


def get_active_containers() -> List[Dict[str, Any]]:
    """Get all active (non-archived, non-placeholder) containers for Inventory."""
    rows = execute("""
        SELECT * FROM resources 
        WHERE is_archived = 0 AND is_placeholder = 0
        ORDER BY relative_path
    """, fetch="all")
    return [dict(row) for row in rows] if rows else []


def get_active_containers_filtered(
    primary_department: str = None,
    training_type: str = None,
    sales_stage: str = None
) -> List[Dict[str, Any]]:
    """
    Get active containers with optional filters.
    
    CANONICAL PREDICATE: is_archived = 0 AND is_placeholder = 0
    Filters are additive (AND).
    
    Args:
        primary_department: Filter by department (exact match)
        training_type: Filter by training type key (exact match)
        sales_stage: Filter by sales stage:
            - None: no filter (all content)
            - 'untagged': only WHERE sales_stage IS NULL
            - stage key: only WHERE sales_stage = ?
    
    Returns:
        List of container dicts matching filters
    """
    # Build parameterized query
    query = """
        SELECT * FROM resources 
        WHERE is_archived = 0 AND is_placeholder = 0
    """
    params = []
    
    if primary_department:
        query += " AND primary_department = ?"
        params.append(primary_department)
    
    if training_type:
        query += " AND training_type = ?"
        params.append(training_type)
    
    if sales_stage == "untagged":
        query += " AND sales_stage IS NULL"
    elif sales_stage:
        query += " AND sales_stage = ?"
        params.append(sales_stage)
    
    query += " ORDER BY relative_path"
    
    rows = execute(query, tuple(params) if params else None, fetch="all")
    return [dict(row) for row in rows] if rows else []


@cached(30)
def get_active_departments() -> List[str]:
    """
    Get distinct departments from active, non-placeholder containers.
    
    Returns:
        Sorted list of department names (raw folder names)
    """
    rows = execute("""
        SELECT DISTINCT primary_department
        FROM resources
        WHERE is_archived = 0 AND is_placeholder = 0
          AND primary_department IS NOT NULL
        ORDER BY primary_department
    """, fetch="all")
    return [row['primary_department'] for row in rows] if rows else []


@cached(30)
def get_active_training_types(primary_department: str = None) -> List[str]:
    """
    Get distinct training types from active, non-placeholder containers.
    
    Args:
        primary_department: If provided, only return types within that department
    
    Returns:
        Sorted list of training type keys (normalized)
    """
    query = """
        SELECT DISTINCT training_type
        FROM resources
        WHERE is_archived = 0 AND is_placeholder = 0
          AND training_type IS NOT NULL
    """
    params = []
    
    if primary_department:
        query += " AND primary_department = ?"
        params.append(primary_department)
    
    query += " ORDER BY training_type"
    
    rows = execute(query, tuple(params) if params else None, fetch="all")
    return [row['training_type'] for row in rows] if rows else []


# -----------------------------------------------------------------------------
# Resource-Only Functions (for Inventory - Option A)
# Resources = files + links only (excludes folders)
# These functions exist SEPARATELY from container functions to avoid regressions
# -----------------------------------------------------------------------------

def get_active_resources_filtered(
    primary_department: str = None,
    training_type: str = None,
    sales_stage: str = None
) -> List[Dict[str, Any]]:
    """
    Get active RESOURCES (file/link only, excludes folders) with optional filters.
    
    For Inventory page use. Dashboard and other pages use get_active_containers().
    
    Canonical predicate: is_archived=0 AND is_placeholder=0 AND resource_type IN ('file','link')
    """
    query = """
        SELECT * FROM resources 
        WHERE is_archived = 0 AND is_placeholder = 0
          AND resource_type IN ('file', 'link')
    """
    params = []
    
    if primary_department:
        query += " AND primary_department = ?"
        params.append(primary_department)
    
    if training_type:
        query += " AND training_type = ?"
        params.append(training_type)
    
    if sales_stage == "untagged":
        query += " AND sales_stage IS NULL"
    elif sales_stage:
        query += " AND sales_stage = ?"
        params.append(sales_stage)
    
    query += " ORDER BY relative_path"
    
    rows = execute(query, tuple(params) if params else None, fetch="all")
    return [dict(row) for row in rows] if rows else []


@cached(30)
def get_active_resource_departments() -> List[str]:
    """
    Get distinct departments from active RESOURCES (file/link only).
    
    For Inventory filter dropdown. Excludes departments that only contain folders.
    """
    rows = execute("""
        SELECT DISTINCT primary_department
        FROM resources
        WHERE is_archived = 0 AND is_placeholder = 0
          AND resource_type IN ('file', 'link')
          AND primary_department IS NOT NULL
        ORDER BY primary_department
    """, fetch="all")
    return [row['primary_department'] for row in rows] if rows else []


@cached(30)
def get_active_resource_training_types(primary_department: str = None) -> List[str]:
    """
    Get distinct training types from active RESOURCES (file/link only).
    
    For Inventory filter dropdown. Excludes training types that only exist on folders.
    """
    query = """
        SELECT DISTINCT training_type
        FROM resources
        WHERE is_archived = 0 AND is_placeholder = 0
          AND resource_type IN ('file', 'link')
          AND training_type IS NOT NULL
    """
    params = []
    
    if primary_department:
        query += " AND primary_department = ?"
        params.append(primary_department)
    
    query += " ORDER BY training_type"
    
    rows = execute(query, tuple(params) if params else None, fetch="all")
    return [row['training_type'] for row in rows] if rows else []


# -----------------------------------------------------------------------------
# Sales Stage Functions
# -----------------------------------------------------------------------------

def update_sales_stage(resource_key: str, stage: str | None) -> None:
    """
    Update sales_stage for a container.
    
    Args:
        resource_key: The container to update
        stage: None to clear (set NULL), or a canonical stage key
    
    Raises:
        ValueError: If stage is not None and not a valid canonical key
    """
    from services.sales_stage import SALES_STAGE_KEYS
    
    if stage is not None and stage not in SALES_STAGE_KEYS:
        raise ValueError(f"Invalid sales_stage: {stage}")
    
    execute(
        "UPDATE resources SET sales_stage = ? WHERE resource_key = ?",
        (stage, resource_key)
    )


def get_sales_stage_breakdown() -> List[Dict]:
    """
    Get counts grouped by sales_stage.
    
    Only includes rows where sales_stage IS NOT NULL.
    Counts use SUM(resource_count) per spec.
    Applies canonical active predicate.
    
    Returns:
        List of dicts with 'stage', 'label', 'count' keys
    """
    from services.sales_stage import SALES_STAGE_LABELS
    
    rows = execute("""
        SELECT sales_stage, SUM(resource_count) as count
        FROM resources
        WHERE is_archived = 0 AND is_placeholder = 0
          AND sales_stage IS NOT NULL
        GROUP BY sales_stage
        ORDER BY sales_stage
    """, fetch="all")
    
    return [
        {
            "stage": row["sales_stage"],
            "label": SALES_STAGE_LABELS.get(row["sales_stage"], row["sales_stage"]),
            "count": row["count"] or 0
        }
        for row in rows
    ] if rows else []


# -----------------------------------------------------------------------------
# Audience Migration (Manual trigger only via Tools page)
# -----------------------------------------------------------------------------

# Maps both snake_case (old) and display labels (new) to canonical display labels
AUDIENCE_MAP = {
    "direct": "Direct",
    "Direct": "Direct",
    "indirect": "Indirect",
    "Indirect": "Indirect",
    "fi": "FI",
    "FI": "FI",
    "partner_management": "Partner Management",
    "Partner Management": "Partner Management",
    "operations": "Operations",
    "Operations": "Operations",
    "compliance": "Compliance",
    "Compliance": "Compliance",
    "integration": "Integration",
    "Integration": "Integration",
    "pos": "POS",
    "POS": "POS",
}


def run_audience_migration() -> Dict[str, Any]:
    """
    Backfill and normalize audience column.
    
    Steps:
    1. Show diagnostic of current primary_department values
    2. Backfill audience from primary_department (normalize to display labels)
    3. Cleanup any snake_case values already in audience column
    
    Returns:
        Dict with diagnostics, updated counts, and cleanup counts
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # Step 1: Diagnostic - what's in primary_department for rows needing migration?
            cursor.execute("""
                SELECT primary_department, COUNT(*) AS cnt
                FROM resources
                WHERE (audience IS NULL OR audience = '')
                  AND primary_department IS NOT NULL
                GROUP BY primary_department
                ORDER BY cnt DESC
                LIMIT 50
            """)
            diagnostics = [(row['primary_department'], row['cnt']) for row in cursor.fetchall()]
            
            # Step 2: Backfill audience from primary_department with normalization
            backfill_count = 0
            
            # For each key in AUDIENCE_MAP, update rows
            for old_val, canonical_val in AUDIENCE_MAP.items():
                cursor.execute(adapt_query("""
                    UPDATE resources
                    SET audience = ?
                    WHERE (audience IS NULL OR audience = '')
                    AND primary_department = ?
                """), (canonical_val, old_val))
                backfill_count += cursor.rowcount
            
            # Step 3: Cleanup any snake_case values already written to audience column
            snake_case_keys = ['direct', 'indirect', 'fi', 'partner_management', 'operations', 'compliance', 'integration']
            cleanup_count = 0
            for old_val in snake_case_keys:
                canonical_val = AUDIENCE_MAP[old_val]
                cursor.execute(adapt_query("""
                    UPDATE resources
                    SET audience = ?
                    WHERE audience = ?
                """), (canonical_val, old_val))
                cleanup_count += cursor.rowcount
            
            # Count remaining NULL
            cursor.execute("""
                SELECT COUNT(*) as cnt FROM resources
                WHERE audience IS NULL OR audience = ''
            """)
            remaining_null = cursor.fetchone()['cnt']
            
            conn.commit()
    finally:
        return_connection(conn)
    
    return {
        'diagnostics': diagnostics,
        'backfilled': backfill_count,
        'cleaned_up': cleanup_count,
        'remaining_null': remaining_null,
    }


def get_audience_stats() -> Dict[str, int]:
    """Get counts by audience for dashboard chart."""
    rows = execute("""
        SELECT 
            COALESCE(audience, 'Unassigned') as audience_group,
            SUM(resource_count) as total
        FROM resources
        WHERE is_archived = 0 AND is_placeholder = 0
        GROUP BY audience_group
        ORDER BY total DESC
    """, fetch="all")
    
    return {row['audience_group']: row['total'] or 0 for row in rows} if rows else {}


def get_scrub_rollups() -> Dict[str, Any]:
    """
    Get decision and reason rollups for dashboard.
    
    Returns:
        {
            'by_decision': {decision: {'count': N, 'resources': M}},
            'by_reason': {reason: {'count': N, 'resources': M}}
        }
    
    Uses SUM(resource_count) for proper reconciliation with inventory totals.
    """
    import json
    
    # By decision (use SUM(resource_count))
    decision_rows = execute("""
        SELECT scrub_status, 
               COUNT(*) as cnt, 
               COALESCE(SUM(resource_count), 0) as total
        FROM resources
        WHERE is_archived = 0 AND is_placeholder = 0
        GROUP BY scrub_status
    """, fetch="all")
    by_decision = {
        row['scrub_status']: {'count': row['cnt'], 'resources': row['total']} 
        for row in decision_rows
    } if decision_rows else {}
    
    # By reason (parse JSON, accumulate resource_count)
    reason_rows = execute("""
        SELECT scrub_reasons, resource_count FROM resources
        WHERE is_archived = 0 AND is_placeholder = 0 
          AND scrub_status IN ('HOLD', 'BLOCK')
          AND scrub_reasons IS NOT NULL AND scrub_reasons != ''
    """, fetch="all")
    reason_counts = {}
    if reason_rows:
        for row in reason_rows:
            reasons = json.loads(row['scrub_reasons'] or '[]')
            rc = row['resource_count'] if row['resource_count'] is not None else 0
            for r in reasons:
                if r not in reason_counts:
                    reason_counts[r] = {'count': 0, 'resources': 0}
                reason_counts[r]['count'] += 1
                reason_counts[r]['resources'] += rc
    
    return {'by_decision': by_decision, 'by_reason': reason_counts}


def upsert_department(department: str, sync_timestamp: str) -> None:
    """
    Record a valid department discovered from folder structure.
    Called during sync to populate the departments table.
    """
    if not department or not department.strip():
        return
    
    execute("""
        INSERT INTO departments (department, last_seen)
        VALUES (?, ?)
        ON CONFLICT(department) DO UPDATE SET last_seen = excluded.last_seen
    """, (department.strip(), sync_timestamp))


def get_valid_departments() -> List[str]:
    """Get list of valid departments from folder structure."""
    rows = execute("SELECT department FROM departments ORDER BY department", fetch="all")
    return [row['department'] for row in rows] if rows else []


def get_folder_file_count(folder_relative_path: str) -> int:
    """
    Get the contents count for a folder container from the database.
    
    This is informational metadata (Contents) per the resource vs contents contract.
    It does NOT affect KPIs or resource identity.
    
    Args:
        folder_relative_path: The relative path of the folder
        
    Returns:
        Number of files inside the folder (from contents_count column)
    """
    row = execute("""
        SELECT contents_count 
        FROM resources 
        WHERE relative_path = ? AND resource_type = 'folder'
    """, (folder_relative_path,), fetch="one")
    
    if row:
        return row['contents_count'] or 0
    return 0


# Initialize on import
init_db()

