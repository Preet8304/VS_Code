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

## Next upgrades for production

- Login and role-based access
- Customer/product edit and delete workflows
- GST invoice numbering rules and return exports
- PDF invoice generation and WhatsApp/email sharing
- Purchase entry + supplier ledger
- Multi-branch and backup/restore support
