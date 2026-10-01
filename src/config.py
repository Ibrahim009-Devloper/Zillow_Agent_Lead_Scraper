import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

START_URL = "https://www.zillow.com/professionals/real-estate-agent-reviews/?isSelling=true"
OUTPUT_ROOT = str(BASE_DIR / "output")
TEMP_DIR = str(BASE_DIR / "temp")


def _split(name):
    return [k.strip() for k in os.getenv(name, "").split(",") if k.strip()]


GEMINI_KEYS = _split("GEMINI_API_KEYS")
GROQ_KEYS = _split("GROQ_API_KEYS")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", str(BASE_DIR / "credentials" / "service_account.json"))
GOOGLE_PARENT_FOLDER_ID = os.getenv("GOOGLE_PARENT_FOLDER_ID", "")

MAX_PAGES = 200
PROFILE_DELAY = (2.0, 4.5)   # random sleep between profile visits
SAVE_EVERY = 10              # xlsx autosave interval

COLUMNS = [
    # Commercial Priority & Scoring
    "priority", "priority_reason", "lead_score", "lead_segment", "tier",
    # Agent Identity & Location
    "first_name", "last_name", "location", "search_location", "profile_url",
    # Data Quality & Verification
    "verification_status", "verification_date", "data_quality_score", "contact_completeness", "duplicate_status",
    # Direct Contact Details
    "email", "phone", "website",
    # Commercial Value Signals & Production
    "sales_volume_12m", "sales_last_12_months", "average_property_price", "average_price", "price_range",
    "close_deal", "for_sold", "for_buy", "for_rent",
    "luxury_agent_flag", "high_volume_agent_flag", "high_value_agent_flag",
    # Digital & Social Footprint
    "linkedin", "facebook", "instagram", "youtube", "twitter", "other_socials",
    # AI Lead Insights
    "relevance_score", "quality_score", "reason",
]
