# Install the Media page on mary

Instructions for Claude Code running on **mary**, the office server that will
host the Media page. Work through the steps in order. Where a step says
**Ask**, stop and get the answer from the user before continuing. Where a step
changes system settings (firewall, startup tasks, services), tell the user
what you are about to do and get a yes first.

## What this is

The Media page is a small internal website for CyberData product media. It
reads a folder of product folders named by 01 number (e.g. `011393`), each
holding PNG images and PDF files, plus a product list (`.xlsx` or `.csv`) with
part numbers and descriptions. Office PCs open it at `http://mary:8080`. No
login. It is reached from outside the office only over VPN.

The code is already written and tested. Your job is to install it, point it at
the real files, check the real data reads correctly, and keep it running.

- Repository: `https://github.com/plembo2009-coder/Ingram-scrape`
- Branch: `claude/project-media-page-naming-qpup15`
- Code lives in the `media-page/` folder of that branch:
  - `server.py`: the web server. Python standard library only; no pip installs.
  - `static/index.html`: the page.
  - `README.md`: the human setup guide. Read it before starting.

Do not rewrite the program. If something needs changing, make the smallest
fix, explain it to the user, and keep a note of it (see step 9).

## 1. Find out what mary is

Work out the operating system (Windows or Linux) and report it to the user.
All later steps have a Windows and a Linux variant; use the matching one.

Check whether Python 3.8+ is installed (`python --version` or `py --version` on
Windows, `python3 --version` on Linux).

- If Python is missing on **Windows**: ask the user to install it from
  python.org with "Add python.exe to PATH" ticked (or, with their OK, run
  `winget install Python.Python.3.12`). Open a new terminal afterwards.
- If missing on **Linux**: with their OK, install it with the package manager
  (`sudo apt install python3` or `sudo dnf install python3`).

## 2. Get the code

**Ask** where to install it. Suggest `C:\media-page` (Windows) or
`/opt/media-page` (Linux).

If `git` is available:

```
git clone -b claude/project-media-page-naming-qpup15 https://github.com/plembo2009-coder/Ingram-scrape.git <temp-folder>
```

then copy `<temp-folder>/media-page` to the install location.

If `git` is not available, download
`https://github.com/plembo2009-coder/Ingram-scrape/archive/refs/heads/claude/project-media-page-naming-qpup15.zip`,
unzip it, and copy its `media-page` folder to the install location.

If the repository is private and the clone or download fails with a 404 or
login prompt, tell the user; they need to sign in to GitHub on mary or copy
the folder over themselves.

Confirm the install location contains `server.py` and `static/index.html`.

## 3. Locate the media folder and product list

**Ask** the user:

1. The full path of the media folder (the folder that contains the 01-number
   folders).
2. Where the product list file is. The easiest setup is to save it inside the
   media folder as `products.xlsx` or `products.csv`; then it is found
   automatically. Otherwise note its path for `--products`.

Then inspect the folder, without changing anything in it, and report:

- how many product folders there are, with a few example names
- folders whose name is not a 01 number (these still show on the page, under
  their folder name; check with the user that that is intended)
- how many folders have no PNG with "photo" or "picture" in the name (the page
  falls back to the first PNG; folders with no PNG at all show "No photo yet")
- folders with no PNG or PDF files at all
- other file types present (they are ignored by the page; mention it in case
  the user expected them to show)

## 4. Check the product list reads correctly

From the install folder, run this (use `python3` on Linux, and add
`--products` handling if the list is not in the media folder):

```
python -c "import server, collections; p = server.load_products(r'<path-to-product-list>'); print(len(p), 'products'); print(collections.Counter(x['function'] for x in p.values())); [print(v) for v in list(p.values())[:10]]"
```

Report to the user:

1. The number of products read. Compare it to the number of rows in the file.
   If it is 0 or far off, the header row was not recognised. The page expects
   a part-number column (header containing Part, Item, SKU, Model or Number)
   and a description column (Description, Name, Product or Title). Show the
   user the actual headers and fix the file's headers with their OK, rather
   than changing the code.
2. The count per function (Speakers, Intercoms, Servers, Other). Function is
   guessed from words in the description unless the file has a Function,
   Category or Type column.
3. Every product that landed in **Other**, and a sample of each group so the
   user can spot wrong guesses.

