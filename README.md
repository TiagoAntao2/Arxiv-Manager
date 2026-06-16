# arXiv Manager

A local web app for browsing, filtering, and building a personal library of arXiv papers.

## Features

### Daily feed
- Fetches arXiv papers matching your keywords on a configurable time window
- Automatically adjusts the lookback window based on the last run (handles weekend batches correctly)
- Papers are stored in a local SQLite database

### Highlights
- Sends fetched papers to an LLM to identify the most relevant ones based on your research interests
- Highlighted papers are marked with a ★ badge and sorted to the top

### Library
- Browse all saved papers across all dates
- Filter by downloaded or highlighted
- Full-text search across titles, authors, and abstracts

### Ad-hoc search
- Search arXiv directly with a free-form query and a custom time window (hours, weeks, or months)
- Results are temporary — save individual papers to your library with one click
- Run highlights on search results with an optional custom motivation prompt

### PDF management
- Download PDFs for individual papers or in bulk
- Open downloaded PDFs directly from the browser

### Settings
- Edit your keywords and research interests description from the web interface
- Changes take effect on the next fetch

## Setup

### Requirements
- Python 3.10+
- An OpenAI-compatible LLM API (for highlights and summaries)

### Installation

```bash
git clone https://github.com/TiagoAntao2/Arxiv-Manager.git
cd Arxiv-Manager
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Configuration

Copy `.env_.example` to `.env_` and fill in your values:

```bash
cp .env_.example .env_
```

```
LLM_API_KEY="your-api-key"
LLM_BASE_URL="https://your-llm-gateway/api/v1"  # omit to use OpenAI directly
LLM_MODEL="gpt-4o-mini"
```

Edit `config.json` to set your keywords and research interests, or do it from the Settings page after launching.

### Running

```bash
python app.py
```

The app opens automatically at `http://localhost:5050`.

On Windows you can also double-click `launch.bat`.
