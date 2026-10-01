# Zillow Agent Lead Scraper

## Setup
    pip install -r requirements.txt
    cp .env.example .env            # add Gemini/Groq keys + Drive folder ID
    # put service_account.json inside credentials/

## Run
    python main.py --location "Chicago, IL"
    python main.py --location "Chicago, IL" --skip-llm --skip-sheets

## Folder map
    main.py                       entry point (CLI)
    src/config.py                 settings, paths, API keys
    src/scraper/scraper.py        browser flow: search -> collect links -> profile scrape
    src/scraper/locator.py        all selectors + JS snippets (fix here if Zillow changes)
    src/extractors/               email_finder.py, phone_finder.py
    src/validation/validator.py   email/phone/url/duplicate/required checks
    src/scoring/llm_scorer.py     Gemini + Groq key rotation, lead scoring
    src/export/google_sheets.py   Drive folders + Google Sheet upload
    credentials/                  service_account.json (git-ignored)
    temp/                         collected links cache (resume)
    output/<location>/agent_lead/ final xlsx
