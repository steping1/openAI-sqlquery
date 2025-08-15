import os
import sys
from typing import List, Tuple

from dotenv import load_dotenv
from tabulate import tabulate

from context_loader import load_context_and_schema
from db import create_db_engine, execute_select
from llm import build_sql_prompt, build_answer_prompt, ask_llm

load_dotenv()


def print_header():
    print("=" * 72)
    print("Türkçe Doğal Dilden PostgreSQL'e Sorgu ve Türkçe Cevap (MVP)")
    print("=" * 72)
    print("Çıkmak için boş satır bırakıp Enter'a basın veya Ctrl+C\n")


def find_similar_products(engine, search_term: str) -> List[str]:
    """
    Veritabanından benzer ürün adlarını bulur (fuzzy matching).
    """
    try:
        # ILIKE ile benzer ürünleri ara
        fuzzy_sql = f"""
        SELECT DISTINCT product_name 
        FROM products 
        WHERE product_name ILIKE '%{search_term.strip()}%'
        OR product_name ILIKE '%{search_term.strip().lower()}%'
        OR product_name ILIKE '%{search_term.strip().capitalize()}%'
        LIMIT 10
        """
        columns, rows = execute_select(engine, fuzzy_sql, timeout_seconds=5)
        return [row[0] for row in rows] if rows else []
    except Exception:
        return []


def preview_rows(columns: List[str], rows: List[Tuple], max_rows: int = 10) -> str:
    """
    İlk max_rows kadar satırı metin olarak önizleme için döndürür.
    """
    if not rows:
        return "(sonuç yok)"
    head = rows[:max_rows]
    try:
        return tabulate(head, headers=columns, tablefmt="github")
    except Exception:
        # Tabulate sorun çıkarsa basit format
        lines = []
        lines.append(" | ".join(columns))
        for r in head:
            lines.append(" | ".join(str(x) for x in r))
        return "\n".join(lines)


