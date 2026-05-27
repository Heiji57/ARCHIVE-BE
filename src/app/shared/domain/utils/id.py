import uuid


def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid7().hex}"
