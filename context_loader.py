from pathlib import Path
from typing import Tuple, List
import os

from sqlalchemy import create_engine, text as sqtext
from sqlalchemy.engine import Engine
from dotenv import load_dotenv

load_dotenv()


def load_context_and_schema(context_file: str = "context.md") -> Tuple[str, str]:
    """
    Öncelik sırası:
    1) Canlı veritabanından Northwind benzeri tablo/kolon şemasını çıkar ve döndür.
    2) Eğer DB erişilemezse context.md içinden:
       - Bağlam kuralları (4. bölüm)
       - Şema (5. bölüm)
    bölümlerini okuyup döndür.

    Dönen şema metni, LLM'e verilecek özet/insan-okur biçimli bir tablo+kolon listesi olarak tasarlanır.
    """
    # Önce DB'den otomatik şema çıkarmayı dene
    try:
        schema_text = extract_live_schema()
        rules_text = extract_rules_from_file(context_file)
        if schema_text.strip():
            return rules_text, schema_text
    except Exception:
        # Sessiz geç ve dosyadan devam et
        pass

    # Dosyadan fallback
    p = Path(context_file)
    if not p.exists():
        raise FileNotFoundError(f"{context_file} bulunamadı.")

    text = p.read_text(encoding="utf-8")

    rules = _extract_section(text, "## 4. Bağlam (Context) Kuralları", "## 5.")
    # Hem eski başlık hem yeni başlık olasılığına bak
    schema = _extract_section(text, "## 5. Örnek Şema (Northwind uyumlu)", "## 6.")
    if not schema.strip():
        schema = _extract_section(text, "## 5. Örnek Şema", "## 6.")

    rules = rules.strip()
    schema = schema.strip()

    if not rules:
        raise ValueError("Bağlam kuralları bölümü bulunamadı veya boş.")
    if not schema:
        raise ValueError("Şema bölümü bulunamadı veya boş.")

    return rules, schema


def _extract_section(text: str, start_marker: str, next_section_prefix: str) -> str:
    """
    start_marker ile başlayan bölümden, bir sonraki '## ' başlığına kadar olan kısmı döndürür.
    start_marker bulunamazsa boş string döner.
    """
    start_idx = text.find(start_marker)
    if start_idx == -1:
        return ""

    # start satırından sonraki içeriği al
    section_text = text[start_idx + len(start_marker):]

    # Sonraki bölüm başlığını bul
    next_idx = section_text.find("\n## ")
    if next_idx == -1:
        # Metnin sonuna kadar
        return section_text

    # Kırp
    return section_text[:next_idx]


def extract_rules_from_file(context_file: str) -> str:
    p = Path(context_file)
    if not p.exists():
        raise FileNotFoundError(f"{context_file} bulunamadı.")
    text = p.read_text(encoding="utf-8")
    rules = _extract_section(text, "## 4. Bağlam (Context) Kuralları", "## 5.")
    return rules.strip()


def extract_live_schema() -> str:
    """
    PostgreSQL 'public' şemasındaki Northwind çekirdek tablolarını ve kolonlarını listeler.
    DATABASE_URL üzerinden bağlanır.
    """
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL tanımlı değil.")

    engine = create_engine(db_url, future=True)

    desired_tables = [
        "customers", "orders", "orderdetails", "order_details",
        "products", "suppliers", "categories", "employees", "shippers",
        "customer_customer_demo", "customer_demographics",
        "employee_territories", "region", "territories", "us_states",
    ]

    with engine.connect() as conn:
        # Var olan tabloları çek
        rows = conn.execute(sqtext("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY 1
        """)).fetchall()

        existing = set(r[0].lower() for r in rows)
        present = [t for t in desired_tables if t in existing]
        if not present:
            present = sorted(existing)

        lines: List[str] = []
        lines.append("Northwind (canlı şemadan çıkarım) - public şema")
        for t in present:
            cols = conn.execute(sqtext("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = :t
                ORDER BY ordinal_position
            """), {"t": t}).fetchall()
            col_str = ", ".join(f"{c[0]} ({c[1]})" for c in cols) if cols else "(kolon yok)"
            lines.append(f"- {t}: {col_str}")

        return "\n".join(lines)
