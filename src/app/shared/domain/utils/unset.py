from typing import Final


class _Unset:
    """Sentinel for 'field not provided' in partial-update commands.

    omitted (UNSET)  → do not touch the existing value
    explicit None    → clear the existing value
    """

    _instance: "_Unset | None" = None

    def __new__(cls) -> "_Unset":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "<UNSET>"

    def __bool__(self) -> bool:
        return False


UNSET: Final[_Unset] = _Unset()
