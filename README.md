# Cement Billing Web Software

Web-based cement billing system built with Flask + SQLite.

## Features

- Dashboard with key stats and low-stock alerts
- Customer management
- Product catalog with stock and GST settings
- Invoice creation with:
  - multi-line items
  - GST calculations per line
  - loading/transport/discount adjustments
  - paid vs due tracking
- Printable invoice view
- Basic sales and product reports

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open: `http://127.0.0.1:5000`

## Deploy on Render

Files added for Render:

- `render.yaml`
- `wsgi.py`
- `Procfile`

Steps:

1. Push this repo to GitHub.
2. In Render, create a new Blueprint (recommended) or Web Service from this repo.
3. Render picks `render.yaml` automatically, including:
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn wsgi:app`
   - Persistent disk mounted at `/var/data`
4. App DB path is configured via:
   - `RENDER=true`
   - `DB_PATH=/var/data/cement_billing.db`

Important:
- If you skip disk setup, SQLite data will be temporary and may reset on deploy/restart.
- For scale and multi-instance use, migrate to Postgres.

## Netlify Files (Optional)

- `netlify.toml`
- `netlify/functions/app.py`

## Next upgrades for production

- Login and role-based access
- Customer/product edit and delete workflows
- GST invoice numbering rules and return exports
- PDF invoice generation and WhatsApp/email sharing
- Purchase entry + supplier ledger
- Multi-branch and backup/restore support
