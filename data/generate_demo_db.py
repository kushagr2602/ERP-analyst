"""
Generate a realistic ERP demo database (SQLite).

Tables:
  customers       — B2B company accounts
  contacts        — customer contacts
  products        — product catalogue with categories
  suppliers       — vendor/supplier registry
  purchase_orders — supplier PO header
  po_items        — PO line items
  orders          — sales order header
  order_items     — sales order line items
  invoices        — AR invoices
  inventory       — warehouse stock levels
  employees       — sales reps + managers
"""

import os
import random
import sqlite3
from datetime import date, timedelta

import faker

SEED = 42
random.seed(SEED)
fake = faker.Faker()
fake.seed_instance(SEED)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "erp_demo.db")

# ── Config ────────────────────────────────────────────────────────────────────
N_CUSTOMERS = 120
N_PRODUCTS = 80
N_SUPPLIERS = 20
N_EMPLOYEES = 15
N_ORDERS = 1_200
N_POS = 300
YEARS_BACK = 3

CATEGORIES = ["Electronics", "Software", "Office Supplies", "Industrial", "Logistics", "Services"]
REGIONS = ["North America", "Europe", "APAC", "Latin America", "Middle East"]
STATUS_ORDERS = ["completed", "completed", "completed", "pending", "shipped", "cancelled"]
STATUS_INVOICES = ["paid", "paid", "outstanding", "overdue", "draft"]
STATUS_POS = ["received", "received", "pending", "partial", "cancelled"]


def rand_date(years_back=YEARS_BACK) -> str:
    start = date.today() - timedelta(days=365 * years_back)
    delta = timedelta(days=random.randint(0, 365 * years_back))
    return (start + delta).isoformat()


