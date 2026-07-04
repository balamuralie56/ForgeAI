"""
Retry policy implementation for the Task Engine.
Calculates backoff intervals with optional jitter.
"""

import random


def calculate_backoff(
    attempt: int, initial_delay: float, backoff_factor: float, jitter: bool = True
) -> float:
    """
    Computes the delay in seconds for a specific retry attempt.

    Args:
        attempt (int): The current attempt number (0-indexed).
        initial_delay (float): The base delay in seconds.
        backoff_factor (float): The exponential factor.
        jitter (bool): Whether to randomize the delay interval.

    Returns:
        float: Calculated delay in seconds.
    """
    # Delay: initial_delay * (backoff_factor ** attempt)
    delay = initial_delay * (backoff_factor**attempt)

    if jitter:
        # standard jitter ranges between 50% and 150% of the calculated exponential backoff
        delay = random.uniform(0.5 * delay, 1.5 * delay)

    return max(0.0, delay)
