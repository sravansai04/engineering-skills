"""Shared text helpers."""
import re
import unicodedata


def slugify(value):
    """ASCII slug: accents folded, separator runs collapsed, no leading or trailing dash."""
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
