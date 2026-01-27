"""
Container Service
=================
Handles container detection, path parsing, and ZIP import.

FOLDER STRUCTURE (4-level with Sub-Department):
- L0: Department (HR, Point of Sale, etc.)
- L1: Sub-Department (_General, Aloha, OnePOS, etc.)
- L2: Bucket (Onboarding, Upskilling, Not Sure)
- L3: Training Type (Instructor Led, Self Directed, etc.)

LEAF DETECTION RULES:
- File directly under L3 folder (L4) → container
- Folder directly under L3 folder (L3+1) → container
- links.txt directly under L3 folder (L4) → container
- L0/L1/L2/L3 category folders → NOT containers
"""

import re
import zipfile
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from db import upsert_resource, make_resource_key, get_all_resources


# Template structure constants
BUCKETS = {
    "01_onboarding": "onboarding",
    "02_upskilling": "upskilling", 
    "03_not sure (drop here)": "not_sure",
}

TRAINING_TYPES = {
    "01_instructor led - in person": "instructor_led_in_person",
    "01_instructor led – in person": "instructor_led_in_person",
    "02_instructor led - virtual": "instructor_led_virtual",
    "02_instructor led – virtual": "instructor_led_virtual",
    "03_self directed": "self_directed",
    "04_video on demand": "video_on_demand",
    "05_job aids": "job_aids",
    "06_resources": "resources",
}

# Friendly display labels for training types (key → label)
TRAINING_TYPE_LABELS = {
    "instructor_led_in_person": "Instructor Led - In Person",
    "instructor_led_virtual": "Instructor Led - Virtual",
    "self_directed": "Self Directed",
    "video_on_demand": "Video On Demand",
    "job_aids": "Job Aids",
    "resources": "Resources",
}

# OS metadata and template files excluded from ingestion.
# Explicit denylist - these NEVER create resources.
# Compare with filename.lower().
EXCLUDED_FILENAMES = frozenset({"desktop.ini", ".ds_store", "thumbs.db", "instructions.txt", "instructions.pdf"})


def compute_file_count(resource: dict) -> int:
    """
    Compute file count for a resource (secondary metric, Inventory only).
    
    This is NOT the canonical KPI. The canonical operational total is SUM(resource_count).
    
    Logic (fail closed):
    - file → 1
    - link/links → max(int(valid_link_count or 0), 0)
    - unknown → 0
    
    Returns:
        int: File count contribution for this resource
    """
    resource_type = resource.get("resource_type", "")
    
    if resource_type == "file":
        return 1
    
    if resource_type in ("link", "links"):
        try:
            count = int(resource.get("valid_link_count") or 0)
            return max(count, 0)
        except (ValueError, TypeError):
            return 0
    
    # Unknown resource type - fail closed
    return 0


def normalize_bucket(name: str) -> Optional[str]:
    """Normalize bucket folder name to key."""
    if not name:
        return None
    key = name.lower().strip()
    for prefix, bucket in BUCKETS.items():
        if key.startswith(prefix.split("_", 1)[0]) and bucket.replace("_", " ") in key.replace("_", " "):
            return bucket
        if key == prefix:
            return bucket
    # Fuzzy match
    for prefix, bucket in BUCKETS.items():
        if bucket in key.replace("_", " ").replace("-", " "):
            return bucket
    # Fallback: return cleaned name (structure is authoritative)
    return key


def normalize_training_type(name: str) -> Optional[str]:
    """Normalize training type folder name to key."""
    key = name.lower().strip()
    for prefix, ttype in TRAINING_TYPES.items():
        if key == prefix:
            return ttype
        # Handle em-dash vs hyphen
        clean_key = key.replace("–", "-").replace("—", "-")
        clean_prefix = prefix.replace("–", "-").replace("—", "-")
        if clean_key == clean_prefix:
            return ttype
    return None


def parse_path(relative_path: str) -> Dict[str, Optional[str]]:
    """
    Parse folder path to extract department, sub_department, bucket, and training_type.
    
    STRUCTURE (4-level with Sub-Department):
    - L0: Department (HR, Point of Sale, etc.)
    - L1: Sub-Department (_General, Aloha, OnePOS, etc.)
    - L2: Bucket (Onboarding, Upskilling, Not Sure)
    - L3: Training Type (Instructor Led, Self Directed, etc.)
    
    Returns dict with primary_department, sub_department, bucket, training_type.
    """
    # Normalize separators
    path = relative_path.replace("\\", "/").strip("/")
    parts = [p for p in path.split("/") if p]
    
    if not parts:
        return {"bucket": None, "primary_department": None, "sub_department": None, "training_type": None, "depth": 0}
    
    # L0: Department (use as-is)
    dept = parts[0] if len(parts) > 0 else None
    
    # L1: Sub-Department (use as-is)
    sub_dept = parts[1] if len(parts) > 1 else None
    
    # L2: Bucket
    bucket = normalize_bucket(parts[2]) if len(parts) > 2 else None
    
    # L3: Training Type
    training_type = normalize_training_type(parts[3]) if len(parts) > 3 else None
    
    return {
        "bucket": bucket,
        "primary_department": dept,
        "sub_department": sub_dept,
        "training_type": training_type,
        "depth": len(parts),
    }


