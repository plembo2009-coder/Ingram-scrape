# Media page

An office website for CyberData product media. It reads a folder of product
folders named by 01 number, and shows every product's photo, datasheet,
manual and marketing files. People can view, print or download any file.
No login is required.

It is one Python program (`server.py`) plus one web page (`static/index.html`).
It uses only standard Python, so there is nothing else to install.

## 1. Set up the media folder on mary

```
Media\
├── products.xlsx          ← the product list (or products.csv)
├── 011393\
│   ├── 011393_photo.png   ← thumbnail (any PNG with "photo" in the name)
│   ├── 011393 Datasheet.pdf
│   ├── 011393 Manual.pdf
│   └── Marketing\         ← subfolders are fine too
│       └── sell-sheet.pdf
└── 011402\
    └── ...
```

- **Folder names** are the 01 number. `011393` and `11393` both work.
- **Files**: PNG and PDF files are shown. Other files in the folder are ignored.
- **Thumbnail**: the PNG with "photo" or "picture" in its name. If there is
  none, the first PNG in the folder is used.
- **File names become labels**: "datasheet" shows as Datasheet, "manual" as
  Manual, and anything else shows its file name (`sell-sheet.pdf` shows as
  "Sell sheet").

### The product list

An Excel (`.xlsx`) or CSV file with a header row. The page looks for:

| Column | Header can be named | Required |
|---|---|---|
| Part number | Part Number, Part #, Item, SKU, Model | yes |
| Description | Description, Product Name, Name | yes |
| Function | Function, Category, Type | no |

If there is no Function column, the function is worked out from the
description: "speaker", "horn" or "strobe" → Speakers; "intercom", "door",
"keypad" or "emergency" → Intercoms; "server", "gateway" or "controller" →
Servers. Anything else shows as Other. Add a Function column to fix any
product that lands in the wrong group.

Excel dropping the leading zero (011393 → 11393) is handled automatically.

Products in the list with no folder yet still appear, marked "0 files".
Folders with no row in the list appear as "Not in product list".

## 2. Install Python on mary

Python 3.8 or newer. On Windows, get it from python.org and tick
**"Add python.exe to PATH"** during install. On Linux it is usually already
there.

## 3. Start it

Copy this `media-page` folder to mary, then:

**Windows**

```
cd C:\media-page
python server.py --media D:\Media
```

**Linux**

```
cd /opt/media-page
python3 server.py --media /srv/media
```

Then open **http://mary:8080** from any PC in the office.

Options:

- `--media PATH`: the media folder (default: a `media` folder next to server.py)
- `--products FILE`: the product list, if it isn't `products.xlsx` or
  `products.csv` inside the media folder
- `--port 8080`: use a different port. Port 80 gives the plain address
  `http://mary`, but may need admin rights.

The page reads the folders fresh each time it loads. Add a folder, replace a
PDF or update the product list, then refresh the browser. No restart needed.

## 4. Keep it running after a reboot

**Windows:** open Task Scheduler → Create Task. Choose "Run whether user is
logged on or not", add the trigger **At startup**, and the action **Start a
program**: `python` with arguments `C:\media-page\server.py --media D:\Media`.
Also allow port 8080 through Windows Firewall (run as administrator):

```
netsh advfirewall firewall add rule name="Media page" dir=in action=allow protocol=TCP localport=8080
```

**Linux:** create `/etc/systemd/system/media-page.service`:

```
[Unit]
Description=Media page
After=network.target

[Service]
ExecStart=/usr/bin/python3 /opt/media-page/server.py --media /srv/media
Restart=always

[Install]
WantedBy=multi-user.target
```

then run `sudo systemctl enable --now media-page`.

## Notes

- Anyone on the office network can open the site; there is no login. It only
  shares PNG and PDF files inside the media folder, nothing else on mary.
- The page's typeface loads from Google Fonts. If mary has no internet access,
  the page still works and uses the computer's standard font.
- `mockup.html` is the original design mockup, kept for reference.
