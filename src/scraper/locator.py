"""All selectors + JS snippets in one place. Tune here if Zillow changes markup."""

SEARCH_INPUT = 'input[role="combobox"][data-search-box-custom-input]'
PROFILE_LINK = 'a[href*="zillow.com/profile/"]'

# Return all profile links currently in DOM
JS_PROFILE_LINKS = """
(() => {
  try {
    return Array.from(document.querySelectorAll('a[href*="/profile/"]'))
      .map(a => a.href).filter(h => h.includes('zillow.com/profile/'));
  } catch (e) {
    return [];
  }
})()
"""

# Find + click the "Next page" pagination control. Returns true if clicked.
JS_CLICK_NEXT_PAGE = """
(() => {
  const candidates = [
    'button[title="Next page"]:not([disabled]):not([aria-disabled="true"])',
    'a[title="Next page"]:not([disabled]):not([aria-disabled="true"])',
    'button[rel="next"]:not([disabled]):not([aria-disabled="true"])',
    'a[rel="next"]:not([disabled]):not([aria-disabled="true"])',
    'button[aria-label*="Next" i]:not([disabled]):not([aria-disabled="true"])',
    'a[aria-label*="Next" i]:not([disabled]):not([aria-disabled="true"])',
    'nav[aria-label*="page" i] button:not([disabled]):not([aria-disabled="true"]):last-child',
    'nav[aria-label*="page" i] li:last-child button:not([disabled]):not([aria-disabled="true"])'
  ];

  let btn = null;
  for (const sel of candidates) {
    const el = document.querySelector(sel);
    if (el) { btn = el; break; }
  }

  if (!btn) {
    btn = Array.from(document.querySelectorAll('a, button')).find(e => {
      const t = (e.getAttribute('title') || '').toLowerCase();
      const a = (e.getAttribute('aria-label') || '').toLowerCase();
      const txt = (e.innerText || e.textContent || '').trim().toLowerCase();
      const isNext = t.includes('next') || a.includes('next') || txt === 'next' || /^next\\s*(?:page|>)?$/i.test(txt) || /^view\\s*more$/i.test(txt);
      const isDisabled = e.disabled || e.getAttribute('aria-disabled') === 'true' || e.classList.contains('disabled');
      return isNext && !isDisabled;
    });
  }

  if (!btn) return false;
  btn.scrollIntoView({block: 'center', behavior: 'instant'});
  btn.click();
  return true;
})()
"""

JS_CLICK_VIEW_MORE = JS_CLICK_NEXT_PAGE

# Pull raw profile data in one shot (including brokerage / company name and sales metrics)
JS_PROFILE_DATA = """
(() => {
  const h1 = document.querySelector('h1');
  const h1Text = (h1 || {}).innerText || '';

  // 1. Brokerage / Company extraction
  let brokerage = '';

  // Priority 1: User's exact selector & known brokerage classes
  const directSelectors = [
    'header [class*="MediaObject__Body"] span[class*="bmGggf"]',
    'header [class*="MediaObject__Body"] span.bmGggf',
    'header [class*="MediaObject__Body"] span[class*="kUNVWz"]',
    'header [class*="MediaObject__Body"] span.kUNVWz',
    'div[class*="AByvS"] span',
    'div[class*="qcRwy"] span',
    '[class*="MediaObject__Body"] span[class*="bmGggf"]',
    '[class*="MediaObject__Body"] span[class*="kUNVWz"]',
    '[data-testid="brokerage-name"]',
    '[data-testid="business-name"]'
  ];
  for (const sel of directSelectors) {
    const el = document.querySelector(sel);
    if (el && el.innerText && el.innerText.trim()) {
      brokerage = el.innerText.trim();
      break;
    }
  }

  // Priority 2: Generic MediaObject__Body inspection
  if (!brokerage) {
    const bodyEl = document.querySelector('[class*="MediaObject__Body"]') || document.querySelector('header');
    if (bodyEl) {
      const spans = Array.from(bodyEl.querySelectorAll('span, div, p')).map(s => (s.innerText || '').trim()).filter(Boolean);
      for (const txt of spans) {
        if (txt !== h1Text && !txt.includes('5.0') && !txt.toLowerCase().includes('review') && !txt.toLowerCase().includes('star') && !txt.toLowerCase().includes('contact') && txt.length < 60) {
          if (!txt.toLowerCase().startsWith('lead of ') && !txt.toLowerCase().startsWith('agent at ')) {
            brokerage = txt;
            break;
          }
        }
      }
    }
  }

  // 2. Metrics extraction (Sales last 12 months, Total sales, Price range, Average price)
  let sales12m = '';
  let totalSales = '';
  let priceRange = '';
  let avgPrice = '';

  for (const div of document.querySelectorAll('div')) {
    const txt = (div.innerText || '').trim();
    if (!txt) continue;
    const lines = txt.split('\\n').map(l => l.trim()).filter(Boolean);
    if (lines.length >= 2 && lines.length <= 4) {
      for (let i = 0; i < lines.length; i++) {
        const l = lines[i].toLowerCase();
        if (l === 'sales last 12 months' && i > 0 && !sales12m) sales12m = lines[i-1];
        else if (l === 'total sales' && i > 0 && !totalSales) totalSales = lines[i-1];
        else if (l === 'price range' && i > 0 && !priceRange) priceRange = lines[i-1];
        else if (l === 'average price' && i > 0 && !avgPrice) avgPrice = lines[i-1];
      }
    }
  }

  return {
    name: h1Text,
    brokerage: brokerage,
    sales12m: sales12m,
    totalSales: totalSales,
    priceRange: priceRange,
    avgPrice: avgPrice,
    text: document.body.innerText || '',
    links: Array.from(document.querySelectorAll('a[href]')).map(a => ({
        text: (a.innerText||'').trim(), href: a.href })),
  };
})()
"""

SOCIAL_DOMAINS = (
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com",
    "youtube.com", "tiktok.com", "pinterest.com", "threads.net",
)
# social links that are Zillow's own footer links -> ignore
ZILLOW_SOCIAL_BLACKLIST = ("/Zillow", "/zillow", "@zillow")

CAPTCHA_HINTS = (
    "press & hold", "press and hold", "are you a human", "px-captcha",
    "access to this page has been denied", "verify you are human",
    "cf-turnstile", "challenges.cloudflare.com", "turnstile"
)
