# Ingram Micro CEP — data extraction (test phase)

Test-phase probe for the Ingram Micro CEP B2B portal: confirm login works and
determine how the search-results page delivers product data, before any scraper
gets built.

## Status: the test has NOT been run against the live site

The session this was developed in has no network route to the target. Outbound
HTTPS goes through an egress proxy that rejected the host at the gateway:

```
usa.ingrammicro.com:443  connect_rejected: gateway answered 403 to CONNECT
```

This is an organization egress-policy denial, not a transient error or a bad
credential — `ingrammicro.com` and unrelated hosts such as `google.com` are
refused the same way, while allowlisted hosts (GitHub, package registries)
connect normally. It has to be resolved by allowing the host in the
environment's network policy, or by running `probe.py` somewhere with ordinary
internet access.

The probe itself is written and verified end-to-end against a local fixture
that reproduces the flow (login → dashboard → search → filters → results grid),
in both a JS-hydrated and a server-rendered variant. The rendering verdict was
confirmed to report each case correctly, so it discriminates rather than always
guessing the same answer. Selector matching against the *real* site is still
unverified — see "Expect to adjust selectors".

## Running it

```bash
pip install -r requirements.txt
playwright install chromium          # skip if Chromium is already provisioned

export INGRAM_USER='you@example.com'
export INGRAM_PASS='...'

python probe.py                      # headless
python probe.py --headed --slow      # watch it drive the browser
python probe.py --term cyberdata     # search term (default: cyberdata)
```

Credentials are read from the environment only. Do not commit them — `.env` is
gitignored.

## What it does

1. Opens the CEP login page and signs in.
2. Confirms it lands on `/cep/app/my/dashboard`.
3. Searches for the term.
4. Clears result filters — a "Clear all" control if present, then any remaining
   checked boxes whose label matches "authorized", "in stock", "available",
   "my products".
5. Dumps the raw HTML of one product card and prints it.
6. Decides **server-rendered vs dynamic** by re-fetching the results URL with
   the session cookies but *without executing JavaScript*, then checking whether
   a product token (VPN/SKU) scraped from the rendered card is present in that
   raw response. It also flags embedded state blobs (`__NEXT_DATA__`,
   `__INITIAL_STATE__`, …), which is the other way a SPA ships data in the
   document.
7. Records every XHR/fetch response and flags those whose URL looks like a
   product/search/catalog/graphql endpoint — if the page is dynamic, this is the
   list of candidate APIs to scrape instead of the DOM.

## Output

Everything lands in `./out/` (gitignored), so one run gives the full picture
even where a selector guess misses:

| File | Contents |
| --- | --- |
| `00_run_log.txt` | Timestamped log of the run |
| `01_login_page.html` / `.png` | Login page as first seen |
| `02_after_login.html` / `.png` | Landing page — check this if login fails |
| `03_results_raw.html` / `.png` | Results before filters are cleared |
| `04_results_filters_cleared.html` / `.png` | Results after filters are cleared |
| `05_one_product_card.html` | **One product card's raw HTML** |
| `06_no_js_response.html` | Same URL, cookies, no JS — the rendering test |
| `07_network_xhr.json` | Every XHR/fetch call observed |
| `08_verdict.json` | Machine-readable summary of all findings |
| `storage_state.json` | Session cookies, reusable to skip re-login |

## Expect to adjust selectors

`probe.py` carries candidate-selector lists rather than one hardcoded guess,
tries each in turn, and logs which matched. On the first real run:

- If the login form is not found it writes `out/ERROR_login_form.html` — read it
  and add the real selector to `USER_SELECTORS` / `PASS_SELECTORS`.
- If no repeating card container is found, inspect
  `out/04_results_filters_cleared.html` and add the real one to `CARD_SELECTORS`.
- Once the real selectors are known, trim the lists to just those.

Two things worth watching for on the first live run, neither of which the probe
can resolve on its own: an MFA or CAPTCHA step after the password (the probe
detects it only as "did not reach the dashboard", so check
`out/02_after_login.png`), and a results grid that paginates or lazy-loads —
the ~159 products likely will not all be in the DOM at once, which the real
scraper will need to handle.

## Fields the eventual export needs

Description · Product VPN · Product SKU · Product image · Option tags · Price ·
MSRP · Qty in stock — one row per product, ~159 CyberData products.

"Option tags" still needs clarification: which element on the card that refers
to. `05_one_product_card.html` from a live run should make it identifiable.
