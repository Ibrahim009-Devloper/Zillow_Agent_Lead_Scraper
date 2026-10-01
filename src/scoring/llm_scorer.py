import itertools
import json
import re
import time

import pandas as pd
import requests

from src import config

SYSTEM_PROMPT = """You are a B2B lead-qualification analyst evaluating verified, segmented, sales/property-data-enriched real-estate agent prospects.
You receive a JSON array of US real estate agent prospects scraped from Zillow with verified production metrics.
For EACH agent return evaluation based ONLY on the data given (do not invent facts):
- relevance_score (0-100): commercial relevance based on recent sales volume, property price tier, and market activity.
- quality_score (0-100): contact completeness and verification (direct phone, email, website, digital footprint).
- tier: "A" (high production/luxury with verified contacts), "B" (steady active producer), "C" (moderate/partial), "D" (limited data).
- reason: one concise sentence clearly explaining WHY this agent is commercially valuable as a sales prospect (production velocity, property value tier, contact verification), NOT merely who they are.
Return STRICT JSON only: an array with one object per input agent, same order, each with keys:
"profile_url", "relevance_score", "quality_score", "tier", "reason".
No markdown, no extra text."""

FIELDS = [
    "first_name", "last_name", "full_name", "email", "phone", "website",
    "close_deal", "for_rent", "for_sold", "for_buy",
    "facebook", "linkedin", "instagram", "youtube", "twitter", "other_socials",
    "profile_url", "sales_volume_12m", "sales_last_12_months", "average_property_price", "average_price",
    "price_range", "lead_segment", "priority", "location"
]


class KeyPool:
    def __init__(self):
        pool = [("gemini", k) for k in config.GEMINI_KEYS] + [("groq", k) for k in config.GROQ_KEYS]
        # interleave providers so load spreads across accounts
        g = [p for p in pool if p[0] == "gemini"]
        q = [p for p in pool if p[0] == "groq"]
        mixed = [x for pair in itertools.zip_longest(g, q) for x in pair if x]
        if not mixed:
            raise RuntimeError("No GEMINI_API_KEYS / GROQ_API_KEYS in .env")
        self.cycle = itertools.cycle(mixed)
        self.size = len(mixed)

    def next(self):
        return next(self.cycle)


def _call_gemini(key, payload):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent?key={key}"
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": payload}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }
    r = requests.post(url, json=body, timeout=90)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _call_groq(key, payload):
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": config.GROQ_MODEL,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT + '\nWrap the array as {"results": [...]}.'},
                {"role": "user", "content": payload},
            ],
            "response_format": {"type": "json_object"},
        },
        timeout=90,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _parse(txt):
    txt = re.sub(r"^```(?:json)?|```$", "", txt.strip(), flags=re.M).strip()
    data = json.loads(txt)
    if isinstance(data, dict):
        data = data.get("results") or next(iter(data.values()))
    return data


def score_batch(pool, batch):
    payload = json.dumps(batch, ensure_ascii=False)
    last = None
    for _ in range(pool.size * 2):  # rotate keys on failure / rate limit
        provider, key = pool.next()
        try:
            out = _call_gemini(key, payload) if provider == "gemini" else _call_groq(key, payload)
            return _parse(out)
        except Exception as e:
            last = e
            time.sleep(1.5)
    raise RuntimeError(f"all keys failed: {last}")


def score_xlsx(xlsx_path, batch_size=8):
    df = pd.read_excel(xlsx_path).fillna("")
    for c in ("relevance_score", "quality_score", "tier", "lead_score", "reason"):
        if c not in df.columns:
            df[c] = ""
        df[c] = df[c].astype(object)
    if not config.GEMINI_KEYS and not config.GROQ_KEYS:
        print("[llm] Notice: No GEMINI_API_KEYS or GROQ_API_KEYS configured in .env. Skipping AI scoring.")
        return df

    try:
        pool = KeyPool()
    except RuntimeError as e:
        print(f"[llm] Skipping AI scoring: {e}")
        return df

    todo = df.index[df["tier"] == ""].tolist()
    print(f"[llm] scoring {len(todo)} rows")
    for s in range(0, len(todo), batch_size):
        idx = todo[s:s + batch_size]
        batch_cols = [c for c in FIELDS if c in df.columns]
        batch = df.loc[idx, batch_cols].astype(str).to_dict("records")
        try:
            res = score_batch(pool, batch)
            by_url = {r.get("profile_url"): r for r in res}
            for i in idx:
                r = by_url.get(df.at[i, "profile_url"])
                if r:
                    for c in ("relevance_score", "quality_score", "tier", "lead_score", "reason"):
                        if c == "lead_score" and df.at[i, "lead_score"] != "":
                            continue
                        raw = r.get(c, "")
                        if c in ("tier", "reason"):
                            val = str(raw) if raw is not None else ""
                        else:
                            try:
                                val = int(raw) if raw != "" and raw is not None else ""
                            except (ValueError, TypeError):
                                val = str(raw) if raw is not None else ""
                        df.at[i, c] = val
        except Exception as e:
            print(f"[llm] batch failed: {e}")
        df.to_excel(xlsx_path, index=False)  # save after each batch
        print(f"[llm] {min(s + batch_size, len(todo))}/{len(todo)}")
    return df
