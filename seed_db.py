import os
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from db import create_db_engine
from dotenv import load_dotenv

load_dotenv()


DDL_SQL = """
CREATE TABLE IF NOT EXISTS customers (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    price NUMERIC NOT NULL,
    category TEXT
);

CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL,
    order_date DATE NOT NULL
);
"""

# Basit test verileri
def seed_data(engine: Engine):
    with engine.begin() as conn:
        # Müşteriler
        conn.execute(text("""
            INSERT INTO customers (name, email, created_at)
            VALUES
            ('Ali Veli', 'ali@example.com', NOW() - INTERVAL '90 days'),
            ('Ayşe Yılmaz', 'ayse@example.com', NOW() - INTERVAL '60 days'),
            ('Mehmet Demir', 'mehmet@example.com', NOW() - INTERVAL '30 days')
            ON CONFLICT (email) DO NOTHING
        """))

        # Ürünler
        conn.execute(text("""
            INSERT INTO products (name, price, category)
            VALUES
            ('Kulaklık', 499.90, 'Elektronik'),
            ('Mouse', 299.50, 'Elektronik'),
            ('Kahve', 129.00, 'Gıda'),
            ('Defter', 39.90, 'Kırtasiye'),
            ('USB Bellek', 149.90, 'Elektronik')
            ON CONFLICT DO NOTHING
        """))

        # Siparişler: son 3 ayda dağılmış örnekler
        # Ürün ve müşteri id'lerini mevcut tablolarından alıp örnek siparişler ekleyelim
        # Basitlik için rastgele değil, sabit örnekler
        conn.execute(text("DELETE FROM orders"))  # temiz başla (demo amaçlı)

        # ids
        cust_ids = [r[0] for r in conn.execute(text("SELECT id FROM customers ORDER BY id")).fetchall()]
        prod_ids = [r[0] for r in conn.execute(text("SELECT id FROM products ORDER BY id")).fetchall()]

        today = date.today()
        base_dates = [
            today - timedelta(days=70),
            today - timedelta(days=40),
            today - timedelta(days=20),
            today - timedelta(days=10),
            today - timedelta(days=5),
            today - timedelta(days=1),
        ]

        inserts = []
        for i, d in enumerate(base_dates, start=1):
            # her tarihte birkaç sipariş
            for j in range(1, 4):
                cust = cust_ids[(i + j) % len(cust_ids)]
                prod = prod_ids[(i * j) % len(prod_ids)]
                qty = ((i + j) % 5) + 1
                inserts.append({"customer_id": cust, "product_id": prod, "quantity": qty, "order_date": d})

        for row in inserts:
            conn.execute(
                text("INSERT INTO orders (customer_id, product_id, quantity, order_date) VALUES (:c, :p, :q, :d)"),
                {"c": row["customer_id"], "p": row["product_id"], "q": row["quantity"], "d": row["order_date"]},
            )


def ensure_schema(engine: Engine):
    with engine.begin() as conn:
        for stmt in DDL_SQL.strip().split(";\n\n"):
            s = stmt.strip()
            if s:
                conn.execute(text(s))


def main():
    print("Veritabanı şeması oluşturuluyor / doğrulanıyor...")
    engine = create_db_engine()
    try:
        ensure_schema(engine)
        print("Şema hazır.")
        print("Örnek veriler ekleniyor...")
        seed_data(engine)
        print("Örnek veriler eklendi.")
    except SQLAlchemyError as e:
        print(f"Hata: {e}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
