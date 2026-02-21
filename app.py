from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

from flask import Flask, flash, g, redirect, render_template, request, url_for


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "cement_billing.db"

if os.getenv("NETLIFY"):
    DB_PATH = Path(os.getenv("DB_PATH", "/tmp/cement_billing.db"))
elif os.getenv("RENDER"):
    DB_PATH = Path(os.getenv("DB_PATH", "/var/data/cement_billing.db"))
else:
    DB_PATH = Path(os.getenv("DB_PATH", str(DEFAULT_DB_PATH)))

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-me-in-production"


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_: object) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            mobile TEXT,
            gstin TEXT,
            address TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            brand TEXT,
            unit TEXT NOT NULL DEFAULT 'Bag',
            rate REAL NOT NULL DEFAULT 0,
            stock REAL NOT NULL DEFAULT 0,
            gst_percent REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_no TEXT NOT NULL UNIQUE,
            invoice_date TEXT NOT NULL,
            customer_id INTEGER NOT NULL,
            loading_charge REAL NOT NULL DEFAULT 0,
            transport_charge REAL NOT NULL DEFAULT 0,
            discount REAL NOT NULL DEFAULT 0,
            subtotal REAL NOT NULL DEFAULT 0,
            gst_total REAL NOT NULL DEFAULT 0,
            grand_total REAL NOT NULL DEFAULT 0,
            paid_amount REAL NOT NULL DEFAULT 0,
            payment_mode TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers (id)
        );

        CREATE TABLE IF NOT EXISTS invoice_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            qty REAL NOT NULL,
            rate REAL NOT NULL,
            gst_percent REAL NOT NULL,
            line_total REAL NOT NULL,
            FOREIGN KEY (invoice_id) REFERENCES invoices (id),
            FOREIGN KEY (product_id) REFERENCES products (id)
        );
        """
    )
    db.commit()


def next_invoice_no(db: sqlite3.Connection) -> str:
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"INV-{today}-"
    row = db.execute(
        "SELECT invoice_no FROM invoices WHERE invoice_no LIKE ? ORDER BY id DESC LIMIT 1",
        (f"{prefix}%",),
    ).fetchone()
    if row is None:
        return f"{prefix}001"
    last = int(row["invoice_no"].split("-")[-1])
    return f"{prefix}{last + 1:03d}"


@app.route("/")
def dashboard() -> str:
    db = get_db()
    stats = {
        "customer_count": db.execute("SELECT COUNT(*) AS c FROM customers").fetchone()["c"],
        "product_count": db.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"],
        "invoice_count": db.execute("SELECT COUNT(*) AS c FROM invoices").fetchone()["c"],
        "pending_amount": db.execute(
            "SELECT COALESCE(SUM(grand_total - paid_amount), 0) AS p FROM invoices"
        ).fetchone()["p"],
    }
    recent_invoices = db.execute(
        """
        SELECT i.id, i.invoice_no, i.invoice_date, i.grand_total, i.paid_amount, c.name AS customer_name
        FROM invoices i
        JOIN customers c ON c.id = i.customer_id
        ORDER BY i.id DESC
        LIMIT 8
        """
    ).fetchall()
    low_stock = db.execute(
        "SELECT id, name, brand, stock, unit FROM products WHERE stock <= 20 ORDER BY stock ASC LIMIT 10"
    ).fetchall()
    return render_template("dashboard.html", stats=stats, recent_invoices=recent_invoices, low_stock=low_stock)


@app.route("/customers", methods=["GET", "POST"])
def customers() -> str:
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Customer name is required.", "error")
            return redirect(url_for("customers"))
        db.execute(
            """
            INSERT INTO customers (name, mobile, gstin, address, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                name,
                request.form.get("mobile", "").strip(),
                request.form.get("gstin", "").strip(),
                request.form.get("address", "").strip(),
                datetime.now().isoformat(),
            ),
        )
        db.commit()
        flash("Customer added.", "success")
        return redirect(url_for("customers"))

    rows = db.execute("SELECT * FROM customers ORDER BY id DESC").fetchall()
    return render_template("customers.html", customers=rows)


