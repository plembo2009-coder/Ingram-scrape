#!/usr/bin/env python3
"""Media page: a small web server for the CyberData product media folders.

Point it at a folder of 01-number subfolders (each holding PNG and PDF files)
and a product list (CSV or XLSX with part number and description), and it
serves the Media page to anyone on the office network.

Uses only the Python standard library, so there is nothing to pip install.

    python server.py --media D:\\Media --products D:\\Media\\products.xlsx

Then open http://mary:8080 from any office PC.
"""

import argparse
import csv
import io
import json
import mimetypes
import os
import re
import sys
import urllib.parse
import zipfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
FILE_TYPES = {".png": "png", ".pdf": "pdf"}

# Function is read from the product list if it has a Function/Category column;
# otherwise it is guessed from the description with these keywords, in order.
FUNCTION_KEYWORDS = [
    ("Servers", ["server", "gateway", "controller", "adapter", "interface", "module"]),
    ("Intercoms", ["intercom", "call box", "callbox", "door", "keypad", "emergency", "talk-back station"]),
    ("Speakers", ["speaker", "horn", "strobe", "loudspeaker", "siren", "clock"]),
]


def part_key(value):
    """Normalize a part number so '011393', '11393', '11393.0' and '011393 ' match."""
    s = str(value).strip()
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".")[0]
    s = re.sub(r"[^0-9A-Za-z]", "", s).upper()
    # Excel drops the leading zero from numeric part numbers like 011393.
    if re.fullmatch(r"1\d{4}", s):
        s = "0" + s
    return s


def guess_function(description):
    d = description.lower()
    for name, words in FUNCTION_KEYWORDS:
        if any(w in d for w in words):
            return name
    return "Other"


def normalize_function(value):
    v = value.strip().lower()
    for name in ("Speakers", "Intercoms", "Servers"):
        if v and (v in name.lower() or name.lower().rstrip("s") in v):
            return name
    return value.strip().title() or None


# ---------- product list ----------

