# Proje Notları

Bu dosya, projenin nasıl ve neden bu şekilde kurgulandığını, alınan kararları
ve klasör yapısını kaydeder — proje bir süre sonra tekrar açıldığında
hatırlanabilmesi için.

## Amaç

DataGov (DataOne) kataloğunda onay bekleyen (`DataScript.StatusId=0`) MSSQL
DB değişiklik script'lerini çekip, kurumun `rules.txt` dosyasındaki DB
tasarım/isimlendirme standartlarına göre bir dil modeline (LLM) göndererek
ONAY/İADE kararı verdirir. Karar verilirken script'in gerçekte hangi
kolonlara ne yaptığı (ADD/ALTER/DROP) kendi metninden çıkarılır; sadece
incelenen ana tabloyu hedefleyen script'ler kural denetiminden geçirilir —
audit/arşiv companion script'leri otomatik onaylanır ve sonuç listesine
hiç girmez (bkz. aşağıdaki ilgili bölümler).

## Veri kaynağı: `DataGov.DTG` şeması

- **`DataSystem`** — 3 seviyeli kendine-referanslı hiyerarşi (`ParentId`):
  T1 = Sunucu, T2 = Veritabanı, T3 = Şema. (Not: bu eşleme deneme-yanılmayla
  bulundu — script içeriğiyle karşılaştırılarak doğrulandı, örn.
  `USE [BOAAI]; CREATE TABLE [BOAAI].[CAI].[Tablo]` → T2.Name='BOAAI',
  T3.Name='CAI' ile birebir eşleşti.)
- **`DataSet`** — mantıksal tablo/nesne kaydı (T4): `Name` (tablo adı),
  `Description` (tablo açıklaması).
