import json
import os
import random
import re
import sys
import time
from urllib.parse import urlparse

import pandas as pd
from seleniumbase import SB

from src import config
from src.scraper import locator as L
from src.extractors.email_finder import find_email
from src.extractors.phone_finder import find_phone
from src.validation.validator import validate_row

NUM_LINE = re.compile(r"^[\$\d][\d,\.]*\s*[KMkm]?(\s*[-–]\s*\$?[\d,\.]+\s*[KMkm]?)?$")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def clean_profile_url(u):
    p = urlparse(u)
    return f"{p.scheme}://{p.netloc}{p.path}"


class ZillowScraper:
    def __init__(self, sb, location):
        self.sb = sb
        self.location = location
        os.makedirs(config.TEMP_DIR, exist_ok=True)
        self.links_file = os.path.join(config.TEMP_DIR, f"links_{slug(location)}.json")

    # ---------- helpers ----------
    def _run_js(self, script):
        s = script.strip()
        bare = s[7:].rstrip(";").strip() if s.startswith("return ") else s
        if hasattr(self.sb, "cdp") and hasattr(self.sb.cdp, "evaluate"):
            try:
                return self.sb.cdp.evaluate(script)
            except Exception:
                try:
                    return self.sb.cdp.evaluate(bare)
                except Exception:
                    pass
        try:
            return self.sb.execute_script(f"return {bare};")
        except Exception:
            return self.sb.execute_script(bare)

    def _is_challenge_present(self):
        try:
            if hasattr(self.sb, "cdp") and hasattr(self.sb.cdp, "get_page_source"):
                src = self.sb.cdp.get_page_source().lower()
            else:
                src = self.sb.get_page_source().lower()
            return any(h in src for h in L.CAPTCHA_HINTS)
        except Exception:
            return False

    def _has_profiles_on_page(self):
        try:
            links = self._run_js(L.JS_PROFILE_LINKS) or []
            return len(links) > 0
        except Exception:
            return False

    def _captcha_check(self, max_retries=3, redirect_wait=12):
        if not self._is_challenge_present():
            return

        px_selectors = [
            "#px-captcha",
            "div#px-captcha",
            "div[id*='px-captcha']",
            "div.px-captcha-container",
            "[aria-label*='press and hold' i]",
            "div[role='button']",
        ]

        for attempt in range(1, max_retries + 1):
            if not self._is_challenge_present():
                return

            print(f"[*] Challenge / Captcha detected (attempt {attempt}/{max_retries}), applying bypass...")
            handled = False

            # Check if PerimeterX element is present
            px_elem = None
            if hasattr(self.sb, "cdp"):
                for sel in px_selectors:
                    try:
                        if self.sb.cdp.is_element_visible(sel):
                            px_elem = sel
                            break
                    except Exception:
                        pass

            # 1. Try PyAutoGUI / CDP click & hold if px_elem found
            if hasattr(self.sb, "cdp") and px_elem:
                hold_time = random.uniform(8.0, 12.0)
                try:
                    print(f"[*] Simulating human press & hold on {px_elem} ({hold_time:.1f}s)...")
                    if hasattr(self.sb.cdp, "gui_click_and_hold"):
                        self.sb.cdp.gui_click_and_hold(px_elem, timeframe=hold_time)
                        handled = True
                    elif hasattr(self.sb.cdp, "click_and_hold"):
                        self.sb.cdp.click_and_hold(px_elem, timeframe=hold_time)
                        handled = True
                except Exception as e:
                    print(f"[!] GUI click & hold error: {e}")

            # 2. Try SeleniumBase built-in solve_captcha
            if not handled or self._is_challenge_present():
                try:
                    if hasattr(self.sb, "solve_captcha"):
                        self.sb.solve_captcha()
                        handled = True
                    elif hasattr(self.sb, "cdp") and hasattr(self.sb.cdp, "solve_captcha"):
                        self.sb.cdp.solve_captcha()
                        handled = True
                except Exception as e:
                    print(f"[!] solve_captcha error: {e}")

            # 3. Fallback to GUI solvers
            if self._is_challenge_present():
                try:
                    if hasattr(self.sb, "uc_gui_click_captcha"):
                        self.sb.uc_gui_click_captcha()
                    elif hasattr(self.sb, "uc_gui_handle_captcha"):
                        self.sb.uc_gui_handle_captcha()
                except Exception:
                    pass

            # 4. Wait polling for challenge removal
            wait_start = time.time()
            cleared = False
            while time.time() - wait_start < redirect_wait:
                time.sleep(1.0)
                if not self._is_challenge_present() and self._has_profiles_on_page():
                    cleared = True
                    print(f"[+] Challenge successfully bypassed on attempt {attempt}!")
                    break

            if cleared:
                return

            print(f"[-] Attempt {attempt} failed to clear challenge.")
            time.sleep(2)

        # Fallback if automated solvers could not clear challenge
        if self._is_challenge_present():
            input("[!] Captcha on screen. Solve it in the browser, then press ENTER...")

    def _open(self, url):
        if hasattr(self.sb, "cdp") and hasattr(self.sb.cdp, "open"):
            try:
                self.sb.cdp.open(url)
            except Exception:
                self.sb.activate_cdp_mode(url)
        else:
            self.sb.activate_cdp_mode(url)
        time.sleep(random.uniform(2.0, 3.5))
        self._captcha_check()

    # ---------- steps 1-2: search ----------
    def search_location(self):
        loc_slug = re.sub(r"[^a-z0-9]+", "-", self.location.lower()).strip("-")
        direct_url = f"https://www.zillow.com/professionals/real-estate-agent-reviews/{loc_slug}/?"
        print(f"[*] Navigating to agent directory: {direct_url}")

        self.sb.activate_cdp_mode(direct_url)
        time.sleep(random.uniform(2.5, 4.0))
        self._captcha_check()

        # Check if direct URL loaded agents
        if self._has_profiles_on_page():
            print(f"[+] Successfully loaded agent directory for {self.location}")
            return

        # Fallback to search bar if direct slug URL didn't have profiles
        print("[*] Direct location URL yielded no profiles. Falling back to search bar...")
        self._open(config.START_URL)
        if hasattr(self.sb, "cdp"):
            try:
                self.sb.cdp.click_if_visible(L.SEARCH_INPUT)
            except Exception:
                pass
            time.sleep(0.5)
            self.sb.cdp.type(L.SEARCH_INPUT, self.location)
            time.sleep(2.0)
            self.sb.cdp.send_keys(L.SEARCH_INPUT, "\n")
        else:
            self.sb.click(L.SEARCH_INPUT)
            time.sleep(0.5)
            self.sb.type(L.SEARCH_INPUT, self.location)
            time.sleep(2.0)
            self.sb.send_keys(L.SEARCH_INPUT, "\n")
        time.sleep(random.uniform(3.0, 4.5))
        self._captcha_check()

    # ---------- step 3: collect links (paginate) ----------
    def collect_links(self, max_pages=config.MAX_PAGES, limit=None):
        sb = self.sb
        links = []
        if os.path.exists(self.links_file):
            try:
                links = json.load(open(self.links_file, "r", encoding="utf-8"))
                print(f"[resume] {len(links)} links loaded from temp file")
            except Exception:
                links = []
        seen = set(links)

        target_links = int(limit * 1.3) + 5 if limit else None
        if target_links and len(links) >= target_links:
            print(f"[resume] already have {len(links)} links (sufficient for limit of {limit})")
            return links

        for page in range(1, max_pages + 1):
            # Scroll down to ensure all profile elements on the page are rendered
            sb.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
            sb.sleep(0.5)
            sb.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            sb.sleep(0.5)

            raw_links = self._run_js(L.JS_PROFILE_LINKS) or []
            found = [clean_profile_url(u) for u in raw_links]
            new = [u for u in dict.fromkeys(found) if u not in seen]
            for u in new:
                seen.add(u)
                links.append(u)
            json.dump(links, open(self.links_file, "w", encoding="utf-8"))  # temp memory file
            print(f"[page {page}] +{len(new)} new | total {len(links)}")

            if target_links and len(links) >= target_links:
                print(f"[done] collected {len(links)} links, sufficient for target limit of {limit}")
                break

            if page >= max_pages:
                print(f"[done] reached max_pages limit ({max_pages})")
                break

            # Click the Next page button
            clicked = self._run_js(L.JS_CLICK_NEXT_PAGE)
            if not clicked:
                print("[done] no more pages (next button disabled or not found)")
                break

            sb.sleep(random.uniform(3.0, 4.5))
            self._captcha_check()

            # Wait for next page profiles to load
            wait_start = time.time()
            page_changed = False
            while time.time() - wait_start < 12:
                raw_after = self._run_js(L.JS_PROFILE_LINKS) or []
                after = [clean_profile_url(u) for u in raw_after]
                if any(u not in seen for u in after):
                    page_changed = True
                    break
                sb.sleep(1.5)
                self._captcha_check()

            if not page_changed:
                raw_after = self._run_js(L.JS_PROFILE_LINKS) or []
                after = [clean_profile_url(u) for u in raw_after]
                if not any(u not in seen for u in after):
                    print("[done] next page returned no new profiles")
                    break

        return links

    # ---------- step 4: profile details ----------
    @staticmethod
    def _lines(text):
        return [l.strip() for l in text.splitlines() if l.strip()]

    def _metric(self, lines, label):
        """Value sits on the line before or after its label."""
        for i, l in enumerate(lines):
            if l.lower() == label.lower() or l.lower().startswith(label.lower()):
                for j in (i - 1, i + 1):
                    if 0 <= j < len(lines) and NUM_LINE.match(lines[j]):
                        return lines[j]
                m = re.search(r"([\$\d][\d,\.]*\s*[KMkm]?(?:\s*[-–]\s*\$?[\d,\.]+\s*[KMkm]?)?)", l[len(label):])
                if m:
                    return m.group(1).strip()
        return ""

    @staticmethod
    def _count(text, label):
        m = re.search(rf"{label}\s*\(?\s*(\d[\d,]*)\s*\)?", text, re.I)
        return m.group(1).replace(",", "") if m else ""

    def scrape_profile(self, url):
        self._open(url)
        if hasattr(self.sb, "cdp"):
            try:
                self.sb.cdp.wait_for_element_present("h1", timeout=8)
            except Exception:
                pass
        time.sleep(random.uniform(1.2, 2.0))
        data = self._run_js(L.JS_PROFILE_DATA) or {"name": "", "text": "", "links": []}
        text, links = data.get("text", ""), data.get("links", [])
        lines = self._lines(text)

        raw_name = data.get("name", "").strip()

        # Clean agent name: remove suffixes, extra words after the last name
        clean_name = raw_name
        clean_name = re.sub(r"\s*[-–|/]\s*.*$", "", clean_name)
        clean_name = re.split(r"\s+at\s+", clean_name, flags=re.I)[0]
        clean_name = re.split(r"\s+and\s+", clean_name, flags=re.I)[0]
        clean_name = clean_name.split(",")[0].strip()

        # Remove known junk/marketing suffixes if attached to name
        junk_patterns = [
            r"Top Florida Broker.*$", r"South Florida.*$", r"Real Estate.*$",
            r"Realty.*$", r"Broker.*$", r"Group.*$", r"Team.*$", r"LLC.*$", r"Inc.*$"
        ]
        for jp in junk_patterns:
            clean_name = re.sub(rf"\s+{jp}", "", clean_name, flags=re.I).strip()

        tokens = clean_name.split()
        if not tokens:
            first_name, last_name = "", ""
        elif len(tokens) == 1:
            first_name, last_name = tokens[0], ""
        else:
            first_name = tokens[0]
            if len(tokens) > 2 and len(tokens[1].rstrip(".")) == 1:
                last_name = tokens[2]
            elif tokens[1].lower() in ("de", "van", "von", "del", "da") and len(tokens) > 2:
                last_name = f"{tokens[1]} {tokens[2]}"
            else:
                last_name = tokens[1]

        brokerage = (data.get("brokerage") or "").strip()
        if not brokerage:
            for i, l in enumerate(lines[:25]):
                if raw_name and raw_name.lower() in l.lower():
                    for j in range(i + 1, min(len(lines), i + 4)):
                        cand = lines[j].strip()
                        if cand and not any(w in cand.lower() for w in ("review", "star", "contact", "about", "share", "save", "rating", "phone", "email", "$", "sales")) and len(cand) < 80 and not re.match(r"^[A-Z][A-Za-z .'\-]+,\s*[A-Z]{2}$", cand):
                            brokerage = cand
                            break
                    break

        if not brokerage:
            if " - " in raw_name:
                brokerage = raw_name.split(" - ", 1)[1].strip()
            elif " at " in raw_name.lower():
                brokerage = re.split(r"\s+at\s+", raw_name, flags=re.I)[1].strip()
            elif "Group" in raw_name or "Realty" in raw_name or "Broker" in raw_name:
                m_b = re.search(r"((?:Top Florida Broker|South Florida|The \w+ Group|[\w\s]+ Realty|[\w\s]+ Brokerage).*)$", raw_name, re.I)
                if m_b:
                    brokerage = m_b.group(1).strip()

        website = ""
        for l in links:
            if re.search(r"website", l["text"], re.I) and "zillow.com" not in l["href"]:
                website = l["href"]
                break

        social_dict = {
            "facebook": "",
            "linkedin": "",
            "instagram": "",
            "youtube": "",
            "twitter": "",
            "other_socials": "",
        }
        others = []
        for l in links:
            h = l["href"]
            if any(d in h for d in L.SOCIAL_DOMAINS) and not any(b in h for b in L.ZILLOW_SOCIAL_BLACKLIST):
                hl = h.lower()
                if "facebook.com" in hl:
                    if not social_dict["facebook"]:
                        social_dict["facebook"] = h
                elif "linkedin.com" in hl:
                    if not social_dict["linkedin"]:
                        social_dict["linkedin"] = h
                elif "instagram.com" in hl:
                    if not social_dict["instagram"]:
                        social_dict["instagram"] = h
                elif "youtube.com" in hl:
                    if not social_dict["youtube"]:
                        social_dict["youtube"] = h
                elif "twitter.com" in hl or "x.com" in hl:
                    if not social_dict["twitter"]:
                        social_dict["twitter"] = h
                else:
                    others.append(h)
        if others:
            social_dict["other_socials"] = ", ".join(dict.fromkeys(others))

        sold_count = self._count(text, "Sold")
        for_sale_count = self._count(text, "For sale")
        for_rent_count = self._count(text, "For rent")
        total_sales = (data.get("totalSales") or "").strip() or self._metric(lines, "Total sales")
        sales_12m = (data.get("sales12m") or "").strip() or self._metric(lines, "Sales last 12 months")
        price_range = (data.get("priceRange") or "").strip() or self._metric(lines, "Price range")
        avg_price = (data.get("avgPrice") or "").strip() or self._metric(lines, "Average price")
        close_deal = total_sales if total_sales else sold_count

        location = ""
        for l in lines[:60]:
            if re.match(r"^[A-Z][A-Za-z .'\-]+,\s*[A-Z]{2}$", l):
                location = l
                break

        row = {
            "first_name": first_name,
            "last_name": last_name,
            "brokerage": brokerage,
            "email": find_email(links, text, website),
            "phone": find_phone(links, text),
            "website": website,
            "close_deal": close_deal,
            "for_rent": for_rent_count,
            "for_sold": sold_count,
            "for_buy": for_sale_count,
            "facebook": social_dict["facebook"],
            "linkedin": social_dict["linkedin"],
            "instagram": social_dict["instagram"],
            "youtube": social_dict["youtube"],
            "twitter": social_dict["twitter"],
            "other_socials": social_dict["other_socials"],
            "profile_url": url,
            "price_range": price_range,
            "average_price": avg_price,
            "sales_last_12_months": sales_12m,
            "location": location or self.location,
            "search_location": self.location,
        }
        return row

    def scrape_all(self, links, xlsx_path, limit=None):
        rows, seen = [], set()
        if os.path.exists(xlsx_path):  # resume
            old = pd.read_excel(xlsx_path).fillna("")
            rows = old.to_dict("records")
            for r in rows:
                if "full_name" in r and not r.get("first_name"):
                    parts = str(r["full_name"]).split(None, 1)
                    r["first_name"] = parts[0] if parts else ""
                    r["last_name"] = parts[1] if len(parts) > 1 else ""
                if "total_sales" in r and not r.get("close_deal"):
                    r["close_deal"] = r.get("total_sales") or r.get("sold_items", "")
                if "for_rent_items" in r and not r.get("for_rent"):
                    r["for_rent"] = r.get("for_rent_items", "")
                if "sold_items" in r and not r.get("for_sold"):
                    r["for_sold"] = r.get("sold_items", "")
                if "for_sale_items" in r and not r.get("for_buy"):
                    r["for_buy"] = r.get("for_sale_items", "")
                if "social_links" in r and not r.get("facebook") and not r.get("linkedin"):
                    s_links = [s.strip() for s in str(r["social_links"]).split(",") if s.strip()]
                    for s in s_links:
                        sl = s.lower()
                        if "facebook.com" in sl and not r.get("facebook"):
                            r["facebook"] = s
                        elif "linkedin.com" in sl and not r.get("linkedin"):
                            r["linkedin"] = s
                        elif "instagram.com" in sl and not r.get("instagram"):
                            r["instagram"] = s
                        elif "youtube.com" in sl and not r.get("youtube"):
                            r["youtube"] = s
                        elif ("twitter.com" in sl or "x.com" in sl) and not r.get("twitter"):
                            r["twitter"] = s
            seen = {r["profile_url"] for r in rows if r.get("profile_url")}
            print(f"[resume] {len(rows)} rows already in xlsx")

        def _save(current_rows):
            df = pd.DataFrame(current_rows)
            ordered_cols = [c for c in config.COLUMNS if c in df.columns] + [c for c in df.columns if c not in config.COLUMNS]
            try:
                df.reindex(columns=ordered_cols).to_excel(xlsx_path, index=False)
            except PermissionError:
                print(f"[!] Warning: Cannot write to {xlsx_path} (is the file open in Excel?). Please close it so changes can be saved.")

        if limit and len(rows) >= limit:
            print(f"[done] already have {len(rows)} rows in xlsx (requested limit: {limit})")
            return rows

        todo = [u for u in links if u not in seen]
        for i, url in enumerate(todo, 1):
            if limit and len(rows) >= limit:
                print(f"[done] reached requested limit of {limit} leads")
                break
            try:
                row = validate_row(self.scrape_profile(url), seen)
                if row:
                    rows.append(row)
                    name_display = f"{row.get('first_name', '')} {row.get('last_name', '')}".strip()
                    count_str = f"({len(rows)}/{limit})" if limit else f"({len(rows)})"
                    print(f"[{i}/{len(todo)}] {name_display} | {row['email'] or '-'} | {row['phone'] or '-'} {count_str}")
            except Exception as e:
                print(f"[{i}/{len(todo)}] FAIL {url}: {e}")
            if i % config.SAVE_EVERY == 0:
                _save(rows)
            time.sleep(random.uniform(*config.PROFILE_DELAY))
        _save(rows)
        return rows


def run_scrape(location, xlsx_path, headless=False, max_pages=config.MAX_PAGES, limit=None):
    proxy = getattr(config, "PROXY", os.getenv("PROXY", None))
    is_linux = sys.platform.startswith("linux")
    use_xvfb = bool(headless and is_linux)
    use_headless = bool(headless and not use_xvfb)

    sb_kwargs = {
        "uc": True,
        "test": False,
        "locale_code": "en",
        "ad_block": False,
    }
    if proxy:
        sb_kwargs["proxy"] = proxy
    if use_xvfb:
        sb_kwargs["xvfb"] = True
    elif use_headless:
        sb_kwargs["headless"] = True

    with SB(**sb_kwargs) as sb:
        s = ZillowScraper(sb, location)
        s.search_location()
        links = s.collect_links(max_pages, limit=limit)
        print(f"[step 3 finished] {len(links)} profile links")
        return s.scrape_all(links, xlsx_path, limit=limit)
