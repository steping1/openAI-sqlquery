import os
from typing import Dict, Any, List

from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

# LangChain imports (OpenAI client via OpenRouter-compatible endpoint)
from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage, AIMessage

load_dotenv()

DEFAULT_MODEL = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")


def _build_headers() -> Dict[str, str]:
    # OpenRouter is OpenAI-compatible with extra headers; basic usage works without extra headers
    headers = {}
    # You may optionally pass HTTP headers like HTTP-Referer and X-Title if desired
    referer = os.getenv("OPENROUTER_HTTP_REFERER")
    title = os.getenv("OPENROUTER_HTTP_TITLE")
    if referer:
        headers["HTTP-Referer"] = referer
    if title:
        headers["X-Title"] = title
    return headers


def get_llm(temperature: float = 0.1) -> ChatOpenAI:
    """
    Returns a ChatOpenAI configured to talk to OpenRouter (DeepSeek or other OpenRouter models).
    """
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY ortam değişkeni bulunamadı. .env dosyanızı kontrol edin.")

    # ChatOpenAI from langchain-openai supports base_url to override the endpoint
    # max_tokens'i küçük tutarak ücretsiz/limitli kredilere takılmayı azalt.
    # Deepseek free sürümler bazen boş içerik döndürebilir. Daha uyumlu bir model zorlayalım (gerekirse .env ile override edilir).
    model = DEFAULT_MODEL or "openai/gpt-3.5-turbo"
    llm = ChatOpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        model=model,
        temperature=temperature,
        default_headers=_build_headers(),
        max_tokens=256,
    )
    return llm


