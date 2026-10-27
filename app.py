
import os
import sqlite3
import secrets
from functools import wraps
from flask import Flask, request, redirect, url_for, session, render_template_string, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("KIRANA_SECRET_KEY") or secrets.token_hex(32)

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kirana_shop.db")
HELP_PHONE = "6372245966"

# Render dashboard mein ye environment variables set karna.
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "manoj-kirana.lokal@gmail.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Manoj@#13579")

def db():
    c = sqlite3.connect(DB, timeout=15)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            mobile TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            address TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            price REAL NOT NULL,
            stock INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            total REAL NOT NULL,
            delivery_fee REAL NOT NULL,
            address TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS admins(
            id INTEGER PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings(
            id INTEGER PRIMARY KEY CHECK(id=1),
            shop_name TEXT NOT NULL DEFAULT 'Manoj Kirana Shop',
            delivery_fee REAL NOT NULL DEFAULT 5,
            announcement TEXT NOT NULL DEFAULT '',
            is_open INTEGER NOT NULL DEFAULT 1
        );
        """)
        if not c.execute("SELECT id FROM settings WHERE id=1").fetchone():
            c.execute("INSERT INTO settings(id) VALUES(1)")

        # Create admin only when this email does not exist.
        if not c.execute(
            "SELECT id FROM admins WHERE email=?", (ADMIN_EMAIL,)
        ).fetchone():
            c.execute(
                "INSERT INTO admins(email,password_hash) VALUES(?,?)",
                (ADMIN_EMAIL, generate_password_hash(ADMIN_PASSWORD))
            )

init_db()

BASE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }}</title>
<style>
*{box-sizing:border-box}
body{font-family:Arial,sans-serif;margin:0;background:#f2f6f2;color:#222}
header{background:#176b3a;color:white;padding:15px}
header a{color:white;margin-right:12px;line-height:2}
main{max-width:950px;margin:18px auto;padding:0 12px}
.card{background:white;padding:16px;margin:12px 0;border-radius:12px;box-shadow:0 2px 7px #0001}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
input,textarea,select,button{width:100%;padding:11px;margin:6px 0;border:1px solid #ccc;border-radius:7px;font-size:16px}
button,.btn{background:#176b3a;color:white;border:0;padding:11px;border-radius:7px;text-decoration:none;display:inline-block;cursor:pointer}
.notice{padding:10px;background:#fff0c2;border-radius:7px}
a{overflow-wrap:anywhere}
footer{text-align:center;padding:20px}
</style>
</head>
<body>
<header>
<h2>🛒 {{ settings.shop_name }}</h2>
<p>Shop status: <b>{{ 'OPEN' if settings.is_open else 'CLOSED' }}</b></p>
<nav>
<a href="{{ url_for('home') }}">Home</a>
{% if session.get('user_id') %}
<a href="{{ url_for('my_orders') }}">My Orders</a>
<a href="{{ url_for('logout') }}">Logout</a>
{% else %}
<a href="{{ url_for('login') }}">Login</a>
<a href="{{ url_for('register') }}">Register</a>
{% endif %}
<a href="{{ url_for('admin_login') }}">Admin</a>
</nav>
</header>
<main>
{% for message in get_flashed_messages() %}
<div class="notice">{{ message }}</div>
{% endfor %}
{{ content|safe }}
</main>
<footer>
<b>Help:</b> <a href="tel:6372245966">6372245966</a>
<br>Cash on Delivery · {{ settings.shop_name }}
</footer>
</body>
</html>
"""

def page(title, template, **data):
    content = render_template_string(template, **data)
    with db() as c:
        settings = c.execute(
            "SELECT * FROM settings WHERE id=1"
        ).fetchone()
    return render_template_string(
        BASE, title=title, content=content, settings=settings
    )

def customer_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please login first.")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return wrapper

@app.route("/")
def home():
    q = request.args.get("q", "").strip()
    with db() as c:
        products = c.execute("""
            SELECT * FROM products
            WHERE active=1 AND name LIKE ?
            ORDER BY id DESC
        """, ("%" + q + "%",)).fetchall()
        settings = c.execute(
            "SELECT * FROM settings WHERE id=1"
        ).fetchone()

    return page("Home", """
    <div class="card">
      <h2>Welcome to {{ settings.shop_name }}</h2>
      <p>Customer help: <a href="tel:6372245966">6372245966</a></p>
      {% if settings.announcement %}
        <p>{{ settings.announcement }}</p>
      {% endif %}
      <form>
        <input name="q" value="{{ q }}" placeholder="Search products">
        <button>Search</button>
      </form>
      <p>Home delivery fee: ₹{{ '%.2f'|format(settings.delivery_fee) }}</p>
    </div>
    {% if not settings.is_open %}
      <div class="notice">Shop is currently closed.</div>
    {% endif %}
    <div class="grid">
    {% for p in products %}
      <div class="card">
        <h3>{{ p.name }}</h3>
        <p>{{ p.description }}</p>
        <b>₹{{ '%.2f'|format(p.price) }} per piece</b>
        <p>Stock: {{ p.stock }}</p>
        <a class="btn" href="{{ url_for('buy', pid=p.id) }}">View / Order</a>
      </div>
    {% else %}
      <div class="card">No products available yet.</div>
    {% endfor %}
    </div>
    """, q=q, products=products, settings=settings)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        mobile = request.form.get("mobile", "").strip()
        password = request.form.get("password", "")
        address = request.form.get("address", "").strip()

        if not name or not mobile or not address or len(password) < 8:
            flash("Fill all fields. Password must be at least 8 characters.")
        else:
            try:
                with db() as c:
                    c.execute("""
                    INSERT INTO users(name,mobile,password_hash,address)
                    VALUES(?,?,?,?)
                    """, (
                        name, mobile, generate_password_hash(password), address
                    ))
                flash("Registration successful. Please login.")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("This mobile number is already registered.")

    return page("Register", """
    <div class="card"><h2>Customer Registration</h2>
    <form method="post">
      <label>Name</label><input name="name" required>
      <label>Mobile number</label><input name="mobile" required>
      <label>Password (8+ characters)</label>
      <input name="password" type="password" minlength="8" required>
      <label>Delivery address</label>
      <textarea name="address" required></textarea>
      <button>Register</button>
    </form></div>
    """)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        mobile = request.form.get("mobile", "").strip()
        password = request.form.get("password", "")
        with db() as c:
            user = c.execute(
                "SELECT * FROM users WHERE mobile=?", (mobile,)
            ).fetchone()

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("home"))
        flash("Invalid mobile number or password.")

    return page("Login", """
    <div class="card"><h2>Customer Login</h2>
    <form method="post">
      <input name="mobile" placeholder="Mobile number" required>
      <input name="password" type="password" placeholder="Password" required>
      <button>Login</button>
    </form></div>
    """)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/buy/<int:pid>", methods=["GET", "POST"])
