const urlForm = document.querySelector("#urlForm");
const labelForm = document.querySelector("#labelForm");
const urlInput = document.querySelector("#productUrl");
const labelInput = document.querySelector("#labelFile");
const urlButton = document.querySelector("#urlButton");
const labelButton = document.querySelector("#labelButton");
const urlModeButton = document.querySelector("#urlModeButton");
const labelModeButton = document.querySelector("#labelModeButton");
const activeModeTitle = document.querySelector("#activeModeTitle");
const activeModeDescription = document.querySelector("#activeModeDescription");
const fillDemoUrlButton = document.querySelector("#fillDemoUrl");
const clearResultsButton = document.querySelector("#clearResults");
const fileName = document.querySelector("#fileName");
const serviceStatus = document.querySelector("#serviceStatus");
const activityBadge = document.querySelector("#activityBadge");
const activityText = document.querySelector("#activityText");
const sourceValue = document.querySelector("#sourceValue");
const confidenceValue = document.querySelector("#confidenceValue");
const pulseBar = document.querySelector("#pulseBar");
const scoreRing = document.querySelector("#scoreRing");
const scoreValue = document.querySelector("#scoreValue");
const gradeValue = document.querySelector("#gradeValue");
const scoreNote = document.querySelector("#scoreNote");
const naturalRatio = document.querySelector("#naturalRatio");
const syntheticRatio = document.querySelector("#syntheticRatio");
const totalRatio = document.querySelector("#totalRatio");
const resultSource = document.querySelector("#resultSource");
const validityBadge = document.querySelector("#validityBadge");
const compositionList = document.querySelector("#compositionList");
const insightBadge = document.querySelector("#insightBadge");
const insightList = document.querySelector("#insightList");
const historyCount = document.querySelector("#historyCount");
const historyList = document.querySelector("#historyList");
const messagePanel = document.querySelector("#messagePanel");

const MODE_CONTENT = {
  url: {
    title: "URL uzerinden analiz",
    description: "Urun linkini gir, sistem urun sayfasindaki kumas bilgisini cekip kalite skorunu olustursun.",
  },
  label: {
    title: "Etiket fotografi uzerinden analiz",
    description: "Net bir etiket fotografi yukle, OCR metni okuyup confidence ile birlikte kompozisyonu cikarsin.",
  },
};

const historyEntries = [];
let activeMode = "url";

const fabricLabels = {
  pamuk: "Pamuk",
  polyester: "Polyester",
  viskon: "Viskon",
  naylon: "Naylon",
  yun: "Yun",
  ipek: "Ipek",
  keten: "Keten",
  akrilik: "Akrilik",
  elastan: "Elastan",
};

function setMode(mode) {
  activeMode = mode;
  const isUrl = mode === "url";

  urlModeButton.classList.toggle("active", isUrl);
  labelModeButton.classList.toggle("active", !isUrl);
  urlForm.hidden = !isUrl;
  labelForm.hidden = isUrl;
  urlForm.classList.toggle("active", isUrl);
  labelForm.classList.toggle("active", !isUrl);
  activeModeTitle.textContent = MODE_CONTENT[mode].title;
  activeModeDescription.textContent = MODE_CONTENT[mode].description;
  sourceValue.textContent = isUrl ? "URL akisi" : "Etiket OCR";
}

async function checkHealth() {
  try {
    const response = await fetch("/health");
    serviceStatus.textContent = response.ok ? "Backend hazir" : "Backend yanit vermiyor";
  } catch {
    serviceStatus.textContent = "Backend baglantisi yok";
  }
}

function setButtonLoading(button, isLoading, loadingText, idleText) {
  button.disabled = isLoading;
  button.textContent = isLoading ? loadingText : idleText;
}

function showMessage(message, tone = "error") {
  messagePanel.hidden = false;
  messagePanel.className = `message-panel ${tone}`;
  messagePanel.textContent = message;
}

function clearMessage() {
  messagePanel.hidden = true;
  messagePanel.textContent = "";
}

function setActivity(state, message, source = "Bekleniyor", confidence = "-") {
  activityBadge.textContent = state;
  activityText.textContent = message;
  sourceValue.textContent = source;
  confidenceValue.textContent = confidence;
  pulseBar.parentElement.classList.toggle("loading", state === "Analiz suruyor");
}

