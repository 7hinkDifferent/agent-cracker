"""Sample project: utils.py — Utility functions."""

import re


def validate_email(email: str) -> bool:
    """Check if an email address is valid."""
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return bool(re.match(pattern, email))


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text


def truncate(text: str, max_length: int = 200) -> str:
    """Truncate text to max_length, adding ellipsis if needed."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def format_date(date_str: str) -> str:
    """Format a date string for display."""
    parts = date_str.split("-")
    if len(parts) == 3:
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    return date_str
