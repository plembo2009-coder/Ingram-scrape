#!/usr/bin/env python3
"""
Ingram Micro CEP - login + page-structure probe (TEST PHASE, not the scraper).

What it does:
  1. Opens the CEP login page and signs in.
  2. Confirms it lands on the dashboard.
  3. Searches for a term (default: "cyberdata").
  4. Clears result filters ("Authorized products only", "In stock only", etc.).
  5. Dumps the raw HTML of one product card.
  6. Decides whether the results are server-rendered or JS/XHR-hydrated, by
     re-fetching the same URL with the session cookies but WITHOUT running JS
     and checking whether the product data is present in that raw response.

Everything it sees is written to ./out/ so a single run gives you the full
picture even if a selector guess misses.

Credentials come from the environment, never from this file:
    export INGRAM_USER='you@example.com'
    export INGRAM_PASS='...'
    python probe.py                 # headless
    python probe.py --headed --slow # watch it drive the browser
"""

import argparse
import json
import os
import pathlib
import re
import sys
import time

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

# Overridable so the flow can be smoke-tested against a local fixture.
LOGIN_URL = os.environ.get("INGRAM_LOGIN_URL", "https://usa.ingrammicro.com/cep/app/login")
DASHBOARD_URL = os.environ.get(
    "INGRAM_DASHBOARD_URL", "https://usa.ingrammicro.com/cep/app/my/dashboard")
DASHBOARD_RE = os.environ.get("INGRAM_DASHBOARD_RE", r"/cep/app/my/dashboard")
SEARCH_URL_TMPL = os.environ.get(
    "INGRAM_SEARCH_URL", "https://usa.ingrammicro.com/cep/app/search?keyword={term}")
OUT = pathlib.Path(__file__).parent / "out"

# Candidate selectors. The site may use any of these; the probe tries each in
# order and reports which one actually matched, so the list can be trimmed to
# the real one after the first successful run.
USER_SELECTORS = [
    "input[name='username']", "input[name='userName']", "input[name='email']",
    "input[type='email']", "input#username", "input#userName", "input#email",
    "input[autocomplete='username']",
]
PASS_SELECTORS = [
    "input[name='password']", "input#password", "input[type='password']",
    "input[autocomplete='current-password']",
]
SUBMIT_SELECTORS = [
    "button[type='submit']", "input[type='submit']",
    "button:has-text('Sign In')", "button:has-text('Sign in')",
    "button:has-text('Log In')", "button:has-text('Login')",
]
SEARCH_SELECTORS = [
    "input[name='search']", "input[type='search']", "input#search",
    "input[placeholder*='Search' i]", "input[aria-label*='Search' i]",
    "[data-testid*='search' i] input",
]
# Repeating containers that usually hold one product each.
CARD_SELECTORS = [
    "[data-testid*='product' i]", "[class*='product-card' i]",
    "[class*='productCard' i]", "[class*='search-result' i]",
    "[class*='result-item' i]", "article", "li[class*='product' i]",
    "div[class*='grid'] > div[class*='item']", "tr[class*='product' i]",
]
FILTER_CLEAR_SELECTORS = [
    "button:has-text('Clear all')", "a:has-text('Clear all')",
    "button:has-text('Clear All')", "button:has-text('Reset filters')",
    "button:has-text('Clear filters')", "[data-testid*='clear' i]",
]
FILTER_LABEL_PATTERNS = [
    r"authorized", r"in\s*stock", r"available", r"my\s*products",
]

log_lines = []


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    log_lines.append(line)


def first_visible(page, selectors, what):
    """Return the first selector that resolves to a visible element."""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                log(f"  matched {what}: {sel}")
                return loc, sel
        except Exception:
            continue
    log(f"  !! no selector matched {what}")
    return None, None


