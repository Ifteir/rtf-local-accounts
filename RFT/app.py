from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, send_from_directory
import sqlite3, os
from functools import wraps
from datetime import date, datetime
from math import isfinite
from werkzeug.security import generate_password_hash, check_password_hash

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "accounts.db")
app = Flask(__name__)
app.secret_key = os.environ.get("RTF_SECRET_KEY", "change-this-local-secret-key")

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS parties(
          id INTEGER PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('client','vendor')),
          name TEXT NOT NULL, company TEXT DEFAULT '', phone TEXT DEFAULT '', address TEXT DEFAULT '',
          page_no TEXT DEFAULT '', opening_balance REAL NOT NULL DEFAULT 0, notes TEXT DEFAULT '',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS transactions(
          id INTEGER PRIMARY KEY, party_id INTEGER NOT NULL REFERENCES parties(id) ON DELETE CASCADE,
          txn_date TEXT NOT NULL, txn_type TEXT NOT NULL, description TEXT DEFAULT '',
          amount REAL NOT NULL CHECK(amount >= 0), reference TEXT DEFAULT '',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_party_name ON parties(name);
        CREATE INDEX IF NOT EXISTS idx_txn_party_date ON transactions(party_id, txn_date);
        """)
        cols = [r[1] for r in con.execute("PRAGMA table_info(transactions)").fetchall()]
        if "payment" not in cols:
            con.execute("ALTER TABLE transactions ADD COLUMN payment REAL NOT NULL DEFAULT 0")
        if "discount" not in cols:
            con.execute("ALTER TABLE transactions ADD COLUMN discount REAL NOT NULL DEFAULT 0")
        if "invoice_no" not in cols:
            con.execute("ALTER TABLE transactions ADD COLUMN invoice_no TEXT DEFAULT ''")
        if not con.execute("SELECT 1 FROM users WHERE username='admin'").fetchone():
            con.execute("INSERT INTO users(username,password_hash) VALUES(?,?)",
                        ("admin", generate_password_hash("admin123")))

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped

def money(value):
    return f"{float(value or 0):,.2f}"

def parse_date(value):
    value = (value or "").strip()
    try:
        return datetime.strptime(value, "%d-%m-%Y").date()
    except ValueError:
        return date.fromisoformat(value)

def date_range_from_request():
    result = []
    for label in ("from", "to"):
        value = request.args.get(label, "").strip()
        if not value:
            result.append("")
            continue
        try:
            result.append(parse_date(value).isoformat())
        except ValueError:
            flash(f"Enter a valid {label} date in day-month-year format.", "error")
            result.append("")
    return result

@app.template_filter("money")
def money_filter(value): return money(value)

@app.template_filter("dmy")
def date_dmy(value):
    if not value:
        return ""
    try:
        parsed = value if isinstance(value, date) else parse_date(str(value))
        return parsed.strftime("%d-%m-%Y")
    except ValueError:
        return str(value)

@app.route("/static/<path:filename>")
def static_file(filename):
    return send_from_directory(os.path.join(APP_DIR, "static"), filename)

def party_balance(p, con):
    rows = con.execute("SELECT txn_type, amount, payment, discount FROM transactions WHERE party_id=?", (p["id"],)).fetchall()
    bal = float(p["opening_balance"] or 0)
    for r in rows:
        t, a = r["txn_type"], float(r["amount"])
        if p["kind"] == "client":
            if t == "bill": bal += a - float(r["payment"] or 0) - float(r["discount"] or 0)
            elif t == "adjustment_debit": bal += a
            elif t == "payment": bal -= a + float(r["discount"] or 0)
            elif t == "adjustment_credit": bal -= a
        else:
            if t in ("purchase", "adjustment_debit"): bal += a
            elif t in ("vendor_payment", "adjustment_credit"): bal -= a
    return bal

def transaction_amounts(kind, txn):
    txn_type = txn["txn_type"]
    amount = float(txn["amount"] or 0)
    discount = float(txn["discount"] or 0)
    if kind == "client":
        if txn_type == "bill":
            payment = float(txn["payment"] or 0)
            return amount, payment, discount, amount - payment - discount
        if txn_type == "payment":
            return 0, amount, discount, -amount - discount
        if txn_type == "adjustment_debit":
            return amount, 0, 0, amount
        if txn_type == "adjustment_credit":
            return amount, 0, 0, -amount
    else:
        if txn_type == "purchase":
            return amount, 0, 0, amount
        if txn_type == "vendor_payment":
            return 0, amount, 0, -amount
        if txn_type == "adjustment_debit":
            return amount, 0, 0, amount
        if txn_type == "adjustment_credit":
            return amount, 0, 0, -amount
    return 0, 0, 0, 0

def statement_totals(kind, txns):
    totals = {"amount": 0, "payment": 0, "discount": 0, "due": 0}
    for txn in txns:
        amount, payment, discount, due = transaction_amounts(kind, txn)
        totals["amount"] += amount
        totals["payment"] += payment
        totals["discount"] += discount
        totals["due"] += due
    return totals

def statement_rows(kind, txns):
    rows = []
    for txn in txns:
        row = dict(txn)
        (row["display_amount"], row["display_payment"], row["display_discount"],
         row["display_due"]) = transaction_amounts(kind, txn)
        rows.append(row)
    return rows

@app.route("/")
def home():
    return redirect(url_for("dashboard") if session.get("user_id") else url_for("login"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        with db() as con:
            u = con.execute("SELECT * FROM users WHERE username=?", (request.form.get("username","").strip(),)).fetchone()
        if u and check_password_hash(u["password_hash"], request.form.get("password","")):
            session.clear()
            session["user_id"], session["username"] = u["id"], u["username"]
            return redirect(url_for("dashboard"))
        flash("Username or password is incorrect.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    with db() as con:
        parties = con.execute("SELECT * FROM parties ORDER BY name").fetchall()
        recent = con.execute("""SELECT t.*,p.name,p.kind FROM transactions t JOIN parties p ON p.id=t.party_id
                                ORDER BY t.txn_date DESC,t.id DESC LIMIT 8""").fetchall()
        totals = {"clients":0,"vendors":0,"client_due":0,"vendor_due":0}
        for p in parties:
            b = party_balance(p, con)
            if p["kind"] == "client":
                totals["clients"] += 1; totals["client_due"] += b
            else:
                totals["vendors"] += 1; totals["vendor_due"] += b
    return render_template("dashboard.html", totals=totals, recent=recent)

@app.route("/parties")
@login_required
def parties():
    kind = request.args.get("kind","all")
    due_only = request.args.get("due") == "1"
    q = request.args.get("q","").strip()
    sql, params = "SELECT * FROM parties WHERE 1=1", []
    if kind in ("client","vendor"): sql += " AND kind=?"; params.append(kind)
    if q:
        sql += " AND (name LIKE ? OR company LIKE ? OR phone LIKE ?)"
        params += [f"%{q}%"]*3
    sql += " ORDER BY kind,name"
    with db() as con:
        rows = con.execute(sql, params).fetchall()
        data = [{"party":p, "balance":party_balance(p,con)} for p in rows]
    if due_only:
        data = [row for row in data if (
            row["balance"] != 0 if row["party"]["kind"] == "vendor"
            else row["balance"] > 0
        )]
    return render_template("parties.html", rows=data, kind=kind, q=q, due_only=due_only)

@app.route("/party/new", methods=["GET","POST"])
@login_required
def party_new():
    kind = request.args.get("kind", request.form.get("kind","client"))
    if kind not in ("client","vendor"): kind="client"
    if request.method == "POST":
        with db() as con:
            con.execute("""INSERT INTO parties(kind,name,company,phone,address,page_no,opening_balance,notes)
                VALUES(?,?,?,?,?,?,?,?)""",
                (kind, request.form["name"].strip(), request.form.get("company","").strip(),
                 request.form.get("phone","").strip(), request.form.get("address","").strip(),
                 request.form.get("page_no","").strip(), 0,
                 request.form.get("notes","").strip()))
            pid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        flash("Record added.", "success")
        return redirect(url_for("party_detail", party_id=pid))
    return render_template("party_form.html", party=None, kind=kind)

@app.route("/party/<int:party_id>/edit", methods=["GET","POST"])
@login_required
def party_edit(party_id):
    with db() as con: p=con.execute("SELECT * FROM parties WHERE id=?",(party_id,)).fetchone()
    if not p: abort(404)
    if request.method=="POST":
        with db() as con:
            con.execute("""UPDATE parties SET name=?,company=?,phone=?,address=?,page_no=?,opening_balance=?,notes=? WHERE id=?""",
             (request.form["name"].strip(),request.form.get("company","").strip(),request.form.get("phone","").strip(),
              request.form.get("address","").strip(),request.form.get("page_no","").strip(),
              float(p["opening_balance"] or 0),request.form.get("notes","").strip(),party_id))
        flash("Record updated.","success"); return redirect(url_for("party_detail",party_id=party_id))
    return render_template("party_form.html",party=p,kind=p["kind"])

@app.route("/party/<int:party_id>")
@login_required
def party_detail(party_id):
    start, end = date_range_from_request()
    with db() as con:
        p=con.execute("SELECT * FROM parties WHERE id=?",(party_id,)).fetchone()
        if not p: abort(404)
        sql="SELECT * FROM transactions WHERE party_id=?"; args=[party_id]
        if start: sql+=" AND txn_date>=?"; args.append(start)
        if end: sql+=" AND txn_date<=?"; args.append(end)
        sql+=" ORDER BY txn_date,id"
        txns=con.execute(sql,args).fetchall()
        balance=party_balance(p,con)
        totals=statement_totals(p["kind"],txns)
        txns=statement_rows(p["kind"],txns)
    return render_template("party_detail.html",p=p,txns=txns,balance=balance,start=start,end=end,
                           total_amount=totals["amount"],total_payment=totals["payment"],
                           total_discount=totals["discount"],total_due=totals["due"])

@app.route("/party/<int:party_id>/transaction/new", methods=["GET","POST"])
@login_required
def transaction_new(party_id):
    with db() as con: p=con.execute("SELECT * FROM parties WHERE id=?",(party_id,)).fetchone()
    if not p: abort(404)
    payment_type = "payment" if p["kind"] == "client" else "vendor_payment"
    payment_mode = request.args.get("type") in (payment_type, "advance")
    advance_mode = request.args.get("type") == "advance"
    if request.method=="POST":
        txn_type=payment_type if payment_mode else request.form.get("txn_type","")
        allowed=("bill","payment","adjustment_debit","adjustment_credit") if p["kind"]=="client" else ("purchase","vendor_payment","adjustment_debit","adjustment_credit")
        if txn_type not in allowed: abort(400)
        try:
            txn_date=parse_date(request.form.get("txn_date",""))
            amount=float(request.form.get("amount") or 0)
            payment=float(request.form.get("payment") or 0) if p["kind"]=="client" and txn_type=="bill" else 0
            discount=float(request.form.get("discount") or 0) if p["kind"]=="client" else 0
        except ValueError:
            flash("Enter a valid date in day-month-year format and amount.","error")
            return render_template("transaction_form.html",p=p,today=date.today(),
                                   payment_mode=payment_mode,payment_type=payment_type,
                                   advance_mode=advance_mode)
        bill_total = payment + discount
        amount_valid = amount > 0 if not (payment_mode and p["kind"] == "client") else amount >= 0 and amount + discount > 0
        if (not isfinite(amount) or not isfinite(payment) or not isfinite(discount)
                or not amount_valid or payment<0 or discount<0
                or (txn_type=="bill" and bill_total>amount)):
            flash("Enter a valid amount. A bill payment cannot exceed the bill total.","error")
        else:
            with db() as con:
                con.execute("""INSERT INTO transactions(party_id,txn_date,txn_type,description,amount,payment,discount,reference,invoice_no)
                               VALUES(?,?,?,?,?,?,?,?,?)""",
                 (party_id,txn_date.isoformat(),txn_type,
                  request.form.get("description","").strip() or ("Advance payment" if advance_mode else ""),
                  amount,payment,discount,request.form.get("reference","").strip(),
                  request.form.get("invoice_no","").strip() if p["kind"]=="client" and txn_type=="bill" else ""))
            flash("Transaction saved.","success"); return redirect(url_for("party_detail",party_id=party_id))
    return render_template("transaction_form.html",p=p,today=date.today(),
                           payment_mode=payment_mode,payment_type=payment_type,
                           advance_mode=advance_mode)

@app.route("/transaction/<int:txn_id>/delete", methods=["POST"])
@login_required
def transaction_delete(txn_id):
    with db() as con:
        row=con.execute("SELECT party_id FROM transactions WHERE id=?",(txn_id,)).fetchone()
        if row: con.execute("DELETE FROM transactions WHERE id=?",(txn_id,))
    if row: flash("Transaction deleted.","success"); return redirect(url_for("party_detail",party_id=row["party_id"]))
    abort(404)

@app.route("/party/<int:party_id>/delete",methods=["POST"])
@login_required
def party_delete(party_id):
    with db() as con: con.execute("DELETE FROM parties WHERE id=?",(party_id,))
    flash("Record and its transactions deleted.","success")
    return redirect(url_for("parties"))

@app.route("/statement/<int:party_id>")
@login_required
def statement(party_id):
    start, end = date_range_from_request()
    with db() as con:
        p=con.execute("SELECT * FROM parties WHERE id=?",(party_id,)).fetchone()
        if not p: abort(404)
        sql="SELECT * FROM transactions WHERE party_id=?"; args=[party_id]
        if start: sql+=" AND txn_date>=?"; args.append(start)
        if end: sql+=" AND txn_date<=?"; args.append(end)
        sql+=" ORDER BY txn_date,id"
        txns=con.execute(sql,args).fetchall()
        bal=party_balance(p,con)
        totals=statement_totals(p["kind"],txns)
        txns=statement_rows(p["kind"],txns)
    return render_template("print_statement.html",p=p,txns=txns,balance=bal,start=start,end=end,
                           total_amount=totals["amount"],total_payment=totals["payment"],total_discount=totals["discount"],
                           total_due=totals["due"],username=session.get("username",""))

@app.route("/settings",methods=["GET","POST"])
@login_required
def settings():
    if request.method=="POST":
        old=request.form.get("old_password","")
        new=request.form.get("new_password","")
        confirmation=request.form.get("confirm_new_password","")
        with db() as con: u=con.execute("SELECT * FROM users WHERE id=?",(session["user_id"],)).fetchone()
        if not u:
            session.clear()
            flash("Your account could not be found. Please sign in again.","error")
            return redirect(url_for("login"))
        if not check_password_hash(u["password_hash"],old): flash("Current password is incorrect.","error")
        elif len(new)<8: flash("New password must be at least 8 characters.","error")
        elif new!=confirmation: flash("New password and confirmation do not match.","error")
        else:
            new_hash=generate_password_hash(new)
            with db() as con:
                updated=con.execute("UPDATE users SET password_hash=? WHERE id=?",(new_hash,session["user_id"])).rowcount
            with db() as con:
                saved=con.execute("SELECT password_hash FROM users WHERE id=?",(session["user_id"],)).fetchone()
            if updated!=1 or not saved or not check_password_hash(saved["password_hash"],new):
                flash("Password could not be verified as saved. Please try again.","error")
            else:
                session.clear()
                flash("Password changed. Sign in with your new password.","success")
                return redirect(url_for("login"))
    return render_template("settings.html")

@app.errorhandler(404)
def not_found(e): return render_template("base.html", standalone_message="The requested record was not found."),404

init_db()
if __name__ == "__main__":
    app.run(host="127.0.0.1",port=5000,debug=False)
