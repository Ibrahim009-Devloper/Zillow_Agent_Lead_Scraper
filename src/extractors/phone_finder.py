import re
from src.validation.validator import normalize_phone

PHONE_RE = re.compile(r"(?:\+?1[\s.\-]?)?\(?\b([2-9]\d{2})\)?[\s.\-]?(\d{3})[\s.\-]?(\d{4})\b")


def find_phone(links, text):
    """tel: links first (most reliable), then regex on visible text."""
    for l in links:
        if l["href"].lower().startswith("tel:"):
            p = normalize_phone(l["href"][4:])
            if p:
                return p
    for m in PHONE_RE.finditer(text or ""):
        p = normalize_phone("".join(m.groups()))
        if p:
            return p
    return ""
