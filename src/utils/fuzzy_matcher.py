"""Fuzzy matching utility for project/task names."""

from difflib import SequenceMatcher
from typing import Dict, List, Optional

from src.utils.logger import log


def calculate_similarity(str1: str, str2: str) -> float:
    """Calculate similarity ratio between two strings (0.0 to 1.0).

    Args:
        str1: First string
        str2: Second string

    Returns:
        Similarity ratio (1.0 = exact match, 0.0 = no match)
    """
    if not str1 or not str2:
        return 0.0

    # Normalize to lowercase for comparison
    s1 = str1.lower().strip()
    s2 = str2.lower().strip()

    # Exact match
    if s1 == s2:
        return 1.0

    # Calculate similarity using SequenceMatcher
    ratio = SequenceMatcher(None, s1, s2).ratio()

    return ratio


def fuzzy_match_project(
    user_input: str, projects: List[Dict], threshold: float = 0.80
) -> Optional[Dict]:
    """Find best matching project using fuzzy matching.

    Args:
        user_input: User's input text
        projects: List of project dicts with 'id' and 'nom'
        threshold: Minimum similarity threshold (0.0-1.0)

    Returns:
        Dict with matched project info or None if no good match
        {
            'project_id': str,
            'project_name': str,
            'confidence': float,
            'input': str
        }
    """
    if not user_input or not projects:
        log.debug("🔍 Fuzzy match: Empty input or no projects")
        return None

    user_input_clean = user_input.lower().strip()
    log.debug(
        f"🔍 Fuzzy matching '{user_input_clean}' against {len(projects)} projects (threshold: {threshold})"
    )

    best_match = None
    best_score = 0.0

    for project in projects:
        project_name = project.get("nom", "")
        if not project_name:
            continue

        # Calculate similarity
        similarity = calculate_similarity(user_input_clean, project_name)

        log.debug(f"   '{user_input_clean}' vs '{project_name}' → {similarity:.2f}")

        if similarity > best_score:
            best_score = similarity
            best_match = {
                "project_id": project.get("id"),
                "project_name": project_name,
                "confidence": similarity,
                "input": user_input,
            }

    # Check if best match meets threshold
    if best_match and best_score >= threshold:
        log.info(
            f"✅ Fuzzy match: '{user_input}' → '{best_match['project_name']}' (confidence: {best_score:.2%})"
        )
        return best_match
    elif best_match:
        log.debug(
            f"❌ Fuzzy match: Best match '{best_match['project_name']}' ({best_score:.2%}) below threshold ({threshold:.2%})"
        )
    else:
        log.debug(f"❌ Fuzzy match: No matches found")

    return None


def fuzzy_match_task(
    user_input: str, tasks: List[Dict], threshold: float = 0.80
) -> Optional[Dict]:
    """Find best matching task using fuzzy matching.

    Args:
        user_input: User's input text
        tasks: List of task dicts with 'id' and 'title'
        threshold: Minimum similarity threshold (0.0-1.0)

    Returns:
        Dict with matched task info or None if no good match
        {
            'task_id': str,
            'task_title': str,
            'confidence': float,
            'input': str
        }
    """
    if not user_input or not tasks:
        log.debug("🔍 Fuzzy match: Empty input or no tasks")
        return None

    user_input_clean = user_input.lower().strip()
    log.debug(
        f"🔍 Fuzzy matching '{user_input_clean}' against {len(tasks)} tasks (threshold: {threshold})"
    )

    best_match = None
    best_score = 0.0

    for task in tasks:
        task_title = task.get("title", "")
        if not task_title:
            continue

        # Calculate similarity
        similarity = calculate_similarity(user_input_clean, task_title)

        log.debug(f"   '{user_input_clean}' vs '{task_title}' → {similarity:.2f}")

        if similarity > best_score:
            best_score = similarity
            best_match = {
                "task_id": task.get("id"),
                "task_title": task_title,
                "confidence": similarity,
                "input": user_input,
            }

    # Check if best match meets threshold
    if best_match and best_score >= threshold:
        log.info(
            f"✅ Fuzzy match: '{user_input}' → '{best_match['task_title']}' (confidence: {best_score:.2%})"
        )
        return best_match
    elif best_match:
        log.debug(
            f"❌ Fuzzy match: Best match '{best_match['task_title']}' ({best_score:.2%}) below threshold ({threshold:.2%})"
        )
    else:
        log.debug(f"❌ Fuzzy match: No matches found")

    return None
