from uuid6 import uuid7


def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid7().hex}"
