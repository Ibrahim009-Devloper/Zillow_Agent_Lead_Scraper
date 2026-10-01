"""
lead_enricher.py - Lead Value Enhancement, Data Quality, Segmentation & QA

Transforms scraped agent contacts into:
"verified, segmented, sales/property-data-enriched real-estate agent prospects"
"""

import os
import re
from datetime import datetime
import numpy as np
import pandas as pd

from src import config

FREE_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com",
    "icloud.com", "mail.com", "msn.com", "live.com", "ymail.com", "comcast.net",
    "sbcglobal.net", "verizon.net", "att.net", "me.com"
}

CANONICAL_COLUMN_MAP = {
    "first name": "first_name",
    "first_name": "first_name",
    "last name": "last_name",
    "last_name": "last_name",
    "full name": "name",
    "name": "name",
    "company / brokerage": "brokerage",
    "brokerage / company": "brokerage",
    "brokerage": "brokerage",
    "company": "brokerage",
    "business name": "brokerage",
    "location": "location",
    "professional email": "email",
    "email": "email",
    "phone": "phone",
    "phone number": "phone",
    "linkedin url": "linkedin",
    "linkedin": "linkedin",
    "website": "website",
    "website url": "website",
    "zillow profile url": "profile_url",
    "zillow profile": "profile_url",
    "profile_url": "profile_url",
    "sales volume (12 months)": "sales_volume_12m",
    "sales — last 12 months": "sales_volume_12m",
    "sales_volume_12m": "sales_volume_12m",
    "sales_last_12_months": "sales_volume_12m",
    "average property price": "average_property_price",
    "average_property_price": "average_property_price",
    "average_price": "average_property_price",
    "price range": "price_range",
    "price_range": "price_range",
    "agent segment": "lead_segment",
    "agent type / segment": "lead_segment",
    "lead_segment": "lead_segment",
    "lead score": "lead_score",
    "lead_score": "lead_score",
    "priority": "priority",
    "ai valuation reason": "reason",
    "reason": "reason",
    "priority reason": "priority_reason",
    "priority_reason": "priority_reason",
    "verification status": "verification_status",
    "verification_status": "verification_status",
    "verification date": "verification_date",
    "verification_date": "verification_date",
    "data quality score": "data_quality_score",
    "data_quality_score": "data_quality_score",
    "contact completeness": "contact_completeness",
    "contact_completeness": "contact_completeness",
    "duplicate status": "duplicate_status",
    "duplicate_status": "duplicate_status",
}


def get_canonical_key(col_name):
    norm = re.sub(r"\.\d+$", "", str(col_name)).strip().lower()
    norm_dash = re.sub(r"[—–\-\ufffd?]+", " ", norm)
    tokens = set(norm_dash.split())

    if "first" in tokens and "name" in tokens:
        return "first_name"
    if "last" in tokens and "name" in tokens:
        return "last_name"
    if "brokerage" in tokens or "company" in tokens:
        return "brokerage"
    if "location" in tokens:
        return "location"
    if "email" in tokens:
        return "email"
    if "phone" in tokens:
        return "phone"
    if "linkedin" in tokens:
        return "linkedin"
    if "website" in tokens:
        return "website"
    if "profile" in tokens:
        return "profile_url"
    if "sales" in tokens and ("12" in tokens or "months" in tokens or "volume" in tokens or "last" in tokens):
        return "sales_volume_12m"
    if "price" in tokens and ("average" in tokens or "avg" in tokens or "property" in tokens):
        return "average_property_price"
    if "price" in tokens and "range" in tokens:
        return "price_range"
    if "segment" in tokens or "type" in tokens:
        return "lead_segment"
    if "score" in tokens and "quality" not in tokens and "relevance" not in tokens:
        return "lead_score"
    if "reason" in tokens or "valuation" in tokens:
        return "reason"
    return CANONICAL_COLUMN_MAP.get(norm, col_name)


def normalize_dataframe_columns(df):
    new_cols = {}
    for col in df.columns:
        target = get_canonical_key(col)
        new_cols[col] = target

    renamed_df = df.rename(columns=new_cols)
    res_df = pd.DataFrame(index=df.index)
    for c in renamed_df.columns.unique():
        sub = renamed_df.loc[:, renamed_df.columns == c]
        if isinstance(sub, pd.DataFrame) and sub.shape[1] > 1:
            combined = sub.bfill(axis=1).iloc[:, 0]
            res_df[c] = combined
        else:
            res_df[c] = renamed_df[c]
    return res_df