@customer_required
def buy(pid):
    with db() as c:
        product = c.execute(
            "SELECT * FROM products WHERE id=? AND active=1", (pid,)
        ).fetchone()
        user = c.execute(
            "SELECT * FROM users WHERE id=?", (session["user_id"],)
        ).fetchone()
        settings = c.execute(
            "SELECT * FROM settings WHERE id=1"
        ).fetchone()

        if not product:
            return "Product not found", 404

        if request.method == "POST":
            try:
                quantity = int(request.form.get("quantity", "0"))
            except ValueError:
                quantity = 0

            if not settings["is_open"]:
                flash("Shop is closed. Please order later.")
            elif quantity < 1 or quantity > product["stock"]:
                flash("Please enter a valid quantity within available stock.")
            else:
                fee = float(settings["delivery_fee"])
                total = quantity * float(product["price"]) + fee
                c.execute("""
                    INSERT INTO orders(
                        user_id,product_id,product_name,quantity,
                        unit_price,total,delivery_fee,address
                    ) VALUES(?,?,?,?,?,?,?,?)
                """, (
                    user["id"], product["id"], product["name"], quantity,
                    product["price"], total, fee, user["address"]
                ))
                c.execute(
                    "UPDATE products SET stock=stock-? WHERE id=?",
                    (quantity, pid)
                )
                flash("Order placed! Payment method: Cash on Delivery.")
                return redirect(url_for("my_orders"))

    return page("Place Order", """
    <div class="card">
      <h2>{{ product.name }}</h2>
      <p>{{ product.description }}</p>
      <p>Price per piece: ₹{{ '%.2f'|format(product.price) }}</p>
      <p>Available stock: {{ product.stock }}</p>
      <p>Current home delivery fee: ₹{{ '%.2f'|format(settings.delivery_fee) }}</p>
      <p>Payment: Cash on Delivery</p>
      <form method="post">
        <label>Quantity</label>
        <input name="quantity" type="number" min="1"
          max="{{ product.stock }}" value="1" required>
        <button>Place Order</button>
      </form>
    </div>
    """, product=product, settings=settings)