@app.route("/products", methods=["GET", "POST"])
def products() -> str:
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Product name is required.", "error")
            return redirect(url_for("products"))
        db.execute(
            """
            INSERT INTO products (name, brand, unit, rate, stock, gst_percent, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                request.form.get("brand", "").strip(),
                request.form.get("unit", "Bag").strip() or "Bag",
                float(request.form.get("rate", "0") or 0),
                float(request.form.get("stock", "0") or 0),
                float(request.form.get("gst_percent", "0") or 0),
                datetime.now().isoformat(),
            ),
        )
        db.commit()
        flash("Product added.", "success")
        return redirect(url_for("products"))

    rows = db.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    return render_template("products.html", products=rows)


@app.route("/invoices")
def invoices() -> str:
    db = get_db()
    rows = db.execute(
        """
        SELECT i.*, c.name AS customer_name
        FROM invoices i
        JOIN customers c ON c.id = i.customer_id
        ORDER BY i.id DESC
        """
    ).fetchall()
    return render_template("invoices.html", invoices=rows)


@app.route("/invoices/new", methods=["GET", "POST"])
def invoice_new() -> str:
    db = get_db()
    if request.method == "POST":
        customer_id = int(request.form.get("customer_id", "0") or 0)
        if customer_id <= 0:
            flash("Select a customer.", "error")
            return redirect(url_for("invoice_new"))

        raw_items = request.form.get("items_json", "")
        if not raw_items:
            flash("Add at least one product line.", "error")
            return redirect(url_for("invoice_new"))

        try:
            items = json.loads(raw_items)
        except json.JSONDecodeError:
            flash("Invalid invoice item payload.", "error")
            return redirect(url_for("invoice_new"))

        if not items:
            flash("Add at least one product line.", "error")
            return redirect(url_for("invoice_new"))

        subtotal = 0.0
        gst_total = 0.0
        parsed_items = []
        for item in items:
            product_id = int(item["product_id"])
            qty = float(item["qty"])
            rate = float(item["rate"])
            gst_percent = float(item["gst_percent"])
            taxable = qty * rate
            line_gst = taxable * gst_percent / 100
            line_total = taxable + line_gst
            subtotal += taxable
            gst_total += line_gst
            parsed_items.append((product_id, qty, rate, gst_percent, line_total))

        loading_charge = float(request.form.get("loading_charge", "0") or 0)
        transport_charge = float(request.form.get("transport_charge", "0") or 0)
        discount = float(request.form.get("discount", "0") or 0)
        grand_total = subtotal + gst_total + loading_charge + transport_charge - discount
        paid_amount = float(request.form.get("paid_amount", "0") or 0)

        invoice_no = next_invoice_no(db)
        cursor = db.execute(
            """
            INSERT INTO invoices (
                invoice_no, invoice_date, customer_id, loading_charge, transport_charge, discount,
                subtotal, gst_total, grand_total, paid_amount, payment_mode, notes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                invoice_no,
                request.form.get("invoice_date") or date.today().isoformat(),
                customer_id,
                loading_charge,
                transport_charge,
                discount,
                subtotal,
                gst_total,
                grand_total,
                paid_amount,
                request.form.get("payment_mode", ""),
                request.form.get("notes", ""),
                datetime.now().isoformat(),
            ),
        )
        invoice_id = cursor.lastrowid

        for product_id, qty, rate, gst_percent, line_total in parsed_items:
            db.execute(
                """
                INSERT INTO invoice_items (invoice_id, product_id, qty, rate, gst_percent, line_total)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (invoice_id, product_id, qty, rate, gst_percent, line_total),
            )
            db.execute(
                "UPDATE products SET stock = stock - ? WHERE id = ?",
                (qty, product_id),
            )

        db.commit()
        flash("Invoice created.", "success")
        return redirect(url_for("invoice_view", invoice_id=invoice_id))

    customer_rows = db.execute("SELECT id, name, mobile, gstin FROM customers ORDER BY name ASC").fetchall()
    product_rows = db.execute(
        "SELECT id, name, brand, unit, rate, stock, gst_percent FROM products ORDER BY name ASC"
    ).fetchall()
    return render_template(
        "invoice_new.html",
        customers=customer_rows,
        products=product_rows,
        invoice_date=date.today().isoformat(),
        suggested_invoice_no=next_invoice_no(db),
    )


@app.route("/invoices/<int:invoice_id>")
def invoice_view(invoice_id: int) -> str:
    db = get_db()
    invoice = db.execute(
        """
        SELECT i.*, c.name AS customer_name, c.mobile, c.gstin, c.address
        FROM invoices i
        JOIN customers c ON c.id = i.customer_id
        WHERE i.id = ?
        """,
        (invoice_id,),
    ).fetchone()
    if invoice is None:
        flash("Invoice not found.", "error")
        return redirect(url_for("invoices"))

    items = db.execute(
        """
        SELECT ii.*, p.name AS product_name, p.brand, p.unit
        FROM invoice_items ii
        JOIN products p ON p.id = ii.product_id
        WHERE ii.invoice_id = ?
        """,
        (invoice_id,),
    ).fetchall()
    return render_template("invoice_view.html", invoice=invoice, items=items)


@app.route("/reports")
def reports() -> str:
    db = get_db()
    sales_by_day = db.execute(
        """
        SELECT invoice_date, SUM(grand_total) AS total_sales, COUNT(*) AS bills
        FROM invoices
        GROUP BY invoice_date
        ORDER BY invoice_date DESC
        LIMIT 30
        """
    ).fetchall()
    top_products = db.execute(
        """
        SELECT p.name, p.brand, SUM(ii.qty) AS sold_qty
        FROM invoice_items ii
        JOIN products p ON p.id = ii.product_id
        GROUP BY ii.product_id
        ORDER BY sold_qty DESC
        LIMIT 10
        """
    ).fetchall()
    return render_template("reports.html", sales_by_day=sales_by_day, top_products=top_products)


@app.context_processor
def inject_now() -> dict[str, str]:
    return {"today": date.today().isoformat()}


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(debug=True)