def extract_brokerage_from_domain(email="", website=""):
    domain = ""
    if email and "@" in str(email):
        domain = str(email).split("@")[-1].lower().strip()
    elif website and "http" in str(website):
        m = re.search(r"https?://(?:www\.)?([^/]+)", str(website).lower())
        if m:
            domain = m.group(1).strip()

    if not domain or domain in FREE_EMAIL_DOMAINS:
        return ""

    known_brokers = {
        "windermere.com": "Windermere Real Estate",
        "compass.com": "Compass",
        "redfin.com": "Redfin",
        "elliman.com": "Douglas Elliman",
        "sothebysrealty.com": "Sotheby's International Realty",
        "onesothebysrealty.com": "ONE Sotheby's International Realty",
        "resf.com": "RESF (Real Estate Sales Force)",
        "onepathrealty.com": "ONEPATH Realty",
        "chezre.com": "CHEZ Realty",
        "luxeknows.com": "LUXE Properties",
        "nestnwg.com": "Nest Northwest Group",
        "raintownrealty.com": "Raintown Realty",
        "exprealty.com": "eXp Realty",
        "kw.com": "Keller Williams Realty",
        "coldwellbanker.com": "Coldwell Banker",
        "remax.com": "RE/MAX",
        "century21.com": "Century 21",
        "serhant.com": "SERHANT.",
        "theagencyre.com": "The Agency",
    }
    if domain in known_brokers:
        return known_brokers[domain]

    root = domain.split(".")[0]
    if any(k in root for k in ["realty", "properties", "group", "realestate", "broker"]):
        words = re.findall(r"[a-z]+", root)
        return " ".join(w.capitalize() for w in words)
    return ""


def clean_person_name_and_brokerage(first_name, last_name, existing_brokerage="", email="", website=""):
    raw_fn = str(first_name or "").strip()
    raw_ln = str(last_name or "").strip()
    b = str(existing_brokerage or "").strip()
    if b.lower() in ("nan", "none"):
        b = ""

    # 1. First, check if brokerage can be extracted from raw_ln if b is empty
    if not b:
        if " - " in raw_ln:
            parts = raw_ln.split(" - ", 1)
            raw_ln = parts[0].strip()
            b = parts[1].strip()
        elif " at " in raw_ln.lower():
            parts = re.split(r"\s+at\s+", raw_ln, flags=re.I)
            raw_ln = parts[0].strip()
            b = parts[1].strip()
        elif "-" in raw_ln and any(k in raw_ln for k in ["Sotheby", "Compass", "RESF", "Realty", "Broker"]):
            parts = raw_ln.split("-", 1)
            raw_ln = parts[0].strip()
            b = parts[1].strip()

    # If the candidate was a full team/brokerage entity (e.g. "The Opes Group", "Century 21")
    full_cand = f"{raw_fn} {raw_ln}".strip()
    if any(k in full_cand for k in ["Realty", "Real Estate", "Brokerage", "Century 21", "RE/MAX"]):
        if not b:
            b = full_cand

    # Check email / website domain if still empty
    if not b and (email or website):
        b = extract_brokerage_from_domain(email, website)

    # 2. Clean last name
    clean_ln = re.sub(r"\(.*?\)", "", raw_ln).strip()
    clean_ln = re.sub(r'[\",]', "", clean_ln).strip()
    clean_ln = re.sub(r"\s*[-–|/]\s*.*$", "", clean_ln)
    clean_ln = re.split(r"\s+at\s+", clean_ln, flags=re.I)[0]
    clean_ln = re.split(r"\s+and\s+", clean_ln, flags=re.I)[0]
    clean_ln = re.split(r"\s+&\s+", clean_ln)[0]
    clean_ln = clean_ln.split(",")[0].strip()

    # Strip certifications and junk titles
    clean_ln = re.sub(r"\b(PA|P\.A\.|MBA|CRS|PSA|LLC|Inc|REALTOR|Realtor|Broker|Agent|Top Producer|TOP PRODUCER|Owner|Junior|Jr|SR|Sr)\b", "", clean_ln, flags=re.I).strip()

    # Strip marketing buzzwords
    junk_regex = r"(Top Florida Broker|South Florida|Miami Real Estate Agent|Real Estate Expert|RE Expert|Real Estate|Realty|Brokerage|Group|Team|Collective|Best .* Realtor|5-Star.*)$"
    m_junk = re.search(junk_regex, clean_ln, re.I)
    if m_junk:
        if not b:
            b = m_junk.group(0).strip()
        clean_ln = re.sub(junk_regex, "", clean_ln, flags=re.I).strip()

    tokens = clean_ln.split()
    if not tokens:
        final_ln = ""
    elif len(tokens) == 1:
        final_ln = tokens[0]
    else:
        if tokens[0].lower() in ("de", "van", "von", "del", "da") and len(tokens) >= 2:
            if len(tokens) >= 3 and tokens[1].lower() == "la":
                final_ln = f"{tokens[0]} {tokens[1]} {tokens[2]}"
            else:
                final_ln = f"{tokens[0]} {tokens[1]}"
        elif len(tokens[0].rstrip(".")) == 1:
            final_ln = tokens[1]
        else:
            final_ln = tokens[0]

    return raw_fn, final_ln, b


