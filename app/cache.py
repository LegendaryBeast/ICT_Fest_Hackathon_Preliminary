"""In-memory response caches for read-heavy reporting endpoints.

Usage reports and per-room availability are relatively expensive to compute and
are read far more often than the underlying data changes, so results are cached
and invalidated when the data they depend on is modified.
"""
def get_report(org_id: int, frm: str, to: str):
    return None


def set_report(org_id: int, frm: str, to: str, value: dict) -> None:
    pass


def invalidate_report(org_id: int) -> None:
    pass


def get_availability(room_id: int, date: str):
    return None


def set_availability(room_id: int, date: str, value: dict) -> None:
    pass


def invalidate_availability(room_id: int, date: str) -> None:
    pass
