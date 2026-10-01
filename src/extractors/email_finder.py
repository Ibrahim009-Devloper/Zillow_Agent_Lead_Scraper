import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from src.validation.validator import valid_email

EMAIL_FIND = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
CONTACT_PATHS = ("", "/contact", "/contact-us", "/about", "/about-us")


def _emails_from_html(html):
    soup = BeautifulSoup(html, "html.parser")
    found = []
    for a in soup.select('a[href^="mailto:"]'):
        found.append(a["href"][7:].split("?")[0].strip())
    text = html.replace("[at]", "@").replace("(at)", "@").replace("&#64;", "@")
    found += EMAIL_FIND.findall(text)
    return [e for e in dict.fromkeys(found) if valid_email(e)]


def find_email(links, text, website=""):
    # 1) zillow profile mailto / text
    for l in links:
        if l["href"].lower().startswith("mailto:"):
            e = l["href"][7:].split("?")[0].strip()
            if valid_email(e):
                return e
    for e in EMAIL_FIND.findall(text or ""):
        if valid_email(e):
            return e
    # 2) agent website: home + contact pages
    if website:
        for path in CONTACT_PATHS:
            try:
                r = requests.get(urljoin(website, path), headers=HEADERS, timeout=12)
                if r.ok:
                    emails = _emails_from_html(r.text)
                    if emails:
                        return emails[0]
            except Exception:
                continue
    return ""