def parse_price(val):
    if val is None or pd.isna(val):
        return None
    s = str(val).strip().replace("$", "").replace(",", "")
    if not s or s.lower() in ("nan", "none", ""):
        return None
    m = re.search(r"([\d\.]+)\s*([KkMmBb])?", s)
    if not m:
        return None
    try:
        num = float(m.group(1))
        unit = (m.group(2) or "").upper()
        if unit == "K":
            num *= 1_000
        elif unit == "M":
            num *= 1_000_000
        elif unit == "B":
            num *= 1_000_000_000
        return int(num)
    except (ValueError, TypeError):
        return None


def parse_max_price_range(val):
    if val is None or pd.isna(val):
        return None
    parts = re.split(r"[-–]", str(val))
    if len(parts) >= 2:
        return parse_price(parts[1])
    return parse_price(parts[0])


def parse_numeric_sales(val):
    if val is None or pd.isna(val):
        return None
    s = str(val).strip().replace(",", "")
    m = re.search(r"\d+", s)
    return int(m.group(0)) if m else None


def is_professional_email(email):
    if not email or pd.isna(email):
        return False
    e = str(email).strip().lower()
    if "@" not in e:
        return False
    domain = e.split("@", 1)[1]
    return domain not in FREE_EMAIL_DOMAINS


def has_value(val):
    if val is None or pd.isna(val):
        return False
    s = str(val).strip()
    return bool(s and s.lower() not in ("nan", "none", "", "-"))


def calculate_lead_score(row):
    """
    Transparent 0–100 lead score based ONLY on available verified data.
    Never increases score simply because data is missing or unverified.
    """
    score = 0

    # 1. Contactability & Verification (up to 40 pts)
    has_phone = has_value(row.get("phone"))
    has_email = has_value(row.get("email"))
    has_web = has_value(row.get("website"))
    has_social = any(has_value(row.get(s)) for s in ("linkedin", "facebook", "instagram", "youtube", "twitter", "other_socials"))

    if has_phone:
        score += 15
    if has_email:
        score += 15
        if is_professional_email(row.get("email")):
            score += 5
    if has_web or has_social:
        score += 5

    # 2. Sales Volume & Commercial Track Record (up to 40 pts)
    sales_12m = parse_numeric_sales(row.get("sales_volume_12m") if has_value(row.get("sales_volume_12m")) else row.get("sales_last_12_months"))
    close_deal = parse_numeric_sales(row.get("close_deal"))

    if sales_12m is not None:
        if sales_12m >= 30:
            score += 30
        elif sales_12m >= 15:
            score += 22
        elif sales_12m >= 5:
            score += 15
        elif sales_12m >= 1:
            score += 8
    elif close_deal is not None:
        # Fallback if 12m sales is missing but lifetime deals are present
        if close_deal >= 100:
            score += 20
        elif close_deal >= 30:
            score += 12
        elif close_deal >= 10:
            score += 6

    if close_deal is not None:
        if close_deal >= 100:
            score += 10
        elif close_deal >= 30:
            score += 7
        elif close_deal >= 10:
            score += 4

    # 3. Market Property Value & Price Tier (up to 20 pts)
    avg_price = parse_price(row.get("average_property_price") if has_value(row.get("average_property_price")) else row.get("average_price"))
    if avg_price is not None:
        if avg_price >= 1_500_000:
            score += 20
        elif avg_price >= 1_000_000:
            score += 16
        elif avg_price >= 600_000:
            score += 12
        elif avg_price >= 350_000:
            score += 8
        elif avg_price > 0:
            score += 4

    return min(100, max(0, score))