def get_container_depth(bucket: str) -> int:
    """Get the L3 depth for container detection (4-level hierarchy)."""
    return 4  # L0 (dept) + L1 (sub-dept) + L2 (bucket) + L3 (training type)


def is_leaf_container(relative_path: str, is_folder: bool, filename: str) -> bool:
    """
    Determine if an item is a leaf container.
    
    Rules (4-level structure):
    - File directly under L3 (L4 depth) → YES
    - Folder directly under L3 (L3+1 = L4 depth) → YES
    - links.txt at L4 depth → YES (special)
    - L0/L1/L2/L3 folders → NO
    - Items nested under L4 → NO
    
    Detection is based on DEPTH, not bucket normalization.
    Structure is authoritative.
    """
    parsed = parse_path(relative_path)
    current_depth = parsed["depth"]
    
    # L3 depth is always 4 (Dept/SubDept/Bucket/TrainingType)
    l3_depth = 4
    
    # links.txt special handling
    if filename.lower() == "links.txt":
        return current_depth == l3_depth  # Must be directly under L3
    
    if is_folder:
        # Folder is container only if it's L3+1 (L4)
        return current_depth == l3_depth + 1
    else:
        # File is container if directly under L3 (L4)
        return current_depth >= l3_depth


def parse_links_content(content: str) -> Dict[str, Any]:
    """
    Parse links.txt content to extract URLs.
    
    Rules:
    - Valid URL: starts with http:// or https://
    - Ignore blank lines
    - Ignore comment lines (starting with #)
    """
    lines = content.strip().split('\n') if content else []
    valid_urls = []
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        # Normalize common URL formats
        url = line
        if url.startswith('www.'):
            url = 'https://' + url  # Add protocol for www. URLs
        elif not url.startswith(('http://', 'https://')):
            continue  # Skip non-URL lines
        valid_urls.append(url)
    
    count = len(valid_urls)
    return {
        'valid_link_count': count,
        'is_placeholder': count == 0,
        'resource_count': count,  # Each valid URL is 1 resource
        'urls': valid_urls
    }


