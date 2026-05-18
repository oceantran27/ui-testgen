import uuid

def generate_id(prefix: str) -> str:
    """
    Generate a standardized ID.
    Format: {prefix}_{uuid4[:12]}
    """
    return f"{prefix}_{uuid.uuid4().hex[:12]}"
