const runButton = document.getElementById("run-button");
const providerSelect = document.getElementById("provider-select");
const loadingIndicator = document.getElementById("loading-indicator");
const errorBanner = document.getElementById("error-banner");
const summarySection = document.getElementById("summary");
const summaryOnay = document.getElementById("summary-onay");
const summaryIade = document.getElementById("summary-iade");
const summaryHataWrap = document.getElementById("summary-hata-wrap");
const summaryHata = document.getElementById("summary-hata");
const resultsSection = document.getElementById("results");
const onayList = document.getElementById("onay-list");
const iadeList = document.getElementById("iade-list");
const hataGroup = document.getElementById("hata-group");
const hataList = document.getElementById("hata-list");

function showError(message) {
  errorBanner.textContent = message;
  errorBanner.classList.remove("hidden");
}

function hideError() {
  errorBanner.classList.add("hidden");
  errorBanner.textContent = "";
}

function setLoading(isLoading) {
  runButton.disabled = isLoading;
  loadingIndicator.classList.toggle("hidden", !isLoading);
}

function termStatusMarkup(termStatus) {
  if (!termStatus) return "";
  if (termStatus.durum === "eslesti") {
    return `<div class="row-term term-ok">Terim: ${escapeHtml(termStatus.terim)} ✓</div>`;
  }
  if (termStatus.durum === "eslesmedi") {
    const oneriler = (termStatus.oneriler || []).join(", ");
    return `<div class="row-term term-warn">Terim eşleşmedi. Öneriler: ${escapeHtml(oneriler || "-")}</div>`;
  }
  if (termStatus.durum === "hata") {
    return `<div class="row-term term-warn">Terim denetimi hatası: ${escapeHtml(termStatus.hata || "")}</div>`;
  }
  return "";
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

const GEREKCE_LABEL = { IADE: "İade sebebi", HATA: "Hata" };
const CHANGE_ROW_CLASS = { ADD: "col-added", ALTER: "col-altered", DROP: "col-dropped" };

function columnsTableMarkup(columns, changedColumns) {
  const changeMap = new Map(
    (changedColumns || []).map((c) => [(c.column || "").toLowerCase(), c.change_type])
  );
  const existingNames = new Set((columns || []).map((c) => (c.KolonAdi || "").toLowerCase()));

  if ((!columns || columns.length === 0) && (!changedColumns || changedColumns.length === 0)) {
    return '<div class="row-empty">Kolon bilgisi yok.</div>';
  }

  const rows = (columns || [])
    .map((c) => {
      const rowClass = CHANGE_ROW_CLASS[changeMap.get((c.KolonAdi || "").toLowerCase())] || "";
      return `
        <tr class="${rowClass}">
          <td>${escapeHtml(c.KolonAdi || "-")}</td>
          <td>${escapeHtml(c.VeriTipi || "-")}</td>
          <td class="col-center">${escapeHtml(c.BosBirakilabilir || "-")}</td>
          <td class="col-center">${escapeHtml(c.Identity || "-")}</td>
          <td class="col-center">${escapeHtml(c.BirincilAnahtar || "-")}</td>
          <td>${escapeHtml(c.Aciklama || "-")}</td>
          <td>${escapeHtml(c.IsTerimi || "-")}</td>
        </tr>`;
    })
    .join("");

  const droppedRows = (changedColumns || [])
    .filter((c) => c.change_type === "DROP" && !existingNames.has((c.column || "").toLowerCase()))
    .map(
      (c) => `
        <tr class="col-dropped">
          <td>${escapeHtml(c.column)}</td>
          <td colspan="6"><em>Script'te siliniyor (DROP COLUMN) — tabloda artık bulunmuyor</em></td>
        </tr>`
    )
    .join("");

  return `
    <table class="col-table">
      <thead>
        <tr>
          <th>Kolon Adı</th>
          <th>Fiziksel Veri Tipi</th>
          <th class="col-center">Boş Bırakılabilir</th>
          <th class="col-center">Identity</th>
          <th class="col-center">Birincil Anahtar</th>
          <th>Kolon Açıklaması</th>
          <th>İş Terimi</th>
        </tr>
      </thead>
      <tbody>${rows}${droppedRows}</tbody>
    </table>
  `;
}

function buildRowElement(row) {
  const wrapper = document.createElement("div");
  wrapper.className = "row-item";

  const gerekceText = row.karar === "HATA" ? row.hata : row.gerekce;
  const gerekceLabel = GEREKCE_LABEL[row.karar];
  const suggestedTerm =
    row.term_status && row.term_status.durum === "eslesmedi" && row.term_status.oneriler?.length
      ? row.term_status.oneriler[0]
      : null;

  wrapper.innerHTML = `
    <div class="row-header">
      <div class="row-fields">
        <div class="row-field">
          <span class="row-field-label">Sunucu</span>
          <span class="row-field-value">${escapeHtml(row.LocationName || "-")}</span>
        </div>
        <div class="row-field">
          <span class="row-field-label">Veritabanı</span>
          <span class="row-field-value">${escapeHtml(row.DatabaseName || "-")}</span>
        </div>
        <div class="row-field">
          <span class="row-field-label">Şema</span>
          <span class="row-field-value">${escapeHtml(row.SchemaName || "-")}</span>
        </div>
        <div class="row-field">
          <span class="row-field-label">Tablo Adı</span>
          <span class="row-field-value">${escapeHtml(row.TableName || "-")}</span>
          <span class="row-field-sub">Tablo Açıklaması: ${escapeHtml(row.table_description || "-")}</span>
        </div>
        <span class="row-toggle-hint">Kolonları göster ▾</span>
        ${row.script_text ? '<span class="row-script-toggle-hint">Script\'i göster ▾</span>' : ""}
      </div>
      <div class="row-actions">
        <button class="copy-btn" data-copy="${escapeHtml(row.label)}">Kopyala</button>
        ${suggestedTerm ? `<button class="copy-btn" data-copy="${escapeHtml(suggestedTerm)}">Terimi Kopyala</button>` : ""}
      </div>
    </div>
    ${gerekceLabel ? `<div class="row-gerekce"><span class="row-gerekce-label">${escapeHtml(gerekceLabel)}:</span> ${escapeHtml(gerekceText || "-")}</div>` : ""}
    ${termStatusMarkup(row.term_status)}
    <div class="row-columns hidden">${columnsTableMarkup(row.columns, row.changed_columns)}</div>
    ${row.script_text ? `<div class="row-script hidden"><pre>${escapeHtml(row.script_text)}</pre></div>` : ""}
  `;

  const header = wrapper.querySelector(".row-header");
  const columnsPanel = wrapper.querySelector(".row-columns");
  const toggleHint = wrapper.querySelector(".row-toggle-hint");
  header.addEventListener("click", () => {
    const isOpen = columnsPanel.classList.toggle("hidden") === false;
    toggleHint.textContent = isOpen ? "Kolonları gizle ▴" : "Kolonları göster ▾";
  });

  const scriptToggleHint = wrapper.querySelector(".row-script-toggle-hint");
  const scriptPanel = wrapper.querySelector(".row-script");
  if (scriptToggleHint && scriptPanel) {
    scriptToggleHint.addEventListener("click", (event) => {
      event.stopPropagation();
      const isOpen = scriptPanel.classList.toggle("hidden") === false;
      scriptToggleHint.textContent = isOpen ? "Script'i gizle ▴" : "Script'i göster ▾";
    });
  }

  wrapper.querySelectorAll(".copy-btn").forEach((btn) => {
    btn.addEventListener("click", async (event) => {
      event.stopPropagation();
      try {
        await navigator.clipboard.writeText(btn.dataset.copy);
        btn.classList.add("copied");
        const original = btn.textContent;
        btn.textContent = "Kopyalandı";
        setTimeout(() => {
          btn.classList.remove("copied");
          btn.textContent = original;
        }, 1200);
      } catch (err) {
        showError("Panoya kopyalama başarısız oldu: " + err.message);
      }
    });
  });

  return wrapper;
}

function renderResults(data) {
  summaryOnay.textContent = data.summary.onay;
  summaryIade.textContent = data.summary.iade;
  summaryHata.textContent = data.summary.hata || 0;
  summaryHataWrap.classList.toggle("hidden", !data.summary.hata);
  summarySection.classList.remove("hidden");

  onayList.innerHTML = "";
  iadeList.innerHTML = "";
  hataList.innerHTML = "";

  const onayRows = data.results.filter((r) => r.karar === "ONAY");
  const iadeRows = data.results.filter((r) => r.karar === "IADE");
  const hataRows = data.results.filter((r) => r.karar === "HATA");

  if (onayRows.length === 0) {
    onayList.innerHTML = '<div class="row-empty">Onaylanan kayıt yok.</div>';
  } else {
    onayRows.forEach((r) => onayList.appendChild(buildRowElement(r)));
  }

  if (iadeRows.length === 0) {
    iadeList.innerHTML = '<div class="row-empty">İade edilen kayıt yok.</div>';
  } else {
    iadeRows.forEach((r) => iadeList.appendChild(buildRowElement(r)));
  }

  hataGroup.classList.toggle("hidden", hataRows.length === 0);
  hataRows.forEach((r) => hataList.appendChild(buildRowElement(r)));

  resultsSection.classList.remove("hidden");
}

async function runCheck() {
  hideError();
  setLoading(true);
  resultsSection.classList.add("hidden");
  summarySection.classList.add("hidden");

  try {
    const response = await fetch("/api/run-check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: providerSelect.value }),
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "Bilinmeyen bir hata oluştu.");
    }

    renderResults(data);
  } catch (err) {
    showError(err.message);
  } finally {
    setLoading(false);
  }
}

runButton.addEventListener("click", runCheck);
