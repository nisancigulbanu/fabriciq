const urlForm = document.querySelector("#urlForm");
const labelForm = document.querySelector("#labelForm");
const urlInput = document.querySelector("#productUrl");
const labelInput = document.querySelector("#labelFile");
const urlButton = document.querySelector("#urlButton");
const labelButton = document.querySelector("#labelButton");
const fileName = document.querySelector("#fileName");
const serviceStatus = document.querySelector("#serviceStatus");
const scoreRing = document.querySelector("#scoreRing");
const scoreValue = document.querySelector("#scoreValue");
const gradeValue = document.querySelector("#gradeValue");
const scoreNote = document.querySelector("#scoreNote");
const naturalRatio = document.querySelector("#naturalRatio");
const syntheticRatio = document.querySelector("#syntheticRatio");
const totalRatio = document.querySelector("#totalRatio");
const validityBadge = document.querySelector("#validityBadge");
const compositionList = document.querySelector("#compositionList");
const messagePanel = document.querySelector("#messagePanel");

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

function renderResult(data) {
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
    : fabric.warning || "Kumas oranlari dogrulanamadi.";

  naturalRatio.textContent = `${score.natural_ratio || 0}%`;
  syntheticRatio.textContent = `${score.synthetic_ratio || 0}%`;
  totalRatio.textContent = `${fabric.total_ratio || 0}%`;
  validityBadge.textContent = fabric.is_valid ? "Gecerli kompozisyon" : "Kontrol gerekli";
  validityBadge.style.color = fabric.is_valid ? "var(--accent-strong)" : "var(--warn)";

  renderComposition(fabric.composition || []);

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
  showMessage(message);
}

urlForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearMessage();
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

    renderResult(payload);
  } catch {
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

    renderResult(payload);
  } catch {
    showMessage("Backend ile baglanti kurulamadi.");
  } finally {
    setButtonLoading(labelButton, false, "Analiz ediliyor", "Gorsel Analiz Et");
  }
});

checkHealth();
