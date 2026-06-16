#!/usr/bin/env python3
"""
app.py: Local web UI for browsing and downloading arXiv papers.
Run with: python app.py
"""

import datetime
import subprocess
import sys
from pathlib import Path

import arxiv as arxiv_lib
import json
import os
import re
import threading
import webbrowser
from dotenv import load_dotenv
from openai import OpenAI
from flask import Flask, render_template, request, jsonify, Response, stream_with_context, redirect, url_for, flash
from store import init_db, get_papers, mark_downloaded, mark_highlighted, get_pending_highlight, get_available_dates, upsert_paper

app = Flask(__name__)
app.secret_key = "arxiv-manager-local"
PDF_DIR = Path("pdfs")


def download_pdf(arxiv_id: str) -> Path:
    PDF_DIR.mkdir(exist_ok=True)
    outfile = PDF_DIR / f"{arxiv_id.replace('/', '_')}.pdf"
    if not outfile.exists():
        url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        import requests
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        outfile.write_bytes(r.content)
    mark_downloaded(arxiv_id, outfile)
    return outfile


@app.route("/")
def index():
    dates = get_available_dates()
    selected = request.args.get("date", dates[0] if dates else "")
    highlighted_only = request.args.get("highlighted") == "1"
    papers = get_papers(highlighted_only=highlighted_only, date=selected)
    prev_date = dates[dates.index(selected) + 1] if selected in dates and dates.index(selected) + 1 < len(dates) else None
    next_date = dates[dates.index(selected) - 1] if selected in dates and dates.index(selected) > 0 else None
    return render_template("index.html", papers=papers, dates=dates, selected_date=selected,
                           prev_date=prev_date, next_date=next_date, highlighted_only=highlighted_only)


@app.route("/library")
def library():
    search = request.args.get("q", "")
    downloaded_only = request.args.get("downloaded") == "1"
    highlighted_only = request.args.get("highlighted") == "1"
    papers = get_papers(downloaded_only=downloaded_only, highlighted_only=highlighted_only, search=search)
    return render_template("library.html", papers=papers, search=search,
                           downloaded_only=downloaded_only, highlighted_only=highlighted_only)


@app.route("/download", methods=["POST"])
def download():
    ids = request.json.get("ids", [])
    results = {}
    for arxiv_id in ids:
        try:
            path = download_pdf(arxiv_id)
            results[arxiv_id] = {"ok": True, "path": str(path)}
        except Exception as e:
            results[arxiv_id] = {"ok": False, "error": str(e)}
    return jsonify(results)


@app.route("/open", methods=["POST"])
def open_pdf():
    arxiv_id = request.json.get("id")
    path = PDF_DIR / f"{arxiv_id.replace('/', '_')}.pdf"
    if not path.exists():
        return jsonify({"ok": False, "error": "Not downloaded yet"})
    if sys.platform == "win32":
        subprocess.Popen(["start", "", str(path)], shell=True)
    else:
        subprocess.Popen(["xdg-open", str(path)])
    return jsonify({"ok": True})


PROMPT_HIGHLIGHTS = """
You are a research assistant for someone who works on {interests}.
From the papers below, select only those most directly relevant to their research.
Reply with ONLY a JSON array of arxiv IDs (e.g. ["2401.12345", "2312.67890"]).
Be selective — only include papers with clear relevance. No explanation, just the JSON array.

Papers:
{papers}
"""

CONFIG_FILE = Path("config.json")


def _llm_client() -> tuple[OpenAI, str]:
    load_dotenv(dotenv_path=".env_")
    client = OpenAI(
        api_key=os.environ["LLM_API_KEY"],
        base_url=os.environ.get("LLM_BASE_URL"),
    )
    return client, os.environ.get("LLM_MODEL", "gpt-4o-mini")


@app.route("/highlight", methods=["POST"])
def highlight():
    papers = get_pending_highlight()
    if not papers:
        return jsonify({"ok": True, "message": "No new papers to evaluate.", "highlighted": []})

    interests = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))["interests"]

    paper_text = "\n\n".join(
        f"ID: {p['arxiv_id']}\nTitle: {p['title']}\nAbstract: {p['abstract']}"
        for p in papers
    )
    prompt = PROMPT_HIGHLIGHTS.format(interests=interests, papers=paper_text)

    try:
        client, model = _llm_client()
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.choices[0].message.content.strip()
        match = re.search(r"\[.*?\]", raw, re.DOTALL)
        highlighted_ids = set(json.loads(match.group()) if match else [])
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

    for p in papers:
        mark_highlighted(p["arxiv_id"], p["arxiv_id"] in highlighted_ids)

    return jsonify({"ok": True, "highlighted": list(highlighted_ids),
                    "total": len(papers)})


