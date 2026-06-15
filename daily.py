#!/usr/bin/env python3
# Minimal: fetch today's arXiv papers in given categories, filter by keywords, print Title/Abstract/URL.
import argparse, datetime, json, sys, time
import arxiv
from store import init_db, upsert_paper

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path
# from datetime import datetime

STAMP_FILE = Path(".last_run")

def hours_since_last_run(default: int = 26) -> int:
    if STAMP_FILE.exists():
        elapsed = time.time() - STAMP_FILE.stat().st_mtime
        return int(elapsed / 3600) + 2  # +2h buffer for arxiv indexing lag
    return default

def write_stamp() -> None:
    STAMP_FILE.touch()


def load_keywords(path: str = "config.json") -> list[str]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    return [kw.lower() for kw in config.get("keywords", [])]

def within_window(dt: datetime.datetime, hours: int) -> bool:
    # make sure `dt` is timezone-aware (arxiv gives aware datetimes, but be robust)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    now = datetime.datetime.now(datetime.timezone.utc)
    delta = now - dt
    return datetime.timedelta(0) <= delta <= datetime.timedelta(hours=hours)
        # def within_window(dt: datetime.datetime, hours: int) -> bool:
        #     now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
        #     return (now - dt).total_seconds() <= hours * 3600 and dt <= now

def matches(text: str, kws: list[str]) -> bool:
    L = text.lower()
    return any(kw in L for kw in kws)

def fetch_for_categories(cats: list[str], max_results: int) -> list[arxiv.Result]:
    client = arxiv.Client()
    by_id: dict[str, arxiv.Result] = {}
    for c in cats:
        search = arxiv.Search(
            query=f"cat:{c}",
            sort_by=arxiv.SortCriterion.SubmittedDate,
            max_results=max_results,
        )
        for r in client.results(search):
            by_id[r.entry_id] = r
    # newest-first: arxiv already sorts; stable order by published desc as a guard
    return sorted(by_id.values(), key=lambda r: r.published, reverse=True)

def print_entry(r: arxiv.Result) -> None:
    print("\n", end="")
    print(r.title.strip())
    print("--->", format_authors(r.authors))     # <-- changed
    print("--->", r.entry_id.strip())
    print("\n", r.summary.strip(), end="\n\n", sep="")
    print("-" * 80)

def format_authors(authors) -> str:
    names = [a.name for a in authors]
    n = len(names)
    if n <= 4:
        return ", ".join(names)
    return f"{names[0]}, {names[1]}, {names[2]}, et al., {names[-1]}"

def load_categories(path: str) -> list[str]:
    seen, out = set(), []
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            s = ln.strip()
            if not s or s.startswith("#"):
                continue
            if s not in seen:
                seen.add(s); out.append(s)
    return out

def render_entry(r: arxiv.Result) -> str:
    return "\n".join([
        r.title.strip(),
        format_authors(r.authors),
        r.entry_id.strip(),
        r.summary.strip(),
        "-" * 80,
        ""
    ])

def main(argv=None):
    p = argparse.ArgumentParser(description="Filter daily arXiv papers by keywords.")
    p.add_argument("--cats-file", default="categories.txt", help="path to categories file (one arXiv category per line)")
    p.add_argument("--cats", nargs="+", default=None, help="explicit categories (overrides --cats-file)")
    p.add_argument("--config", default="config.json", help="path to config file")
    p.add_argument("--hours", type=int, default=None, help="look back this many hours (default: auto from last run)")
    p.add_argument("--max", type=int, default=100, help="max results to fetch (safety cap)")
    p.add_argument("--outdir", default="contents", help="directory to write the daily abstracts file")
    args = p.parse_args(argv)

    hours = args.hours if args.hours is not None else hours_since_last_run()
    print(f"Looking back {hours} hours.")

    kws = load_keywords(args.config)
    if not kws:
        print("No keywords loaded.", file=sys.stderr); return 1

    cats = args.cats if args.cats else load_categories(args.cats_file)
    if not cats:
        print("No categories provided (empty --cats and empty categories file).", file=sys.stderr)
        return 1

    init_db()

    results = fetch_for_categories(cats, args.max)
    hits = []
    for r in results:
        if not within_window(r.published, hours):
            continue
        blob = f"{r.title}\n{r.summary}"
        if matches(blob, kws):
            hits.append(r)

    for r in hits:
        arxiv_id = r.entry_id.split("/abs/")[-1]
        upsert_paper(
            arxiv_id=arxiv_id,
            title=r.title.strip(),
            authors=format_authors(r.authors),
            abstract=r.summary.strip(),
            url=r.entry_id.strip(),
            submitted=r.published,
            recipients=[],
        )

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.datetime.now().astimezone().date().isoformat()  # local date
    outfile = outdir / f"daily-abstracts-{date_str}.txt"

    with outfile.open("w", encoding="utf-8") as f:
        if hits:
            for r in hits:
                f.write(render_entry(r))
        else:
            f.write("(no matches)\n")

    print(f"Wrote {len(hits)} matches to {outfile}")
    write_stamp()

    # Print
    if not hits:
        print("(no matches)")
        return 0
    # Newest first already; print
    for r in hits:
        print_entry(r)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
