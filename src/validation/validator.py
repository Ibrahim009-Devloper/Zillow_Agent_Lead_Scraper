import re
from urllib.parse import urlparse

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
JUNK_EMAIL = ("sentry", "example.com", "wixpress", "domain.com", "yourdomain",
              ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", "u003e")


def valid_email(e):
    if not e or not EMAIL_RE.match(e):
        return False
    return not any(j in e.lower() for j in JUNK_EMAIL)


def normalize_phone(p):
    digits = re.sub(r"\D", "", p or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10 or digits[0] in "01":
        return ""
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


def valid_url(u):
    try:
        r = urlparse(u)
        return r.scheme in ("http", "https") and bool(r.netloc)
    except Exception:
        return False


def validate_row(row, seen_urls):
    """Return cleaned row or None (drop). Duplicate + required-field check."""
    if not (row.get("first_name") or row.get("full_name")) or not row.get("profile_url"):
        return None
    if row["profile_url"] in seen_urls:
        return None
    row["email"] = row["email"] if valid_email(row.get("email")) else ""
    row["phone"] = normalize_phone(row.get("phone"))
    row["website"] = row["website"] if valid_url(row.get("website", "")) else ""
    seen_urls.add(row["profile_url"])
    return row
