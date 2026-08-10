# Proje Notları

Bu dosya, projenin nasıl ve neden bu şekilde kurgulandığını, alınan kararları
ve klasör yapısını kaydeder — proje bir süre sonra tekrar açıldığında
hatırlanabilmesi için.

## Amaç

Butona basıldığında MS SQL Server'da sabit bir sorgu çalıştırılır, dönen her
satır `rules.txt` dosyasındaki serbest metin kurallarına göre bir dil
modeline (LLM) gönderilerek ONAY/İADE kararı verdirilir. Ayrıca her satırdaki
"kolon adı" değeri, kurumun iş terimi sözlüğüyle karşılaştırılıp eşleşme
durumu / öneri terimler gösterilir.

## Teknoloji seçimleri ve nedenleri

- **Backend: FastAPI** — async destekli, hafif, tip güvenli (Pydantic) ve
  hızlı geliştirme sağlıyor. Çoklu satırı eşzamanlı (concurrent) modele
  gönderebilmek için async doğal bir gereksinimdi.
- **MSSQL: pyodbc** — Windows/Linux'ta ODBC Driver 17/18 ile en yaygın ve
  stabil MSSQL istemcisi. Bağlantı yalnızca `SELECT` sorgularını
  çalıştıracak şekilde kodlandı (`db.py` içinde `_run_select` bunu zorunlu
  kılar).
- **Ortam değişkenleri: python-dotenv** — `.env` dosyası proje kök
  dizininde tutuluyor; backend hangi dizinden başlatılırsa başlatılsın
  (`backend/` içinden `uvicorn main:app`), `.env` ve `rules.txt` yolları
  `config.PROJECT_ROOT` üzerinden mutlak olarak çözülüyor (CWD'ye bağımlı
  değil).
- **Frontend: Sade HTML + CSS + Vanilla JS** — Framework gerektirmeyecek
  kadar basit bir tek-sayfa arayüz; build adımı yok, doğrudan FastAPI
  `StaticFiles` ile servis ediliyor.
- **LLM entegrasyonu: Anthropic Claude API** — Resmi `anthropic` Python
  SDK'sı, `AsyncAnthropic` istemcisi ile. Güvenilir JSON çıktı almak için
  serbest metin ayrıştırma yerine **structured outputs**
  (`output_config.format` + JSON schema) kullanıldı — bu, model çıktısını
  ayrıştırırken oluşabilecek hataları ortadan kaldırıyor.

## Model provider (sağlayıcı) katmanı — strategy pattern

`backend/providers/base.py` içinde soyut `ModelProvider` sınıfı iki async
metot tanımlar:

- `check_row(row_data, rules_text) -> {"karar": "ONAY"|"IADE", "gerekce": str}`
- `check_term_match(column_name, reference_data) -> {"durum": ..., "terim": ..., "oneriler": [...]}`

`ClaudeProvider` (`claude_provider.py`) bu arayüzü Anthropic API ile
implemente eder. `LocalProvider` (`local_provider.py`) ileride Ollama gibi
bir yerel model için doldurulacak bir iskelet olarak bırakıldı — arayüz aynı
olduğu için `main.py`'deki `get_provider()` fonksiyonuna tek satırla
eklenebilir.

Frontend'deki "Model Sağlayıcı" dropdown'ı seçilen değeri
(`"claude"` / `"local"`) backend'e `POST /api/run-check` gövdesinde
(`{"provider": "..."}`) iletir.

### Neden ayrı bir `check_term_match` fonksiyonu?

Kullanıcı isteğinde açıkça belirtildiği gibi, ONAY/İADE kural denetimi ile
terim eşleştirmesi **ayrı fonksiyonlar/adımlar** olarak kurgulandı (aynı
provider üzerinden, ama bağımsız API çağrıları). Böylece ikisi birbirinden
bağımsız test edilip geliştirilebilir. Şu anki implementasyonda her satır
için iki ayrı model çağrısı yapılıyor; performans gerektiğinde bu ikisi tek
bir çağrıda birleştirilebilir (schema'yı genişleterek), ama okunabilirlik ve
modülerlik için ayrı tutuldu.

## "Ek veri" kolonlarının otomatik ayrıştırılması

`backend/config.py` içindeki `REQUIRED_COLUMNS = ["id", "LocationName",
"SchemaName", "TableName"]` sabiti dışındaki tüm kolonlar, `main.py` içindeki
`_split_row()` fonksiyonu tarafından otomatik olarak "ek veri" (denetime tabi
veri) olarak ayrılıp modele gönderiliyor. Yani `MAIN_QUERY`'ye yeni bir kolon
eklemek, kod değişikliği gerektirmeden o kolonu da denetime dahil eder.

## Terim eşleştirme kolonu varsayımı

Terim eşleştirmesi için, ek veri içinde hangi alanın "denetlenecek kolon adı"
olduğunu bilmek gerekiyor. Bu, `config.py` içinde `TERM_MATCH_COLUMN_KEY`
(varsayılan: `"KolonAdi"`) ile yapılandırılabilir bırakıldı — gerçek şemanıza
göre bu anahtarı `MAIN_QUERY`'nizdeki ilgili kolon adıyla eşleştirin. Bu
alan satırda yoksa veya boşsa, o satır için terim eşleştirmesi atlanır
(`term_status: null`).

## Hata yönetimi

- **rules.txt bulunamadı / boş** → `RulesFileNotFoundError` → HTTP 400,
  arayüzde kırmızı hata banner'ında gösterilir.
- **MSSQL bağlantı/sorgu hatası** → `DatabaseError` → HTTP 502.
- **Model API hatası (Claude)** → `ModelProviderError`. İstek düzeyinde
  (örn. API anahtarı eksikse) HTTP 400 döner. Satır düzeyinde (örn. tek bir
  satır için geçici bir API hatası) o satır "HATA" kategorisine düşer ve
  diğer satırların denetimi devam eder — tek bir satırdaki geçici hata tüm
  denetimi durdurmaz.

## Performans

Satırlar `asyncio.gather` ile eşzamanlı işlenir; eşzamanlı model çağrısı
sayısı `config.MAX_CONCURRENT_MODEL_CALLS` (varsayılan 5) ile sınırlanır —
hem hız hem de API rate limit koruması için. Sistem promptu (kurallar dahil)
`cache_control: ephemeral` ile işaretlenerek, aynı çalıştırma içindeki
tekrarlanan çağrılarda prompt caching'den faydalanılır.

## Klasör yapısı

```
SQLTableRuleCheck/
  backend/
    main.py              FastAPI app, /api/run-check endpoint'i
    config.py             Sabit SQL sorguları ve ayarlar
    db.py                 MSSQL bağlantı ve sorgu çalıştırma (yalnızca SELECT)
    providers/
      base.py             Soyut ModelProvider arayüzü
      claude_provider.py  Anthropic Claude API implementasyonu
      local_provider.py   Yerel model (Ollama vb.) için iskelet
    rules_loader.py       rules.txt'yi her seferinde taze okur
  frontend/
    index.html
    style.css              Koyu tema
    app.js                 Vanilla JS — fetch, render, kopyala
  rules.txt                 Kullanıcı tarafından doldurulacak kurallar
  .env.example               Şablon (gerçek .env repoya girmez)
  requirements.txt
  README.md
  PROJECT_NOTES.md            (bu dosya)
```
