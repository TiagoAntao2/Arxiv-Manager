#!/usr/bin/env python3
"""
download_pdfs.py: Read a daily-abstracts-*.txt (or summary/highlights file),
extract arXiv links, and download the PDFs into ./pdfs/YYYY-MM-DD/
"""

import argparse
import re
from pathlib import Path
import requests

def extract_arxiv_ids(text: str) -> list[str]:
    # Matches arxiv.org/abs/ID (with optional vN)
    pattern = r"arxiv\.org/abs/(\d{4}\.\d{5}(v\d+)?)"
    return re.findall(pattern, text)

def pdf_url(arxiv_id: str) -> str:
    return f"https://arxiv.org/pdf/{arxiv_id}.pdf"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("infile", help="path to daily-abstracts-*.txt or highlights/summary file")
    args = ap.parse_args()

    infile = Path(args.infile)

    # derive date from filename (expects daily-abstracts-YYYY-MM-DD.txt)
    stem_parts = infile.stem.split("-")
    date_str = "-".join(stem_parts[-3:])  # grab YYYY-MM-DD
    outdir = Path("pdfs") / date_str
    outdir.mkdir(parents=True, exist_ok=True)

    text = infile.read_text(encoding="utf-8")
    matches = extract_arxiv_ids(text)

    if not matches:
        print("No arXiv IDs found.")
        return

    for arxiv_id, _ in matches:
        url = pdf_url(arxiv_id)
        outfile = outdir / f"{arxiv_id.replace('/', '_')}.pdf"
        if outfile.exists():
            print(f"Already have {outfile}")
            continue
        print(f"Downloading {url}")
        r = requests.get(url)
        r.raise_for_status()
        outfile.write_bytes(r.content)

    print(f"Saved {len(matches)} PDFs to {outdir}")

if __name__ == "__main__":
    main()