def import_from_zip(zip_path: str) -> Dict[str, Any]:
    """
    Import containers from a ZIP file.
    
    Only imports leaf containers (files/folders/links.txt under L3).
    Structural folders are NOT stored.
    
    Returns import statistics.
    """
    results = {
        'new_containers': 0,
        'updated_containers': 0,
        'skipped': 0,
        'errors': [],
    }
    
    with zipfile.ZipFile(zip_path, 'r') as zf:
        entries = zf.namelist()
        
        # Identify containers
        for entry in entries:
            # Skip root folder entry
            if not entry or entry.endswith('/') and entry.count('/') <= 1:
                continue
            
            is_folder = entry.endswith('/')
            path = entry.rstrip('/')
            filename = Path(path).name
            
            # Skip excluded files (OS metadata, template files)
            if filename.lower() in EXCLUDED_FILENAMES:
                continue
            
            # Get relative path (strip root folder)
            parts = path.split('/')
            if len(parts) <= 1:
                continue
            relative_path = '/'.join(parts[1:])  # Skip root folder
            
            # Determine container type and check if leaf
            if filename.lower() == "links.txt":
                # SPECIAL: links.txt → individual LINK containers per URL
                # No depth check - all links.txt files are valid in ZIP import
                parent_path = '/'.join(parts[1:-1])
                
                # Parse path for metadata (from parent folder)
                parsed = parse_path(parent_path)
                
                try:
                    content = zf.read(entry).decode('utf-8', errors='ignore')
                    links_data = parse_links_content(content)
                    urls = links_data.get('urls', [])
                    
                    # Create individual LINK container for each URL
                    for url in urls:
                        # Generate unique key per URL
                        url_hash = hashlib.sha256(url.encode()).hexdigest()[:8]
                        # Handle empty parent_path edge case
                        if parent_path:
                            link_relative_path = f"{parent_path}/links.txt#{url_hash}"
                        else:
                            link_relative_path = f"links.txt#{url_hash}"
                        
                        resource_key = make_resource_key(
                            relative_path=link_relative_path,
                            resource_type="link"
                        )
                        
                        is_new = upsert_resource(
                            resource_key=resource_key,
                            relative_path=link_relative_path,
                            resource_type="link",
                            bucket=parsed['bucket'],
                            primary_department=parsed['primary_department'],
                            sub_department=parsed['sub_department'],
                            training_type=parsed['training_type'],
                            display_name=url,
                            web_url=url,
                            resource_count=1,
                            valid_link_count=1,
                            is_placeholder=False,
                            source="zip"
                        )
                        
                        if is_new:
                            results['new_containers'] += 1
                        else:
                            results['updated_containers'] += 1
                    
                    # If 0 valid URLs, create 0 containers (no placeholders)
                    if not urls:
                        results['skipped'] += 1
                        
                except Exception as e:
                    results['errors'].append(f"Error reading {entry}: {e}")
                
                continue  # links.txt itself is never a container
            
            elif is_folder:
                # SKIP: Folders are structural, not resources
                # Only their contents (files underneath) count
                continue
            
            else:
                resource_type = "file"
            
            # ZIP import: ALL files are valid resources regardless of depth
            # No is_leaf_container() check - depth is irrelevant
            parent_path = '/'.join(parts[1:-1])
            
            # Parse path for metadata
            parsed = parse_path(parent_path)
            
            # Generate deterministic key
            resource_key = make_resource_key(
                relative_path=relative_path,
                resource_type=resource_type
            )
            
            # Upsert container
            is_new = upsert_resource(
                resource_key=resource_key,
                relative_path=relative_path,
                resource_type=resource_type,
                bucket=parsed['bucket'],
                primary_department=parsed['primary_department'],
                sub_department=parsed['sub_department'],
                training_type=parsed['training_type'],
                display_name=filename,
                resource_count=1,
                valid_link_count=0,
                is_placeholder=False,
                source="zip"
            )
            
            if is_new:
                results['new_containers'] += 1
            else:
                results['updated_containers'] += 1
    
    # Clear reference data cache after sync
    from db import clear_cache
    clear_cache()
    
    return results


