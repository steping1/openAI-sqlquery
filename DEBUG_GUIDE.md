# 🐛 Ürün Sorgu Problemleri Debug Rehberi

Bu kılavuz, projedeki ürün sorgularında yaşanan problemleri çözmek için geliştirilmiştir.

## 🔧 Yapılan İyileştirmeler

### 1. ILIKE Operatörü Kullanımı
```sql
-- Eski (büyük/küçük harf duyarlı):
SELECT * FROM products WHERE product_name = 'chai'

-- Yeni (büyük/küçük harf duyarsız):
SELECT * FROM products WHERE product_name ILIKE '%chai%'
```

### 2. Çoklu Fallback Stratejileri
Sistem artık ürün bulunamadığında sırayla şu stratejileri dener:

1. **ILIKE Dönüşümü**: `=` operatörünü `ILIKE '%...%'` formatına çevirir
2. **Title Case**: İlk harfi büyük yapar (`chai` → `Chai`)
3. **Küçük Harf**: Tamamen küçük harfe çevirir

### 3. Fuzzy Matching
Hiçbir strateji çalışmazsa benzer ürün önerileri sunar:
```
🔍 'chai' bulunamadı. Benzer ürünler:
  - Chai
  - Chocolade
  - Chartreuse verte
```

### 4. Debug Modu
Detaylı log görmek için:
```bash
set DEBUG_SQL=true
python main.py
```

## 🚀 Kullanım Örnekleri

### Başarılı Sorgular:
- "chai stokta ne kadar var"
- "Chai ürünü bul"
- "CHAI fiyatı nedir"
- "chocolade ürünleri"

### Sistem Otomatik Düzeltir:
- `product_name = 'chai'` → `product_name ILIKE '%Chai%'`
- Küçük/büyük harf uyumsuzlukları
- Türkçe karakter normalizasyonu

## 🔍 Problem Çözme

### Sık Karşılaşılan Problemler:

1. **Ürün Bulunamıyor**
   - ✅ Sistem otomatik olarak ILIKE kullanacak
   - ✅ Farklı büyük/küçük harf kombinasyonlarını deneyecek
   - ✅ Benzer ürün önerileri sunacak

2. **SQL Hataları**
   - ✅ DEBUG_SQL=true ile detaylı log al
   - ✅ Sistem safe fallback'ler kullanacak

3. **LLM Yanlış SQL Üretiyor**
   - ✅ Prompt'ta daha iyi örnekler eklendi
   - ✅ ILIKE kullanımı zorlanıyor
   - ✅ Şema bilgisi artırıldı

## 📊 Performans İyileştirmeleri

- Şema bilgisi optimize edildi (150 → 200 satır)
- Fuzzy search timeout'u 5 saniyeye düşürüldü
- Debug modunda detaylı timing bilgileri

## 🛠️ Teknik Detaylar

### Regex Patterns:
```python
# Ürün adı yakalama
search_terms = re.findall(r"['\"]([^'\"]+)['\"]", user_question)

# Operatör değiştirme
retry_sql = re.sub(r"(=|ILIKE)\s*['\"]([a-zA-ZçğıöşüÇĞIÖŞÜ]+)['\"]", 
                   replacement_func, sql_query, flags=re.IGNORECASE)
```

### Fallback Sırası:
1. ILIKE dönüşümü
2. Title case (`Chai`)
3. Lowercase (`chai`)
4. Fuzzy matching
5. Kullanıcı önerileri

## ⚡ Hızlı Test

Aşağıdaki komutları test ederek sistem çalışıyor mu kontrol edin:

```bash
# Normal mod
python main.py

# Debug mod
set DEBUG_SQL=true && python main.py

# Test sorguları:
# - "chai stokta kaç var"
# - "CHAI fiyatı"
# - "chocolade ürünleri"
# - "olmayan_ürün test"  # Önerileri görmek için
```

## 📈 Gelecek İyileştirmeler

- [ ] Levenshtein distance ile daha akıllı fuzzy matching
- [ ] Ürün kategorisi bazlı arama
- [ ] Cache mekanizması ürün adları için
- [ ] Sesli komut desteği
- [ ] Web arayüzü
