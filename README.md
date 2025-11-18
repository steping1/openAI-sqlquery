# Türkçe Doğal Dilden PostgreSQL'e SQL ve Türkçe Cevap (Python MVP)

Bu MVP, context.md'de tanımlanan akışa uygun olarak geliştirilmiş **akıllı veritabanı sorgulama sistemi**dir. Kullanıcıların Türkçe doğal dilde soruları karşılığında PostgreSQL sorguları üretip, sonuçları yine Türkçe olarak anlamlı şekilde sunar.

## 🎯 Sistemin Amacı
Teknik bilgisi olmayan kullanıcıların veritabanından bilgi alabilmesi için Türkçe doğal dil ile SQL arasında köprü görevi görür. OpenRouter üzerinden çalışan Gemma LLM modeli ile güçlendirilmiştir.

## 🔄 Çalışma Akışı
1) **Kullanıcı Girişi**: Türkçe doğal dilde soru alır
2) **Bağlam Enjeksiyonu**: Kurallar ve şema bilgisini LLM'e verir 
3) **SQL Üretimi**: Gemma modeli ile güvenli PostgreSQL sorgusu üretir
4) **Sorgu Çalıştırma**: SQL'i veritabanında güvenli şekilde çalıştırır
5) **Cevap Üretimi**: Ham sonucu tekrar LLM ile Türkçe ve anlamlı cevaba dönüştürür
6) **Kullanıcıya Sunum**: Formatlanmış, okunaklı Türkçe cevap gösterir

**Teknolojiler**: Python, LangChain, OpenRouter (Gemma), SQLAlchemy, psycopg, Docker PostgreSQL

## Hızlı Başlangıç

Önkoşullar:
- Python 3.10+
- Docker Desktop (PostgreSQL container)

### 1) PostgreSQL Container’ı Çalıştır
Aşağıdaki komut, context’te verilen değerlerle aynıdır (şifreleri ve portu istersen değiştir):
```
docker run --name postgres-test ^
  -e POSTGRES_USER= ^
  -e POSTGRES_PASSWORD= ^
  -e POSTGRES_DB= ^
  -p 5432:5432 ^
  -d postgres
```
Windows PowerShell kullanıyorsan `^` yerine ``` ` ``` backtick kullanabilirsin veya tek satırda çalıştırabilirsin.

### 2) Python Bağımlılıklarını Kur
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3) Ortam Değişkenlerini Ayarla
`.env` dosyasını düzenle:
```
OPENROUTER_API_KEY=YOUR_KEY_HERE
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=google/gemma-7b-it

