"""
SharePoint Sync Service
=======================
Syncs training resources from SharePoint via Microsoft Graph API.

MENTAL MODEL: This is os.walk() over HTTPS. Not a SharePoint integration—a filesystem replacement.

SCOPE BOUNDARIES (compile-time locked, non-configurable):
- Site: https://payrocllc.sharepoint.com/sites/Roc_UCentral
- Library: Payroc Training Catalogue
- Root: Entire library root

GUARDS:
1. No site enumeration - resolve from constant only
2. Exact library match - fail if not found or ambiguous
3. Drive-scoped endpoints only
4. Runtime validation on EVERY item before processing
5. No future expansion - no UI/env/args for scope
"""

import os
import hashlib
import logging
import time
import requests
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from msal import ConfidentialClientApplication

# -----------------------------------------------------------------------------
# COMPILE-TIME LOCKED SCOPE CONSTANTS (NON-CONFIGURABLE)
# -----------------------------------------------------------------------------
SHAREPOINT_SITE_URL = "https://payrocllc.sharepoint.com/sites/Roc_UCentral"
SHAREPOINT_LIBRARY_NAME = "Payroc Training Catalogue"
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

# OS artifacts excluded from ingestion (matches container_service.py)
EXCLUDED_FILENAMES = frozenset({"desktop.ini", ".ds_store", "thumbs.db"})

_logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# EXCEPTIONS
# -----------------------------------------------------------------------------
class ScopeViolationError(Exception):
    """Raised when a Graph API item is outside authorized scope."""
    pass


class SharePointSyncError(Exception):
    """Raised when SharePoint sync fails."""
    pass


# -----------------------------------------------------------------------------
# ENVIRONMENT VALIDATION (fail-closed)
# -----------------------------------------------------------------------------
def _validate_env() -> Dict[str, str]:
    """
    Validate required SharePoint environment variables.
    Raises RuntimeError if any are missing.
    Never logs secret values.
    """
    required = {
        "SHAREPOINT_TENANT_ID": os.getenv("SHAREPOINT_TENANT_ID"),
        "SHAREPOINT_CLIENT_ID": os.getenv("SHAREPOINT_CLIENT_ID"),
        "SHAREPOINT_CLIENT_SECRET": os.getenv("SHAREPOINT_CLIENT_SECRET"),
    }
    
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise RuntimeError(
            f"SharePoint sync disabled: Missing environment variables: {', '.join(missing)}. "
            f"Configure these in Railway staging environment settings."
        )
    
    _logger.info("SharePoint environment validated (credentials present)")
    return required


def is_sharepoint_enabled() -> bool:
    """Check if SharePoint sync is enabled via environment variable."""
    return os.getenv("SHAREPOINT_SYNC_ENABLED", "").lower() == "true"


# -----------------------------------------------------------------------------
# AUTHENTICATION (MSAL client credentials)
# -----------------------------------------------------------------------------
def get_graph_token() -> str:
    """
    Acquire access token for Microsoft Graph using client credentials.
    Fail-closed: raises RuntimeError on any auth failure.
    """
    env = _validate_env()
    
    app = ConfidentialClientApplication(
        client_id=env["SHAREPOINT_CLIENT_ID"],
        client_credential=env["SHAREPOINT_CLIENT_SECRET"],
        authority=f"https://login.microsoftonline.com/{env['SHAREPOINT_TENANT_ID']}"
    )
    
    result = app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"]
    )
    
    if "access_token" not in result:
        error_desc = result.get("error_description", "Unknown error")
        raise RuntimeError(
            f"SharePoint auth failed: {error_desc}. "
            f"Verify app registration has Sites.Read.All and admin consent."
        )
    
    _logger.info("Graph API token acquired successfully")
    return result["access_token"]


