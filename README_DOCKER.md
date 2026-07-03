# Lead Generation — Docker Setup

## Project Structure
```
lead Generation/
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── requirements.txt
├── main.py               ← entry point (asks for search query)
├── scrapers/
│   └── crawler.py        ← Playwright + Google Maps scraper
├── config/
├── output/               ← CSVs saved here (mounted as volume)
└── logs/
```

---

## Quick Start

### 1. Build the image
```bash
docker build -t leadgen-app .
```

### 2. Run interactively (you type the search query)
```bash
docker run -it --rm \
  -v $(pwd)/output:/app/output \
  leadgen-app
```
The app will prompt:
```
Enter business type and city: restaurants in Mumbai
```
Results are saved to `./output/local_business_leads.csv` on your machine.

---

### Using Docker Compose (easier)

```bash
# Build + run
docker compose up --build

# Run again without rebuilding
docker compose run --rm leadgen
```

---

### Non-interactive mode (pass query via env var)

Edit `docker-compose.yml` and uncomment:
```yaml
environment:
  - SEARCH_QUERY=restaurants in Bhopal
```

Then update `main.py` to read from env:
```python
import os
search_query = os.environ.get("SEARCH_QUERY") or input("Enter business type and city: ")
```

---

## Retrieving Output

The `./output` folder on your host machine is synced with `/app/output` inside the container.
After the run completes, open:
```
output/local_business_leads.csv
```

---

## Common Issues

| Problem | Fix |
|---|---|
| `playwright install` fails | Run `docker build --no-cache .` |
| No results / Maps blocked | Google Maps may detect automation — add delays or rotate user agent |
| `output/` folder is empty | Make sure you used `-v $(pwd)/output:/app/output` |
| Container exits immediately | Use `docker run -it` (interactive mode required) |