function resetResults() {
  scoreRing.style.setProperty("--score", "0");
  scoreValue.textContent = "0";
  gradeValue.textContent = "Bekleniyor";
  scoreNote.textContent = "Bir urun linki gir veya etiket fotografi yukle; sonuc burada gorunur.";
  naturalRatio.textContent = "0%";
  syntheticRatio.textContent = "0%";
  totalRatio.textContent = "0%";
  resultSource.textContent = "-";
  validityBadge.textContent = "Sonuc yok";
  validityBadge.style.color = "var(--muted)";
  insightBadge.textContent = "Bekleniyor";
  compositionList.innerHTML = '<p class="empty-state">Analiz sonucu geldiginde materyal oranlari burada listelenir.</p>';
  insightList.innerHTML = '<p class="empty-state">Sonuc geldiginde kalite skorunun hangi sinyallerle olustugu burada ozetlenir.</p>';
  clearMessage();
  setActivity("Hazir", "Analiz baslatildiginda bu alan islenen kaynagi ve son durumu gosterir.", activeMode === "url" ? "URL akisi" : "Etiket OCR");
}

function renderComposition(composition) {
  compositionList.innerHTML = "";

  if (!composition.length) {
    compositionList.innerHTML = '<p class="empty-state">Kumas bilesimi bulunamadi.</p>';
    return;
  }

  for (const item of composition) {
    const ratio = Number(item.ratio || 0);
    const row = document.createElement("div");
    row.className = "composition-item";
    row.innerHTML = `
      <span class="fabric-name">${fabricLabels[item.fabric] || item.fabric}</span>
      <div class="bar" aria-hidden="true"><span style="--ratio: ${Math.min(ratio, 100)}%"></span></div>
      <span class="ratio">${ratio}%</span>
    `;
    compositionList.appendChild(row);
  }
}

function renderInsights(score, fabric, confidence, source) {
  const natural = Number(score.natural_ratio || 0);
  const synthetic = Number(score.synthetic_ratio || 0);
  const qualityScore = Number(score.quality_score || 0);
  const topFabric = Array.isArray(fabric.composition) ? fabric.composition[0] : null;
  const items = [];

  items.push({
    title: "Skor mantigi",
    text: `Agirlikli kalite skoru ${qualityScore} olarak hesaplandi ve not ${score.grade || "F"} seviyesine yerlesti.`,
  });

  if (topFabric) {
    items.push({
      title: "Baskin materyal",
      text: `${fabricLabels[topFabric.fabric] || topFabric.fabric} %${topFabric.ratio} ile kompozisyondaki en yuksek paya sahip.`,
    });
  }

  items.push({
    title: "Kompozisyon dengesi",
    text: `Dogal oran %${natural}, sentetik oran %${synthetic}. Bu dagilim kalite yorumunu dogrudan etkiliyor.`,
  });

  items.push({
    title: "Kaynak guveni",
    text: source === "Etiket OCR"
      ? confidence > 0
        ? `OCR confidence yaklasik %${Math.round(confidence)} oldugu icin sonuc buna gore yorumlandi.`
        : "OCR confidence bilgisi gelmedi; sonuc kompozisyon parse edilerek verildi."
      : "Sonuc urun sayfasi iceriginden parse edildi.",
  });

  insightList.innerHTML = "";
  for (const item of items) {
    const row = document.createElement("article");
    row.className = "insight-item";
    row.innerHTML = `<strong>${item.title}</strong><p>${item.text}</p>`;
    insightList.appendChild(row);
  }
  insightBadge.textContent = fabric.is_valid ? "Aciklanmis sonuc" : "Kontrol onerilir";
}

function renderHistory() {
  historyCount.textContent = `${historyEntries.length} kayit`;
  historyList.innerHTML = "";

  if (!historyEntries.length) {
    historyList.innerHTML = '<p class="empty-state">Henuz analiz yapilmadi.</p>';
    return;
  }

  for (const item of historyEntries) {
    const row = document.createElement("article");
    row.className = "history-item";
    row.innerHTML = `
      <div>
        <strong>${item.title}</strong>
        <div class="history-meta">
          <span>${item.source}</span>
          <span>${item.grade}</span>
          <span>Toplam %${item.total}</span>
        </div>
      </div>
      <div class="history-score">${item.score}</div>
    `;
    historyList.appendChild(row);
  }
}

function pushHistory(data, sourceLabel) {
  const score = data.score || {};
  const fabric = data.fabric || {};
  const leadFabric = Array.isArray(fabric.composition) && fabric.composition.length
    ? fabricLabels[fabric.composition[0].fabric] || fabric.composition[0].fabric
    : "Kompozisyon yok";

  historyEntries.unshift({
    title: leadFabric,
    source: sourceLabel,
    grade: `Not ${score.grade || "F"}`,
    total: fabric.total_ratio || 0,
    score: score.quality_score || 0,
  });

  historyEntries.splice(4);
  renderHistory();
}

