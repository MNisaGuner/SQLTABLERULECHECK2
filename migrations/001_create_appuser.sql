-- SQLTableRuleCheck uygulamasina giris icin kullanici tablosu.
-- DataGov'un ana katalog tablolarina (DataSystem/DataSet/DataItem/DataScript/
-- Term) DOKUNULMUYOR -- bu tamamen ayri, bagimsiz yeni bir tablo.
--
-- Elle calistirilmasi gerekiyor (Claude Code otomatik calistirmadi).

IF NOT EXISTS (
    SELECT 1 FROM sys.tables AS t
    INNER JOIN sys.schemas AS s ON s.schema_id = t.schema_id
    WHERE t.name = 'AppUser' AND s.name = 'DTG'
)
BEGIN
    CREATE TABLE DataGov.DTG.AppUser
    (
        UserId        INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        Username      VARCHAR(50) COLLATE SQL_Latin1_General_CP1254_CI_AS NOT NULL UNIQUE,
        PasswordHash  VARCHAR(255) NOT NULL,
        IsActive      TINYINT NOT NULL DEFAULT 1,
        CreatedDate   DATETIME NOT NULL DEFAULT GETDATE()
    );
END
GO
