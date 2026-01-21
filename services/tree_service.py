"""
Tree Service
=============
Builds folder tree dynamically from container paths.
NO HARDCODED TEMPLATE - shows exact structure from imported ZIP.
"""

from typing import Dict, List, Any, Optional
from db import get_active_containers


def format_folder_name(name: str) -> str:
    """Format folder name for display (remove numeric prefix)."""
    import re
    match = re.match(r'^\d+[_\-\s]*(.+)$', name)
    if match:
        return match.group(1)
    return name


def get_folder_contents(path: str) -> Dict[str, Any]:
    """
    Get contents of a specific folder.
    Dynamically builds tree from container paths - NO hardcoded template.
    
    Returns:
    - folders: list of child folders
    - containers: list of containers in this folder
    - breadcrumbs: list of path segments
    """
    containers = get_active_containers()
    path = path.replace("\\", "/").strip("/")
    
    folders = {}  # Use dict to track unique folders with their full path
    items = []
    
    for container in containers:
        container_path = container['relative_path'].replace("\\", "/").strip("/")
        
        if not path:
            # Root level - get first folder from each path
            first_part = container_path.split("/")[0]
            if first_part not in folders:
                folders[first_part] = {
                    "name": format_folder_name(first_part),
                    "path": first_part,
                    "raw_key": first_part
                }
        elif container_path.startswith(path + "/"):
            remaining = container_path[len(path) + 1:]
            parts = remaining.split("/")
            
            if len(parts) == 1:
                # Direct child - could be container or file
                items.append(container)
            else:
                # Child folder
                folder_name = parts[0]
                folder_path = f"{path}/{folder_name}"
                if folder_name not in folders:
                    folders[folder_name] = {
                        "name": format_folder_name(folder_name),
                        "path": folder_path,
                        "raw_key": folder_name
                    }
    
    # Build breadcrumbs
    breadcrumbs = []
    if path:
        parts = path.split("/")
        current = ""
        for part in parts:
            current = f"{current}/{part}".strip("/")
            breadcrumbs.append({
                "name": format_folder_name(part),
                "path": current
            })
    
    # Sort folders by raw key to maintain order
    sorted_folders = sorted(folders.values(), key=lambda x: x.get("raw_key", x["name"]))
    
    return {
        "folders": sorted_folders,
        "containers": items,
        "breadcrumbs": breadcrumbs,
        "current_path": path,
    }


def search_containers(query: str, folder_path: str = None) -> List[Dict[str, Any]]:
    """
    Search containers by name.
    
    If folder_path provided, searches only within that folder.
    Otherwise searches all.
    """
    containers = get_active_containers()
    query_lower = query.lower()
    
    results = []
    for container in containers:
        # Filter by folder if specified
        if folder_path:
            container_path = container['relative_path'].replace("\\", "/").strip("/")
            if not container_path.startswith(folder_path):
                continue
        
        # Match by display name
        if query_lower in (container.get('display_name') or '').lower():
            results.append(container)
    
    return results


def get_bucket_summary() -> List[Dict[str, Any]]:
    """Get summary of containers by bucket."""
    from db import get_connection
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            bucket,
            COUNT(*) as container_count,
            SUM(resource_count) as resource_total
        FROM resource_containers
        WHERE is_archived = 0
        GROUP BY bucket
    """)
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]