# -----------------------------------------------------------------------------
# GRAPH API REQUEST WRAPPER (with retry/backoff)
# -----------------------------------------------------------------------------
def _make_graph_request(
    url: str,
    headers: Dict[str, str],
    max_retries: int = 5
) -> Optional[Dict[str, Any]]:
    """
    Make Graph API request with retry logic for 429/503.
    
    Returns:
        Response JSON dict, or None if item should be skipped (403/404).
    
    Raises:
        RuntimeError on unrecoverable errors or max retries exceeded.
    """
    retry_count = 0
    backoff_seconds = 3
    
    while retry_count < max_retries:
        try:
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            
            elif response.status_code == 429:
                # Throttled - exponential backoff
                retry_after = int(response.headers.get("Retry-After", backoff_seconds))
                _logger.warning(f"Graph API throttled. Retrying after {retry_after}s...")
                time.sleep(retry_after)
                retry_count += 1
                backoff_seconds = min(backoff_seconds * 2, 60)
            
            elif response.status_code == 503:
                # Service unavailable - retry with backoff
                _logger.warning(f"Graph API unavailable. Retrying after {backoff_seconds}s...")
                time.sleep(backoff_seconds)
                retry_count += 1
                backoff_seconds = min(backoff_seconds * 2, 60)
            
            elif response.status_code in (403, 404):
                # Permission denied or not found - skip item
                _logger.warning(f"Graph API {response.status_code}: {url}")
                return None
            
            elif response.status_code == 401:
                # Auth failure - fail closed
                raise RuntimeError(
                    f"Graph API auth failed (401). Token may be expired or consent missing."
                )
            
            else:
                # Unknown error - fail
                raise RuntimeError(
                    f"Graph API error {response.status_code}: {response.text[:200]}"
                )
        
        except requests.exceptions.Timeout:
            _logger.warning(f"Graph API timeout. Retrying after {backoff_seconds}s...")
            time.sleep(backoff_seconds)
            retry_count += 1
            backoff_seconds = min(backoff_seconds * 2, 60)
        
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Graph API request failed: {e}")
    
    raise RuntimeError(f"Graph API max retries ({max_retries}) exceeded for: {url}")


def _download_file_content(item_id: str, drive_id: str, headers: Dict[str, str]) -> str:
    """
    Download file content from Graph API.
    Only used for links.txt files.
    """
    url = f"{GRAPH_BASE_URL}/drives/{drive_id}/items/{item_id}/content"
    
    response = requests.get(url, headers=headers, timeout=30)
    
    if response.status_code == 200:
        return response.text
    else:
        _logger.warning(f"Failed to download {item_id}: {response.status_code}")
        return ""


# -----------------------------------------------------------------------------
# SCOPE RESOLUTION (fail-closed)
# -----------------------------------------------------------------------------
def resolve_site_id(headers: Dict[str, str]) -> str:
    """
    Resolve site_id from the locked SHAREPOINT_SITE_URL constant.
    
    Fail-closed: raises RuntimeError if site cannot be resolved.
    """
    # Extract site path from URL
    # URL: https://payrocllc.sharepoint.com/sites/Roc_UCentral
    # Graph: /sites/payrocllc.sharepoint.com:/sites/Roc_UCentral
    
    url = f"{GRAPH_BASE_URL}/sites/payrocllc.sharepoint.com:/sites/Roc_UCentral"
    
    result = _make_graph_request(url, headers)
    
    if not result:
        raise RuntimeError(
            f"Failed to resolve site: {SHAREPOINT_SITE_URL}. "
            f"Verify site exists and app has access."
        )
    
    site_id = result.get("id")
    if not site_id:
        raise RuntimeError(
            f"Site resolved but no ID returned: {SHAREPOINT_SITE_URL}"
        )
    
    _logger.info(f"Resolved site_id={site_id}")
    return site_id


def resolve_drive_id(site_id: str, headers: Dict[str, str]) -> str:
    """
    Resolve drive_id by exact library name match.
    
    Fail-closed:
    - No match → RuntimeError
    - Multiple matches → RuntimeError
    """
    url = f"{GRAPH_BASE_URL}/sites/{site_id}/drives"
    
    result = _make_graph_request(url, headers)
    
    if not result or "value" not in result:
        raise RuntimeError(
            f"Failed to list drives for site: {site_id}"
        )
    
    drives = result["value"]
    
    # Exact name match only
    matching_drives = [
        d for d in drives 
        if d.get("name") == SHAREPOINT_LIBRARY_NAME
    ]
    
    if len(matching_drives) == 0:
        available = [d.get("name") for d in drives]
        raise RuntimeError(
            f"Library '{SHAREPOINT_LIBRARY_NAME}' not found. "
            f"Available libraries: {available}"
        )
    
    if len(matching_drives) > 1:
        raise RuntimeError(
            f"Ambiguous library: multiple drives match '{SHAREPOINT_LIBRARY_NAME}'"
        )
    
    drive_id = matching_drives[0]["id"]
    
    _logger.info(f"Resolved drive_id={drive_id}")
    _logger.info(f"Library name match={SHAREPOINT_LIBRARY_NAME}")
    
    return drive_id


