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

   Terim önerisi (bkz. madde 5) için `TERM_SUGGESTION_THRESHOLD` (varsayılan
   `70`, fuzzy eşleşme için minimum skor) ve `TERM_CACHE_TTL_SECONDS`
   (varsayılan `300`, terim sözlüğünün bellek içi cache süresi) `.env`
   üzerinden isteğe bağlı ayarlanabilir — varsayılanlar çoğu durumda yeterli.

5. **rules.txt** — Proje kök dizinindeki `rules.txt` dosyasını kendi
   kurallarınızla doldurun. Bu dosya her istek anında taze okunur, sunucuyu
   yeniden başlatmanıza gerek yoktur.

6. **Giriş ekranı (kullanıcı tablosu)** — Uygulama, `DTG.AppUser` tablosunda
   doğrulanan bir kullanıcı adı/şifre girişi ister:

   - `.env` dosyasına rastgele, uzun bir `SESSION_SECRET_KEY` ekleyin
     (örn. `python -c "import secrets; print(secrets.token_hex(32))"`).
     Bu değer oturum çerezlerini imzalar; değişirse tüm oturumlar düşer.
   - [migrations/001_create_appuser.sql](./migrations/001_create_appuser.sql)
     dosyasını SQL Server'da **elle** çalıştırın (uygulama bunu otomatik
     çalıştırmaz).
   - Yeni kullanıcı eklemek için (`backend/` dizininden):
     ```bash
     python scripts/create_user.py <kullanici_adi>
     ```
     Şifre terminalde gizli olarak sorulur, `bcrypt` ile hash'lenip tabloya
     eklenir.

## Çalıştırma

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Tarayıcıda [http://localhost:8000](http://localhost:8000) adresini açın —
önce `/login` ekranına yönlendirilirsiniz, oluşturduğunuz kullanıcı ile
giriş yapmanız gerekir.

## Kullanım

1. Kullanıcı adı/şifre ile giriş yapın (sağ üstteki "Çıkış Yap" ile oturumu
   kapatabilirsiniz).
2. Arayüzden bir model sağlayıcı seçin (şu an yalnızca "Claude API" aktif).
3. "Sorguyu Çalıştır ve Denetle" butonuna basın.
4. Sonuçlar ONAY / İADE gruplarında listelenir. Her kartın başlığı
   (Sunucu/Veritabanı/Şema/Tablo Adı) tıklanabilir — tıklanınca altında
   tablonun tüm kolonları (tip, nullable, identity, PK, açıklama, iş
   terimi) bir tabloda açılır; script'in dokunduğu kolonlar
   yeşil(ADD)/turuncu(ALTER)/kırmızı(DROP) renklenir. Ayrı bir "Script'i
   göster" linki ham DDL metnini gösterir.
5. İş Terimi hücresinde bir kolon hiç terimle eşleştirilmemişse (`TermId`
   boş) ve bir öneri bulunabiliyorsa küçük bir ℹ️ ikonu görünür; üzerine
   gelince terim adı, eşleşme tipi (geçmiş eşleşme/birebir/fuzzy) ve
   (fuzzy ise) skor gösteren bir tooltip açılır. Bu tamamen bilgilendirme
   amaçlıdır, ONAY/İADE kararını etkilemez.
6. "Kopyala" butonu, Dataone'a yapıştırılmaya hazır bir not üretir: İADE/HATA
   kartlarında gerekçe + (varsa) tablodaki eşleşmemiş kolonlar için terim
   önerileri; ONAY kartlarında sadece terim önerileri (varsa). Hiç önerilecek
   bir şey yoksa buton pasiftir.
7. Sadece incelenen ana tabloyu hedefleyen script'ler kural denetiminden
   geçirilir; audit/arşiv companion script'leri (aynı mantıksal değişikliğin
   parçası ama farklı bir fiziksel tabloyu hedefleyen script'ler) otomatik
   onaylanır ve listede ayrı bir kalem olarak görünmez.

## Proje yapısı ve tasarım kararları

Detaylar için [PROJECT_NOTES.md](./PROJECT_NOTES.md) dosyasına bakın.

## Güvenlik notu

`.env` dosyanızı asla paylaşmayın veya repoya eklemeyin (`SESSION_SECRET_KEY`
dahil — değişirse tüm oturumlar düşer, ama yine de gizli tutulmalı).

Web uygulamasının kendisi (FastAPI endpoint'leri) veritabanına yalnızca
`SELECT` sorguları çalıştırır. Tek istisna, `backend/scripts/create_user.py`
— bilerek ayrı tutulan, elle çalıştırılan bir CLI script'i; `DTG.AppUser`
tablosuna kullanıcı eklemek için INSERT yapar, web akışının bir parçası
değildir.