@app.route("/orders")
@customer_required
def my_orders():
    with db() as c:
        orders = c.execute("""
            SELECT * FROM orders WHERE user_id=? ORDER BY id DESC
        """, (session["user_id"],)).fetchall()

    return page("My Orders", """
    <h2>My Orders</h2>
    {% for o in orders %}
      <div class="card">
        <h3>Order #{{ o.id }} — {{ o.product_name }}</h3>
        <p>Quantity: {{ o.quantity }}</p>
        <p>Product price: ₹{{ '%.2f'|format(o.unit_price * o.quantity) }}</p>
        <p>Delivery fee at order time: ₹{{ '%.2f'|format(o.delivery_fee) }}</p>
        <b>Total: ₹{{ '%.2f'|format(o.total) }}</b>
        <p>Status: {{ o.status }}</p>
        <p>Delivery address: {{ o.address }}</p>
        <small>{{ o.created_at }}</small>
      </div>
    {% else %}
      <div class="card">You have not placed any orders yet.</div>
    {% endfor %}
    """, orders=orders)

@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        with db() as c:
            admin = c.execute(
                "SELECT * FROM admins WHERE email=?", (email,)
            ).fetchone()

        if admin and check_password_hash(admin["password_hash"], password):
            session.clear()
            session["admin_id"] = admin["id"]
            return redirect(url_for("admin_panel"))
        flash("Invalid admin email or password.")

    return page("Admin Login", """
    <div class="card"><h2>Admin Login</h2>
    <form method="post">
      <input name="email" type="email" placeholder="Admin email" required>
      <input name="password" type="password" placeholder="Admin password" required>
      <button>Login</button>
    </form></div>
    """)