If many products are in the wrong group, offer two fixes and let the user
choose:

- **Add a Function column** to the product list with Speakers, Intercoms or
  Servers per row (most reliable; the user controls it).
- **Adjust the keyword list** `FUNCTION_KEYWORDS` near the top of `server.py`
  (quick, but guesses stay guesses).

Also match the list against the folders and report:

- products in the list with no folder (they show on the page with "0 files")
- folders with no row in the list (they show as "Not in product list")

Part numbers are matched after removing spaces and punctuation, and a missing
leading zero is added back (Excel turns 011393 into 11393), so those are not
mismatches.

## 5. Test run

Start it in the foreground (Linux: `python3`):

```
python server.py --media "<media-folder>"
```

Add `--products "<file>"` if the list is not inside the media folder.

The startup lines show the media folder, the product list and the number of
products. Then check:

1. Open `http://localhost:8080/api/products` (browser or `curl`). It should
   return JSON listing the products with their files.
2. Ask the user to open `http://localhost:8080` in a browser on mary and
   confirm: thumbnails show, clicking a product opens its file list, a PDF
   opens in the viewer, **Download** saves the file, **Print** opens the print
   dialog, and "Sort by: Function" groups products correctly.

Port 8080 already in use: pick another (e.g. `--port 8081`) and use it in all
later steps. Port 80 gives the shorter address `http://mary` but needs admin
rights and must be free; only use it if the user asks.

Stop the test server (Ctrl+C) when done.

## 6. Open the firewall

Other PCs must be able to reach port 8080 on mary. Tell the user, get a yes,
then:

**Windows** (administrator terminal):

```
netsh advfirewall firewall add rule name="Media page" dir=in action=allow protocol=TCP localport=8080 profile=domain,private
```

**Linux**: if `ufw` is active, `sudo ufw allow 8080/tcp`; if `firewalld` is
active, `sudo firewall-cmd --permanent --add-port=8080/tcp && sudo firewall-cmd --reload`.
If neither is active, nothing to do.

Keep the rule limited to the office network (the `domain,private` profiles on
Windows). The site has no login, so it must not be opened to the internet;
remote staff reach it through the VPN.

## 7. Start it automatically

The site should run whenever mary is on, without anyone logged in.

**Windows**: create a scheduled task (administrator terminal). Use the full
path to `python.exe` (find it with `where python`); `pythonw.exe` from the
same folder runs it without a console window.

```
schtasks /Create /TN "Media page" /SC ONSTART /RU SYSTEM /RL HIGHEST /TR "\"C:\Path\To\pythonw.exe\" \"C:\media-page\server.py\" --media \"D:\Media\""
schtasks /Run /TN "Media page"
```

If the media folder is on a network share rather than a local drive, the
SYSTEM account may not be able to read it. In that case run the task as a
user account that can (`/RU <domain\user> /RP`), and confirm with the user
which account to use.

**Linux**: create `/etc/systemd/system/media-page.service`:

```
[Unit]
Description=Media page
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/python3 /opt/media-page/server.py --media /srv/media
Restart=always
User=<a user that can read the media folder>

[Install]
WantedBy=multi-user.target
```

then `sudo systemctl daemon-reload && sudo systemctl enable --now media-page`
and check `systemctl status media-page`.

Confirm it is running: `http://localhost:8080` loads on mary.

## 8. Check from another PC

Ask the user to open `http://mary:8080` from another office PC, and once from
a PC connected over VPN. If it works on mary but not elsewhere:

- `http://<mary's IP address>:8080` works but `http://mary:8080` does not:
  a name-resolution (DNS) issue; the user or IT can add a DNS entry, or use
  the IP address.
- Neither works: recheck the firewall rule from step 6 and that the server
  is listening on all addresses (it does by default; `--host 0.0.0.0`).

## 9. Hand over

Write `media-page/LOCAL-SETUP.md` in the install folder, recording:

- the install folder, media folder and product list paths
- the port and the address people use
- how it is started (task name or service name) and how to restart it
- any change made to `server.py`, the product list or anything else, and why

Then tell the user, in plain words:

- the address to share with staff
- how to add a product: create a folder named with its 01 number in the media
  folder, put the PNG photo (with "photo" in its name) and PDFs in it, and add
  a row to the product list. People just refresh the page; no restart needed.
- how to restart the site if it stops (the task or service from step 7)