def main():
    print_header()
    
    # DEBUG modu için ortam değişkeni kontrolü
    DEBUG_MODE = os.getenv("DEBUG_SQL", "false").lower() == "true"
    if DEBUG_MODE:
        print("🐛 DEBUG MODU AÇIK - Detaylı loglar gösterilecek\n")

    try:
        context_rules, schema_text = load_context_and_schema("context.md")
        if DEBUG_MODE:
            print(f"📄 Context kuralları yüklendi ({len(context_rules)} karakter)")
            print(f"📊 Şema bilgisi yüklendi ({len(schema_text)} karakter)\n")
    except Exception as e:
        print(f"Bağlam/şema yüklenirken hata: {e}")
        sys.exit(1)

    engine = None
    try:
        engine = create_db_engine(echo=DEBUG_MODE)  # DEBUG modunda SQL logları göster
        if DEBUG_MODE:
            print("✅ Veritabanı bağlantısı başarılı\n")
    except Exception as e:
        print(f"Veritabanına bağlanılamadı: {e}")
        sys.exit(1)

    while True:
        try:
            user_q = input("Soru (TR): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nÇıkılıyor...")
            break

        if not user_q:
            print("Çıkılıyor...")
            break

        # 1) SQL üret
        try:
            sql_messages = build_sql_prompt(context_rules, schema_text, user_q)
            sql_query = ask_llm(sql_messages, temperature=0.0, mode="sql")
            # Temizlik: kod bloğu işaretçileri geldiyse ayıkla ve CamelCase -> snake_case normalize et
            sql_query = sql_query.strip().strip("`").replace("```sql", "").replace("```", "").strip()
            try:
                from llm import _normalize_identifiers_in_text  # type: ignore
                sql_query = _normalize_identifiers_in_text(sql_query)
                # Ek güvenlik: SELECT ... parçalarını normalleştirirken eksik kolon isimlerini de tamamlamaya çalış
                # Örn: "SELECT ProductName, UnitsIn" -> "select product_name, units_in_stock"
                # Basit düzeltme heuristiği:
                fixed = sql_query
                # Küçük harfe indir ve birden çok boşluğu sadeleştir
                low = fixed.lower()
                # Kısmi anahtar kelime hataları
                low = low.replace(" unitsin ", " units_in_stock ")
                low = low.replace(" unitsinstock ", " units_in_stock ")
                low = low.replace(" productname ", " product_name ")
                # Başta/sonda da olma ihtimali
                low = low.replace("select productname", "select product_name")
                low = low.replace(", unitsin ", ", units_in_stock ")
                # random fonksiyonunun büyük yazılması
                low = low.replace("random()", "random()")
                # Sonucu geri yaz
                sql_query = low

                # ÜRÜN ADI TİTLE-CASE DÜZELTMESİ (Chai kuralı ve genel baş harf büyütme):
                # Eğer where product_name = 'chai' gibi küçük harfli üretim geldiyse 'Chai' olarak düzelt.
                import re
                def _titlecase_literal(m):
                    val = m.group(1)
                    # Sadece ilk harfi büyüt, diğerleri küçük kalsın (Chai -> Chai)
                    if val:
                        return f"= '{val[:1].upper()}{val[1:]}'"
                    return m.group(0)
                # Yalnızca eşleşen literal için uygula
                sql_query = re.sub(r"=\s*'chai'", "= 'Chai'", sql_query)
                # Genel baş harf büyütme: tek kelimeli ürünler için (örn. chai -> Chai)
                sql_query = re.sub(r"=\s*'([a-zçğıöşü]+)'", lambda m: f"= '{m.group(1)[:1].upper()}{m.group(1)[1:]}'", sql_query)
            except Exception:
                # Normalizasyon başarısız olsa bile devam et
                pass
        except Exception as e:
            print(f"SQL sorgusu üretilemedi: {e}")
            continue

        print(f"\nÜretilen SQL:\n{sql_query}\n")

        # 2) SQL'i çalıştır
        try:
            columns, rows = execute_select(engine, sql_query, timeout_seconds=None)
            
            # Eğer sonuç boş ve ürün adı arama sorgusu varsa farklı stratejiler dene
            if not rows and ("product_name" in sql_query.lower()):
                fallback_attempts = []
                
                # Fallback 1: ILIKE yerine = kullanılmışsa ILIKE'a çevir
                if " = '" in sql_query and "ilike" not in sql_query.lower():
                    fallback_sql = sql_query.replace(" = '", " ILIKE '%").replace("'", "%'")
                    fallback_attempts.append(("ILIKE dönüşümü", fallback_sql))
                
                # Fallback 2: Title Case dene
                if " where product_name" in sql_query.lower():
                    import re
                    def _title_case(m):
                        word = m.group(1)
                        return f"ILIKE '%{word[:1].upper()}{word[1:]}%'"
                    retry_sql = re.sub(r"(=|ILIKE)\s*['\"]([a-zçğıöşü]+)['\"]", _title_case, sql_query, flags=re.IGNORECASE)
                    if retry_sql != sql_query:
                        fallback_attempts.append(("Title case", retry_sql))
                
                # Fallback 3: Tamamen küçük harf dene
                if " where product_name" in sql_query.lower():
                    import re
                    def _lower_case(m):
                        word = m.group(1)
                        return f"ILIKE '%{word.lower()}%'"
                    retry_sql = re.sub(r"(=|ILIKE)\s*['\"]([a-zA-ZçğıöşüÇĞIÖŞÜ]+)['\"]", _lower_case, sql_query, flags=re.IGNORECASE)
                    if retry_sql != sql_query:
                        fallback_attempts.append(("Küçük harf", retry_sql))
                
                # Fallback stratejilerini sırayla dene
                for strategy_name, retry_sql in fallback_attempts:
                    try:
                        columns2, rows2 = execute_select(engine, retry_sql, timeout_seconds=None)
                        if rows2:
                            print(f"[DEBUG] {strategy_name} stratejisi başarılı: {retry_sql}")
                            columns, rows = columns2, rows2
                            sql_query = retry_sql  # bilgi amaçlı güncelle
                            break
                    except Exception as e:
                        print(f"[DEBUG] {strategy_name} stratejisi başarısız: {e}")
                        continue
                
                # Hala sonuç bulunamadıysa benzer ürünleri öner
                if not rows:
                    # Kullanıcının aradığı terimi çıkarmaya çalış
                    import re
                    search_terms = re.findall(r"['\"]([^'\"]+)['\"]", user_q)
                    for term in search_terms:
                        similar_products = find_similar_products(engine, term)
                        if similar_products:
                            print(f"\n🔍 '{term}' bulunamadı. Benzer ürünler:")
                            for product in similar_products[:5]:
                                print(f"  - {product}")
                            print("Bu ürünlerden birini deneyebilirsiniz.\n")
                            break
                        
        except Exception as e:
            print(f"Sorgu çalıştırılırken hata: {e}")
            continue

        # 3) Sonucu özetleyip Türkçe cevap üret
        raw_preview = preview_rows(columns, rows, max_rows=10)

        # Basit deterministik cevaplayıcı: bilinen bazı kalıpları LLM'e gerek kalmadan açıkla
        normalized_q = user_q.strip().lower()
        deterministic_answer = None

        try:
            # "stokta ne kadar var" benzeri soru ve beklenen tek değerli sonuçlar
            if "stokta" in normalized_q and ("ne kadar" in normalized_q or "kaç" in normalized_q):
                # units_in_stock tek kolonsa tek değer döndür
                if columns and len(columns) == 1 and columns[0].lower() == "units_in_stock":
                    if rows:
                        miktar = rows[0][0]
                        deterministic_answer = f"Stokta {miktar} adet var."
                    else:
                        deterministic_answer = "Bu ürüne ait stok bulunamadı."
            # "rastgele 3 ürün" gibi isteklerde isim+fiyat tabloyu kısa listele
            if deterministic_answer is None and "rastgele" in normalized_q and "ürün" in normalized_q:
                # Ürün adını ve fiyatı bulmaya çalış
                name_idx = None
                price_idx = None
                if columns:
                    for i, c in enumerate(columns):
                        lc = c.lower()
                        if lc in ("product_name", "name"):
                            name_idx = i
                        if lc in ("unit_price", "price"):
                            price_idx = i
                if rows and name_idx is not None:
                    lines = []
                    for r in rows[:3]:
                        if price_idx is not None:
                            lines.append(f"- {r[name_idx]} — Fiyat: {r[price_idx]}")
                        else:
                            lines.append(f"- {r[name_idx]}")
                    deterministic_answer = "Rastgele seçilen ürünler:\n" + "\n".join(lines)
        except Exception:
            deterministic_answer = None

        if deterministic_answer is None:
            # LLM ile özetlet
            try:
                answer_messages = build_answer_prompt(
                    context_rules=context_rules,
                    schema_text=schema_text,
                    sql_query=sql_query,
                    raw_rows_preview=raw_preview,
                    columns=columns,
                    user_question=user_q,
                )
                final_answer = ask_llm(answer_messages, temperature=0.1, mode="answer")
            except Exception as e:
                print("Sonuç yorumlanırken LLM hatası:", e)
                final_answer = None
        else:
            final_answer = deterministic_answer

        # 4) Yazdır
        if final_answer:
            print("Cevap:")
            print(final_answer)
        else:
            print("Ham Sonuç (önizleme):")
            print(raw_preview)

        print("\n" + "-" * 72 + "\n")


if __name__ == "__main__":
    main()
