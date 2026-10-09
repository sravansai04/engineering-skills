"""Append-only audit trail. Finance reconciles every export against it."""

EVENTS = []


def record(kind, ref):
    EVENTS.append((kind, ref))
    return len(EVENTS)
