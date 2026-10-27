
import os
import sqlite3
import secrets
from datetime import datetime
from functools import wraps

from flask import (
    Flask, request, redirect, url_for, session,
    render_template_string, flash, abort, send_from_directory
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("KIRANA_SECRET_KEY") or secrets.token_hex(32)

ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(ROOT, "kirana_shop.db")
UPLOADS = os.path.join(ROOT, "uploads")
os.makedirs(UPLOADS, exist_ok=True)

ADMIN_EMAIL = os.environ.get(
    "ADMIN_EMAIL", "manoj-kirana.shop@gmail.com"
).strip().lower()
ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD", "Manoj@#13579"
)

HELP_PHONE = "6372245966"
ALLOWED = {"png", "jpg", "jpeg", "webp"}
STATUSES = [
    "Pending", "Confirmed", "Packed",
    "Out for Delivery", "Delivered", "Cancelled"
]


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def db():
    c = sqlite3.connect(DB, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def money(value):
    return f"₹{float(value):.2f}"


app.jinja_env.filters["money"] = money


def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            mobile TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            dob TEXT NOT NULL,
            gender TEXT NOT NULL,
            address TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            recovery_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS admins(
            id INTEGER PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            price REAL NOT NULL,
            kind TEXT NOT NULL DEFAULT 'piece',
            stock INTEGER NOT NULL DEFAULT 0,
            image TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            product_id INTEGER,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            quantity_label TEXT NOT NULL,
            unit_price REAL NOT NULL,
            total REAL NOT NULL,
            status TEXT DEFAULT 'Pending',
            payment_method TEXT DEFAULT 'Cash on Delivery',
            delivery_address TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS reviews(
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            order_id INTEGER UNIQUE NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chats(
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            sender TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS settings(
            id INTEGER PRIMARY KEY CHECK(id=1),
            shop_name TEXT DEFAULT 'Manoj Kirana Shop',
            open_time TEXT DEFAULT '09:00',
            close_time TEXT DEFAULT '21:00',
            is_open INTEGER DEFAULT 1,
            announcement TEXT DEFAULT ''
        );
        """)

        if not c.execute(
            "SELECT id FROM settings WHERE id=1"
        ).fetchone():
            c.execute(
                "INSERT INTO settings(id,shop_name) VALUES(1,?)",
                ("Manoj Kirana Shop",)
            )

        # Create admin if this email does not already exist.
        if not c.execute(
            "SELECT id FROM admins WHERE email=?", (ADMIN_EMAIL,)
        ).fetchone():
            c.execute(
                "INSERT INTO admins(email,password_hash) VALUES(?,?)",
                (ADMIN_EMAIL, generate_password_hash(ADMIN_PASSWORD))
            )


init_db()


def page(title, content, **ctx):
    inner = render_template_string(content, **ctx)
    with db() as c:
        s = c.execute(
            "SELECT * FROM settings WHERE id=1"
        ).fetchone()

    return render_template_string("""
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width,initial-scale=1">
      <title>{{title}}</title>
      <style>
        *{box-sizing:border-box}
        body{font-family:Arial,sans-serif;margin:0;background:#f3f6f4;color:#222}
        header{background:#176b3a;color:white;padding:14px}
        header a{color:white;margin-right:12px;text-decoration:none;line-height:2}
        main{max-width:1050px;margin:18px auto;padding:0 12px}
        .card{background:white;padding:15px;border-radius:12px;margin:12px 0;
              box-shadow:0 2px 7px #0001}
        .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
        input,select,textarea,button{width:100%;padding:11px;margin:6px 0;
              border:1px solid #ccc;border-radius:7px;font-size:16px}
        button,.btn{background:#176b3a;color:white;border:0;padding:11px;
              border-radius:7px;cursor:pointer;text-decoration:none;display:inline-block}
        .danger{background:#a22}
        .product{width:100%;max-width:600px;height:190px;object-fit:cover;
              border-radius:8px;cursor:zoom-in}
        .notice,.chat{padding:10px;border-radius:7px;margin:8px 0;background:#fff0c2}
        .success{padding:10px;border-radius:7px;margin:8px 0;background:#d8f3df}
        .chat{background:#edf5ee;overflow-wrap:anywhere}
        .stars{color:#d18a00;font-size:19px}
        .tablewrap{overflow-x:auto}
        table{border-collapse:collapse;width:100%;background:white}
        td,th{border:1px solid #ddd;padding:8px;text-align:left;vertical-align:top}
        footer{text-align:center;padding:20px;color:#666}
        .modal{display:none;position:fixed;inset:0;background:#000e;z-index:999;
              align-items:center;justify-content:center}
        .modal img{max-width:96vw;max-height:90vh;object-fit:contain}
        .modal button{position:absolute;top:8px;right:8px;width:auto;background:white;color:black}
      </style>
    </head>
    <body>
      <header>
        <h2>🛒 {{s.shop_name}}</h2>
        <div>Shop: <b>{{'OPEN' if s.is_open else 'CLOSED'}}</b>
        · {{s.open_time}}–{{s.close_time}}</div>
        {% if s.announcement %}<p>{{s.announcement}}</p>{% endif %}
        <nav>
          <a href="{{url_for('home')}}">Home</a>
          {% if session.get('user_id') %}
            <a href="{{url_for('orders')}}">My Orders</a>
            <a href="{{url_for('chat')}}">Chat Admin</a>
            <a href="{{url_for('logout')}}">Logout</a>
          {% else %}
            <a href="{{url_for('login')}}">Login</a>
            <a href="{{url_for('register')}}">Register</a>
          {% endif %}
          <a href="{{url_for('admin_login')}}">Admin</a>
        </nav>
      </header>
      <main>
        {% for cat,msg in get_flashed_messages(with_categories=true) %}
          <div class="{{'success' if cat=='success' else 'notice'}}">{{msg}}</div>
        {% endfor %}
        {{inner|safe}}
      </main>
      <footer>
        {{s.shop_name}} · Cash on Delivery<br>
        Help: <a href="tel:6372245966">6372245966</a>
      </footer>
      <div class="modal" id="modal" onclick="if(event.target===this)closePic()">
        <button onclick="closePic()">✕ Close</button>
        <img id="bigPic">
      </div>
      <script>
        function openPic(src){
          document.getElementById('bigPic').src=src;
          document.getElementById('modal').style.display='flex';
        }
        function closePic(){
          document.getElementById('modal').style.display='none';
        }
        document.addEventListener('keydown',e=>{
          if(e.key==='Escape')closePic();
        });
      </script>
    </body>
    </html>
    """, title=title, inner=inner, s=s)


def customer(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please login first.")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return wrapper


def save_image(file):
    if not file or not file.filename:
        return ""

    filename = secure_filename(file.filename)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in ALLOWED:
        flash("Use PNG, JPG, JPEG or WEBP photo.")
        return None

    filename = secrets.token_hex(10) + "." + ext
    file.save(os.path.join(UPLOADS, filename))
    return filename


@app.route("/")
def home():
    q = request.args.get("q", "").strip()

    with db() as c:
        products = c.execute("""
            SELECT p.*, COALESCE(AVG(r.rating),0) avg_rating,
                   COUNT(r.id) review_count
            FROM products p
            LEFT JOIN reviews r ON r.product_id=p.id
            WHERE p.active=1 AND (p.name LIKE ? OR p.description LIKE ?)
            GROUP BY p.id ORDER BY p.id DESC
        """, (f"%{q}%", f"%{q}%")).fetchall()

        s = c.execute(
            "SELECT * FROM settings WHERE id=1"
        ).fetchone()

    return page("Home", """
    <div class="card">
      <h2>Search products</h2>
      <form>
        <input name="q" value="{{q}}" placeholder="Search rice, oil, snacks...">
        <button>Search</button>
      </form>
    </div>

    {% if not s.is_open %}
      <div class="notice">Shop is currently closed.</div>
    {% endif %}

    <div class="grid">
      {% for p in products %}
        <div class="card">
          {% if p.image %}
            <img class="product" onclick="openPic(this.src)"
                 src="{{url_for('image',filename=p.image)}}" alt="{{p.name}}">
          {% endif %}
          <h3>{{p.name}}</h3>
          <p>{{p.description}}</p>
          <b>
            {% if p.kind=='weight' %}{{p.price|money}}/kg
            {% else %}{{p.price|money}}/piece{% endif %}
          </b>
          <p>Stock:
            {% if p.kind=='weight' %}{{'%.3f'|format(p.stock/1000)}} kg
            {% else %}{{p.stock}} pieces{% endif %}
          </p>
          <span class="stars">{{'★'*(p.avg_rating|round|int)}}{{'☆'*(5-(p.avg_rating|round|int))}}</span>
          ({{p.review_count}} reviews)
          <p><a class="btn" href="{{url_for('product',pid=p.id)}}">View Product</a></p>
        </div>
      {% else %}
        <p>No products found.</p>
      {% endfor %}
    </div>

    <div class="card">
      <h3>Need help?</h3>
      <p>Call <a href="tel:6372245966">6372245966</a></p>
      {% if session.get('user_id') %}
        <a class="btn" href="{{url_for('chat')}}">Chat with Admin</a>
      {% else %}
        <a class="btn" href="{{url_for('login')}}">Login to chat with Admin</a>
      {% endif %}
    </div>
    """, q=q, products=products, s=s)


@app.route("/product/<int:pid>")
def product(pid):
    with db() as c:
        p = c.execute("""
            SELECT p.*,COALESCE(AVG(r.rating),0) avg_rating,
                   COUNT(r.id) review_count
            FROM products p LEFT JOIN reviews r ON r.product_id=p.id
            WHERE p.id=? AND p.active=1 GROUP BY p.id
        """, (pid,)).fetchone()

        reviews = c.execute("""
            SELECT r.*,u.name FROM reviews r
            JOIN users u ON u.id=r.user_id
            WHERE r.product_id=? ORDER BY r.id DESC
        """, (pid,)).fetchall()

    if not p:
        abort(404)

    return page(p["name"], """
    <div class="card">
      {% if p.image %}
        <img class="product" onclick="openPic(this.src)"
             src="{{url_for('image',filename=p.image)}}" alt="{{p.name}}">
        <p>Touch photo to view full screen.</p>
      {% endif %}
      <h2>{{p.name}}</h2>
      <p>{{p.description}}</p>
      <span class="stars">{{'★'*(p.avg_rating|round|int)}}{{'☆'*(5-(p.avg_rating|round|int))}}</span>
      ({{p.review_count}} reviews)

      {% if p.kind=='weight' %}
        <p>{{p.price|money}} per kg · Stock {{p.stock}} grams</p>
        <form method="post" action="{{url_for('buy',pid=p.id)}}">
          <label>Weight</label>
          <select name="quantity" id="qty">
            {% for n in [250,500,750,1000,1500,2000,3000,5000] %}
              {% if n<=p.stock %}<option value="{{n}}">{{n}} grams</option>{% endif %}
            {% endfor %}
          </select>
          <p>Total <b id="total"></b></p>
          <button>Buy with Cash on Delivery</button>
        </form>
        <script>
        (() => {
          let q=document.getElementById('qty');
          let t=document.getElementById('total');
          let p=Number({{p.price|tojson}});
          function calc(){
            t.textContent=q.value?'₹'+(p*Number(q.value)/1000).toFixed(2):'Unavailable';
          }
          q.addEventListener('change',calc);calc();
        })();
        </script>
      {% else %}
        <p>{{p.price|money}} per piece · Stock {{p.stock}} pieces</p>
        <form method="post" action="{{url_for('buy',pid=p.id)}}" id="bf">
          <label>Number of pieces</label>
          <input id="qty" name="quantity" type="number" inputmode="numeric"
                 min="1" max="{{p.stock}}" step="1" value="1" required>
          <p>Total <b id="total">{{p.price|money}}</b></p>
          <p id="err" class="notice" hidden></p>
          <button id="bb">Buy with Cash on Delivery</button>
        </form>
        <script>
        (() => {
          let q=document.getElementById('qty'),t=document.getElementById('total');
          let e=document.getElementById('err'),b=document.getElementById('bb');
          let f=document.getElementById('bf'),p=Number({{p.price|tojson}});
          let s=Number({{p.stock|tojson}});
          function calc(){
            let n=Number(q.value);
            if(q.value.trim()===''||!Number.isInteger(n)||n<1||n>s){
              t.textContent='—';e.hidden=false;
              e.textContent='Enter a whole quantity from 1 to '+s;
              b.disabled=true;return false;
            }
            e.hidden=true;t.textContent='₹'+(p*n).toFixed(2);
            b.disabled=false;return true;
          }
          q.addEventListener('input',calc);
          q.addEventListener('change',calc);
          f.addEventListener('submit',e=>{if(!calc())e.preventDefault();});
          calc();
        })();
        </script>
      {% endif %}
    </div>

    <div class="card">
      <h3>Customer reviews</h3>
      {% for r in reviews %}
        <div class="chat">
          <b>{{r.name}}</b>
          <span class="stars">{{'★'*r.rating}}{{'☆'*(5-r.rating)}}</span>
          <p>{{r.comment}}</p><small>{{r.created_at}}</small>
        </div>
      {% else %}
        <p>No reviews yet.</p>
      {% endfor %}
    </div>
    """, p=p, reviews=reviews)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        v = [
            request.form.get(x, "").strip()
            for x in ("name", "mobile", "email", "dob", "gender", "address")
        ]
        password = request.form.get("password", "")
        recovery = request.form.get("recovery", "")

        if not all(v) or not password or not recovery:
            flash("All fields are required.")
            return redirect(url_for("register"))

        if len(password) < 8 or len(recovery) < 4:
            flash("Password must be 8+ characters and recovery code 4+.")
            return redirect(url_for("register"))

        try:
            with db() as c:
                c.execute("""
                    INSERT INTO users(
                        name,mobile,email,dob,gender,address,password_hash,
                        recovery_hash,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                """, (*v, generate_password_hash(password),
                      generate_password_hash(recovery), now()))

            flash("Registration successful. Login using your mobile number.", "success")
            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash("Mobile number or email is already registered.")

    return page("Register", """
    <div class="card">
      <h2>Customer Registration</h2>
      <form method="post">
        <label>Name</label><input name="name" required>
        <label>Mobile (login ID)</label><input name="mobile" inputmode="tel" required>
        <label>Email</label><input name="email" type="email" required>
        <label>Date of birth</label><input name="dob" type="date" required>
        <label>Gender</label>
        <select name="gender" required>
          <option value="">Select</option><option>Male</option>
          <option>Female</option><option>Other</option>
          <option>Prefer not to say</option>
        </select>
        <label>Full address</label><textarea name="address" required></textarea>
        <label>Password (8+ characters)</label>
        <input name="password" type="password" minlength="8" required>
        <label>Private recovery code (remember it; not OTP)</label>
        <input name="recovery" type="password" minlength="4" required>
        <button>Register</button>
      </form>
      <a href="{{url_for('login')}}">Login</a>
    </div>
    """)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        mobile = request.form.get("mobile", "").strip()
        pw = request.form.get("password", "")

        with db() as c:
            u = c.execute(
                "SELECT * FROM users WHERE mobile=?", (mobile,)
            ).fetchone()

        if u and u["password_hash"] and check_password_hash(u["password_hash"], pw):
            session.clear()
            session["user_id"] = u["id"]
            session["user_name"] = u["name"]
            return redirect(url_for("home"))

        flash("Mobile number or password is incorrect.")

    return page("Login", """
    <div class="card">
      <h2>Customer Login</h2>
      <form method="post">
        <label>Mobile</label><input name="mobile" required>
        <label>Password</label><input name="password" type="password" required>
        <button>Login</button>
      </form>
      <a href="{{url_for('forgot')}}">Forgot password?</a> ·
      <a href="{{url_for('register')}}">Register</a>
    </div>
    """)


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot():
    if request.method == "POST":
        mobile = request.form.get("mobile", "").strip()
        recovery = request.form.get("recovery", "")
        pw = request.form.get("new_password", "")

        if len(pw) < 8:
            flash("New password must be at least 8 characters.")
        else:
            with db() as c:
                u = c.execute(
                    "SELECT * FROM users WHERE mobile=?", (mobile,)
                ).fetchone()

                if u and u["recovery_hash"] and check_password_hash(
                    u["recovery_hash"], recovery
                ):
                    c.execute(
                        "UPDATE users SET password_hash=? WHERE id=?",
                        (generate_password_hash(pw), u["id"])
                    )
                    flash("Password reset successful.", "success")
                    return redirect(url_for("login"))

            flash("Mobile or recovery code did not match. Contact admin if needed.")

    return page("Forgot password", """
    <div class="card">
      <h2>Reset password</h2>
      <form method="post">
        <label>Registered mobile</label><input name="mobile" required>
        <label>Recovery code</label><input name="recovery" type="password" required>
        <label>New password (8+ characters)</label>
        <input name="new_password" type="password" minlength="8" required>
        <button>Reset password</button>
      </form>
    </div>
    """)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/buy/<int:pid>", methods=["POST"])
@customer
def buy(pid):
    try:
        qty = int(request.form.get("quantity", "0"))
    except ValueError:
        flash("Invalid quantity.")
        return redirect(url_for("product", pid=pid))

    with db() as c:
        p = c.execute(
            "SELECT * FROM products WHERE id=? AND active=1", (pid,)
        ).fetchone()
        u = c.execute(
            "SELECT * FROM users WHERE id=?", (session["user_id"],)
        ).fetchone()

        if not p or not u:
            flash("Product or customer not found.")
            return redirect(url_for("home"))

        if qty < 1 or qty > p["stock"]:
            flash("Quantity exceeds available stock.")
            return redirect(url_for("product", pid=pid))

        if p["kind"] == "weight":
            if qty not in [250, 500, 750, 1000, 1500, 2000, 3000, 5000]:
                flash("Invalid weight.")
                return redirect(url_for("product", pid=pid))
            total = round(p["price"] * qty / 1000, 2)
            label = f"{qty} grams"
        else:
            total = round(p["price"] * qty, 2)
            label = f"{qty} piece(s)"

        changed = c.execute(
            "UPDATE products SET stock=stock-? WHERE id=? AND stock>=? AND active=1",
            (qty, pid, qty)
        )
        if changed.rowcount != 1:
            flash("Stock changed; try again.")
            return redirect(url_for("product", pid=pid))

        c.execute("""
            INSERT INTO orders(
                user_id,product_id,product_name,quantity,quantity_label,
                unit_price,total,status,payment_method,delivery_address,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """, (
            u["id"], p["id"], p["name"], qty, label, p["price"], total,
            "Pending", "Cash on Delivery", u["address"], now()
        ))

    flash("Order placed! Pay on delivery.", "success")
    return redirect(url_for("orders"))


@app.route("/orders")
@customer
def orders():
    with db() as c:
        os_ = c.execute(
            "SELECT * FROM orders WHERE user_id=? ORDER BY id DESC",
            (session["user_id"],)
        ).fetchall()

        done = {
            r["order_id"] for r in c.execute(
                "SELECT order_id FROM reviews WHERE user_id=?",
                (session["user_id"],)
            )
        }

    return page("My orders", """
    <h2>My Orders</h2>
    {% for o in os_ %}
      <div class="card">
        <h3>#{{o.id}} {{o.product_name}}</h3>
        <p>{{o.quantity_label}} · {{o.total|money}} · {{o.status}}</p>
        <p>{{o.payment_method}} · {{o.delivery_address}}</p>
        {% if o.status in ['Pending','Confirmed'] %}
          <form method="post" action="{{url_for('cancel',oid=o.id)}}">
            <button class="danger">Cancel order</button>
          </form>
        {% endif %}
        {% if o.status=='Delivered' and o.id not in done %}
          <form method="post" action="{{url_for('review',oid=o.id)}}">
            <label>Star rating</label>
            <select name="rating">
              <option value="5">★★★★★ 5</option>
              <option value="4">★★★★ 4</option>
              <option value="3">★★★ 3</option>
              <option value="2">★★ 2</option>
              <option value="1">★ 1</option>
            </select>
            <label>Comment</label>
            <textarea name="comment" maxlength="1000" required></textarea>
            <button>Submit review</button>
          </form>
        {% elif o.status=='Delivered' %}
          <p>Review submitted. Thank you!</p>
        {% endif %}
      </div>
    {% else %}
      <p>No orders yet.</p>
    {% endfor %}
    """, os_=os_, done=done)


@app.route("/cancel/<int:oid>", methods=["POST"])
@customer
def cancel(oid):
    with db() as c:
        o = c.execute(
            "SELECT * FROM orders WHERE id=? AND user_id=?",
            (oid, session["user_id"])
        ).fetchone()

        if not o:
            flash("Order not found.")
        elif o["status"] not in ("Pending", "Confirmed"):
            flash("This order cannot be cancelled now; contact admin.")
        else:
            c.execute(
                "UPDATE orders SET status='Cancelled' WHERE id=?", (oid,)
            )
            if o["product_id"]:
                c.execute(
                    "UPDATE products SET stock=stock+? WHERE id=?",
                    (o["quantity"], o["product_id"])
                )
            flash("Order cancelled; stock restored.", "success")

    return redirect(url_for("orders"))


@app.route("/review/<int:oid>", methods=["POST"])
@customer
def review(oid):
    try:
        rating = int(request.form.get("rating", "0"))
    except ValueError:
        rating = 0

    comment = request.form.get("comment", "").strip()

    with db() as c:
        o = c.execute(
            "SELECT * FROM orders WHERE id=? AND user_id=?",
            (oid, session["user_id"])
        ).fetchone()

        if not o or o["status"] != "Delivered" or not o["product_id"]:
            flash("Only delivered orders can be reviewed.")
        elif rating not in range(1, 6) or not comment:
            flash("Rating and comment are required.")
        else:
            try:
                c.execute("""
                    INSERT INTO reviews(
                        user_id,product_id,order_id,rating,comment,created_at
                    ) VALUES(?,?,?,?,?,?)
                """, (
                    session["user_id"], o["product_id"], oid,
                    rating, comment, now()
                ))
                flash("Review published. Thank you!", "success")
            except sqlite3.IntegrityError:
                flash("Review already submitted.")

    return redirect(url_for("orders"))


@app.route("/chat", methods=["GET", "POST"])
@customer
def chat():
    uid = session["user_id"]

    if request.method == "POST":
        msg = request.form.get("message", "").strip()
        if msg and len(msg) <= 2000:
            with db() as c:
                c.execute(
                    "INSERT INTO chats(user_id,sender,message,created_at) VALUES(?,?,?,?)",
                    (uid, "customer", msg, now())
                )
            flash("Message sent.", "success")
        return redirect(url_for("chat"))

    with db() as c:
        messages = c.execute(
            "SELECT * FROM chats WHERE user_id=? ORDER BY id", (uid,)
        ).fetchall()

    return page("Chat with Admin", """
    <div class="card">
      <h2>Chat with Admin</h2>
      {% for m in messages %}
        <div class="chat">
          <b>{{'You' if m.sender=='customer' else 'Admin'}}:</b>
          {{m.message}}<br><small>{{m.created_at}}</small>
        </div>
      {% endfor %}
      <form method="post">
        <textarea name="message" maxlength="2000" required
                  placeholder="Message admin"></textarea>
        <button>Send</button>
      </form>
      <small>Refresh page to see new replies.</small>
    </div>
    """, messages=messages)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")

        with db() as c:
            a = c.execute(
                "SELECT * FROM admins WHERE email=?", (email,)
            ).fetchone()

        if a and check_password_hash(a["password_hash"], pw):
            session.clear()
            session["admin_id"] = a["id"]
            return redirect(url_for("dashboard"))

        flash("Admin email or password is incorrect.")

    return page("Admin login", """
    <div class="card">
      <h2>Admin Login</h2>
      <form method="post">
        <label>Email</label><input name="email" type="email" required>
        <label>Password</label><input name="password" type="password" required>
        <button>Login</button>
      </form>
    </div>
    """)


@app.route("/admin")
@app.route("/admin/dashboard")
@admin
def dashboard():
    with db() as c:
        users = c.execute("SELECT * FROM users ORDER BY id DESC").fetchall()

        orders_ = c.execute("""
            SELECT o.*,u.name customer,u.mobile
            FROM orders o JOIN users u ON u.id=o.user_id
            ORDER BY o.id DESC
        """).fetchall()

        products = c.execute(
            "SELECT * FROM products ORDER BY id DESC"
        ).fetchall()

        chats = c.execute("""
            SELECT u.id,u.name,u.mobile,MAX(ch.id) last
            FROM users u JOIN chats ch ON ch.user_id=u.id
            GROUP BY u.id ORDER BY last DESC
        """).fetchall()

        reviews = c.execute("""
            SELECT r.*,u.name customer,p.name product
            FROM reviews r JOIN users u ON u.id=r.user_id
            JOIN products p ON p.id=r.product_id
            ORDER BY r.id DESC
        """).fetchall()

        s = c.execute(
            "SELECT * FROM settings WHERE id=1"
        ).fetchone()

    return page("Admin dashboard", """
    <h2>Admin Dashboard</h2>
    <p>
      <a class="btn" href="{{url_for('add_product')}}">Add product</a>
      <a class="btn" href="{{url_for('settings')}}">Shop settings</a>
      <a class="btn" href="{{url_for('chats_admin')}}">Customer chats</a>
      <a class="btn" href="{{url_for('admin_logout')}}">Logout</a>
    </p>

    <div class="card">
      Shop: <b>{{'OPEN' if s.is_open else 'CLOSED'}}</b>
      · {{s.open_time}}–{{s.close_time}}
    </div>

    <h2>Orders</h2>
    {% for o in orders_ %}
      <div class="card">
        <b>#{{o.id}} {{o.product_name}}</b>
        <p>{{o.customer}} · {{o.mobile}}</p>
        <p>{{o.quantity_label}} · {{o.total|money}} · {{o.delivery_address}}</p>
        <p>Status: {{o.status}}</p>
        <form method="post" action="{{url_for('status',oid=o.id)}}">
          <select name="status">
            {% for x in statuses %}
              <option {% if x==o.status %}selected{% endif %}>{{x}}</option>
            {% endfor %}
          </select>
          <button>Update status</button>
        </form>
      </div>
    {% else %}
      <p>No orders.</p>
    {% endfor %}

    <h2>Customers ({{users|length}})</h2>
    <div class="tablewrap">
      <table>
        <tr><th>Name</th><th>Mobile</th><th>Email</th><th>Address</th><th>Reset password</th></tr>
        {% for u in users %}
          <tr>
            <td>{{u.name}}</td><td>{{u.mobile}}</td><td>{{u.email}}</td><td>{{u.address}}</td>
            <td>
              <form method="post" action="{{url_for('admin_reset_password',uid=u.id)}}">
                <input name="new_password" type="password" minlength="8"
                       placeholder="Temporary password" required>
                <button>Reset</button>
              </form>
            </td>
          </tr>
        {% endfor %}
      </table>
    </div>

    <h2>Products</h2>
    <div class="tablewrap">
      <table>
        <tr><th>Name</th><th>Price</th><th>Stock</th><th>Visibility</th><th>Actions</th></tr>
        {% for p in products %}
          <tr>
            <td>{{p.name}}</td>
            <td>{% if p.kind=='weight' %}{{p.price|money}}/kg
                {% else %}{{p.price|money}}/piece{% endif %}</td>
            <td>{{p.stock}} {% if p.kind=='weight' %}grams{% else %}pieces{% endif %}</td>
            <td>{{'Shown' if p.active else 'Hidden'}}</td>
            <td>
              <a class="btn" href="{{url_for('edit_product',pid=p.id)}}">Edit / Refill</a>
              <form method="post" action="{{url_for('toggle',pid=p.id)}}">
                <button class="danger">{{'Hide' if p.active else 'Show'}}</button>
              </form>
            </td>
          </tr>
        {% endfor %}
      </table>
    </div>

    <h2>Customer chats</h2>
    {% for u in chats %}
      <div class="card">
        {{u.name}} · {{u.mobile}}
        <a class="btn" href="{{url_for('admin_chat',uid=u.id)}}">Open chat</a>
      </div>
    {% else %}
      <p>No chats.</p>
    {% endfor %}

    <h2>Reviews</h2>
    {% for r in reviews %}
      <div class="card">
        <b>{{r.product}} — {{r.customer}}</b>
        <span class="stars">{{'★'*r.rating}}{{'☆'*(5-r.rating)}}</span>
        <p>{{r.comment}}</p>
      </div>
    {% else %}
      <p>No reviews.</p>
    {% endfor %}
    """, users=users, orders_=orders_, products=products,
       chats=chats, reviews=reviews, s=s, statuses=STATUSES)


@app.route("/admin/settings", methods=["GET", "POST"])
@admin
def settings():
    if request.method == "POST":
        vals = (
            request.form.get("shop_name", "Manoj Kirana Shop").strip()[:80]
            or "Manoj Kirana Shop",
            request.form.get("open_time", "09:00"),
            request.form.get("close_time", "21:00"),
            1 if request.form.get("is_open") == "1" else 0,
            request.form.get("announcement", "").strip()[:300]
        )

        with db() as c:
            c.execute("""
                UPDATE settings
                SET shop_name=?,open_time=?,close_time=?,is_open=?,announcement=?
                WHERE id=1
            """, vals)

        flash("Settings saved.", "success")
        return redirect(url_for("settings"))

    with db() as c:
        s = c.execute("SELECT * FROM settings WHERE id=1").fetchone()

    return page("Shop settings", """
    <div class="card">
      <h2>Shop settings</h2>
      <form method="post">
        <label>Shop name</label><input name="shop_name" value="{{s.shop_name}}" required>
        <label>Open time</label><input type="time" name="open_time" value="{{s.open_time}}" required>
        <label>Close time</label><input type="time" name="close_time" value="{{s.close_time}}" required>
        <label>Status</label>
        <select name="is_open">
          <option value="1" {% if s.is_open %}selected{% endif %}>Open</option>
          <option value="0" {% if not s.is_open %}selected{% endif %}>Closed</option>
        </select>
        <label>Home announcement</label>
        <textarea name="announcement">{{s.announcement}}</textarea>
        <button>Save settings</button>
      </form>
    </div>
    """, s=s)


@app.route("/admin/chats")
@admin
def chats_admin():
    with db() as c:
        users = c.execute("""
            SELECT u.id,u.name,u.mobile,MAX(ch.id) last
            FROM users u JOIN chats ch ON ch.user_id=u.id
            GROUP BY u.id ORDER BY last DESC
        """).fetchall()

    return page("Customer chats", """
    <h2>Customer chats</h2>
    {% for u in users %}
      <div class="card">
        {{u.name}} · {{u.mobile}}
        <a class="btn" href="{{url_for('admin_chat',uid=u.id)}}">Open</a>
      </div>
    {% else %}
      <p>No messages.</p>
    {% endfor %}
    """, users=users)


@app.route("/admin/chats/<int:uid>", methods=["GET", "POST"])
@admin
def admin_chat(uid):
    with db() as c:
        u = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not u:
            abort(404)

        if request.method == "POST":
            msg = request.form.get("message", "").strip()
            if msg and len(msg) <= 2000:
                c.execute(
                    "INSERT INTO chats(user_id,sender,message,created_at) VALUES(?,?,?,?)",
                    (uid, "admin", msg, now())
                )
            return redirect(url_for("admin_chat", uid=uid))

        messages = c.execute(
            "SELECT * FROM chats WHERE user_id=? ORDER BY id", (uid,)
        ).fetchall()

    return page("Chat", """
    <div class="card">
      <h2>{{u.name}} · {{u.mobile}}</h2>
      {% for m in messages %}
        <div class="chat">
          <b>{{'Admin' if m.sender=='admin' else u.name}}:</b>
          {{m.message}}<br><small>{{m.created_at}}</small>
        </div>
      {% endfor %}
      <form method="post">
        <textarea name="message" maxlength="2000" required></textarea>
        <button>Reply</button>
      </form>
    </div>
    """, u=u, messages=messages)


@app.route("/admin/product/add", methods=["GET", "POST"])
@admin
def add_product():
    return product_form_route(None)


@app.route("/admin/product/<int:pid>/edit", methods=["GET", "POST"])
@admin
def edit_product(pid):
    with db() as c:
        p = c.execute(
            "SELECT * FROM products WHERE id=?", (pid,)
        ).fetchone()

    if not p:
        abort(404)

    return product_form_route(p)


def product_form_route(p):
    editing = p is not None

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        desc = request.form.get("description", "").strip()
        kind = request.form.get("kind", "")

        try:
            price = float(request.form.get("price", "0"))
            stockv = float(request.form.get("stock", "0"))

            if price <= 0 or stockv < 0:
                raise ValueError

            if kind == "weight":
                stock = round(stockv * 1000)
            elif kind == "piece" and stockv.is_integer():
                stock = int(stockv)
            else:
                raise ValueError

        except (ValueError, OverflowError):
            flash("Invalid price or stock.")
            return redirect(request.path)

        if not name:
            flash("Product name is required.")
            return redirect(request.path)

        image_name = p["image"] if p else ""
        uploaded = request.files.get("image")

        if uploaded and uploaded.filename:
            new_image = save_image(uploaded)
            if new_image is None:
                return redirect(request.path)
            image_name = new_image

        with db() as c:
            if p:
                c.execute("""
                    UPDATE products
                    SET name=?,description=?,price=?,kind=?,stock=?,image=?
                    WHERE id=?
                """, (name, desc, price, kind, stock, image_name, p["id"]))
            else:
                c.execute("""
                    INSERT INTO products(
                        name,description,price,kind,stock,image,active,created_at
                    ) VALUES(?,?,?,?,?,?,1,?)
                """, (name, desc, price, kind, stock, image_name, now()))

        flash("Product saved. Stock/price updated.", "success")
        return redirect(url_for("dashboard"))

    data = p or {
        "name": "", "description": "", "kind": "piece",
        "price": "", "stock": 0, "image": ""
    }
    stockv = data["stock"] / 1000 if data["kind"] == "weight" else data["stock"]

    return page("Edit product" if p else "Add product", """
    <div class="card">
      <h2>{{'Edit / Refill product' if editing else 'Add product'}}</h2>

      {% if p.image %}
        <img class="product" onclick="openPic(this.src)"
             src="{{url_for('image',filename=p.image)}}" alt="{{p.name}}">
      {% endif %}

      <form method="post" enctype="multipart/form-data">
        <label>Name</label><input name="name" value="{{p.name}}" required>
        <label>Description</label><textarea name="description">{{p.description}}</textarea>
        <label>Type</label>
        <select name="kind" id="kind">
          <option value="piece" {% if p.kind=='piece' %}selected{% endif %}>Piece</option>
          <option value="weight" {% if p.kind=='weight' %}selected{% endif %}>Weight</option>
        </select>
        <label id="pl">Price per piece (₹)</label>
        <input type="number" step="0.01" min="0.01" name="price" value="{{p.price}}" required>
        <label id="sl">Stock in whole pieces</label>
        <input id="stock" type="number" min="0" step="any" name="stock" value="{{stockv}}" required>
        <label>Photo (optional)</label>
        <input type="file" name="image" accept=".png,.jpg,.jpeg,.webp">
        <button>Save / Refill</button>
      </form>
    </div>
    <script>
      let k=document.getElementById('kind'),s=document.getElementById('stock');
      function updateLabels(){
        document.getElementById('pl').textContent =
          k.value==='weight'?'Price per kg (₹)':'Price per piece (₹)';
        document.getElementById('sl').textContent =
          k.value==='weight'?'Stock in kilograms':'Stock in whole pieces';
        s.step=k.value==='weight'?'any':'1';
      }
      k.addEventListener('change',updateLabels);updateLabels();
    </script>
    """, p=data, stockv=stockv, editing=editing)


@app.route("/admin/product/<int:pid>/toggle", methods=["POST"])
@admin
def toggle(pid):
    with db() as c:
        p = c.execute(
            "SELECT active FROM products WHERE id=?", (pid,)
        ).fetchone()

        if p:
            c.execute(
                "UPDATE products SET active=? WHERE id=?",
                (0 if p["active"] else 1, pid)
            )

    return redirect(url_for("dashboard"))


@app.route("/admin/order/<int:oid>/status", methods=["POST"])
@admin
def status(oid):
    st = request.form.get("status", "")

    if st not in STATUSES:
        flash("Invalid status.")
    else:
        with db() as c:
            c.execute(
                "UPDATE orders SET status=? WHERE id=?", (st, oid)
            )
        flash("Order status updated.", "success")

    return redirect(url_for("dashboard"))


@app.route("/admin/customer/<int:uid>/reset-password", methods=["POST"])
@admin
def admin_reset_password(uid):
    new_password = request.form.get("new_password", "")

    if len(new_password) < 8:
        flash("Temporary password must be at least 8 characters.")
        return redirect(url_for("dashboard"))

    with db() as c:
        user = c.execute(
            "SELECT id FROM users WHERE id=?", (uid,)
        ).fetchone()

        if not user:
            flash("Customer not found.")
        else:
            c.execute(
                "UPDATE users SET password_hash=? WHERE id=?",
                (generate_password_hash(new_password), uid)
            )
            flash("Customer password reset successfully.", "success")

    return redirect(url_for("dashboard"))


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_id", None)
    return redirect(url_for("admin_login"))


@app.route("/uploads/<path:filename>")
def image(filename):
    return send_from_directory(UPLOADS, filename)


if __name__ == "__main__":
    print("Kirana Shop: http://127.0.0.1:5000")
    print("Admin email:", ADMIN_EMAIL)
    print("Database:", DB)
    app.run(host="127.0.0.1", port=5000, debug=False)