function renderResult(data, sourceLabel) {
  const score = data.score || {};
  const fabric = data.fabric || {};
  const ocr = data.ocr || {};
  const qualityScore = Number(score.quality_score || 0);
  const confidence = Number(ocr.avg_confidence || 0);

  scoreRing.style.setProperty("--score", String(qualityScore));
  scoreValue.textContent = String(qualityScore);
  gradeValue.textContent = `Not ${score.grade || "F"}`;
  scoreNote.textContent = fabric.is_valid
    ? confidence > 0
      ? `Kumas oranlari OCR ile okundu. OCR guveni: ${Math.round(confidence)}%.`
      : "Kumas oranlari dengeli okundu ve kalite skoru hesaplandi."
    : data.advice || "Kumas oranlari dogrulanamadi.";

  naturalRatio.textContent = `${score.natural_ratio || 0}%`;
  syntheticRatio.textContent = `${score.synthetic_ratio || 0}%`;
  totalRatio.textContent = `${fabric.total_ratio || 0}%`;
  resultSource.textContent = sourceLabel;
  validityBadge.textContent = fabric.is_valid ? "Gecerli kompozisyon" : "Kontrol gerekli";
  validityBadge.style.color = fabric.is_valid ? "var(--accent-strong)" : "var(--warn)";

  renderComposition(fabric.composition || []);
  renderInsights(score, fabric, confidence, sourceLabel);
  setActivity(
    fabric.is_valid ? "Tamamlandi" : "Kontrol gerekli",
    fabric.is_valid
      ? `${sourceLabel} akisi tamamlandi. Kalite skoru ve kompozisyon guncellendi.`
      : `${sourceLabel} akisi sonuc verdi ancak kompozisyon kontrol gerektiriyor.`,
    sourceLabel,
    confidence > 0 ? `%${Math.round(confidence)}` : sourceLabel === "Etiket OCR" ? "Dusuk/veri yok" : "Sayfa parse",
  );
  pushHistory(data, sourceLabel);

  const guidance = data.advice || fabric.warning;

  if ((!fabric.is_valid || data.advice) && guidance) {
    showMessage(guidance, "warning");
  } else {
    clearMessage();
  }
}

function renderError(payload) {
  const error = payload.error || {};
  const message = typeof error === "string" ? error : error.message || "Analiz tamamlanamadi.";
  setActivity("Hata", message, activeMode === "url" ? "URL akisi" : "Etiket OCR");
  showMessage(message);
}

urlModeButton.addEventListener("click", () => setMode("url"));
labelModeButton.addEventListener("click", () => setMode("label"));

fillDemoUrlButton.addEventListener("click", () => {
  setMode("url");
  urlInput.value = "https://www.koton.com/uzun-kollu-bisiklet-yaka-viskon-triko-kazak-sari-4166045-2/";
  urlInput.focus();
});

clearResultsButton.addEventListener("click", () => resetResults());

urlForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearMessage();
  setActivity("Analiz suruyor", "URL uzerinden urun sayfasi okunuyor ve kumas verisi parse ediliyor.", "URL akisi", "Sayfa okunuyor");
  setButtonLoading(urlButton, true, "Analiz ediliyor", "URL Analiz Et");

  try {
    const response = await fetch("/analyze/url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: urlInput.value.trim() }),
    });
    const payload = await response.json();

    if (!response.ok || payload.success === false) {
      renderError(payload);
      return;
    }

    renderResult(payload, "URL akisi");
  } catch {
    setActivity("Hata", "Backend ile baglanti kurulamadi.", "URL akisi");
    showMessage("Backend ile baglanti kurulamadi.");
  } finally {
    setButtonLoading(urlButton, false, "Analiz ediliyor", "URL Analiz Et");
  }
});

labelInput.addEventListener("change", () => {
  fileName.textContent = labelInput.files[0]?.name || "Dosya secilmedi";
});

labelForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearMessage();

  if (!labelInput.files.length) {
    showMessage("Analiz icin bir etiket fotografi sec.");
    return;
  }

  const formData = new FormData();
  formData.append("file", labelInput.files[0]);
  setActivity("Analiz suruyor", "Etiket fotografisi OCR ile okunuyor ve kumas oranlari eslestiriliyor.", "Etiket OCR", "OCR isleniyor");
  setButtonLoading(labelButton, true, "Analiz ediliyor", "Gorsel Analiz Et");

  try {
    const response = await fetch("/analyze/label", {
      method: "POST",
      body: formData,
    });
    const payload = await response.json();

    if (!response.ok || payload.success === false) {
      renderError(payload);
      return;
    }

    renderResult(payload, "Etiket OCR");
  } catch {
    setActivity("Hata", "Backend ile baglanti kurulamadi.", "Etiket OCR");
    showMessage("Backend ile baglanti kurulamadi.");
  } finally {
    setButtonLoading(labelButton, false, "Analiz ediliyor", "Gorsel Analiz Et");
  }
});

checkHealth();
setMode("url");
resetResults();
renderHistory();