def read_xlsx_rows(path):
    """Read the first worksheet of an .xlsx file as a list of string rows."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", ns):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t")))
        sheets = sorted(n for n in z.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))
        if not sheets:
            return []
        sheets.sort(key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)))
        root = ET.fromstring(z.read(sheets[0]))
    rows = []
    for row in root.iter(f"{{{ns['m']}}}row"):
        cells = {}
        for c in row.findall("m:c", ns):
            ref = c.get("r", "")
            col = 0
            for ch in re.match(r"[A-Z]*", ref).group(0):
                col = col * 26 + (ord(ch) - 64)
            t = c.get("t")
            v = c.find("m:v", ns)
            if t == "s" and v is not None:
                text = shared[int(v.text)]
            elif t == "inlineStr":
                text = "".join(x.text or "" for x in c.iter(f"{{{ns['m']}}}t"))
            else:
                text = v.text if v is not None and v.text else ""
            cells[max(col - 1, 0)] = text
        if cells:
            rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
    return rows


def read_csv_rows(path):
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return [r for r in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in r)]


def load_products(path):
    """Return {part_key: {"pn", "name", "function"}} from a CSV or XLSX file."""
    if not path or not Path(path).exists():
        return {}
    rows = read_xlsx_rows(path) if str(path).lower().endswith((".xlsx", ".xlsm")) else read_csv_rows(path)
    if not rows:
        return {}

    header = [c.strip().lower() for c in rows[0]]
    pn_col = next((i for i, h in enumerate(header) if re.search(r"part|sku|item|model|number|p/n|^pn$", h)), None)
    desc_col = next((i for i, h in enumerate(header) if re.search(r"desc|name|product|title", h) and i != pn_col), None)
    fn_col = next((i for i, h in enumerate(header) if re.search(r"function|category|type|group", h)), None)
    if pn_col is None and desc_col is None:
        pn_col, desc_col, body = 0, 1, rows  # no header row
    else:
        pn_col = 0 if pn_col is None else pn_col
        desc_col = (1 if pn_col == 0 else 0) if desc_col is None else desc_col
        body = rows[1:]

    products = {}
    for r in body:
        pn = r[pn_col].strip() if pn_col < len(r) else ""
        if not pn:
            continue
        name = r[desc_col].strip() if desc_col < len(r) else ""
        fn = normalize_function(r[fn_col]) if fn_col is not None and fn_col < len(r) and r[fn_col].strip() else None
        key = part_key(pn)
        products[key] = {"pn": key, "name": name, "function": fn or guess_function(name)}
    return products


# ---------- media folder ----------

def label_for(filename):
    n = filename.lower()
    stem = Path(filename).stem
    if "datasheet" in n or "data sheet" in n or "data_sheet" in n or "data-sheet" in n:
        return "Datasheet"
    if "manual" in n:
        return "Manual"
    if "quick" in n and "start" in n:
        return "Quick start guide"
    if "photo" in n or "picture" in n:
        return "Product photo"
    pretty = re.sub(r"[_\-]+", " ", stem).strip()
    return pretty[:1].upper() + pretty[1:] if pretty else filename


def human_size(n):
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024


def scan(media_dir, products):
    """Build the product list the page shows, from the folders on disk."""
    media_dir = Path(media_dir)
    found = {}
    if media_dir.is_dir():
        for folder in media_dir.iterdir():
            if not folder.is_dir() or folder.name.startswith("."):
                continue
            key = part_key(folder.name)
            files = []
            for f in sorted(folder.rglob("*")):
                if f.is_file() and f.suffix.lower() in FILE_TYPES and not f.name.startswith("."):
                    rel = f.relative_to(media_dir).as_posix()
                    files.append({
                        "name": f.name,
                        "label": label_for(f.name),
                        "type": FILE_TYPES[f.suffix.lower()],
                        "size": human_size(f.stat().st_size),
                        "url": "/media/" + urllib.parse.quote(rel),
                    })
            found[key] = (folder.name, files)

    out = []
    for key in sorted(set(found) | set(products)):
        info = products.get(key)
        folder, files = found.get(key, (None, []))
        pngs = [f for f in files if f["type"] == "png"]
        photo = next((f for f in pngs if f["label"] == "Product photo"), pngs[0] if pngs else None)
        # Order: photo first, then datasheet, manual, the rest alphabetically.
        rank = {"Product photo": 0, "Datasheet": 1, "Manual": 2, "Quick start guide": 3}
        files.sort(key=lambda f: (f is not photo, rank.get(f["label"], 9), f["label"].lower()))
        out.append({
            "pn": key,
            "name": info["name"] if info else "",
            "function": info["function"] if info else "Other",
            "folder": folder,
            "inList": bool(info),
            "photo": photo["url"] if photo else None,
            "files": files,
        })
    return out


# ---------- web server ----------

class Handler(SimpleHTTPRequestHandler):
    media_dir = None
    products_file = None

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(STATIC), **kw)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(url.path)
        if path == "/api/products":
            return self.send_products()
        if path.startswith("/media/"):
            download = "download" in urllib.parse.parse_qs(url.query)
            return self.send_media(path[len("/media/"):], download)
        if path.startswith("/print/"):
            return self.send_print_page(path[len("/print/"):])
        return super().do_GET()

    def send_json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_products(self):
        products = load_products(self.products_file)
        self.send_json({
            "products": scan(self.media_dir, products),
            "productListLoaded": bool(products),
        })

    def resolve(self, rel):
        root = Path(self.media_dir).resolve()
        target = (root / rel).resolve()
        if root not in target.parents or not target.is_file() or target.suffix.lower() not in FILE_TYPES:
            return None
        return target

    def send_media(self, rel, download):
        target = self.resolve(rel)
        if not target:
            return self.send_error(404, "File not found")
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        size = target.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        disp = "attachment" if download else "inline"
        quoted = urllib.parse.quote(target.name)
        self.send_header("Content-Disposition", f"{disp}; filename*=UTF-8''{quoted}")
        self.end_headers()
        with open(target, "rb") as f:
            while chunk := f.read(1 << 16):
                self.wfile.write(chunk)

    def send_print_page(self, rel):
        """A page that shows one PNG and opens the print dialog."""
        if not self.resolve(rel):
            return self.send_error(404, "File not found")
        src = "/media/" + urllib.parse.quote(rel)
        html = (
            "<!doctype html><meta charset=utf-8><title>Print</title>"
            "<style>@page{margin:12mm}body{margin:0}img{max-width:100%;max-height:100vh;display:block;margin:auto}</style>"
            f"<img src=\"{src}\" onload=\"setTimeout(()=>print(),100)\">"
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)


def main():
    p = argparse.ArgumentParser(description="Serve the Media page.")
    p.add_argument("--media", default=str(HERE / "media"),
                   help="folder that holds the 01-number product folders (default: ./media)")
    p.add_argument("--products", default=None,
                   help="product list, .csv or .xlsx (default: products.xlsx or products.csv inside the media folder)")
    p.add_argument("--port", type=int, default=8080, help="port to listen on (default: 8080)")
    p.add_argument("--host", default="0.0.0.0", help="address to listen on (default: all)")
    args = p.parse_args()

    media = Path(args.media)
    products = args.products
    if not products:
        for name in ("products.xlsx", "products.csv"):
            if (media / name).exists():
                products = str(media / name)
                break
    if not media.is_dir():
        sys.exit(f"Media folder not found: {media}")

    Handler.media_dir = str(media)
    Handler.products_file = products
    count = len(load_products(products))
    print(f"Media folder:  {media.resolve()}")
    print(f"Product list:  {products or '(none found)'}" + (f"  ({count} products)" if products else ""))
    print(f"Open http://localhost:{args.port}  (or http://<this server's name>:{args.port} from other PCs)")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