@app.route("/admin/panel", methods=["GET", "POST"])
@admin_required
def admin_panel():
    if request.method == "POST":
        action = request.form.get("action", "")

        if action == "add_product":
            name = request.form.get("name", "").strip()
            description = request.form.get("description", "").strip()
            try:
                price = float(request.form.get("price", "0"))
                stock = int(request.form.get("stock", "-1"))
            except ValueError:
                price, stock = -1, -1

            if name and price > 0 and stock >= 0:
                with db() as c:
                    c.execute("""
                        INSERT INTO products(name,description,price,stock)
                        VALUES(?,?,?,?)
                    """, (name, description, price, stock))
                flash("Product added.")
            else:
                flash("Enter a name, positive price and valid stock.")

        elif action == "settings":
            try:
                fee = float(request.form.get("delivery_fee", "-1"))
            except ValueError:
                fee = -1

            shop_name = request.form.get("shop_name", "").strip()
            announcement = request.form.get("announcement", "").strip()
            is_open = 1 if request.form.get("is_open") == "yes" else 0

            if fee < 0 or not shop_name:
                flash("Shop name is required and delivery fee cannot be negative.")
            else:
                with db() as c:
                    c.execute("""
                        UPDATE settings SET shop_name=?, delivery_fee=?,
                        announcement=?, is_open=? WHERE id=1
                    """, (shop_name, fee, announcement, is_open))
                flash("Shop settings updated.")

        elif action == "status":
            try:
                oid = int(request.form.get("order_id", "0"))
            except ValueError:
                oid = 0
            status = request.form.get("status", "")
            allowed = [
                "Pending", "Confirmed", "Packed",
                "Out for Delivery", "Delivered", "Cancelled"
            ]
            if status in allowed:
                with db() as c:
                    c.execute(
                        "UPDATE orders SET status=? WHERE id=?", (status, oid)
                    )
                flash("Order status updated.")
            else:
                flash("Invalid order status.")

        return redirect(url_for("admin_panel"))

    with db() as c:
        settings = c.execute(
            "SELECT * FROM settings WHERE id=1"
        ).fetchone()
        products = c.execute(
            "SELECT * FROM products ORDER BY id DESC"
        ).fetchall()
        orders = c.execute("""
            SELECT o.*,u.name customer,u.mobile
            FROM orders o JOIN users u ON u.id=o.user_id
            ORDER BY o.id DESC
        """).fetchall()

    return page("Admin Panel", """
    <div class="card">
      <h2>Shop Settings</h2>
      <form method="post">
        <input type="hidden" name="action" value="settings">
        <label>Shop name</label>
        <input name="shop_name" value="{{ settings.shop_name }}" required>
        <label>Home delivery fee (₹)</label>
        <input name="delivery_fee" type="number" min="0" step="0.01"
          value="{{ settings.delivery_fee }}" required>
        <label>Home page announcement</label>
        <textarea name="announcement">{{ settings.announcement }}</textarea>
        <label>Shop status</label>
        <select name="is_open">
          <option value="yes" {% if settings.is_open %}selected{% endif %}>Open</option>
          <option value="no" {% if not settings.is_open %}selected{% endif %}>Closed</option>
        </select>
        <button>Save Shop Settings</button>
      </form>
      <p>Customer help number: <a href="tel:6372245966">6372245966</a></p>
    </div>

    <div class="card">
      <h2>Add Product</h2>
      <form method="post">
        <input type="hidden" name="action" value="add_product">
        <input name="name" placeholder="Product name" required>
        <textarea name="description" placeholder="Description"></textarea>
        <input name="price" type="number" min="0.01" step="0.01"
          placeholder="Price per piece" required>
        <input name="stock" type="number" min="0"
          placeholder="Stock pieces" required>
        <button>Add Product</button>
      </form>
    </div>

    <h2>Products</h2>
    {% for p in products %}
      <div class="card">
        <b>{{ p.name }}</b> — ₹{{ '%.2f'|format(p.price) }}
        <p>Stock: {{ p.stock }}</p>
      </div>
    {% else %}
      <p>No products yet.</p>
    {% endfor %}

    <h2>Customer Orders</h2>
    {% for o in orders %}
      <div class="card">
        <h3>Order #{{ o.id }} — {{ o.product_name }}</h3>
        <p>Customer: {{ o.customer }} · {{ o.mobile }}</p>
        <p>Quantity: {{ o.quantity }} · Total: ₹{{ '%.2f'|format(o.total) }}</p>
        <p>Delivery fee charged: ₹{{ '%.2f'|format(o.delivery_fee) }}</p>
        <p>Address: {{ o.address }}</p>
        <p>Status: {{ o.status }}</p>
        <form method="post">
          <input type="hidden" name="action" value="status">
          <input type="hidden" name="order_id" value="{{ o.id }}">
          <select name="status">
            {% for s in ['Pending','Confirmed','Packed','Out for Delivery','Delivered','Cancelled'] %}
              <option {% if s==o.status %}selected{% endif %}>{{ s }}</option>
            {% endfor %}
          </select>
          <button>Update Order Status</button>
        </form>
      </div>
    {% else %}
      <p>No orders yet.</p>
    {% endfor %}
    <div class="card"><a href="{{ url_for('admin_logout') }}">Admin logout</a></div>
    """, settings=settings, products=products, orders=orders)

@app.route("/admin/logout")
@admin_required
def admin_logout():
    session.clear()
    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
