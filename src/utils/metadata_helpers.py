"""Metadata helper functions for compact data storage.

These helpers extract only essential fields from database objects
to minimize metadata bloat when storing tool outputs.
"""
from typing import List, Dict


def compact_projects(projects: List[Dict]) -> List[Dict]:
    """Extract only essential fields from projects for metadata storage.

    Args:
        projects: Full project objects from database

    Returns:
        Compact project list with only id, nom, planradar_project_id
    """
    return [
        {
            "id": p.get("id"),
            "nom": p.get("nom"),
            "planradar_project_id": p.get("planradar_project_id")
        }
        for p in projects
    ]


def compact_tasks(tasks: List[Dict]) -> List[Dict]:
    """Extract only essential fields from tasks for metadata storage.

    Args:
        tasks: Full task objects from database

    Returns:
        Compact task list with only id, title, status, progress
    """
    from src.utils.logger import log

    compact = [
        {
            "id": t.get("id"),
            "title": t.get("title"),
            "status": t.get("status"),
            "progress": t.get("progress")
        }
        for t in tasks
    ]

    # DEBUG: Log first task to see what's being stored
    if compact:
        log.info(f"   🗜️ compact_tasks: first task id={compact[0].get('id')}, title={compact[0].get('title')}")

    return compact


def compact_documents(documents: List[Dict]) -> List[Dict]:
    """Extract only essential fields from documents for metadata storage.

    Args:
        documents: Full document objects from database

    Returns:
        Compact document list with only id, name, type
    """
    return [
        {
            "id": d.get("id"),
            "name": d.get("name"),
            "type": d.get("type")
        }
        for d in documents
    ]
