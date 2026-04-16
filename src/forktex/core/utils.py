"""
forktex.core.utils - Shared utility functions.
"""

from __future__ import annotations

import random
import string
import time


def generate_id(length: int = 12) -> str:
    """
    Generate a unique identifier.

    Args:
        length: Length of the ID

    Returns:
        Random alphanumeric string
    """
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choices(chars, k=length))


def current_timestamp() -> float:
    """Get current Unix timestamp."""
    return time.time()