def save(name, content, binary=False):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if binary:
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    log(f"  wrote {path.relative_to(OUT.parent)} ({len(content)} bytes)")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--term", default="cyberdata", help="search term")
    ap.add_argument("--headed", action="store_true", help="show the browser")
    ap.add_argument("--slow", action="store_true", help="slow motion, for watching")
    ap.add_argument("--timeout", type=int, default=45000, help="per-step timeout ms")
    args = ap.parse_args()

    user = os.environ.get("INGRAM_USER")
    pw = os.environ.get("INGRAM_PASS")
    if not user or not pw:
        sys.exit("Set INGRAM_USER and INGRAM_PASS in the environment first.")

    OUT.mkdir(exist_ok=True)
    api_calls = []          # XHR/fetch traffic, to spot a JSON product API
    verdict = {}

    with sync_playwright() as p:
        launch_kw = {"headless": not args.headed,
                     "slow_mo": 400 if args.slow else 0}
        # Some environments ship a Chromium whose build number does not match
        # the pip package; point at it explicitly instead of re-downloading.
        exe = os.environ.get("CHROMIUM_PATH") or "/opt/pw-browsers/chromium"
        if os.path.exists(exe):
            launch_kw["executable_path"] = exe
            log(f"  using chromium at {exe}")
        browser = p.chromium.launch(**launch_kw)
        ctx = browser.new_context(
            viewport={"width": 1600, "height": 1000},
            user_agent=("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
        )
        page = ctx.new_page()
        page.set_default_timeout(args.timeout)

        def on_response(resp):
            rt = resp.request.resource_type
            if rt in ("xhr", "fetch"):
                api_calls.append({
                    "method": resp.request.method,
                    "url": resp.url,
                    "status": resp.status,
                    "type": resp.headers.get("content-type", ""),
                })
        page.on("response", on_response)

        # ---------- 1. login ----------
        log(f"STEP 1  opening {LOGIN_URL}")
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        save("01_login_page.html", page.content())
        page.screenshot(path=str(OUT / "01_login_page.png"), full_page=True)

        log("STEP 2  filling credentials")
        u_loc, _ = first_visible(page, USER_SELECTORS, "username field")
        p_loc, _ = first_visible(page, PASS_SELECTORS, "password field")
        if not u_loc or not p_loc:
            save("ERROR_login_form.html", page.content())
            sys.exit("Could not find the login form - see out/ERROR_login_form.html")

        u_loc.fill(user)
        # Some CEP flows reveal the password field only after the username step.
        if not p_loc.is_visible():
            u_loc.press("Enter")
            page.wait_for_timeout(2000)
            p_loc, _ = first_visible(page, PASS_SELECTORS, "password field (step 2)")
        p_loc.fill(pw)

        s_loc, _ = first_visible(page, SUBMIT_SELECTORS, "submit button")
        if s_loc:
            s_loc.click()
        else:
            p_loc.press("Enter")

        # ---------- 3. dashboard ----------
        log("STEP 3  waiting for dashboard")
        landed = False
        try:
            page.wait_for_url(re.compile(DASHBOARD_RE), timeout=args.timeout)
            landed = True
        except PWTimeout:
            log("  did not reach the dashboard URL within the timeout")
        page.wait_for_load_state("networkidle", timeout=args.timeout)
        page.wait_for_timeout(2000)

        log(f"  current URL: {page.url}")
        log(f"  title:       {page.title()}")
        save("02_after_login.html", page.content())
        page.screenshot(path=str(OUT / "02_after_login.png"), full_page=True)
        verdict["landed_on_dashboard"] = landed or bool(re.search(DASHBOARD_RE, page.url))
        verdict["post_login_url"] = page.url

        if not verdict["landed_on_dashboard"]:
            body = page.inner_text("body")[:1500]
            save("ERROR_post_login_text.txt", body)
            log("  !! login may have failed (MFA / captcha / bad creds?).")
            log("     Check out/02_after_login.png before trusting later steps.")

        ctx.storage_state(path=str(OUT / "storage_state.json"))
        log("  saved session cookies to out/storage_state.json")

        # ---------- 4. search ----------
        log(f"STEP 4  searching for '{args.term}'")
        sr_loc, _ = first_visible(page, SEARCH_SELECTORS, "search box")
        if sr_loc:
            sr_loc.click()
            sr_loc.fill(args.term)
            sr_loc.press("Enter")
        else:
            # Fall back to the conventional search URL.
            url = SEARCH_URL_TMPL.format(term=args.term)
            log(f"  no search box found; navigating to {url}")
            page.goto(url, wait_until="domcontentloaded")

        page.wait_for_load_state("networkidle", timeout=args.timeout)
        page.wait_for_timeout(3000)
        results_url = page.url
        log(f"  results URL: {results_url}")
        save("03_results_raw.html", page.content())
        page.screenshot(path=str(OUT / "03_results.png"), full_page=True)

        # ---------- 5. clear filters ----------
        log("STEP 5  clearing filters")
        cleared = []
        c_loc, c_sel = first_visible(page, FILTER_CLEAR_SELECTORS, "clear-all control")
        if c_loc:
            try:
                c_loc.click()
                cleared.append(c_sel)
                page.wait_for_timeout(3000)
            except Exception as e:
                log(f"  clear-all click failed: {e}")

        # Uncheck any remaining restrictive checkboxes by their label text.
        for box in page.locator("input[type='checkbox']").all():
            try:
                if not box.is_visible() or not box.is_checked():
                    continue
                label = ""
                for get in (lambda: box.evaluate(
                        "el => (el.closest('label')||el.parentElement||{}).innerText || ''"),):
                    label = (get() or "").strip()
                if any(re.search(pat, label, re.I) for pat in FILTER_LABEL_PATTERNS):
                    log(f"  unchecking filter: {label[:60]!r}")
                    box.uncheck(force=True)
                    cleared.append(label[:60])
                    page.wait_for_timeout(2500)
            except Exception:
                continue

        page.wait_for_load_state("networkidle", timeout=args.timeout)
        page.wait_for_timeout(3000)
        verdict["filters_cleared"] = cleared
        results_url = page.url
        save("04_results_filters_cleared.html", page.content())
        page.screenshot(path=str(OUT / "04_results_filters_cleared.png"), full_page=True)

        # Result count, if the page states one.
        body_text = page.inner_text("body")
        m = re.search(r"([\d,]+)\s*(?:results?|products?|items?)", body_text, re.I)
        if m:
            verdict["result_count_text"] = m.group(0).strip()
            log(f"  result count on page: {m.group(0).strip()}")

        # ---------- 6. one product card ----------
        log("STEP 6  extracting one product card")
        card_html, card_sel, card_n = None, None, 0
        for sel in CARD_SELECTORS:
            try:
                loc = page.locator(sel)
                n = loc.count()
                # A results grid has many siblings; 3+ is a good signal.
                if n >= 3:
                    card_html = loc.first.evaluate("el => el.outerHTML")
                    card_sel, card_n = sel, n
                    break
            except Exception:
                continue

        if card_html:
            log(f"  card selector {card_sel!r} matched {card_n} elements")
            save("05_one_product_card.html", card_html)
            verdict["card_selector"] = card_sel
            verdict["cards_on_page"] = card_n
            print("\n" + "=" * 70)
            print("ONE PRODUCT CARD (raw HTML)")
            print("=" * 70)
            print(card_html[:6000])
            print("=" * 70 + "\n")
        else:
            log("  !! no repeating card container found - inspect 04_*.html by hand")

        # ---------- 7. server-rendered or JS-hydrated? ----------
        log("STEP 7  server-rendered vs dynamic")
        # Pull a token that only appears if real product data is present.
        token = None
        if card_html:
            for pat in (r"\b([A-Z0-9]{3,}-[A-Z0-9-]{3,})\b",   # looks like a VPN/SKU
                        r"\b(\d{6,8})\b"):                      # Ingram part number
                mm = re.search(pat, re.sub(r"<[^>]+>", " ", card_html))
                if mm:
                    token = mm.group(1)
                    break
        verdict["probe_token"] = token
        log(f"  probing for token {token!r} in the no-JS response")

        # Same URL, same cookies, no JavaScript executed.
        raw = ctx.request.get(results_url)
        raw_body = raw.text()
        save("06_no_js_response.html", raw_body)
        verdict["no_js_status"] = raw.status
        verdict["no_js_bytes"] = len(raw_body)
        verdict["rendered_bytes"] = len(page.content())

        token_in_raw = bool(token and token in raw_body)
        verdict["token_in_no_js_html"] = token_in_raw
        # Embedded-state blobs are the other way a SPA ships data in the document.
        verdict["has_embedded_json_state"] = bool(re.search(
            r"__NEXT_DATA__|__NUXT__|__INITIAL_STATE__|window\.__", raw_body))

        if token and token_in_raw:
            verdict["rendering"] = "server-rendered (product data present without JS)"
        elif token:
            verdict["rendering"] = "dynamic (product data absent without JS; needs JS or the API)"
        else:
            verdict["rendering"] = "inconclusive (no token extracted - check out/ by hand)"
        log(f"  VERDICT: {verdict['rendering']}")

        # Candidate product APIs seen during the run.
        interesting = [c for c in api_calls
                       if re.search(r"search|product|catalog|item|sku|graphql", c["url"], re.I)]
        verdict["api_calls_total"] = len(api_calls)
        verdict["candidate_product_apis"] = interesting[:25]
        save("07_network_xhr.json", json.dumps(api_calls, indent=2))
        if interesting:
            log(f"  {len(interesting)} candidate product API call(s):")
            for c in interesting[:10]:
                log(f"    {c['method']} {c['status']} {c['url'][:120]}")

        save("08_verdict.json", json.dumps(verdict, indent=2))
        save("00_run_log.txt", "\n".join(log_lines))
        browser.close()

    print("\nSummary:")
    print(json.dumps(verdict, indent=2)[:4000])
    print("\nAll artifacts in ./out/")


if __name__ == "__main__":
    main()