def import_from_folder(root_dir: str) -> Dict[str, Any]:
    """
    Import containers from a local folder (temporary SharePoint source of truth).
    
    Uses batched upsert for performance:
    - Phase 1: Filesystem walk, collect rows (no DB writes)
    - Phase 2: Single transaction for batch upsert + archive
    
    Args:
        root_dir: Path to the Payroc Training Catalogue folder
        
    Returns:
        Import statistics dict with processed_containers, skipped, errors, archived
    """
    import os
    from datetime import datetime, timezone
    from db import (
        get_active_resource_count, archive_stale_resources, record_sync_run,
        upsert_department, transaction, batch_upsert_resources, clear_cache
    )
    
    # Record sync start time (all upserts use this as last_seen)
    sync_started_at = datetime.now(timezone.utc).isoformat()
    active_before = get_active_resource_count()
    
    # Track discovered departments for upsert
    discovered_departments = set()
    
    # Collect rows for batch upsert (Phase 1: no DB writes)
    rows = []
    skipped = 0
    errors = []
    
    root_path = Path(root_dir).resolve()
    
    if not root_path.exists():
        errors.append(f"Folder not found: {root_dir}")
        return {
            'processed_containers': 0,
            'skipped': 0,
            'errors': errors,
            'archived': 0,
        }
    
    if not root_path.is_dir():
        errors.append(f"Not a directory: {root_dir}")
        return {
            'processed_containers': 0,
            'skipped': 0,
            'errors': errors,
            'archived': 0,
        }
    
    # Walk the directory tree
    for dirpath, dirnames, filenames in os.walk(root_path):
        current_path = Path(dirpath)
        
        # Compute relative path from root
        try:
            rel_path = current_path.relative_to(root_path)
            relative_path = str(rel_path).replace("\\", "/")
        except ValueError:
            # Path traversal guard - skip if outside root
            errors.append(f"Path traversal detected: {dirpath}")
            continue
        
        # Skip the root folder itself
        if relative_path == ".":
            continue
        
        # Process files in this directory
        for filename in filenames:
            # OS artifact exclusion (before any other logic)
            if filename.lower() in EXCLUDED_FILENAMES:
                continue
            
            file_path = current_path / filename
            file_relative = f"{relative_path}/{filename}" if relative_path else filename
            
            # Get parent path for leaf detection
            parent_path = relative_path
            
            # Check if this is a leaf container
            if not is_leaf_container(parent_path, False, filename):
                skipped += 1
                continue
            
            # Parse path for metadata
            parsed = parse_path(parent_path)
            
            # Collect department for departments table
            if parsed.get('primary_department'):
                discovered_departments.add(parsed['primary_department'])
            
            # Handle links.txt specially - expand into individual link records
            if filename.lower() == "links.txt":
                try:
                    content = file_path.read_text(encoding='utf-8', errors='ignore')
                    links_data = parse_links_content(content)
                    urls = links_data.get('urls', [])
                    
                    # Create individual record for each URL
                    for url in urls:
                        # Generate unique relative_path for display/hierarchy
                        url_hash = hashlib.sha256(url.encode()).hexdigest()[:8]
                        link_relative_path = f"{parent_path}/links.txt#{url_hash}"
                        
                        # Generate deterministic key from full string (no collision risk)
                        key_source = f"{parent_path}|{url}|link"
                        resource_key = hashlib.sha256(key_source.encode()).hexdigest()[:16]
                        
                        rows.append({
                            'resource_key': resource_key,
                            'drive_item_id': None,
                            'relative_path': link_relative_path,
                            'bucket': parsed['bucket'],
                            'primary_department': parsed['primary_department'],
                            'sub_department': parsed['sub_department'],
                            'training_type': parsed['training_type'],
                            'resource_type': 'link',
                            'display_name': url,
                            'web_url': url,
                            'resource_count': 1,
                            'valid_link_count': 1,
                            'contents_count': 0,
                            'is_placeholder': 0,
                            'first_seen': sync_started_at,
                            'last_seen': sync_started_at,
                            'source': 'folder',
                            'is_archived': 0,
                        })
                    
                    # If no valid URLs, skip (no placeholder record for empty links.txt)
                    if not urls:
                        skipped += 1
                        
                except Exception as e:
                    errors.append(f"Error reading {file_relative}: {e}")
                
                continue  # links.txt itself produces no row
            
            # Regular file handling (non-links.txt)
            resource_type = "file"
            
            # Count contents for ZIP files (archives are like folders)
            contents_count = 0
            if filename.lower().endswith('.zip'):
                try:
                    import zipfile
                    with zipfile.ZipFile(file_path, 'r') as zf:
                        # Count only files, not directories
                        contents_count = sum(1 for info in zf.infolist() if not info.is_dir())
                except Exception:
                    contents_count = 0  # Fallback if ZIP is corrupted/unreadable
            
            # Generate deterministic key
            resource_key = make_resource_key(
                relative_path=file_relative,
                resource_type=resource_type
            )
            
            rows.append({
                'resource_key': resource_key,
                'drive_item_id': None,
                'relative_path': file_relative,
                'bucket': parsed['bucket'],
                'primary_department': parsed['primary_department'],
                'sub_department': parsed['sub_department'],
                'training_type': parsed['training_type'],
                'resource_type': resource_type,
                'display_name': filename,
                'web_url': None,
                'resource_count': 1,
                'valid_link_count': 0,
                'contents_count': contents_count,
                'is_placeholder': 0,
                'first_seen': sync_started_at,
                'last_seen': sync_started_at,
                'source': 'folder',
                'is_archived': 0,
            })
    
    # -------------------------------------------------------------------------
    # PHASE 2: Single transaction for batch upsert + archive
    # -------------------------------------------------------------------------
    with transaction() as conn:
        processed_count = batch_upsert_resources(rows, conn=conn)
        archived_count = archive_stale_resources(sync_started_at, conn=conn)
    
    # -------------------------------------------------------------------------
    # DEPARTMENT DISCOVERY: Upsert all discovered departments (outside main txn)
    # -------------------------------------------------------------------------
    for dept in discovered_departments:
        upsert_department(dept, sync_started_at)
    
    # Record sync run for CFO metrics
    active_after = get_active_resource_count()
    record_sync_run(
        started_at=sync_started_at,
        finished_at=datetime.now(timezone.utc).isoformat(),
        source="local_folder",
        active_total_before=active_before,
        added_count=processed_count,  # Note: this is total processed, not just new
        archived_count=archived_count,
        active_total_after=active_after
    )
    
    # Clear reference data cache after sync
    clear_cache()
    
    return {
        'processed_containers': processed_count,
        'skipped': skipped,
        'errors': errors,
        'archived': archived_count,
    }
