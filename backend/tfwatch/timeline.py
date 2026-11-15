BUCKETS = 72


def summarize(checks, start, end):
    last = None
    last_open = None
    count = 0
    total_seconds = 0
    measured = 0
    current_seconds = 0
    points = [None] * BUCKETS
    width = max(end - start + 1, 1)
    for check in checks:
        index = min(BUCKETS - 1, (check.checked_at - start) * BUCKETS // width)
        points[index] = {"status": check.status, "at": check.checked_at}
        contiguous = (
            last is not None and last.status == "open" and check.status == "open"
            and 0 <= check.checked_at - last.checked_at <= last.interval * 1.5
        )
        if contiguous:
            current_seconds += check.checked_at - last.checked_at
        else:
            if current_seconds:
                total_seconds += current_seconds
                measured += 1
                current_seconds = 0
            if check.status == "open":
                count += 1
        if check.status == "open":
            last_open = check.checked_at
        last = check
    if current_seconds:
        total_seconds += current_seconds
        measured += 1

    return {
        "start": start, "end": end, "points": points, "open_periods": count,
        "last_open": last_open, "observed_open_seconds": total_seconds if measured else None,
        "average_open_seconds": round(total_seconds / measured) if measured else None,
    }