- **`DataScript`** — bir DataSet'e ait fiziksel DDL script'i (`ScriptText`).
  `StatusId=0` = onay bekliyor. Aynı `DataSetId`'ye birden fazla `DataScript`
  bağlı olabilir (örn. ana tablo + audit mirror + arşiv tablosu için ayrı
  script'ler — DataOne mantıksal bir değişikliği birden fazla fiziksel
  script'e bölebiliyor, her biri farklı bir veritabanını hedefliyor).
- **`DataItem`** — kolon kataloğu (`DataSetId` altında). `StatusId=5` =
  "Bilgi Mimarı Onayında" (`COLUMN_STATUS_PENDING`, `config.py`). Bu
  değerler DataOne tarafından yönetilir, uygulama **sadece okur, yazmaz**.
- **`Term`** — iş terimi sözlüğü. Şu an aktif kullanılmıyor (bkz. "Terim
  eşleştirme" bölümü).

## `MAIN_QUERY` (`backend/config.py`)

`DataSystem` (T1→T2→T3) → `DataSet` (T4) → `DataScript` (T7) zincirini
join'leyip `StatusId=0` olan script'leri döndürür. Döndürdüğü alanlar:
`id` (DataScriptId), `LocationName`, `DatabaseName`, `SchemaName`,
`TableName`, `DataSetId` (kolon sorgusu için, sonra silinir),
`TableDescription`, `ScriptText`.

## Script parse — `backend/script_parser.py`

`ScriptText` regex ile parse edilip, script'in **incelenen tabloya (ana
tablo)** ne tür bir işlem yaptığı çıkarılır:

- `CREATE TABLE [db].[schema].[table] (...)` → içindeki her kolon `ADD`
- `ALTER TABLE ... ADD [Col] ...` → `ADD`
- `ALTER TABLE ... ALTER COLUMN [Col] ...` → `ALTER`
- `ALTER TABLE ... DROP COLUMN [Col1], [Col2]` → `DROP`

Eşleşme, ifadenin hedefinin (`[Database].[Schema].[Table]`) satırın
`DatabaseName`/`SchemaName`/`TableName` alanlarıyla **TAM** (case-insensitive)
eşleşmesi şartına bağlıdır — aynı script bloğunda geçen audit/arşiv
tablolarına veya trigger tanımlarına ait ifadeler bu sayede otomatik yok
sayılır (10 farklı gerçek script'te test edildi, hepsi doğru ayrıştı).

`_split_top_level()` yardımcı fonksiyonu, `NUMERIC(10,2)` gibi parantez içi
virgülleri es geçerek üst seviye kolon tanımlarını doğru ayırır.

## Ana tablo dışı (audit/arşiv) script'lerin otomatik onayı

Kullanıcı onay verirken sadece **ana tabloya** ne yapıldığına bakıyor;
audit/arşiv tablolarının güncellenmesi geliştiricinin zaten yapması gereken
mekanik bir adım, ayrıca değerlendirilmiyor. Bu yüzden `main.py` ->
`_process_row()` içinde:

- `parse_column_changes()` sonucu **boşsa** (script tek başına ana tabloya
  hiç dokunmuyorsa — örn. sadece `BOAAuditArchive` tablosunu hedefleyen bir
  script), model çağrısı **atlanır**, otomatik `ONAY` verilir.
- Bu satırlar `run_check()` içinde sonuç listesinden **tamamen çıkarılır**
  (`results = [r for r in all_results if not r["auto_approved"]]`) — aynı
  mantıksal tablonun hem ONAY hem İADE grubunda görünmesini önlemek için
  (aynı `DataSetId`'ye bağlı birden fazla fiziksel script olabildiğinden,
  bu görsel karışıklığa yol açıyordu).
- Ana tabloyu hedefleyen script (aynı `DataSetId`'nin "gerçek" script'i)
  normal şekilde modele gidip denetleniyor.

## Kolon verisi: iki ayrı sorgu — `TumKolonlar` / `OnayBekleyenKolonlar`

`COLUMN_QUERY_TEMPLATE` (`config.py`), `db.py -> _fetch_columns_for_datasets()`
tarafından **iki farklı modda** çalıştırılır (`only_pending` parametresi):

- `only_pending=False` → **`TumKolonlar`**: tabloya ait tüm kolonlar,
  StatusId ne olursa olsun. Sadece **ekranda** tam bağlam göstermek için
  kullanılır, modele **gönderilmez**.
- `only_pending=True` (`AND di.StatusId = 5`) → **`OnayBekleyenKolonlar`**:
  sadece o an onayda olan kolonlar. Kural denetiminin **TEK** kolon
  kaynağıdır, modele bununla gidilir.

Bu ayrım, modelin script'in dokunmadığı ama tabloya ait eski/canlı
kolonları (örn. `CustomerId`) yanlışlıkla İade sebebi göstermesini önlemek
için eklendi (gerçek bir bug'dı: script sadece 7 kolonu `ALTER COLUMN`
ediyordu ama model tabloya ait ilgisiz bir kolonu gerekçe gösteriyordu).

**Bilinen sınırlama:** Dev ortamında `DataItem.StatusId` şu an tüm
satırlarda `NULL` — yani `OnayBekleyenKolonlar` her zaman boş dönüyor,
model sadece `ScriptText`'e bakarak karar veriyor. DataOne gerçek akışta bu
alanı doldurunca kolon bazlı bağlam (tip, nullable, PK, identity) da
modele ulaşacak.

`Identity`/`PrimaryKey` formatı: `CASE` ile `"seed,increment"` / `"PK"` /
`"-"` string'i olarak dönüyor (checkbox/boolean değil) — kullanıcının
kendi referans sorgusuyla birebir aynı format.

## Kural yazımıyla ilgili bulgu: Identity vs Primary Key

`rules.txt`'deki "Identity alan adı `<TabloAdı>Id` olmalı" kuralı, SQL
Server'daki `IDENTITY` özelliğini (auto-increment) hedefliyor — sadece
`PRIMARY KEY` olup `IDENTITY` olmayan kolonlar (örn. `LedgerId INT PRIMARY
KEY`, identity'siz) bu kurala göre ihlal sayılmıyor; model bu ayrımı
teknik olarak doğru yapıyor. Bu, kuralın yazımından kaynaklanan bir durum,
kod hatası değil.

## Frontend: toggle'lı kolon tablosu + script görüntüleyici + renklendirme

- Kart başlığı (Sunucu/Veritabanı/Şema/Tablo Adı) tıklanabilir — tıklanınca
  altında `TumKolonlar` bir tablo halinde açılır/kapanır (varsayılan kapalı).
  Kolonlar: Kolon Adı, Fiziksel Veri Tipi, Boş Bırakılabilir, Identity,
  Birincil Anahtar, Kolon Açıklaması, İş Terimi.
- Ayrı bir "Script'i göster/gizle" toggle'ı ham `ScriptText`'i açar/kapatır
  (kontrol amaçlı, varsayılan kapalı).
- Kolon tablosunda, `changed_columns` (script_parser çıktısı) ile eşleşen
  satırlar renklendirilir: **yeşil** = ADD, **turuncu** (`#ff9500`) = ALTER,
  **kırmızı** = DROP. DROP edilip `TumKolonlar`'da artık bulunmayan kolonlar
  için ayrı bir "siliniyor" notu satırı eklenir.
- ONAY kartlarında gerekçe/red sebebi gösterilmez (zaten yok), sadece
  başlık + kolon tablosu; İADE/HATA kartlarında gerekçe/hata metni
  gösterilir.

## Teknoloji seçimleri ve nedenleri

- **Backend: FastAPI** — async destekli, hafif, tip güvenli (Pydantic) ve
  hızlı geliştirme sağlıyor. Çoklu satırı eşzamanlı (concurrent) modele
  gönderebilmek için async doğal bir gereksinimdi.
- **MSSQL: pyodbc** — ODBC Driver 18 ile bağlanıyor (`Encrypt=yes;
  TrustServerCertificate=yes` eklendi, aksi halde localhost/self-signed
  sertifikalarda bağlantı reddediliyordu). Bağlantı yalnızca `SELECT`
  sorgularını çalıştıracak şekilde kodlandı (`db.py` içinde `_run_select`
  bunu zorunlu kılar).
- **Ortam değişkenleri: python-dotenv** — `.env` dosyası proje kök
  dizininde tutuluyor; backend hangi dizinden başlatılırsa başlatılsın,
  `.env` ve `rules.txt` yolları `config.PROJECT_ROOT` üzerinden mutlak
  olarak çözülüyor (CWD'ye bağımlı değil).
- **Frontend: Sade HTML + CSS + Vanilla JS** — Framework gerektirmeyecek
  kadar basit bir tek-sayfa arayüz; build adımı yok, doğrudan FastAPI
  `StaticFiles` ile servis ediliyor.
- **LLM entegrasyonu: Anthropic Claude API** — Resmi `anthropic` Python
  SDK'sı, `AsyncAnthropic` istemcisi ile. Güvenilir JSON çıktı almak için
  serbest metin ayrıştırma yerine **structured outputs**
  (`output_config.format` + JSON schema) kullanıldı.

## Model provider (sağlayıcı) katmanı — strategy pattern

`backend/providers/base.py` içinde soyut `ModelProvider` sınıfı iki async
metot tanımlar:

- `check_row(row_data, rules_text) -> {"karar": "ONAY"|"IADE", "gerekce": str}`
- `check_term_match(column_name, reference_data) -> {"durum": ..., "terim": ..., "oneriler": [...]}`

`ClaudeProvider` (`claude_provider.py`) bu arayüzü Anthropic API ile
implemente eder. `LocalProvider` (`local_provider.py`) ileride Ollama gibi
bir yerel model için doldurulacak bir iskelet olarak bırakıldı.

### Terim eşleştirme — şu an pasif

`check_term_match` altyapısı hâlâ kodda duruyor ama bu akışta (script
denetimi) kullanılmıyor: `TERM_MATCH_QUERY` bilerek boş/zararsız bırakıldı
(`SELECT TOP 0 ...`), ve `extra` verisinde `TERM_MATCH_COLUMN_KEY`
(`"KolonAdi"`) hiç geçmediği için `term_status` her zaman `null` dönüyor.
İleride kolon bazlı terim eşleştirmesi gerekirse `OnayBekleyenKolonlar`
üzerinden yeniden etkinleştirilebilir.

## Hata yönetimi

- **rules.txt bulunamadı / boş** → `RulesFileNotFoundError` → HTTP 400,
  arayüzde kırmızı hata banner'ında gösterilir.
- **MSSQL bağlantı/sorgu hatası** → `DatabaseError` → HTTP 502.
- **Model API hatası (Claude)** → `ModelProviderError`. İstek düzeyinde
  (örn. API anahtarı eksikse/kredi bittiyse) HTTP 400 döner. Satır
  düzeyinde (örn. tek bir satır için geçici bir API hatası) o satır "HATA"
  kategorisine düşer ve diğer satırların denetimi devam eder.

## Performans

Satırlar `asyncio.gather` ile eşzamanlı işlenir; eşzamanlı model çağrısı
sayısı `config.MAX_CONCURRENT_MODEL_CALLS` (varsayılan 5) ile sınırlanır.
Sistem promptu `cache_control: ephemeral` ile işaretlenerek prompt
caching'den faydalanılır. Audit/arşiv-only script'ler ve `TumKolonlar`
modele hiç gönderilmediği için token maliyeti de azaltılmış oluyor.

## Kullanıcı girişi (auth)

Uygulama artık açık degil -- `DTG.AppUser` tablosunda dogrulanan basit bir
kullanici adi/sifre girisi var:

- **Sifreler**: `bcrypt` ile hash'lenir (`backend/auth.py`), duz metin asla
  saklanmaz/karsilastirilmaz.
- **Oturum**: Starlette'in `SessionMiddleware`'i ile imzali (signed) cookie
  -- `SESSION_SECRET_KEY` (.env) ile imzalanir, 8 saatte duser. JWT/refresh
  token gibi karmasik bir sisteme gerek yok, tek oturum yeterli.
- **Koruma**: `require_auth` dependency'si `/api/run-check`'e (ve ileride
  eklenecek her API endpoint'ine) uygulanir; session yoksa 401 doner.
  Frontend (`app.js`) sayfa yuklenirken `/api/me`'yi kontrol eder, 401
  alirsa otomatik `/login`'e yonlendirir.
- **Kullanici ekleme**: `backend/scripts/create_user.py` -- elle
  calistirilan bir CLI. Web uygulamasi (FastAPI) `AppUser` tablosuna asla
  YAZMAZ, sadece login icin SELECT yapar (`db.py -> fetch_user_by_username`).
  INSERT yetkisi bilerek sadece CLI script'e (`db.py -> get_raw_connection`)
  tanindi -- boylece "web app sadece SELECT calistirir" ilkesi bozulmadi.
- **Migration**: `migrations/001_create_appuser.sql` -- Claude Code
  tarafindan calistirilmadi, kullanici elle calistirdi. DataGov'un ana
  katalog tablolarina (DataSystem/DataSet/DataItem/DataScript/Term) hic
  dokunulmuyor, `AppUser` tamamen bagimsiz yeni bir tablo.

## Klasör yapısı

```
SQLTableRuleCheck/
  backend/
    main.py              FastAPI app, auth + /api/run-check endpoint'leri
    config.py             Sabit SQL sorguları ve ayarlar (DataGov.DTG semasi)
    db.py                 MSSQL baglanti, sorgu calistirma, kolon fetch (2 mod)
    script_parser.py      ScriptText -> ADD/ALTER/DROP kolon cikarimi (regex)
    auth.py                Sifre hash/dogrulama (bcrypt)
    scripts/
      create_user.py      CLI: DTG.AppUser'a kullanici ekler (elle calistirilir)
    providers/
      base.py             Soyut ModelProvider arayuzu
      claude_provider.py  Anthropic Claude API implementasyonu
      local_provider.py   Yerel model (Ollama vb.) icin iskelet
    rules_loader.py       rules.txt'yi her seferinde taze okur
  frontend/
    index.html
    login.html              Giris ekrani
    style.css              Koyu tema
    app.js                 Vanilla JS -- fetch, render, toggle, renklendirme, oturum kontrolu
    login.js                Giris formu
  migrations/
    001_create_appuser.sql  DTG.AppUser DDL (elle calistirilir)
  rules.txt                 Kuveyt Turk BT veri yonetisimi standartlari
  .env.example               Sablon (gercek .env repoya girmez)
  requirements.txt
  README.md
  PROJECT_NOTES.md            (bu dosya)
```