def determine_segment(row):
    """
    Market-agnostic segmentation (works across any US market).
    """
    is_luxury = row.get("luxury_agent_flag") == "Yes"
    is_high_vol = row.get("high_volume_agent_flag") == "Yes"
    is_high_val = row.get("high_value_agent_flag") == "Yes"

    sales_12m = parse_numeric_sales(row.get("sales_volume_12m") if has_value(row.get("sales_volume_12m")) else row.get("sales_last_12_months"))
    close_deal = parse_numeric_sales(row.get("close_deal"))
    avg_price = parse_price(row.get("average_property_price") if has_value(row.get("average_property_price")) else row.get("average_price"))
    max_price = parse_max_price_range(row.get("price_range"))

    if is_luxury or (avg_price and avg_price >= 1_200_000) or (max_price and max_price >= 2_000_000):
        return "Luxury"
    if is_high_vol or (sales_12m and sales_12m >= 20) or (close_deal and close_deal >= 60):
        return "High Volume"
    if is_high_val or (avg_price and avg_price >= 750_000 and ((sales_12m and sales_12m >= 10) or (close_deal and close_deal >= 25))):
        return "High Value"

    has_activity = (sales_12m is not None and sales_12m > 0) or (close_deal is not None and close_deal > 0) or (avg_price is not None and avg_price > 0)
    has_contact = has_value(row.get("phone")) or has_value(row.get("email"))

    if has_activity or has_contact:
        return "General"
    return "Insufficient Data"


def determine_priority_and_reason(row):
    """
    Determines commercial priority (High, Medium, Low) and supported priority reason.
    """
    lead_score = row.get("lead_score", 0)
    segment = row.get("lead_segment", "General")
    sales_12m = row.get("sales_volume_12m")
    close_deal = parse_numeric_sales(row.get("close_deal"))
    avg_price = row.get("average_property_price")
    v_status = row.get("verification_status", "Unverified")

    reasons = []

    if sales_12m and sales_12m >= 20:
        reasons.append(f"High transaction volume ({sales_12m} sales/12m)")
    elif close_deal and close_deal >= 50:
        reasons.append(f"Extensive deal history ({close_deal} closed deals)")
    elif sales_12m and sales_12m >= 5:
        reasons.append(f"Active producer ({sales_12m} sales/12m)")

    if avg_price and avg_price >= 1_000_000:
        reasons.append(f"Luxury property focus (${avg_price:,.0f} avg)")
    elif avg_price and avg_price >= 600_000:
        reasons.append(f"High-value market activity (${avg_price:,.0f} avg)")

    if v_status == "Verified":
        reasons.append("complete verified contact profile")
    elif v_status == "Partially Verified":
        reasons.append("verified direct contact channel")

    if not reasons:
        if segment == "Insufficient Data":
            reason = "Limited transaction history and unverified contact details"
        else:
            reason = "Standard market presence with basic contact profile"
    else:
        reason = " | ".join(reasons)

    # Priority determination
    if lead_score >= 70 or (segment in ("Luxury", "High Volume") and v_status == "Verified"):
        priority = "High"
    elif lead_score >= 45 or (v_status in ("Verified", "Partially Verified") and (sales_12m or close_deal)):
        priority = "Medium"
    else:
        priority = "Low"

    return priority, reason




