"""
Catalog service: CRUD operations and query helpers for catalog items.
Keeps DB logic out of page files.
"""

import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from db import get_connection
from models.enums import ScrubStatus, SourceType


def get_all_items() -> List[Dict[str, Any]]:
    """Retrieve all catalog items."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM catalog_items ORDER BY department, bucket, functional_area"
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_items_by_scrub_status(statuses: List[str]) -> List[Dict[str, Any]]:
    """Get items filtered by scrub status."""
    conn = get_connection()
    cursor = conn.cursor()
    placeholders = ",".join("?" * len(statuses))
    cursor.execute(
        f"SELECT * FROM catalog_items WHERE scrub_status IN ({placeholders})",
        statuses
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def add_manual_item(
    department: str,
    bucket: str,
    functional_area: str,
    training_type: str,
    item_name: str,
    item_type: str,
    url: Optional[str] = None,
    notes: Optional[str] = None
) -> str:
    """Add a manually entered item. Returns item_id."""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    
    item_id = str(uuid.uuid4())
    display_name = url if item_type == "link" else item_name
    # Unique identity for manual items
    item_identity = f"manual|{department}|{item_name}|{now}"
    
    cursor.execute("""
        INSERT INTO catalog_items 
        (item_id, department, bucket, functional_area, training_type, 
         item_type, item_identity, display_name, size, modified, 
         first_seen, last_seen, source, source_type, scrub_status, scrub_notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        item_id, department, bucket, functional_area, training_type,
        item_type, item_identity, display_name, None, now,
        now, now, "manual", SourceType.MANUAL.value, 
        ScrubStatus.NOT_REVIEWED.value, notes
    ))
    
    conn.commit()
    conn.close()
    return item_id


def update_scrub_status(
    item_id: str,
    status: str,
    owner: str,
    notes: Optional[str] = None
) -> None:
    """Update scrubbing fields for an item."""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    
    cursor.execute("""
        UPDATE catalog_items 
        SET scrub_status = ?, scrub_owner = ?, scrub_notes = ?, scrub_updated = ?
        WHERE item_id = ?
    """, (status, owner, notes, now, item_id))
    
    conn.commit()
    conn.close()


def update_investment(
    item_id: str,
    decision: str,
    owner: str,
    effort: Optional[str] = None,
    notes: Optional[str] = None
) -> None:
    """Update investment fields for an item."""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    
    cursor.execute("""
        UPDATE catalog_items 
        SET invest_decision = ?, invest_owner = ?, invest_effort = ?, 
            invest_notes = ?, invest_updated = ?
        WHERE item_id = ?
    """, (decision, owner, effort, notes, now, item_id))
    
    conn.commit()
    conn.close()


def get_departments() -> List[str]:
    """Get unique departments from catalog."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT department FROM catalog_items ORDER BY department")
    rows = cursor.fetchall()
    conn.close()
    return [row['department'] for row in rows]