# -----------------------------------------------------------------------------
# SCOPE VALIDATION GUARD (called on EVERY item)
# -----------------------------------------------------------------------------
def validate_item_in_scope(item: dict, authorized_drive_id: str) -> None:
    """
    Validates Graph API item is within authorized drive and root.
    
    MUST be called on every item before:
    - Recursing into folders
    - Processing files
    - Upserting to database
    
    FAIL-CLOSED: Missing or empty parentReference/path is treated as scope violation.
    
    Raises:
        ScopeViolationError if item is outside authorized scope.
    """
    parent_ref = item.get("parentReference")
    
    # Fail-closed: Missing parentReference entirely
    if not parent_ref:
        raise ScopeViolationError(
            f"Item {item.get('id')} has no parentReference (fail-closed)"
        )
    
    # Guard 1: driveId must match exactly
    item_drive = parent_ref.get("driveId")
    if not item_drive:
        raise ScopeViolationError(
            f"Item {item.get('id')} has no driveId (fail-closed)"
        )
    if item_drive != authorized_drive_id:
        raise ScopeViolationError(
            f"Item {item.get('id')} in unauthorized drive: {item_drive}"
        )
    
    # Guard 2: path must exist and start with /drives/{drive_id}/root:
    parent_path = parent_ref.get("path")
    if not parent_path:
        raise ScopeViolationError(
            f"Item {item.get('id')} has no parentReference.path (fail-closed)"
        )
    
    expected_prefix = f"/drives/{authorized_drive_id}/root:"
    if not parent_path.startswith(expected_prefix):
        raise ScopeViolationError(
            f"Item {item.get('id')} outside root: {parent_path}"
        )
    
    # Guard 3: Never use webUrl for traversal (implicit - no traversal code uses it)


# -----------------------------------------------------------------------------
# PATH UTILITIES
# -----------------------------------------------------------------------------
def _strip_drive_prefix(parent_path: str, drive_id: str) -> str:
    """
    Convert Graph path to relative path.
    
    /drives/{drive_id}/root:/HR/L&D → HR/L&D
    /drives/{drive_id}/root: → "" (root level)
    """
    prefix = f"/drives/{drive_id}/root:"
    if parent_path.startswith(prefix):
        stripped = parent_path[len(prefix):]
        return stripped.lstrip("/")
    return parent_path


def _build_relative_path(item: dict, drive_id: str) -> str:
    """
    Build relative path from Graph item.
    
    Returns path WITHOUT trailing slash (even for folders).
    Trailing slash is only added to container_key for folders.
    """
    parent_path = item.get("parentReference", {}).get("path", "")
    parent_relative = _strip_drive_prefix(parent_path, drive_id)
    
    if parent_relative:
        return f"{parent_relative}/{item['name']}"
    return item["name"]


def _parse_path_components(relative_path: str) -> Dict[str, Optional[str]]:
    """
    Parse relative path to extract taxonomy components.
    Mirrors container_service.parse_path() exactly.
    """
    from services.container_service import parse_path
    return parse_path(relative_path)


