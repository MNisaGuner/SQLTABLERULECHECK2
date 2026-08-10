"""
Sabit ayarlar ve SQL sorguları.

Bu dosyayı ihtiyaca göre düzenleyin:
- MAIN_QUERY: Denetlenecek satırları döndüren ana sorgu.
- TERM_MATCH_QUERY: Kolon adı -> iş terimi eşleşmelerini içeren referans veri sorgusu.
- REQUIRED_COLUMNS: MAIN_QUERY'nin döndürmesi ZORUNLU olan kolonlar
  (id, LocationName, SchemaName, TableName). Bunların dışındaki tüm kolonlar
  "ek veri" olarak kabul edilip modele gönderilir.
- TERM_MATCH_COLUMN_KEY: MAIN_QUERY sonucundaki ek kolonlardan hangisinin,
  terim eşleştirmesi yapılacak "kolon adı" değerini taşıdığını belirtir.
  Kendi şemanıza göre bu değeri değiştirin (örn. "KolonAdi", "ColumnName" vb.).
  Bu kolon satırda yoksa veya boşsa, o satır için terim eşleştirmesi atlanır.
"""

import os

# Proje kok dizini (backend/'in bir ust dizini) - CWD'den bagimsiz yol cozumlemesi icin.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- Zorunlu kolonlar (ana sorgudan dönmesi gereken) ---
REQUIRED_COLUMNS = ["id", "LocationName", "DatabaseName", "SchemaName", "TableName"]

# --- Terim eşleştirmesi yapılacak kolon adının, ek veri içindeki anahtarı ---
TERM_MATCH_COLUMN_KEY = os.getenv("TERM_MATCH_COLUMN_KEY", "KolonAdi")

# --- Ana denetim sorgusu ---
# DataScript.ScriptText = onay bekleyen (StatusId=0) DB değişiklik script'i.
# Hiyerarşi: T1=Sunucu, T2=Veritabanı, T3=Şema (DataSystem ağacı),
# T4 (DataSet)=Tablo/nesne adı. DataSetId, db.py -> fetch_columns_for_datasets()
# ile o tabloya ait kolon listesini (DataItem+Term) cekmek icin kullanilir,
# sonra "Kolonlar" alani olarak satira eklenip DataSetId silinir. ScriptText ve
# Kolonlar hem ekranda gosteriliyor hem "ek veri" olarak modele gonderiliyor.
MAIN_QUERY = """
SELECT
    T7.DataScriptId  AS id,
    T1.Name           AS LocationName,
    T2.Name           AS DatabaseName,
    T3.Name           AS SchemaName,
    T4.Name           AS TableName,
    T4.DataSetId      AS DataSetId,
    T4.Description    AS TableDescription,
    T7.ScriptText     AS ScriptText
FROM DataGov.DTG.DataSystem T1 WITH (NOLOCK)
LEFT OUTER JOIN DataGov.DTG.DataSystem T2 WITH (NOLOCK) ON T1.DataSystemId = T2.ParentId
LEFT OUTER JOIN DataGov.DTG.DataSystem T3 WITH (NOLOCK) ON T2.DataSystemId = T3.ParentId
LEFT OUTER JOIN DataGov.DTG.DataSet T4 WITH (NOLOCK) ON T3.DataSystemId = T4.DataSystemId
LEFT OUTER JOIN DataGov.DTG.DataScript T7 WITH (NOLOCK) ON T4.DataSetId = T7.DataSetId
WHERE T7.StatusId = 0
"""

# --- Kolon detay sorgusu (DataItem + Term) ---
# fetch_columns_for_datasets() tarafindan, "WHERE di.DataSetId IN (...)" seklinde
# parametrik olarak calistirilir. Identity/PrimaryKey formati kullanicinin verdigi
# referans sorguyla birebir aynidir (CASE ile "seed,increment" / "PK" / "-").
COLUMN_QUERY_TEMPLATE = """
SELECT
    di.DataSetId AS DataSetId,
    di.Name AS ColumnName,
    di.Description AS ColumnDescription,
    di.DataType AS PhysicalType,
    CASE
        WHEN di.IdentitySeed IS NOT NULL AND di.IdentityIncrement IS NOT NULL
        THEN CONCAT(di.IdentitySeed, ',', di.IdentityIncrement)
        ELSE '-'
    END AS IdentityInfo,
    CASE WHEN di.IsPrimaryKey = 1 THEN 'PK' ELSE '-' END AS PrimaryKeyInfo,
    t.Name AS TermName
FROM DataGov.DTG.DataItem di WITH (NOLOCK)
LEFT OUTER JOIN DataGov.DTG.Term t WITH (NOLOCK) ON di.TermId = t.TermId
WHERE di.DataSetId IN ({placeholders})
ORDER BY di.DataSetId, di.ColumnOrder
"""

# --- Referans terim eşleştirme verisi sorgusu ---
# Bu akışta (script denetimi) DataItem/Term eşleştirmesi kullanılmıyor
# ("KolonAdi" alanı ek veride yer almıyor), bu yüzden bos/zararsiz birakildi.
TERM_MATCH_QUERY = """
SELECT TOP 0
    CAST(NULL AS varchar(200)) AS KolonAdi,
    CAST(NULL AS varchar(200)) AS TerimAdi,
    CAST(NULL AS varchar(200)) AS SchemaName,
    CAST(NULL AS varchar(200)) AS TableName
"""

# --- Diğer ayarlar ---
RULES_FILE_PATH = os.getenv("RULES_FILE_PATH", os.path.join(PROJECT_ROOT, "rules.txt"))

# Modele eşzamanlı (concurrent) gönderilecek maksimum istek sayısı
MAX_CONCURRENT_MODEL_CALLS = int(os.getenv("MAX_CONCURRENT_MODEL_CALLS", "5"))
