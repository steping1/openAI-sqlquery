import os
from contextlib import contextmanager
from typing import Any, List, Tuple, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, Result
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv

load_dotenv()


def get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL ortam değişkeni bulunamadı. .env dosyanızı kontrol edin.")
    return url


def get_query_timeout_seconds() -> int:
    try:
        return int(os.getenv("QUERY_TIMEOUT_SECONDS", "10"))
    except ValueError:
        return 10


def get_row_limit_default() -> int:
    try:
        return int(os.getenv("ROW_LIMIT_DEFAULT", "1000"))
    except ValueError:
        return 1000


def create_db_engine(echo: bool = False) -> Engine:
    url = get_database_url()
    # Pool ayarları: makul defaultlar
    engine = create_engine(
        url,
        echo=echo,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_pre_ping=True,
        future=True,
    )
    return engine


@contextmanager
def db_connect(engine: Engine):
    conn = engine.connect()
    try:
        yield conn
    finally:
        conn.close()


def is_select_query(sql: str) -> bool:
    # Basit guard: sadece SELECT ile başlamalı (WITH ... SELECT de olabilir)
    stripped = sql.strip().lower()
    return stripped.startswith("select") or stripped.startswith("with")


def enforce_limit(sql: str, limit: int) -> str:
    """
    Eğer sorguda zaten LIMIT varsa ekleme yapma.
    Basit bir yaklaşımla son SELECT/ORDER BY/...) sonrasındaki LIMIT var mı kontrol eder.
    Not: WITH ... SELECT gibi durumlarda da çalışır.
    """
    # Noktalı virgülü şimdilik temizle
    trimmed = sql.strip().rstrip(";")
    low = trimmed.lower()

    # LIMIT var mı? (regex kullanmadan basit kontrol: ' limit ' ya da satır sonlarında)
    if " limit " in low or low.endswith(" limit") or low.endswith(" limit;"):
        return trimmed + ";"  # orijinalin sonuna tekrar ; ekle

    # ORDER BY ... LIMIT X; gibi iç içe alt sorgulardaki limitleri yakalamak zor olabilir.
    # Pratik çözüm: Tüm metin içinde 'limit' anahtar kelimesi varsa ekleme yapma.
    if "limit" in low:
        return trimmed + ";"

    # LIMIT yoksa ekle
    return f"{trimmed} LIMIT {limit};"


def execute_select(engine: Engine, sql: str, timeout_seconds: Optional[int] = None) -> Tuple[List[str], List[Tuple[Any, ...]]]:
    """
    Sadece SELECT çalıştırır, LIMIT ve statement_timeout uygular.
    Dönüş: (kolon_isimleri, satırlar)
    """
    if not is_select_query(sql):
        raise ValueError("Sadece SELECT sorguları çalıştırılabilir.")

    limit = get_row_limit_default()
    safe_sql = enforce_limit(sql, limit)

    timeout = timeout_seconds if timeout_seconds is not None else get_query_timeout_seconds()
    # PostgreSQL statement_timeout (ms cinsinden)
    timeout_ms = max(1, int(timeout * 1000))

    try:
        with db_connect(engine) as conn:
            # statement_timeout'u session seviyesinde ayarla
            conn.execute(text(f"SET statement_timeout = {timeout_ms}"))
            result: Result = conn.execute(text(safe_sql))
            rows = result.fetchall()
            keys = list(result.keys())
            return keys, [tuple(r) for r in rows]
    except SQLAlchemyError as e:
        # Daha okunaklı hata
        raise RuntimeError(f"Veritabanı hatası: {str(e)}") from e