# -----------------------------------------------------------------------------
# SYNC ORCHESTRATOR
# -----------------------------------------------------------------------------
def sync_from_sharepoint() -> Dict[str, Any]:
    """
    Main SharePoint sync orchestrator.
    
    Mirrors import_from_folder() semantics exactly:
    - One sync_started_at timestamp
    - Every upsert uses last_seen_override=sync_started_at
    - source="sharepoint" for all upserts
    - Archive stale after traversal
    - Record sync run for CFO metrics
    
    Returns:
        Dict with added, archived, total, scope_violations
    """
    from db import (
        get_active_resource_count,
        archive_stale_resources,
        record_sync_run,
        upsert_container,
        clear_cache
    )
    
    # Phase 1: Timestamp
    sync_started_at = datetime.now(timezone.utc).isoformat()
    _logger.info(f"SharePoint sync started at {sync_started_at}")
    
    # Phase 2: Baseline
    active_before = get_active_resource_count()
    _logger.info(f"Active resources before sync: {active_before}")
    
    # Phase 3: Authenticate & Resolve Scope (fail-closed)
    token = get_graph_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    site_id = resolve_site_id(headers)
    drive_id = resolve_drive_id(site_id, headers)
    
    # Phase 4: Traverse & Upsert
    stats = {
        "folders_scanned": 0,
        "files_scanned": 0,
        "links_created": 0,
        "new_containers": 0,
        "updated_containers": 0,
        "scope_violations": 0,
        # Detailed skip categories
        "skipped_excluded": 0,
        "skipped_depth": 0,
        "skipped_download_fail": 0,
        "skipped_no_urls": 0,
    }
    
    _traverse_folder(
        item_id="root",
        drive_id=drive_id,
        headers=headers,
        sync_started_at=sync_started_at,
        stats=stats,
        parent_relative=""
    )
    
    _logger.info(
        f"Traversal complete: {stats['folders_scanned']} folders, "
        f"{stats['files_scanned']} files, {stats['links_created']} links | "
        f"Skipped: excluded={stats['skipped_excluded']}, "
        f"depth={stats['skipped_depth']}, no_urls={stats['skipped_no_urls']}, "
        f"download_fail={stats['skipped_download_fail']}"
    )
    
    if stats['scope_violations'] > 0:
        _logger.warning(f"SECURITY: {stats['scope_violations']} scope violations detected")
    
    # Phase 5: Archive Stale (reuse existing function)
    archived_count = archive_stale_resources(sync_started_at)
    _logger.info(f"Archived stale resources: {archived_count}")
    
    # Phase 6: Metrics
    active_after = get_active_resource_count()
    added_count = stats['new_containers']
    
    # Phase 7: Record Sync Run (reuse existing function)
    record_sync_run(
        started_at=sync_started_at,
        finished_at=datetime.now(timezone.utc).isoformat(),
        source="sharepoint",
        active_total_before=active_before,
        added_count=added_count,
        archived_count=archived_count,
        active_total_after=active_after
    )
    
    # Clear cache after sync
    clear_cache()
    
    _logger.info(
        f"SharePoint sync complete: added={added_count}, archived={archived_count}, "
        f"active_after={active_after}, scope_violations={stats['scope_violations']}"
    )
    
    return {
        "added": added_count,
        "updated": stats['updated_containers'],
        "archived": archived_count,
        "total": active_after,
        "scope_violations": stats['scope_violations'],
        "folders_scanned": stats['folders_scanned'],
        "files_scanned": stats['files_scanned'],
        "links_created": stats['links_created'],
    }


