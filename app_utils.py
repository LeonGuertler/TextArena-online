


def categorize_reason(reason: str) -> str:
    """
    Convert the raw 'reason' string into one of: 
    'invalid_move', 'timeout', or 'game_logic'.
    """
    if not reason:
        return "game_logic"  # or treat as "game_logic" by default
    
    lower = reason.lower()
    if "invalid move" in lower:
        return "invalid_move"
    elif "timed out" in lower or "timeout" in lower:
        return "timeout"
    else:
        return "game_logic"