def enrich_dataframe(df):
    """
    Enriches dataframe with all required fields in-place:
    1. Data Quality Fields
    2. Agent Value Signals
    3. Lead Segmentation
    4. Lead Score
    5. Commercial Priority & Priority Reason
    """
    df = normalize_dataframe_columns(df)
    today_str = datetime.now().strftime("%Y-%m-%d")

    # Track duplicates across profile_url
    seen_urls = set()
    dup_statuses = []
    for _, row in df.iterrows():
        url = str(row.get("profile_url", "")).strip().lower()
        if url and url in seen_urls:
            dup_statuses.append("Duplicate")
        else:
            dup_statuses.append("Unique")
            if url:
                seen_urls.add(url)
    df["duplicate_status"] = dup_statuses

    # 1. Verification & Contact Completeness
    v_statuses = []
    v_dates = []
    completeness_list = []
    data_quality_scores = []

    for _, row in df.iterrows():
        has_phone = has_value(row.get("phone"))
        has_email = has_value(row.get("email"))
        has_web = has_value(row.get("website"))
        has_social = any(has_value(row.get(s)) for s in ("linkedin", "facebook", "instagram", "youtube", "twitter", "other_socials"))

        # Verification status
        if has_phone and has_email:
            v_status = "Verified"
        elif has_phone or has_email:
            v_status = "Partially Verified"
        else:
            v_status = "Unverified"
        v_statuses.append(v_status)
        v_dates.append(today_str)

        # Contact completeness
        channels_count = sum([has_phone, has_email, has_web, has_social])
        if channels_count == 4:
            c_label = "Complete"
        elif channels_count == 3:
            c_label = "High"
        elif channels_count == 2:
            c_label = "Moderate"
        elif channels_count == 1:
            c_label = "Basic"
        else:
            c_label = "Incomplete"
        completeness_list.append(c_label)

        # Data quality score (0-100)
        q_score = 0
        if has_phone:
            q_score += 25
        if has_email:
            q_score += 25
            if is_professional_email(row.get("email")):
                q_score += 10
        has_name = bool(has_value(row.get("first_name")) and has_value(row.get("last_name")))
        if has_name:
            q_score += 10
        if has_web:
            q_score += 10
        if has_value(row.get("profile_url")):
            q_score += 10
        if has_social:
            q_score += 10
        data_quality_scores.append(min(100, q_score))

    df["verification_status"] = v_statuses
    df["verification_date"] = v_dates
    df["data_quality_score"] = data_quality_scores
    df["contact_completeness"] = completeness_list

    # 2. Agent Value Signals
    sales_12m_list = []
    avg_price_list = []
    lux_flags = []
    high_vol_flags = []
    high_val_flags = []

    for _, row in df.iterrows():
        s_12m_val = row.get("sales_volume_12m") if has_value(row.get("sales_volume_12m")) else row.get("sales_last_12_months")
        s_12m = parse_numeric_sales(s_12m_val)
        sales_12m_list.append(s_12m if s_12m is not None else np.nan)

        avg_p_val = row.get("average_property_price") if has_value(row.get("average_property_price")) else row.get("average_price")
        avg_p = parse_price(avg_p_val)
        avg_price_list.append(avg_p if avg_p is not None else np.nan)

        max_range_p = parse_max_price_range(row.get("price_range"))
        close_d = parse_numeric_sales(row.get("close_deal"))

        # Luxury Agent Flag
        is_lux = bool((avg_p and avg_p >= 1_200_000) or (max_range_p and max_range_p >= 2_000_000))
        lux_flags.append("Yes" if is_lux else "No")

        # High Volume Agent Flag
        is_high_vol = bool((s_12m and s_12m >= 20) or (close_d and close_d >= 60))
        high_vol_flags.append("Yes" if is_high_vol else "No")

        # High Value Agent Flag
        is_high_val = bool(is_lux or (avg_p and avg_p >= 750_000 and ((s_12m and s_12m >= 10) or (close_d and close_d >= 25))))
        high_val_flags.append("Yes" if is_high_val else "No")

    df["sales_volume_12m"] = sales_12m_list
    df["average_property_price"] = avg_price_list
    df["luxury_agent_flag"] = lux_flags
    df["high_volume_agent_flag"] = high_vol_flags
    df["high_value_agent_flag"] = high_val_flags

    # 3. Lead Segmentation
    segments = []
    for _, row in df.iterrows():
        segments.append(determine_segment(row))
    df["lead_segment"] = segments

    # 4. Lead Score
    lead_scores = []
    for _, row in df.iterrows():
        lead_scores.append(calculate_lead_score(row))
    df["lead_score"] = lead_scores

    # 5. Priority & Priority Reason
    priorities = []
    priority_reasons = []
    for _, row in df.iterrows():
        pri, reason = determine_priority_and_reason(row)
        priorities.append(pri)
        priority_reasons.append(reason)
    df["priority"] = priorities
    df["priority_reason"] = priority_reasons

    # Reorder columns logically
    ordered = [c for c in config.COLUMNS if c in df.columns] + [c for c in df.columns if c not in config.COLUMNS]
    return df.reindex(columns=ordered)


def enrich_xlsx(xlsx_path):
    """
    Enriches an existing Excel file with data quality, value signals, segmentation, and priority.
    """
    if not os.path.exists(xlsx_path):
        return None

    df = pd.read_excel(xlsx_path).fillna("")
    df_enriched = enrich_dataframe(df)

    # Cast to object to avoid strict string dtype errors in pandas
    for col in df_enriched.columns:
        df_enriched[col] = df_enriched[col].astype(object)

    try:
        df_enriched.to_excel(xlsx_path, index=False)
    except PermissionError:
        print(f"[!] Warning: Cannot write to {xlsx_path} (is it open in Excel?).")
        return df_enriched

    format_and_style_excel(xlsx_path)
    return df_enriched


