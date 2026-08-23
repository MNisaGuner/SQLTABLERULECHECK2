# SQL Table Rule Check

MS SQL Server'da çalıştırılan bir sorgunun her satırını, `rules.txt` içindeki
serbest metin kurallarına göre bir dil modeline (LLM) gönderip ONAY/İADE
kararı verdiren, sonuçları koyu temalı bir web arayüzünde listeleyen araç.

## Kurulum

1. **Python bağımlılıkları**

   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **ODBC Driver (macOS)** — MSSQL'e bağlanmak için `unixODBC` ve Microsoft'un
   ODBC Driver 18'i gerekir. Bu makinede Homebrew ile şu şekilde kuruldu:

   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   # Homebrew'i PATH'e eklemek icin (Apple Silicon):
   echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
   eval "$(/opt/homebrew/bin/brew shellenv)"

   brew install unixodbc
   brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
   brew trust microsoft/mssql-release   # gerekirse
   brew install msodbcsql18 mssql-tools18
   ```

   `pyodbc` bu unixODBC'ye karşı derlenir; kurulum sırasında sorun yaşarsanız:

   ```bash
   LDFLAGS="-L$(brew --prefix unixodbc)/lib" CPPFLAGS="-I$(brew --prefix unixodbc)/include" pip install pyodbc
   ```

3. **.env dosyası** — `.env.example` dosyasını kopyalayıp `.env` olarak
   kaydedin ve gerçek değerlerle doldurun:

   ```bash
   cp .env.example .env
   ```

   `.env` dosyası **gerçek API anahtarı ve veritabanı bilgilerinizi**
   içerecektir — bu dosya `.gitignore` içinde olduğu için repoya girmez,
   ama yine de dikkatli olun.

   Doldurmanız gerekenler:
   - `DB_SERVER`, `DB_DATABASE`, `DB_USER`, `DB_PASSWORD`, `DB_DRIVER`
   - `ANTHROPIC_API_KEY` (Claude API anahtarınız)
   - `ANTHROPIC_MODEL` (varsayılan: `claude-opus-5`)

4. **SQL sorgularını düzenleyin** — `backend/config.py` içindeki
   `MAIN_QUERY`, `COLUMN_QUERY_TEMPLATE` sabitlerini kendi tablo/görünüm
   adlarınıza göre güncelleyin. `MAIN_QUERY` en az `id`, `LocationName`,
   `DatabaseName`, `SchemaName`, `TableName` kolonlarını döndürmelidir;
   bunların dışındaki tüm kolonlar otomatik olarak "ek veri" sayılıp modele
   gönderilir. Şu anki sorgu, DataGov (DataOne) kataloğunun `DTG` şemasına
   (`DataSystem`/`DataSet`/`DataScript`/`DataItem`) göre yazılmıştır —
   detaylar için [PROJECT_NOTES.md](./PROJECT_NOTES.md).

   `COLUMN_STATUS_PENDING` sabiti (varsayılan `5`), hangi `DataItem.StatusId`
   değerinin "onay bekliyor" anlamına geldiğini belirtir; modele giden kolon
   bağlamı (`OnayBekleyenKolonlar`) bu filtreyle sınırlanır.

5. **rules.txt** — Proje kök dizinindeki `rules.txt` dosyasını kendi
   kurallarınızla doldurun. Bu dosya her istek anında taze okunur, sunucuyu
   yeniden başlatmanıza gerek yoktur.

## Çalıştırma

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Tarayıcıda [http://localhost:8000](http://localhost:8000) adresini açın.

## Kullanım

1. Arayüzden bir model sağlayıcı seçin (şu an yalnızca "Claude API" aktif).
2. "Sorguyu Çalıştır ve Denetle" butonuna basın.
3. Sonuçlar ONAY / İADE gruplarında listelenir. Her kartın başlığı
   (Sunucu/Veritabanı/Şema/Tablo Adı) tıklanabilir — tıklanınca altında
   tablonun tüm kolonları (tip, nullable, identity, PK, açıklama, iş
   terimi) bir tabloda açılır; script'in dokunduğu kolonlar
   yeşil(ADD)/turuncu(ALTER)/kırmızı(DROP) renklenir. Ayrı bir "Script'i
   göster" linki ham DDL metnini gösterir. "Kopyala" butonu
   `id-LocationName-DatabaseName-SchemaName-TableName` formatındaki metni
   panoya kopyalar.
4. Sadece incelenen ana tabloyu hedefleyen script'ler kural denetiminden
   geçirilir; audit/arşiv companion script'leri (aynı mantıksal değişikliğin
   parçası ama farklı bir fiziksel tabloyu hedefleyen script'ler) otomatik
   onaylanır ve listede ayrı bir kalem olarak görünmez.

## Proje yapısı ve tasarım kararları

Detaylar için [PROJECT_NOTES.md](./PROJECT_NOTES.md) dosyasına bakın.

## Güvenlik notu

`.env` dosyanızı asla paylaşmayın veya repoya eklemeyin. Veritabanı
bağlantısı yalnızca `SELECT` sorgularını çalıştıracak şekilde kodlanmıştır.
