import argparse
import os

from src import config
from src.scraper.scraper import run_scrape, slug


def main():
    ap = argparse.ArgumentParser(description="Zillow agent lead scraper")
    ap.add_argument("--location", default=None, help='e.g. "Chicago, IL" or ZIP')
    ap.add_argument("--limit", type=int, default=None, help="Maximum number of leads to scrape (default: all)")
    ap.add_argument("--headless", action="store_true", help="(uc mode detects headless more; prefer headed)")
    ap.add_argument("--max-pages", type=int, default=config.MAX_PAGES)
    ap.add_argument("--skip-scrape", action="store_true", help="reuse existing xlsx")
    ap.add_argument("--skip-llm", action="store_true")
    ap.add_argument("--skip-sheets", action="store_true")
    a = ap.parse_args()

    if not a.location:
        loc = input("Enter target location (e.g. 'Chicago, IL' or ZIP): ").strip()
        while not loc:
            loc = input("Location cannot be empty. Please enter location: ").strip()
        a.location = loc

    if a.limit is None:
        count_input = input("How many leads/data do you need? (Press Enter to grab all): ").strip()
        if count_input:
            try:
                val = int(count_input)
                if val > 0:
                    a.limit = val
            except ValueError:
                print("[!] Invalid number entered. Grabbing all data.")
                a.limit = None

    out_dir = os.path.join(config.OUTPUT_ROOT, a.location, "agent_lead")
    os.makedirs(out_dir, exist_ok=True)
    xlsx = os.path.join(out_dir, f"{slug(a.location)}_agents.xlsx")

    if not a.skip_scrape:
        run_scrape(a.location, xlsx, headless=a.headless, max_pages=a.max_pages, limit=a.limit)
        print(f"[saved] {xlsx}")

    # 1. Enrich leads: data quality, value signals, segmentation, lead score, and priority
    from src.enrichment.lead_enricher import enrich_xlsx, print_qa_summary, format_and_style_excel
    enrich_xlsx(xlsx)

    # 2. Optional AI qualitative scoring
    if not a.skip_llm:
        from src.scoring.llm_scorer import score_xlsx
        try:
            score_xlsx(xlsx)
            format_and_style_excel(xlsx)
        except Exception as e:
            print(f"[llm] AI scoring skipped/failed: {e}")

    # 3. Output QA Audit & Commercial Positioning Summary
    print_qa_summary(xlsx)

    # 4. Upload to Google Sheets
    if not a.skip_sheets:
        from src.export.google_sheets import upload_to_sheets
        try:
            print("[sheet]", upload_to_sheets(xlsx, a.location))
        except Exception as e:
            print(f"[sheet] Google Sheets upload skipped/failed: {e}")


if __name__ == "__main__":
    main()
