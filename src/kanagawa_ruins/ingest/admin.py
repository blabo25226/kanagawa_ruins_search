"""N03 aliases only copy fields that exist; CODH municipal boundaries are not oaza."""


def normalize_admin(frame):
    frame = frame.copy()
    # 2026 adds N03_005 (ward). N03_004 remains the source municipal name.
    for original, common in [
        ("N03_001", "pref"),
        ("N03_004", "muni"),
        ("N03_007", "muni_code"),
    ]:
        if original in frame:
            frame[common] = frame[original]
    return frame