def _normalize_identifiers_in_text(text: str) -> str:
    """
    Basit normalizasyon: 
    - Türkçe karakterleri ASCII'ye indirger (ör: Ç->C, ç->c, Ğ->G, ğ->g, İ->I, ı->i, Ö->O, ö->o, Ş->S, ş->s, Ü->U, ü->u).
    - Northwind benzeri alan ve tablo adlarını snake_case (PostgreSQL uyumlu) hale getirir.
    - Büyük/küçük harf duyarsız tam eşleşmeler için bilineni listeler.
    Not: Bu yaklaşım güvenli bir 'parser' değildir; yine de sık görülen üretimleri düzeltir.
    """
    # 1) Türkçe karakter normalizasyonu
    turkish_map = str.maketrans({
        "Ç": "C", "ç": "c",
        "Ğ": "G", "ğ": "g",
        "İ": "I", "I": "I",  # büyük I aynı kalsın
        "ı": "i",
        "Ö": "O", "ö": "o",
        "Ş": "S", "ş": "s",
        "Ü": "U", "ü": "u",
    })
    text = text.translate(turkish_map)

    # 2) Bilinen kimlik normalizasyonları
    replacements = {
        # Tablolar
        "Order_Details": "order_details",
        "OrderDetails": "order_details",
        "Products": "products",
        "Orders": "orders",
        "Customers": "customers",
        "Suppliers": "suppliers",
        "Categories": "categories",
        "Employees": "employees",
        "Shippers": "shippers",
        # Ortak kolonlar
        "ProductID": "product_id",
        "ProductName": "product_name",
        "SupplierID": "supplier_id",
        "CategoryID": "category_id",
        "QuantityPerUnit": "quantity_per_unit",
        "UnitPrice": "unit_price",
        "UnitsInStock": "units_in_stock",
        "UnitsOnOrder": "units_on_order",
        "ReorderLevel": "reorder_level",
        "Discontinued": "discontinued",
        "OrderID": "order_id",
        "CustomerID": "customer_id",
        "EmployeeID": "employee_id",
        "OrderDate": "order_date",
        "RequiredDate": "required_date",
        "ShippedDate": "shipped_date",
        "ShipVia": "ship_via",
        "Freight": "freight",
        "ShipName": "ship_name",
        "ShipAddress": "ship_address",
        "ShipCity": "ship_city",
        "ShipRegion": "ship_region",
        "ShipPostalCode": "ship_postal_code",
        "ShipCountry": "ship_country",
        "Unitprice": "unit_price",
        "Quantity": "quantity",
        "Discount": "discount",
        "CompanyName": "company_name",
        "ContactName": "contact_name",
        "ContactTitle": "contact_title",
        "Address": "address",
        "City": "city",
        "Region": "region",
        "PostalCode": "postal_code",
        "Phone": "phone",
        "Fax": "fax",
        "HomePage": "home_page",
        "CategoryName": "category_name",
        "Description": "description",
        "Picture": "picture",
        "LastName": "last_name",
        "FirstName": "first_name",
        "Title": "title",
        "ReportsTo": "reports_to",
        "BirthDate": "birth_date",
        "HireDate": "hire_date",
        "HomePhone": "home_phone",
        "Extension": "extension",
        "Notes": "notes",
        "Photo": "photo",
        "PhotoPath": "photo_path",
        "ShipperID": "shipper_id",
        # Fonksiyonlar
        "RANDOM()": "random()",
        "Random()": "random()",
        "Random": "random",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text


def build_sql_prompt(context_rules: str, schema_text: str, user_question: str) -> List[Any]:
    """
    Constructs a system+human prompt to ask LLM to produce ONLY a valid PostgreSQL SELECT query.
    The model must follow constraints from context.md.
    """
    # Kuralları ve şemayı olabildiğince kısa ve direkt ver
    context_rules_short = context_rules.strip()
    schema_lines = [line.strip() for line in schema_text.strip().splitlines() if line.strip()]
    schema_compact = []
    for ln in schema_lines:
        if len(ln) > 120:
            schema_compact.append(ln[:120] + " ...")
        else:
            schema_compact.append(ln)
    schema_compact_text = "\n".join(schema_compact[:200])  # şema bilgisini artırdım

    system = f"""Aşağıdaki kurallara SIKI sıkıya uyarak SADECE bir PostgreSQL SELECT sorgusu üret:
- Şemadaki tablo/kolon adlarını AYNEN (snake_case) kullan.
- Kod bloğu, açıklama, doğal dil YAZMA. Yalnızca tek satır SQL döndür.
- Komutlar sadece SELECT/WITH olabilir. INSERT/UPDATE/DELETE/DDL YASAK.
- Belirsizse en basit doğru SELECT'i üret (ör: en çok kalan ürün -> order by units_in_stock desc).
- Ürün adı arama için ILIKE kullan: product_name ILIKE '%arama%' 
- Büyük/küçük harf duyarsız arama için ILIKE operatörünü kullan
- Örnekler:
  "Chai stokta ne kadar var" -> select units_in_stock from products where product_name ILIKE '%Chai%'
  "chai ürünü" -> select * from products where product_name ILIKE '%chai%'
  "rastgele 3 ürün" -> select product_name, unit_price from products order by random() limit 3
  "pahalı ürünler" -> select product_name, unit_price from products where unit_price > 50 order by unit_price desc

Şema (detaylı):
{schema_compact_text}"""
    user = f"""Kullanıcı sorusu (Türkçe): {user_question}

Tek satır SELECT yaz. Ürün adları için ILIKE kullan. Başına/sonuna hiçbir açıklama/kod bloğu ekleme."""
    return [SystemMessage(content=system), HumanMessage(content=user)]


def build_answer_prompt(context_rules: str, schema_text: str, sql_query: str, raw_rows_preview: str, columns: List[str], user_question: str) -> List[Any]:
    """
    Constructs a prompt to ask LLM to transform raw SQL results into a concise, Turkish answer.
    """
    cols_fmt = ", ".join(columns) if columns else "(kolon yok)"
    # Token tasarrufu için yine özet kullan
    context_rules_short = context_rules.strip()
    schema_lines = [line.strip() for line in schema_text.strip().splitlines() if line.strip()]
    schema_compact = []
    for ln in schema_lines:
        if len(ln) > 120:
            schema_compact.append(ln[:120] + " ...")
        else:
            schema_compact.append(ln)
    schema_compact_text = "\n".join(schema_compact[:200])

    system = f"""Sen bir veri analizi asistanısın. Görevlerin:
- SQL sonucu gibi ham veriyi Türkçe, kısa ve anlaşılır final cevaba dönüştür.
- Bağlam kurallarına uy.
- Eğer sonuç boşsa bunu netçe belirt ve mümkünse kullanıcıya yönlendirici, kısa bir not ekle.
- Sayıları binlik ayraç ile formatla (örn: 1.250).
- Cevabı gereksiz uzatma. Yalnızca gerekli bilgiyi ver.
- Tablo veya liste gerekiyorsa kısa ve okunaklı biçimde sun.

Bağlam Kuralları (özet):
{context_rules_short}

Şema (özet):
{schema_compact_text}
"""
    user = f"""Kullanıcı sorusu: {user_question}
Üretilen SQL: {sql_query}
Kolonlar: {cols_fmt}
Önizleme (ilk satırlar):
{raw_rows_preview}

Lütfen Türkçe, kısa ve net nihai cevabı ver."""
    return [SystemMessage(content=system), HumanMessage(content=user)]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def ask_llm(messages: List[Any], temperature: float = 0.1, mode: str = "sql") -> str:
    """
    mode:
      - "sql": SQL üretimi için agresif post-process ve 'select 1' fallback uygula.
      - "answer": Doğal dil cevabı olduğu gibi döndür; SQL temizlemesi ve fallback yapma.
    """
    llm = get_llm(temperature=temperature)
    # Bazı sağlayıcılarda max_tokens param adı desteklenmeyebilir; güvenli çağrı yap
    try:
        resp = llm.invoke(messages, max_tokens=128)  # daha kısa cevap zorlaması
    except TypeError:
        resp = llm.invoke(messages)
    # İçeriği ayıkla
    if isinstance(resp, AIMessage):
        content = (resp.content or "").strip()
    else:
        content = str(getattr(resp, "content", "") or "").strip()

    if mode == "answer":
        # Doğal dil cevabı aynen döndür (en fazla ufak backtick temizliği)
        return content

    # mode == "sql": Güçlü post-process: sadece SELECT döndürülmesini zorlamak
    cleaned = content.replace("```sql", "").replace("```", "").strip()
    # İçerik tamamen boşsa minimal bir planla doldur ve SELECT üretmeye zorla
    if not cleaned:
        return "select 1"

    # Satırları al ve ilk SELECT/WITH ile başlayan satırı seç
    lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]
    selected = ""
    for ln in lines:
        low = ln.lower()
        if low.startswith("select ") or low.startswith("with "):
            selected = ln
            break
    if not selected and cleaned.lower().startswith(("select ", "with ")):
        selected = cleaned

    if not selected:
        # Tüm metinden SELECT'i kaba regex ile yakala
        import re
        m = re.search(r"(?is)\b(select|with)\b.+", cleaned)
        if m:
            selected = m.group(0).strip()

    if not selected:
        # Son çare
        selected = "select 1"

    return selected