DATABASE_URL=postgresql+psycopg2://postgres:123456@localhost:5432/northwind
QUERY_TIMEOUT_SECONDS=10
ROW_LIMIT_DEFAULT=1000
```

### 4) Northwind Veritabanını Oluştur
PostgreSQL içinde `northwind` isimli veritabanını oluştur ve (varsa) Northwind şemasını içe aktar. Örnek:
- psql ile veritabanını oluştur:
```
psql -h localhost -U postgres -c "CREATE DATABASE northwind"
```
- Daha sonra Northwind .sql dosyanı bu veritabanına uygula (örneğin):
```
psql -h localhost -U postgres -d northwind -f path\to\northwind.sql
```

Not: Bu projedeki `seed_db.py` demo şeması içindir. Northwind kullanırken gerekli değildir.

### 5) CLI Uygulamasını Çalıştır
```
python main.py
```
Komut satırında Türkçe sorular gir:
- "Geçen ay kaç sipariş verilmiş?"
- "En çok satan 5 ürünü listele."

Çıkmak için boş satır bırakıp Enter’a bas veya Ctrl+C.

## 📁 Proje Yapısı ve Dosya Açıklamaları

### 🚀 Ana Uygulama Dosyaları
- **`main.py`** (209 satır): 
  - Ana CLI uygulaması ve uçtan uca akış yöneticisi
  - Kullanıcı arayüzü ve interaktif döngü
  - SQL normalizasyonu ve hata yönetimi
  - Deterministik cevap mantığı (basit sorular için LLM'siz yanıt)
  - Fallback mekanizmaları (büyük/küçük harf uyumsuzlukları için)

- **`llm.py`** (273 satır):
  - OpenRouter API entegrasyonu ve Gemma modeli yönetimi
  - SQL üretimi ve Türkçe cevap prompt'ları
  - Türkçe karakter normalizasyonu (ç→c, ğ→g, vb.)
  - Northwind tablo/kolon isimlerinin snake_case dönüşümü
  - Retry mekanizması ve hata toleransı

- **`db.py`** (113 satır):
  - PostgreSQL bağlantı yönetimi (SQLAlchemy)
  - Güvenli SQL çalıştırma (yalnızca SELECT)
  - Otomatik LIMIT ve timeout uygulaması
  - Bağlantı havuzu (connection pool) yapılandırması
  - SQL injection koruması

- **`context_loader.py`** (133 satır):
  - Bağlam kurallarının `context.md`'den yüklenmesi
  - Canlı veritabanından şema çıkarımı (information_schema)
  - Northwind tablolarının otomatik tespiti
  - Fallback mekanizması (DB erişilemezse dosyadan okuma)

### 🛠️ Destek ve Yapılandırma Dosyaları
- **`seed_db.py`** (124 satır):
  - Demo amaçlı basit test veritabanı oluşturma
  - Örnek müşteri, ürün ve sipariş verilerinin eklenmesi
  - DDL (Create Table) komutları
  - Test ortamı hazırlama yardımcıları

- **`context.md`** (233 satır):
  - Sistem kuralları ve kısıtlamaları
  - Northwind şema dokümantasyonu
  - LLM davranış kuralları
  - Güvenlik politikaları (SELECT-only)
  - Örnek soru-cevap akışları

- **`requirements.txt`** (12 satır):
  - Python bağımlılıkları: LangChain, OpenAI, SQLAlchemy, psycopg2, pandas, tabulate
  - Sürüm sabitlemeleri ve uyumluluk garantisi

### 📋 Yapılandırma Dosyaları
- **`.env`**: API anahtarları, veritabanı bağlantı bilgileri, timeout ayarları
- **`README.md`**: Bu dokümantasyon dosyası

## 🔧 Sistem Özellikleri ve Güvenlik

### 🛡️ Güvenlik Önlemleri
- **SQL Injection Koruması**: Parametreli sorgular kullanılır
- **Sadece SELECT İzni**: INSERT/UPDATE/DELETE/DROP komutları engellenir
- **Otomatik Timeout**: Sorgular max 10 saniyede kesilir
- **Satır Limiti**: Varsayılan 1000 satır sınırı otomatik uygulanır
- **Şema Kontrolü**: Sadece mevcut tablo/kolonlar kullanılabilir

### 🎯 Akıllı Özellikler
- **Türkçe Karakter Normalizasyonu**: ç→c, ğ→g, ş→s dönüşümleri
- **CamelCase → snake_case**: ProductName → product_name otomatik dönüşümü
- **Deterministik Cevaplar**: Basit sorular için LLM'siz hızlı yanıt
- **Fallback Mekanizması**: Hata durumlarında alternatif çözümler
- **Retry Sistemi**: API hataları için otomatik yeniden deneme

### 📊 Desteklenen Soru Türleri
- **Sayım Sorguları**: "Kaç müşteri var?", "Toplam sipariş sayısı?"
- **Filtreleme**: "Pahalı ürünleri listele", "İstanbul'daki müşteriler"
- **Sıralama**: "En çok satan ürünler", "Son siparişler"
- **Gruplama**: "Kategoriye göre ürün sayısı", "Aylık satış toplamları"
- **İstatistik**: "Ortalama fiyat", "Minimum/maksimum değerler"

### 🔄 Performans ve Optimizasyon
- **Bağlantı Havuzu**: PostgreSQL için connection pooling
- **Token Optimizasyonu**: LLM prompt'ları için boyut limitleri
- **Önbellekleme**: Şema bilgilerinin cache'lenmesi
- **Paralel İşlem**: Veritabanı ve LLM işlemlerinin optimize edilmesi

## 🚀 Gelecek Geliştirmeler
- **Web Arayüzü**: Flask/FastAPI tabanlı web interface
- **Görselleştirme**: Grafik ve chart entegrasyonu
- **PDF Export**: Sonuçların rapor olarak çıktısı
- **Sesli Soru-Cevap**: Speech-to-text entegrasyonu
- **Multi-Language**: İngilizce ve diğer dil desteği
- **Agent Modu**: Otomatik görev planlama ve yürütme

## 📝 Notlar
- Sistem tamamen Türkçe odaklı tasarlanmıştır
- LLM'e hem kurallar hem canlı şema enjekte edilir
- Hata durumlarında anlaşılır Türkçe mesaj üretimi hedeflenir
- Production kullanımı için ek güvenlik önlemleri önerilir
#


