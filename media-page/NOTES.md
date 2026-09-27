# Media page — planning notes

Status: first working version built (`server.py` + `static/index.html`). See README.md to set it up on mary.

- Mockup: `mockup.html` (open it in a browser; sample products and files)
- Published preview: https://claude.ai/artifact/TfVqKnDkZb9mhh5Rb8UAY6

## What the site should do

- Site title: **Media page**. No login for now.
- Reads a local folder. Each subfolder is a CyberData 01 number (e.g. `011393/`)
  holding the product photo, datasheet, manual and other marketing files.
- Home page: grid of product thumbnails (the product photo) with 01 number and name.
- Clicking a product opens a drop-down listing every file in that product's folder.
- Clicking a file opens a preview with **Print** and **Download**.
- Top of page: sort by **01 number** (default) or **Function**, and a filter for
  Speakers / Intercoms / Servers. Search by number or name.

## Decisions

1. Product names come from a product list file (part number + description)
   the user will upload. Function (Speakers / Intercoms / Servers) is guessed
   from the description unless the list has a Function column.
2. Runs on the office server **mary** (http://mary:8080). No login.
3. File types: PNG images and PDFs.

## Next

- Try it with the real product list and a few real product folders.
