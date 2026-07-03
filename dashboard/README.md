# Lead Generation Dashboard

A read-only FastAPI + Bootstrap 5 dashboard that visualizes the leads produced
by the existing crawler pipeline (`main.py` → `crawler.py` → `lead_cleaner.py`).

It only ever **reads** `output/final_ai_leads.csv`. It does not modify, call,
or depend on `main.py`, `crawler.py`, or `lead_cleaner.py` in any way, so the
existing pipeline keeps working exactly as before.

## Folder structure

```
dashboard/
├── app.py                 FastAPI app + routes
├── dashboard_service.py   pandas-based data layer (stats, charts, filters, export)
├── requirements.txt
├── Dockerfile
├── templates/
│   └── index.html
└── static/
    ├── css/style.css
    └── js/dashboard.js
```

## Running locally (without Docker)

From inside the `dashboard/` folder:

```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Then open: **http://localhost:8000**

The dashboard reads `../output/final_ai_leads.csv` relative to this folder
by default. If that file doesn't exist yet, the UI shows
"No leads generated yet." instead of crashing — run the crawler first
(`python main.py`) and the dashboard will pick the data up automatically
within 30 seconds (or click "Refresh").

You can override the CSV location with an environment variable:

```bash
LEADS_CSV_PATH=/path/to/final_ai_leads.csv uvicorn app:app --host 0.0.0.0 --port 8000
```

## Running with Docker

From the project root (where `docker-compose.yml` lives):

```bash
docker compose up --build
```

This starts two independent services:

- `leadgen` — your existing crawler container (unchanged)
- `dashboard` — this dashboard, exposed at **http://localhost:8000**

Both share the `./output` folder: the crawler writes to it, the dashboard
only reads from it (mounted read-only).

To run just the dashboard:

```bash
docker compose up --build dashboard
```

## API endpoints

| Method | Path                | Description                                   |
|--------|---------------------|------------------------------------------------|
| GET    | `/`                  | Dashboard UI                                  |
| GET    | `/api/stats`         | Total / hot / warm / cold counts, averages    |
| GET    | `/api/charts`        | Priority, score, and completeness distributions |
| GET    | `/api/leads`         | Paginated, filterable, sortable lead list     |
| GET    | `/api/export/csv`    | Export the currently filtered leads as CSV    |
| GET    | `/api/export/excel`  | Export the currently filtered leads as Excel  |
| GET    | `/api/health`        | Health check + resolved CSV path              |

`/api/leads` query params: `search`, `priority` (`all`/`Hot`/`Warm`/`Cold`),
`min_score`, `max_score`, `sort_by`, `sort_order` (`asc`/`desc`), `page`,
`page_size`. The export endpoints accept the same filter params (no
pagination — they export everything matching the current filters).

## Notes

- The frontend polls `/api/stats`, `/api/charts`, and `/api/leads` every
  30 seconds to pick up new crawler output without a page reload.
- All numeric edge cases (missing file, empty file, missing columns) are
  handled in `dashboard_service.py` so the API never returns a 500 for a
  data problem — it returns zeroed/empty results with `has_data: false`
  instead.