def format_and_style_excel(xlsx_path):
    """
    Arranges columns in the exact user-specified order and applies:
    - Deep Navy colored header row (#1B365D) with bold white text
    - Official Excel Table formatting with zebra striping and auto-filters
    - Visual status and priority badges (High=Green, Medium=Amber, Verified=Blue)
    - Currency and numeric cell formatting
    - Dynamic column width auto-fitting
    - Frozen top row
    """
    if not os.path.exists(xlsx_path):
        return

    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.table import Table, TableStyleInfo

    df = pd.read_excel(xlsx_path).fillna("")
    df = normalize_dataframe_columns(df)

    # Fallback to name or full_name if first_name is missing
    if "first_name" not in df.columns or (df["first_name"] == "").all() or df["first_name"].isna().all():
        name_col = None
        for cand in ["name", "full_name"]:
            if cand in df.columns and not df[cand].isna().all():
                name_col = cand
                break
        if name_col:
            for i, val in df[name_col].items():
                parts = str(val).split(None, 1)
                df.at[i, "first_name"] = parts[0] if parts else ""
                df.at[i, "last_name"] = parts[1] if len(parts) > 1 else ""

    # Clean first_name, last_name, and brokerage for all rows
    if "brokerage" not in df.columns:
        df["brokerage"] = ""
    for i, r in df.iterrows():
        fn = str(r.get("first_name", "")).strip()
        ln = str(r.get("last_name", "")).strip()
        b = str(r.get("brokerage", "")).strip()
        em = str(r.get("email", "")).strip()
        web = str(r.get("website", "")).strip()

        n_fn, n_ln, n_b = clean_person_name_and_brokerage(fn, ln, b, email=em, website=web)
        df.at[i, "first_name"] = n_fn
        df.at[i, "last_name"] = n_ln
        df.at[i, "brokerage"] = n_b

        # Ensure AI Valuation Reason is populated
        reason_val = str(r.get("reason", "")).strip()
        if not reason_val or reason_val.lower() in ("nan", "none", ""):
            pri_reason = str(r.get("priority_reason", "")).strip()
            df.at[i, "reason"] = pri_reason if pri_reason and pri_reason.lower() not in ("nan", "none") else "Active licensed real estate agent"

    # Ensure sales_volume_12m, average_property_price, lead_segment, and lead_score are populated
    for i, r in df.iterrows():
        # Sales volume
        s_val = r.get("sales_volume_12m")
        if s_val is None or pd.isna(s_val) or str(s_val).strip() in ("", "nan", "none"):
            s_cand = r.get("sales_last_12_months") or r.get("sales_volume") or r.get("close_deal")
            s_parsed = parse_numeric_sales(s_cand)
            df.at[i, "sales_volume_12m"] = s_parsed if s_parsed is not None else ""

        # Average property price
        p_val = r.get("average_property_price")
        if p_val is None or pd.isna(p_val) or str(p_val).strip() in ("", "nan", "none"):
            p_cand = r.get("average_price") or r.get("price_range")
            p_parsed = parse_price(p_cand)
            df.at[i, "average_property_price"] = p_parsed if p_parsed is not None else ""

        # Lead segment
        seg_val = r.get("lead_segment")
        if seg_val is None or pd.isna(seg_val) or str(seg_val).strip() in ("", "nan", "none"):
            df.at[i, "lead_segment"] = determine_segment(df.loc[i])

        # Lead score
        score_val = r.get("lead_score")
        if score_val is None or pd.isna(score_val) or str(score_val).strip() in ("", "nan", "none"):
            df.at[i, "lead_score"] = calculate_lead_score(df.loc[i])

    # Exact user-requested 14 columns
    target_mapping = [
        ("first_name", "First Name"),
        ("last_name", "Last Name"),
        ("brokerage", "Brokerage / Company"),
        ("location", "Location"),
        ("email", "Email"),
        ("phone", "Phone"),
        ("linkedin", "LinkedIn"),
        ("website", "Website"),
        ("profile_url", "Zillow Profile"),
        ("sales_volume_12m", "Sales — Last 12 Months"),
        ("average_property_price", "Average Property Price"),
        ("lead_segment", "Agent Type / Segment"),
        ("lead_score", "Lead Score"),
        ("reason", "AI Valuation Reason"),
    ]

    selected_cols = []
    rename_dict = {}
    for orig, display in target_mapping:
        if orig in df.columns:
            selected_cols.append(orig)
            rename_dict[orig] = display
        else:
            df[orig] = ""
            selected_cols.append(orig)
            rename_dict[orig] = display

    df_formatted = df[selected_cols].rename(columns=rename_dict)
    df_formatted.to_excel(xlsx_path, index=False, engine="openpyxl")

    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb.active
    ws.title = "Agent Leads"

    # Header styling: Deep Navy Blue (#1B365D) with White Bold text
    header_fill = PatternFill(start_color="1B365D", end_color="1B365D", fill_type="solid")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")

    body_font = Font(name="Segoe UI", size=10, color="1F2937")
    bold_body_font = Font(name="Segoe UI", size=10, bold=True, color="1F2937")

    align_left = Alignment(horizontal="left", vertical="center")
    align_center = Alignment(horizontal="center", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")
    align_header = Alignment(horizontal="center", vertical="center", wrap_text=True)

    thin_border_side = Side(border_style="thin", color="E2E8F0")
    border_cell = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)
    header_border = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=Side(border_style="medium", color="0F172A"))

    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    white_fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")

    num_rows = ws.max_row
    num_cols = ws.max_column

    ws.row_dimensions[1].height = 28

    for col_idx in range(1, num_cols + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = align_header
        cell.border = header_border

    col_names = [ws.cell(row=1, column=c).value for c in range(1, num_cols + 1)]

    for r_idx in range(2, num_rows + 1):
        ws.row_dimensions[r_idx].height = 22
        is_even = (r_idx % 2 == 0)
        row_fill = zebra_fill if is_even else white_fill

        for c_idx in range(1, num_cols + 1):
            cell = ws.cell(row=r_idx, column=c_idx)
            c_name = col_names[c_idx - 1]
            cell.font = body_font
            cell.border = border_cell
            cell.fill = row_fill

            val = str(cell.value or "").strip()

            if c_name in ("Phone", "LinkedIn"):
                cell.alignment = align_center
            elif c_name in ("Lead Score", "Sales — Last 12 Months"):
                cell.alignment = align_center
                if val.isdigit():
                    cell.value = int(val)
                    cell.number_format = "#,##0"
                    cell.font = bold_body_font
            elif c_name == "Average Property Price":
                cell.alignment = align_right
                try:
                    num_val = float(str(val).replace("$", "").replace(",", ""))
                    cell.value = int(num_val)
                    cell.number_format = "$#,##0"
                except (ValueError, TypeError):
                    pass
            elif c_name == "Agent Type / Segment":
                cell.alignment = align_center
                cell.font = bold_body_font
            else:
                cell.alignment = align_left

    # Add Official Excel Table
    table_ref = f"A1:{get_column_letter(num_cols)}{num_rows}"
    tab = Table(displayName="RealEstateProspectsTable", ref=table_ref)
    style = TableStyleInfo(name="TableStyleMedium9", showFirstColumn=False, showLastColumn=False, showRowStripes=True, showColumnStripes=False)
    tab.tableStyleInfo = style
    ws.add_table(tab)

    ws.freeze_panes = "A2"
    ws.views.sheetView[0].showGridLines = True

    for col_idx in range(1, num_cols + 1):
        col_letter = get_column_letter(col_idx)
        max_len = 0
        for r_idx in range(1, num_rows + 1):
            val = str(ws.cell(row=r_idx, column=col_idx).value or "")
            max_len = max(max_len, len(val))
        ws.column_dimensions[col_letter].width = max(max_len + 4, 13)

    try:
        wb.save(xlsx_path)
    except PermissionError:
        print(f"[!] Warning: Cannot write to {xlsx_path} (is the file open in Excel?).")



def print_qa_summary(xlsx_path):
    """
    Prints a commercial QA audit report summarizing lead value, coverage, and segmentation.
    """
    if not os.path.exists(xlsx_path):
        return

    df = pd.read_excel(xlsx_path).fillna("")
    df = normalize_dataframe_columns(df)
    total = len(df)
    if total == 0:
        print("[qa] No records to audit.")
        return

    # Counts
    v_status_counts = df["verification_status"].value_counts().to_dict() if "verification_status" in df.columns else {}
    verified = v_status_counts.get("Verified", 0)
    partial = v_status_counts.get("Partially Verified", 0)

    has_email = df["email"].apply(has_value).sum() if "email" in df.columns else 0
    has_phone = df["phone"].apply(has_value).sum() if "phone" in df.columns else 0
    has_web = df["website"].apply(has_value).sum() if "website" in df.columns else 0
    has_profile = df["profile_url"].apply(has_value).sum() if "profile_url" in df.columns else 0
    has_social = df.apply(lambda r: any(has_value(r.get(s)) for s in ("linkedin", "facebook", "instagram", "youtube", "twitter", "other_socials")), axis=1).sum()

    dup_count = (df["duplicate_status"] == "Duplicate").sum() if "duplicate_status" in df.columns else 0

    # Segments & flags
    seg_counts = df["lead_segment"].value_counts().to_dict() if "lead_segment" in df.columns else {}
    pri_counts = df["priority"].value_counts().to_dict() if "priority" in df.columns else {}
    comp_counts = df["contact_completeness"].value_counts().to_dict() if "contact_completeness" in df.columns else {}

    avg_qual = df["data_quality_score"].mean() if "data_quality_score" in df.columns else 0
    avg_score = df["lead_score"].mean() if "lead_score" in df.columns else 0

    print("\n" + "=" * 80)
    print("[QA] LEAD VALUE & DATA QUALITY AUDIT REPORT")
    print("=" * 80)
    print("Output Type: Verified, segmented, sales/property-data-enriched real-estate agent prospects")
    print("-" * 80)
    print(f"Total Prospects Scraped:        {total}")
    print(f"Fully Verified (Phone + Email): {verified} ({verified / total * 100:.1f}%)")
    print(f"Partially Verified (Phone|Mail):{partial} ({partial / total * 100:.1f}%)")
    print(f"Unique Leads:                   {total - dup_count} ({(total - dup_count) / total * 100:.1f}%)")
    print(f"Duplicate Profiles:             {dup_count}")
    print("\n[+] Verified Contact Coverage:")
    print(f"  * Direct Phone Numbers:       {has_phone}/{total} ({has_phone / total * 100:.1f}%)")
    print(f"  * Email Addresses:            {has_email}/{total} ({has_email / total * 100:.1f}%)")
    print(f"  * Websites / Domains:         {has_web}/{total} ({has_web / total * 100:.1f}%)")
    print(f"  * Social Media Profiles:      {has_social}/{total} ({has_social / total * 100:.1f}%)")
    print(f"  * Zillow Profile Coverage:    {has_profile}/{total} ({has_profile / total * 100:.1f}%)")
    print("\n[+] Commercial Value & Market Segmentation:")
    print(f"  * Luxury Segment:             {seg_counts.get('Luxury', 0)} ({seg_counts.get('Luxury', 0) / total * 100:.1f}%)")
    print(f"  * High Volume Segment:        {seg_counts.get('High Volume', 0)} ({seg_counts.get('High Volume', 0) / total * 100:.1f}%)")
    print(f"  * High Value Market Activity: {seg_counts.get('High Value', 0)} ({seg_counts.get('High Value', 0) / total * 100:.1f}%)")
    print(f"  * General Active Agents:      {seg_counts.get('General', 0)} ({seg_counts.get('General', 0) / total * 100:.1f}%)")
    print(f"  * Insufficient Data:          {seg_counts.get('Insufficient Data', 0)} ({seg_counts.get('Insufficient Data', 0) / total * 100:.1f}%)")
    print("\n[+] Commercial Outreach Priority:")
    print(f"  * High Priority Prospects:    {pri_counts.get('High', 0)} ({pri_counts.get('High', 0) / total * 100:.1f}%)")
    print(f"  * Medium Priority Prospects:  {pri_counts.get('Medium', 0)} ({pri_counts.get('Medium', 0) / total * 100:.1f}%)")
    print(f"  * Low Priority Prospects:     {pri_counts.get('Low', 0)} ({pri_counts.get('Low', 0) / total * 100:.1f}%)")
    print("\n[+] Quality & Completeness Breakdown:")
    print(f"  * Complete (4 Channels):      {comp_counts.get('Complete', 0)}")
    print(f"  * High (3 Channels):          {comp_counts.get('High', 0)}")
    print(f"  * Moderate (2 Channels):      {comp_counts.get('Moderate', 0)}")
    print(f"  * Basic (1 Channel):          {comp_counts.get('Basic', 0)}")
    print(f"  * Average Data Quality Score: {avg_qual:.1f} / 100")
    print(f"  * Average Commercial Score:   {avg_score:.1f} / 100")
    print("=" * 80 + "\n")