@app.route("/highlight-papers", methods=["POST"])
def highlight_papers():
    papers = request.json.get("papers", [])
    if not papers:
        return jsonify({"ok": True, "highlighted": []})
    motivation = request.json.get("motivation")
    if motivation:
        interests = motivation
    else:
        interests = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))["interests"]
    paper_text = "\n\n".join(
        f"ID: {p['arxiv_id']}\nTitle: {p['title']}\nAbstract: {p['abstract']}"
        for p in papers
    )
    prompt = PROMPT_HIGHLIGHTS.format(interests=interests, papers=paper_text)
    try:
        client, model = _llm_client()
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.choices[0].message.content.strip()
        match = re.search(r"\[.*?\]", raw, re.DOTALL)
        highlighted = json.loads(match.group()) if match else []
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})
    return jsonify({"ok": True, "highlighted": highlighted})


@app.route("/run-daily")
def run_daily():
    hours = request.args.get("hours")
    cmd = [sys.executable, "daily.py"]
    if hours:
        cmd += ["--hours", hours]

    def generate():
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, encoding="utf-8", errors="replace",
            env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"}
        )
        for line in proc.stdout:
            yield f"data: {line.rstrip()}\n\n"
        proc.wait()
        yield f"data: __done__ (exit code {proc.returncode})\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@app.route("/settings", methods=["GET", "POST"])
def settings():
    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    if request.method == "POST":
        keywords_raw = request.form.get("keywords", "").replace("\r\n", "\n").replace("\r", "\n").strip()
        keywords = [k.strip() for k in keywords_raw.splitlines() if k.strip()]
        config["keywords"] = keywords
        config["interests"] = request.form.get("interests", "").strip()
        CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        flash("Settings saved.")
        return redirect(url_for("settings"))
    keywords = "\n".join(config.get("keywords", []))
    interests = config["interests"]
    return render_template("settings.html", keywords=keywords, interests=interests)


@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    author = request.args.get("author", "").strip()
    amount = int(request.args.get("amount", 24))
    unit = request.args.get("unit", "hours")
    multipliers = {"hours": 1, "weeks": 168, "months": 730}
    hours = amount * multipliers.get(unit, 1)
    results = []
    if query or author:
        parts = []
        if query:
            parts.append(query)
        if author:
            parts.append(f"au:{author}")
        combined_query = " AND ".join(parts)
        client = arxiv_lib.Client()
        search_obj = arxiv_lib.Search(
            query=combined_query,
            sort_by=arxiv_lib.SortCriterion.SubmittedDate,
            max_results=50,
        )
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
        for r in client.results(search_obj):
            pub = r.published
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=datetime.timezone.utc)
            if pub < cutoff:
                break
            arxiv_id = r.entry_id.split("/abs/")[-1]
            results.append({
                "arxiv_id": arxiv_id,
                "title": r.title.strip(),
                "authors": _format_authors(r.authors),
                "abstract": r.summary.strip(),
                "url": r.entry_id.strip(),
                "submitted": pub.strftime("%Y-%m-%d"),
            })
    return render_template("search.html", results=results, query=query, author=author, amount=amount, unit=unit)


def _format_authors(authors) -> str:
    names = [a.name for a in authors]
    if len(names) <= 4:
        return ", ".join(names)
    return f"{names[0]}, {names[1]}, {names[2]}, et al., {names[-1]}"


@app.route("/save-paper", methods=["POST"])
def save_paper():
    data = request.json
    try:
        submitted = datetime.datetime.fromisoformat(data["submitted"] + "T00:00:00+00:00")
        upsert_paper(
            arxiv_id=data["arxiv_id"],
            title=data["title"],
            authors=data["authors"],
            abstract=data["abstract"],
            url=data["url"],
            submitted=submitted,
            recipients=[],
        )
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


if __name__ == "__main__":
    init_db()
    threading.Timer(1.5, lambda: webbrowser.open("http://localhost:5050")).start()
    app.run(debug=False, port=5050)