def _traverse_folder(
    item_id: str,
    drive_id: str,
    headers: Dict[str, str],
    sync_started_at: str,
    stats: Dict[str, int],
    parent_relative: str
) -> None:
    """
    Recursively traverse folder and process children.
    
    Handles pagination via @odata.nextLink.
    Validates every item before processing.
    """
    from services.container_service import parse_path, is_leaf_container, parse_links_content
    from db import upsert_container, make_container_key
    
    # Build URL for children
    if item_id == "root":
        url = f"{GRAPH_BASE_URL}/drives/{drive_id}/root/children"
    else:
        url = f"{GRAPH_BASE_URL}/drives/{drive_id}/items/{item_id}/children"
    
    # Paginate through all children
    while url:
        result = _make_graph_request(url, headers)
        
        if not result:
            _logger.warning(f"Failed to list children for {item_id}")
            break
        
        children = result.get("value", [])
        
        for item in children:
            item_name = item.get("name", "")
            
            # DIAGNOSTIC: Progress summary every 50 items
            total_scanned = stats.get('folders_scanned', 0) + stats.get('files_scanned', 0)
            if total_scanned > 0 and total_scanned % 50 == 0:
                _logger.info(f"[SYNC] Progress: {stats.get('folders_scanned', 0)} folders, {stats.get('files_scanned', 0)} files, {stats.get('added', 0)} resources")
            
            # OS artifact exclusion
            if item_name.lower() in EXCLUDED_FILENAMES:
                stats['skipped_excluded'] += 1
                continue
            
            # SCOPE GUARD: Validate every item before processing
            try:
                validate_item_in_scope(item, drive_id)
            except ScopeViolationError as e:
                _logger.warning(f"SECURITY: Scope violation: {e}")
                stats['scope_violations'] += 1
                continue  # Skip this item
            
            # Build relative path (no trailing slash, even for folders)
            item_relative = _build_relative_path(item, drive_id)
            
            if "folder" in item:
                # It's a folder - check if leaf container or recurse
                stats['folders_scanned'] += 1
                
                # DIAGNOSTIC: Log folder entry with depth
                folder_depth = len(item_relative.split('/')) if item_relative else 0
                _logger.info(f"[SYNC] FOLDER: {item_relative} (depth {folder_depth})")
                
                # Check if this folder is a leaf container (L3+1 depth)
                if is_leaf_container(item_relative, True, item_name):
                    # Process as folder container
                    _process_folder_container(
                        item=item,
                        drive_id=drive_id,
                        relative_path=item_relative,
                        sync_started_at=sync_started_at,
                        stats=stats
                    )
                
                # Always recurse into folders (traversal continues regardless)
                _traverse_folder(
                    item_id=item["id"],
                    drive_id=drive_id,
                    headers=headers,
                    sync_started_at=sync_started_at,
                    stats=stats,
                    parent_relative=item_relative
                )
            
            elif "file" in item:
                # It's a file
                stats['files_scanned'] += 1
                
                # Get parent path for leaf detection
                parent_path = parent_relative
                
                # Check if leaf container
                if not is_leaf_container(parent_path, False, item_name):
                    stats['skipped_depth'] += 1
                    parent_depth = len(parent_path.split('/')) if parent_path else 0
                    _logger.info(f"[SYNC] SKIP depth: {item_name} | depth: {parent_depth}")
                    continue  # Not a leaf, skip
                
                # Handle links.txt specially
                if item_name.lower() == "links.txt":
                    _process_links_file(
                        item=item,
                        drive_id=drive_id,
                        headers=headers,
                        parent_relative=parent_path,
                        sync_started_at=sync_started_at,
                        stats=stats
                    )
                    # DIAGNOSTIC: Log links.txt processing
                    _logger.info(f"[SYNC] ADD links.txt: {item_relative}")
                else:
                    # Regular file
                    _process_file_container(
                        item=item,
                        drive_id=drive_id,
                        relative_path=item_relative,
                        sync_started_at=sync_started_at,
                        stats=stats
                    )
                    # DIAGNOSTIC: Log file added
                    _logger.info(f"[SYNC] ADD file: {item_name}")
        
        # Pagination: follow nextLink
        url = result.get("@odata.nextLink")


def _process_folder_container(
    item: dict,
    drive_id: str,
    relative_path: str,
    sync_started_at: str,
    stats: Dict[str, int]
) -> None:
    """Process a folder as a container (L3+1 depth)."""
    # REDUNDANT SCOPE GUARD: Prevents drift if this function is called directly
    validate_item_in_scope(item, drive_id)
    
    from services.container_service import parse_path
    from db import upsert_container, make_container_key
    
    parsed = parse_path(relative_path)
    
    # container_key has trailing slash for folders
    container_key = make_container_key(
        relative_path=relative_path,
        container_type="folder"
    )
    
    # Folder metadata (contents_count from Graph childCount)
    contents_count = item.get("folder", {}).get("childCount", 0)
    
    is_new = upsert_container(
        container_key=container_key,
        relative_path=relative_path,  # NO trailing slash
        container_type="folder",
        bucket=parsed.get('bucket'),
        primary_department=parsed.get('primary_department'),
        sub_department=parsed.get('sub_department'),
        training_type=parsed.get('training_type'),
        display_name=item.get("name"),
        resource_count=1,
        valid_link_count=0,
        contents_count=contents_count,
        is_placeholder=False,
        source="sharepoint",
        drive_item_id=item.get("id"),
        last_seen_override=sync_started_at
    )
    
    if is_new:
        stats['new_containers'] += 1
    else:
        stats['updated_containers'] += 1


