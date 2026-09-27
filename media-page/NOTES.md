# Media page — planning notes

Status: design mockup only. Nothing is built yet.

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

## Open questions

1. How does the site get each product's name and function? A folder name only
   gives the number. Option: a small info file per folder, or one spreadsheet
   (01 number, name, function).
2. Where will it run: one PC, an office-network server, or the public internet?
3. Which file types are in the folders? PDF, images and video preview in a
   browser; Word/PowerPoint would likely be download-only.