def build_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # ── Schema ────────────────────────────────────────────────────────────────
    cur.executescript("""
    CREATE TABLE employees (
        employee_id   INTEGER PRIMARY KEY,
        full_name     TEXT NOT NULL,
        email         TEXT,
        role          TEXT,
        region        TEXT,
        hire_date     TEXT,
        quota         REAL
    );

    CREATE TABLE customers (
        customer_id   INTEGER PRIMARY KEY,
        company_name  TEXT NOT NULL,
        industry      TEXT,
        region        TEXT,
        country       TEXT,
        city          TEXT,
        account_manager_id INTEGER REFERENCES employees(employee_id),
        credit_limit  REAL,
        created_at    TEXT
    );

    CREATE TABLE contacts (
        contact_id    INTEGER PRIMARY KEY,
        customer_id   INTEGER REFERENCES customers(customer_id),
        full_name     TEXT,
        email         TEXT,
        phone         TEXT,
        title         TEXT
    );

    CREATE TABLE suppliers (
        supplier_id   INTEGER PRIMARY KEY,
        company_name  TEXT NOT NULL,
        country       TEXT,
        lead_time_days INTEGER,
        rating        REAL
    );

    CREATE TABLE products (
        product_id    INTEGER PRIMARY KEY,
        sku           TEXT UNIQUE,
        name          TEXT NOT NULL,
        category      TEXT,
        unit_cost     REAL,
        unit_price    REAL,
        supplier_id   INTEGER REFERENCES suppliers(supplier_id),
        reorder_point INTEGER,
        is_active     INTEGER DEFAULT 1
    );

    CREATE TABLE inventory (
        inventory_id  INTEGER PRIMARY KEY,
        product_id    INTEGER REFERENCES products(product_id),
        warehouse     TEXT,
        quantity_on_hand INTEGER,
        quantity_reserved INTEGER,
        last_updated  TEXT
    );

    CREATE TABLE purchase_orders (
        po_id         INTEGER PRIMARY KEY,
        supplier_id   INTEGER REFERENCES suppliers(supplier_id),
        po_date       TEXT,
        expected_date TEXT,
        received_date TEXT,
        status        TEXT,
        total_amount  REAL
    );

    CREATE TABLE po_items (
        po_item_id    INTEGER PRIMARY KEY,
        po_id         INTEGER REFERENCES purchase_orders(po_id),
        product_id    INTEGER REFERENCES products(product_id),
        quantity      INTEGER,
        unit_cost     REAL
    );

    CREATE TABLE orders (
        order_id      INTEGER PRIMARY KEY,
        customer_id   INTEGER REFERENCES customers(customer_id),
        employee_id   INTEGER REFERENCES employees(employee_id),
        order_date    TEXT,
        ship_date     TEXT,
        status        TEXT,
        total_amount  REAL,
        discount_pct  REAL DEFAULT 0
    );

    CREATE TABLE order_items (
        item_id       INTEGER PRIMARY KEY,
        order_id      INTEGER REFERENCES orders(order_id),
        product_id    INTEGER REFERENCES products(product_id),
        quantity      INTEGER,
        unit_price    REAL,
        discount_pct  REAL DEFAULT 0
    );

    CREATE TABLE invoices (
        invoice_id    INTEGER PRIMARY KEY,
        order_id      INTEGER REFERENCES orders(order_id),
        customer_id   INTEGER REFERENCES customers(customer_id),
        invoice_date  TEXT,
        due_date      TEXT,
        amount        REAL,
        status        TEXT,
        days_to_pay   INTEGER
    );
    """)

    # ── Employees ─────────────────────────────────────────────────────────────
    roles = ["Sales Rep", "Sales Rep", "Sales Rep", "Account Manager", "VP Sales", "Finance Manager"]
    employees = []
    for i in range(1, N_EMPLOYEES + 1):
        employees.append((
            i, fake.name(), fake.email(),
            random.choice(roles), random.choice(REGIONS),
            rand_date(5), round(random.uniform(200_000, 800_000), 2),
        ))
    cur.executemany("INSERT INTO employees VALUES (?,?,?,?,?,?,?)", employees)

    # ── Customers ─────────────────────────────────────────────────────────────
    customers = []
    for i in range(1, N_CUSTOMERS + 1):
        customers.append((
            i, fake.company(), random.choice(CATEGORIES),
            random.choice(REGIONS), fake.country(), fake.city(),
            random.randint(1, N_EMPLOYEES),
            round(random.uniform(10_000, 500_000), 2),
            rand_date(4),
        ))
    cur.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?,?,?,?)", customers)

    # ── Contacts ─────────────────────────────────────────────────────────────
    contacts = []
    cid = 1
    for c in customers:
        for _ in range(random.randint(1, 3)):
            contacts.append((
                cid, c[0], fake.name(), fake.email(), fake.phone_number(),
                random.choice(["CEO", "CFO", "Procurement Manager", "IT Director", "Operations Lead"]),
            ))
            cid += 1
    cur.executemany("INSERT INTO contacts VALUES (?,?,?,?,?,?)", contacts)

    # ── Suppliers ─────────────────────────────────────────────────────────────
    suppliers = []
    for i in range(1, N_SUPPLIERS + 1):
        suppliers.append((
            i, fake.company(), fake.country(),
            random.randint(7, 45), round(random.uniform(3.0, 5.0), 1),
        ))
    cur.executemany("INSERT INTO suppliers VALUES (?,?,?,?,?)", suppliers)

    # ── Products ─────────────────────────────────────────────────────────────
    products = []
    for i in range(1, N_PRODUCTS + 1):
        cost = round(random.uniform(5, 2000), 2)
        margin = random.uniform(1.2, 2.5)
        products.append((
            i, f"SKU-{i:04d}",
            fake.catch_phrase()[:50],
            random.choice(CATEGORIES),
            cost, round(cost * margin, 2),
            random.randint(1, N_SUPPLIERS),
            random.randint(5, 50),
            1,
        ))
    cur.executemany("INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?)", products)

    # ── Inventory ─────────────────────────────────────────────────────────────
    warehouses = ["WH-East", "WH-West", "WH-Central", "WH-Europe"]
    inv = []
    iid = 1
    for p in products:
        for wh in random.sample(warehouses, random.randint(1, 3)):
            qty = random.randint(0, 500)
            inv.append((iid, p[0], wh, qty, random.randint(0, max(1, qty // 4)), date.today().isoformat()))
            iid += 1
    cur.executemany("INSERT INTO inventory VALUES (?,?,?,?,?,?)", inv)

    # ── Orders + Items ────────────────────────────────────────────────────────
    orders = []
    order_items = []
    invoices = []
    oi_id = 1
    inv_id = 1

    for i in range(1, N_ORDERS + 1):
        cust_id = random.randint(1, N_CUSTOMERS)
        emp_id = random.randint(1, N_EMPLOYEES)
        o_date = rand_date()
        ship_date_obj = (date.fromisoformat(o_date) + timedelta(days=random.randint(1, 14)))
        status = random.choice(STATUS_ORDERS)
        discount = round(random.choice([0, 0, 0, 5, 10, 15]) / 100, 2)

        # Line items
        n_items = random.randint(1, 8)
        total = 0.0
        for _ in range(n_items):
            prod = products[random.randint(0, N_PRODUCTS - 1)]
            qty = random.randint(1, 20)
            price = prod[5]
            item_discount = discount
            line_total = qty * price * (1 - item_discount)
            total += line_total
            order_items.append((oi_id, i, prod[0], qty, price, item_discount))
            oi_id += 1

        total = round(total, 2)
        orders.append((i, cust_id, emp_id, o_date, ship_date_obj.isoformat(), status, total, discount))

        # Invoice
        if status in ("completed", "shipped"):
            inv_date = ship_date_obj + timedelta(days=1)
            due_date = inv_date + timedelta(days=30)
            inv_status = random.choice(STATUS_INVOICES)
            days_pay = random.randint(0, 60) if inv_status == "paid" else None
            invoices.append((
                inv_id, i, cust_id,
                inv_date.isoformat(), due_date.isoformat(),
                total, inv_status, days_pay,
            ))
            inv_id += 1

    cur.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)", orders)
    cur.executemany("INSERT INTO order_items VALUES (?,?,?,?,?,?)", order_items)
    cur.executemany("INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?)", invoices)

    # ── Purchase Orders ────────────────────────────────────────────────────────
    pos = []
    po_items = []
    poi_id = 1
    for i in range(1, N_POS + 1):
        sup_id = random.randint(1, N_SUPPLIERS)
        po_date = rand_date()
        lead = random.randint(7, 45)
        exp_date = (date.fromisoformat(po_date) + timedelta(days=lead)).isoformat()
        status = random.choice(STATUS_POS)
        rec_date = exp_date if status == "received" else None
        total = 0.0
        n_items = random.randint(1, 5)
        for _ in range(n_items):
            prod = products[random.randint(0, N_PRODUCTS - 1)]
            qty = random.randint(10, 200)
            cost = prod[4]
            po_items.append((poi_id, i, prod[0], qty, cost))
            total += qty * cost
            poi_id += 1
        pos.append((i, sup_id, po_date, exp_date, rec_date, status, round(total, 2)))

    cur.executemany("INSERT INTO purchase_orders VALUES (?,?,?,?,?,?,?)", pos)
    cur.executemany("INSERT INTO po_items VALUES (?,?,?,?,?)", po_items)

    con.commit()
    con.close()
    print(f"✅  Demo DB created at: {DB_PATH}")
    print(f"    customers={N_CUSTOMERS}, products={N_PRODUCTS}, orders={N_ORDERS}")


if __name__ == "__main__":
    build_db()