def _process_file_container(
    item: dict,
    drive_id: str,
    relative_path: str,
    sync_started_at: str,
    stats: Dict[str, int]
) -> None:
    """Process a regular file as a container."""
    # REDUNDANT SCOPE GUARD: Prevents drift if this function is called directly
    validate_item_in_scope(item, drive_id)
    
    from services.container_service import parse_path
    from db import upsert_container, make_container_key
    
    # Parse parent path for taxonomy
    parent_path = "/".join(relative_path.split("/")[:-1])
    parsed = parse_path(parent_path)
    
    container_key = make_container_key(
        relative_path=relative_path,
        container_type="file"
    )
    
    is_new = upsert_container(
        container_key=container_key,
        relative_path=relative_path,
        container_type="file",
        bucket=parsed.get('bucket'),
        primary_department=parsed.get('primary_department'),
        sub_department=parsed.get('sub_department'),
        training_type=parsed.get('training_type'),
        display_name=item.get("name"),
        resource_count=1,
        valid_link_count=0,
        contents_count=0,
        is_placeholder=False,
        source="sharepoint",
        drive_item_id=item.get("id"),
        last_seen_override=sync_started_at
    )
    
    if is_new:
        stats['new_containers'] += 1
    else:
        stats['updated_containers'] += 1


def _process_links_file(
    item: dict,
    drive_id: str,
    headers: Dict[str, str],
    parent_relative: str,
    sync_started_at: str,
    stats: Dict[str, int]
) -> None:
    """
    Process links.txt file: download content, parse URLs, create link resources.
    
    Each valid URL becomes its own container with:
    - container_type = "link"
    - resource_count = 1
    - drive_item_id = null (consistent with existing behavior)
    """
    # REDUNDANT SCOPE GUARD: Prevents drift if this function is called directly
    validate_item_in_scope(item, drive_id)
    
    from services.container_service import parse_path, parse_links_content
    from db import upsert_container
    
    # Download file content (only content download allowed)
    content = _download_file_content(item["id"], drive_id, headers)
    
    if not content:
        stats['skipped_download_fail'] += 1
        _logger.warning(f"[SYNC] SKIP download: links.txt at {parent_relative}")
        return
    
    # DIAGNOSTIC: Log every links.txt download with content length
    _logger.info(f"[SYNC] LINKS.TXT: {parent_relative} | content_len={len(content)}")
    
    # Parse URLs
    links_data = parse_links_content(content)
    urls = links_data.get('urls', [])
    
    # DIAGNOSTIC: Log URL parse result
    _logger.info(f"[SYNC] PARSED: {parent_relative} | urls_found={len(urls)}")
    
    if not urls:
        stats['skipped_no_urls'] += 1
        return  # No valid URLs, no containers created
    
    # Parse parent for taxonomy
    parsed = parse_path(parent_relative)
    
    # Create one container per URL (matching existing sha256 scheme)
    for url in urls:
        # url_hash for relative_path display
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:8]
        link_relative_path = f"{parent_relative}/links.txt#{url_hash}"
        
        # container_key from full deterministic source
        key_source = f"{parent_relative}|{url}|link"
        container_key = hashlib.sha256(key_source.encode()).hexdigest()[:16]
        
        is_new = upsert_container(
            container_key=container_key,
            relative_path=link_relative_path,
            container_type="link",
            bucket=parsed.get('bucket'),
            primary_department=parsed.get('primary_department'),
            sub_department=parsed.get('sub_department'),
            training_type=parsed.get('training_type'),
            display_name=url,
            web_url=url,
            resource_count=1,
            valid_link_count=1,
            contents_count=0,
            is_placeholder=False,
            source="sharepoint",
            drive_item_id=None,  # null for links (consistent with existing)
            last_seen_override=sync_started_at
        )
        
        if is_new:
            stats['new_containers'] += 1
            stats['links_created'] += 1
        else:
            stats['updated_containers'] += 1
