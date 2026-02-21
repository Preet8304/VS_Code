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

## Deploy on Netlify

Files added for Netlify:

- `netlify.toml`
- `netlify/functions/app.py`

Steps:

1. Push this repo to GitHub.
2. In Netlify, create a new site from that repo.
3. Build command: `pip install -r requirements.txt`
4. Publish directory: leave empty (functions-driven app).
5. Set environment variable:
   - `NETLIFY=true`
   - optional: `DB_PATH=/tmp/cement_billing.db`

Important:
- SQLite on Netlify function storage is temporary (`/tmp`), so data may reset.
- For production, move data to a persistent DB (Postgres, Supabase, Neon, etc.).

## Next upgrades for production

- Login and role-based access
- Customer/product edit and delete workflows
- GST invoice numbering rules and return exports
- PDF invoice generation and WhatsApp/email sharing
- Purchase entry + supplier ledger
- Multi-branch and backup/restore support
