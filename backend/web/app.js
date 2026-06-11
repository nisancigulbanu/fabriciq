const scrollSequence = document.querySelector("#scrollSequence");
const sequenceCanvas = document.querySelector("#sequenceCanvas");
const sequenceCopy = document.querySelector(".sequence-copy");
const sequenceProgress = document.querySelector("#sequenceProgress");
const languageButtons = document.querySelectorAll("[data-lang]");

const urlModeButton = document.querySelector("#urlModeButton");
const labelModeButton = document.querySelector("#labelModeButton");
const urlForm = document.querySelector("#urlForm");
const labelForm = document.querySelector("#labelForm");
const urlInput = document.querySelector("#productUrl");
const labelInput = document.querySelector("#labelFile");
const urlButton = document.querySelector("#urlButton");
const labelButton = document.querySelector("#labelButton");
const fileName = document.querySelector("#fileName");

const serviceStatus = document.querySelector("#serviceStatus");
const activityBadge = document.querySelector("#activityBadge");
const activityText = document.querySelector("#activityText");
const sourceValue = document.querySelector("#sourceValue");
const confidenceValue = document.querySelector("#confidenceValue");
const pulseTrack = document.querySelector("#pulseTrack");

const scoreRing = document.querySelector("#scoreRing");
const scoreValue = document.querySelector("#scoreValue");
const gradeValue = document.querySelector("#gradeValue");
const scoreNote = document.querySelector("#scoreNote");
const naturalRatio = document.querySelector("#naturalRatio");
const syntheticRatio = document.querySelector("#syntheticRatio");
const totalRatio = document.querySelector("#totalRatio");
const resultSource = document.querySelector("#resultSource");

const validityBadge = document.querySelector("#validityBadge");
const insightBadge = document.querySelector("#insightBadge");
const compositionList = document.querySelector("#compositionList");
const insightList = document.querySelector("#insightList");
const historyCount = document.querySelector("#historyCount");
const historyList = document.querySelector("#historyList");
const messagePanel = document.querySelector("#messagePanel");

const historyEntries = [];
let activeLanguage = localStorage.getItem("fabriciq-language") || "en";
let activeMode = "url";
let currentSequenceFrame = -1;
let sequenceFrameRequest = 0;
let latestResult = null;
let latestSourceLabel = "";

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

const translations = {
  en: {
    heroTitle: "Read the fabric. Understand the quality.",
    dashboardTitle: "Fabric Analysis",
    dashboardCopy: "Analyze a product page or a garment label, then read the quality score and fiber balance in one place.",
    urlMode: "Product URL",
    labelMode: "Label OCR",
    urlFormTitle: "Product URL Analysis",
    urlFormCopy: "Paste a product page to extract fabric composition from the product details.",
    urlButton: "Analyze URL",
    labelFormTitle: "Label OCR Analysis",
    labelFormCopy: "Upload a clear label image to read fabric ratios with OCR before scoring.",
    labelButton: "Analyze Image",
    noFile: "No file selected",
    liveTitle: "Live Session",
    readyActivity: "Choose an analysis mode to begin.",
    sourceLabel: "Source",
    confidenceLabel: "Confidence",
    qualityScoreLabel: "Quality Score",
    scoreNoteEmpty: "Run a product URL or label analysis to reveal the scoring summary.",
    naturalRatioLabel: "Natural Fiber Ratio",
    syntheticRatioLabel: "Synthetic Fiber Ratio",
    totalRatioLabel: "Total Ratio",
    analysisSourceLabel: "Analysis Source",
    compositionTitle: "Fabric Composition",
    compositionEmpty: "Material ratios will appear here after the first analysis.",
    scoreReadingTitle: "Score Reading",
    insightEmpty: "FabricIQ will summarize why the score landed where it did.",
    recentTitle: "Recent Sessions",
    historyEmpty: "No sessions yet.",
    backendChecking: "Checking backend",
    backendReady: "Backend Ready",
    backendUnreachable: "Backend Unreachable",
    connectionFailed: "Connection Failed",
    waiting: "Waiting",
    ready: "Ready",
    pending: "Pending",
    noResult: "No result",
    complete: "Complete",
    review: "Review",
    error: "Error",
    analyzing: "Analyzing",
    explained: "Explained",
    validComposition: "Valid composition",
    needsReview: "Needs review",
    productUrl: "Product URL",
    labelOcr: "Label OCR",
    readingPage: "Reading page",
    ocrRunning: "OCR running",
    parsedPage: "Parsed page",
    lowNA: "Low / n.a.",
    grade: "Grade",
    entries: "entries",
    total: "Total",
    noComposition: "No composition",
    noFabric: "No fabric composition could be extracted.",
    weightedScore: "The weighted quality score landed at {score}, which maps to grade {grade}.",
    dominantMaterial: "{fabric} leads the composition at {ratio}%.",
    fiberBalance: "Natural fibers account for {natural}% and synthetic fibers account for {synthetic}% of the recognized mix.",
    sourceReadUrl: "The composition was parsed from the product page content through the URL analysis route.",
    sourceReadOcr: "OCR confidence was approximately {confidence}%, so the composition reading reflects that extraction quality.",
    sourceReadOcrWeak: "The OCR route returned composition data, but without a strong confidence signal.",
    scorePositionTitle: "Score Position",
    dominantTitle: "Dominant Material",
    fiberBalanceTitle: "Fiber Balance",
    sourceReadTitle: "Source Read",
    scoreValidUrl: "The composition was recognized and the quality score has been calculated.",
    scoreValidOcr: "Label data was read through OCR. Confidence: {confidence}%.",
    scoreInvalid: "The composition needs review before the result can be trusted.",
    activityUrlAnalyzing: "Reading the product page and parsing fabric composition.",
    activityLabelAnalyzing: "Running OCR on the label image and extracting the composition.",
    activityComplete: "{source} session finished and the dashboard has been updated.",
    activityReview: "{source} returned a partial or uncertain composition that should be checked.",
    selectFile: "Select a label image before starting OCR.",
    backendConnectError: "The backend connection could not be established.",
    analysisError: "The analysis could not be completed.",
  },
  tr: {
    heroTitle: "Kumasi oku, kaliteyi anla.",
    dashboardTitle: "Kumas Analizi",
    dashboardCopy: "Urun sayfasini veya etiket fotografini analiz et; kalite skorunu ve lif dengesini tek yerde oku.",
    urlMode: "Urun URL",
    labelMode: "Etiket OCR",
    urlFormTitle: "Urun URL Analizi",
    urlFormCopy: "Kumas bilesimini urun detaylarindan cikarmak icin urun sayfasi linkini yapistir.",
    urlButton: "URL Analiz Et",
    labelFormTitle: "Etiket OCR Analizi",
    labelFormCopy: "Kumas oranlarini okumak ve skorlamak icin net bir etiket fotografi yukle.",
    labelButton: "Gorseli Analiz Et",
    noFile: "Dosya secilmedi",
    liveTitle: "Canli Oturum",
    readyActivity: "Baslamak icin bir analiz modu sec.",
    sourceLabel: "Kaynak",
    confidenceLabel: "Guven",
    qualityScoreLabel: "Kalite Skoru",
    scoreNoteEmpty: "Skor ozetini gormek icin URL veya etiket analizi calistir.",
    naturalRatioLabel: "Dogal Lif Orani",
    syntheticRatioLabel: "Sentetik Lif Orani",
    totalRatioLabel: "Toplam Oran",
    analysisSourceLabel: "Analiz Kaynagi",
    compositionTitle: "Kumas Bilesimi",
    compositionEmpty: "Ilk analizden sonra materyal oranlari burada gorunur.",
    scoreReadingTitle: "Skor Yorumu",
    insightEmpty: "FabricIQ skorun neden bu seviyede oldugunu burada ozetler.",
    recentTitle: "Son Analizler",
    historyEmpty: "Henuz analiz yok.",
    backendChecking: "Backend kontrol ediliyor",
    backendReady: "Backend hazir",
    backendUnreachable: "Backend yanit vermiyor",
    connectionFailed: "Baglanti kurulamadi",
    waiting: "Bekleniyor",
    ready: "Hazir",
    pending: "Bekleniyor",
    noResult: "Sonuc yok",
    complete: "Tamamlandi",
    review: "Kontrol",
    error: "Hata",
    analyzing: "Analiz ediliyor",
    explained: "Aciklandi",
    validComposition: "Gecerli bilesim",
    needsReview: "Kontrol gerekli",
    productUrl: "Urun URL",
    labelOcr: "Etiket OCR",
    readingPage: "Sayfa okunuyor",
    ocrRunning: "OCR calisiyor",
    parsedPage: "Sayfa parse edildi",
    lowNA: "Dusuk / yok",
    grade: "Not",
    entries: "kayit",
    total: "Toplam",
    noComposition: "Bilesim yok",
    noFabric: "Kumas bilesimi cikarilamadi.",
    weightedScore: "Agirlikli kalite skoru {score}; bu sonuc {grade} notuna denk geliyor.",
    dominantMaterial: "{fabric}, %{ratio} oranla bilesimde en baskin materyal.",
    fiberBalance: "Taninmis karisimda dogal lif %{natural}, sentetik lif %{synthetic} oraninda.",
    sourceReadUrl: "Bilesim, URL analiziyle urun sayfasi iceriginden parse edildi.",
    sourceReadOcr: "OCR guveni yaklasik %{confidence}; bilesim okumasinin guveni buna gore degerlendirildi.",
    sourceReadOcrWeak: "OCR akisi bilesim verisi dondurdu fakat guclu bir guven sinyali yok.",
    scorePositionTitle: "Skor Konumu",
    dominantTitle: "Baskin Materyal",
    fiberBalanceTitle: "Lif Dengesi",
    sourceReadTitle: "Kaynak Okumasi",
    scoreValidUrl: "Bilesim tanindi ve kalite skoru hesaplandi.",
    scoreValidOcr: "Etiket verisi OCR ile okundu. Guven: %{confidence}.",
    scoreInvalid: "Bilesim guvenilir sayilmadan once kontrol edilmeli.",
    activityUrlAnalyzing: "Urun sayfasi okunuyor ve kumas bilesimi parse ediliyor.",
    activityLabelAnalyzing: "Etiket fotografi OCR ile okunuyor ve bilesim cikariliyor.",
    activityComplete: "{source} oturumu tamamlandi ve dashboard guncellendi.",
    activityReview: "{source} kismi veya belirsiz bir bilesim dondurdu; kontrol edilmeli.",
    selectFile: "OCR baslatmadan once bir etiket fotografi sec.",
    backendConnectError: "Backend ile baglanti kurulamadi.",
    analysisError: "Analiz tamamlanamadi.",
  },
};

function t(key, values = {}) {
  const template = translations[activeLanguage][key] || translations.en[key] || key;
  return Object.entries(values).reduce((text, [name, value]) => text.replaceAll(`{${name}}`, value), template);
}

function sourceKey(sourceLabel) {
  return sourceLabel === "Label OCR" || sourceLabel === translations.tr.labelOcr ? "labelOcr" : "productUrl";
}

function translatedSource(sourceLabel) {
  return t(sourceKey(sourceLabel));
}

function updateStaticText() {
  document.documentElement.lang = activeLanguage;

  document.querySelectorAll("[data-i18n]").forEach((element) => {
    element.textContent = t(element.dataset.i18n);
  });

  languageButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.lang === activeLanguage);
  });

  if (!labelInput.files.length) {
    fileName.textContent = t("noFile");
  }

  urlButton.textContent = t("urlButton");
  labelButton.textContent = t("labelButton");
  setMode(activeMode);
}

function setLanguage(language) {
  activeLanguage = translations[language] ? language : "en";
  localStorage.setItem("fabriciq-language", activeLanguage);
  updateStaticText();

  if (latestResult) {
    renderResult(latestResult, latestSourceLabel, { skipHistory: true });
  } else {
    resetResults();
  }

  renderHistory();
}

const sequenceFrameUrls = Array.from({ length: 239 }, (_, index) => {
  const frameNumber = String(index + 2).padStart(3, "0");
  return `/frames/ezgif-frame-${frameNumber}.jpg?v=forweb01`;
});

const sequenceFrames = sequenceFrameUrls.map((src, index) => {
  const image = new Image();
  image.addEventListener("load", () => {
    if (index === currentSequenceFrame) {
      drawSequenceFrame(index);
    }
  });
  image.src = src;
  return image;
});

function resizeSequenceCanvas() {
  if (!sequenceCanvas) {
    return;
  }

  const pixelRatio = window.devicePixelRatio || 1;
  const width = Math.round(sequenceCanvas.clientWidth * pixelRatio);
  const height = Math.round(sequenceCanvas.clientHeight * pixelRatio);

  if (sequenceCanvas.width !== width || sequenceCanvas.height !== height) {
    sequenceCanvas.width = width;
    sequenceCanvas.height = height;
    currentSequenceFrame = -1;
    updateSequenceFrame();
  }
}

function getSequenceProgress() {
  const rect = scrollSequence.getBoundingClientRect();
  const scrollableDistance = Math.max(1, scrollSequence.offsetHeight - window.innerHeight);
  return Math.min(1, Math.max(0, -rect.top / scrollableDistance));
}

function drawSequenceFrame(frameIndex, progress = getSequenceProgress()) {
  const context = sequenceCanvas.getContext("2d");
  const image = sequenceFrames[frameIndex];

  if (!context || !image || !image.complete || !image.naturalWidth) {
    return;
  }

  const canvasWidth = sequenceCanvas.width;
  const canvasHeight = sequenceCanvas.height;
  const imageRatio = image.naturalWidth / image.naturalHeight;
  const expansion = 0.62 + progress * 0.34;
  const maxFrameWidth = canvasWidth * expansion;
  const maxFrameHeight = canvasHeight * (0.58 + progress * 0.34);
  const frameRatio = maxFrameWidth / maxFrameHeight;
  const drawWidth = imageRatio > frameRatio ? maxFrameWidth : maxFrameHeight * imageRatio;
  const drawHeight = imageRatio > frameRatio ? maxFrameWidth / imageRatio : maxFrameHeight;
  const drawX = (canvasWidth - drawWidth) / 2;
  const drawY = (canvasHeight - drawHeight) / 2 + canvasHeight * (0.05 - progress * 0.04);

  context.clearRect(0, 0, canvasWidth, canvasHeight);
  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = "high";
  context.drawImage(image, drawX, drawY, drawWidth, drawHeight);
}

function updateSequenceFrame() {
  if (!scrollSequence || !sequenceCanvas) {
    return;
  }

  const progress = getSequenceProgress();
  const frameIndex = Math.min(sequenceFrames.length - 1, Math.floor(progress * (sequenceFrames.length - 1)));

  if (sequenceProgress) {
    sequenceProgress.style.transform = `scaleX(${progress})`;
  }

  if (sequenceCopy) {
    const copyProgress = Math.min(1, progress * 1.6);
    sequenceCopy.style.opacity = String(Math.max(0, 1 - copyProgress));
    sequenceCopy.style.transform = `translateY(${-24 * copyProgress}px)`;
  }

  if (frameIndex === currentSequenceFrame) {
    drawSequenceFrame(frameIndex, progress);
    return;
  }

  currentSequenceFrame = frameIndex;
  drawSequenceFrame(frameIndex, progress);
}

function scheduleSequenceUpdate() {
  if (sequenceFrameRequest) {
    return;
  }

  sequenceFrameRequest = window.requestAnimationFrame(() => {
    sequenceFrameRequest = 0;
    updateSequenceFrame();
  });
}

function initializeScrollSequence() {
  if (!scrollSequence || !sequenceCanvas) {
    return;
  }

  sequenceFrames[0].addEventListener("load", updateSequenceFrame, { once: true });
  resizeSequenceCanvas();
  updateSequenceFrame();
  window.addEventListener("scroll", scheduleSequenceUpdate, { passive: true });
  window.addEventListener("resize", resizeSequenceCanvas);
}

function setMode(mode) {
  activeMode = mode;
  const isUrl = mode === "url";

  urlModeButton.classList.toggle("active", isUrl);
  labelModeButton.classList.toggle("active", !isUrl);
  urlForm.hidden = !isUrl;
  labelForm.hidden = isUrl;
  urlForm.classList.toggle("active", isUrl);
  labelForm.classList.toggle("active", !isUrl);

  sourceValue.textContent = isUrl ? t("productUrl") : t("labelOcr");
}

async function checkHealth() {
  try {
    const response = await fetch("/health");
    serviceStatus.textContent = response.ok ? t("backendReady") : t("backendUnreachable");
  } catch {
    serviceStatus.textContent = t("connectionFailed");
  }
}

function setButtonLoading(button, isLoading, loadingText, idleText) {
  button.disabled = isLoading;
  button.textContent = isLoading ? loadingText : idleText;
}

function showMessage(message, tone = "error") {
  messagePanel.hidden = false;
  messagePanel.className = `panel message-panel ${tone}`;
  messagePanel.textContent = message;
}

function clearMessage() {
  messagePanel.hidden = true;
  messagePanel.textContent = "";
}

function setActivity(state, message, source = "Waiting", confidence = "-") {
  activityBadge.textContent = state;
  activityText.textContent = message;
  sourceValue.textContent = source;
  confidenceValue.textContent = confidence;
  pulseTrack.classList.toggle("loading", state === t("analyzing"));
}

function resetResults() {
  scoreRing.style.setProperty("--score", "0");
  scoreValue.textContent = "0";
  gradeValue.textContent = t("pending");
  scoreNote.textContent = t("scoreNoteEmpty");
  naturalRatio.textContent = "0%";
  syntheticRatio.textContent = "0%";
  totalRatio.textContent = "0%";
  resultSource.textContent = "-";
  validityBadge.textContent = t("noResult");
  insightBadge.textContent = t("waiting");
  compositionList.innerHTML = `<p class="empty-state">${t("compositionEmpty")}</p>`;
  insightList.innerHTML = `<p class="empty-state">${t("insightEmpty")}</p>`;
  setActivity(t("ready"), t("readyActivity"), activeMode === "url" ? t("productUrl") : t("labelOcr"));
  clearMessage();
}

function renderComposition(composition) {
  compositionList.innerHTML = "";

  if (!composition.length) {
    compositionList.innerHTML = `<p class="empty-state">${t("noFabric")}</p>`;
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
  const topFabric = Array.isArray(fabric.composition) && fabric.composition.length ? fabric.composition[0] : null;
  const items = [
    {
      title: t("scorePositionTitle"),
      text: t("weightedScore", { score: qualityScore, grade: score.grade || "F" }),
    },
    {
      title: t("fiberBalanceTitle"),
      text: t("fiberBalance", { natural, synthetic }),
    },
    {
      title: t("sourceReadTitle"),
      text: sourceKey(source) === "labelOcr"
        ? confidence > 0
          ? t("sourceReadOcr", { confidence: Math.round(confidence) })
          : t("sourceReadOcrWeak")
        : t("sourceReadUrl"),
    },
  ];

  if (topFabric) {
    items.splice(1, 0, {
      title: t("dominantTitle"),
      text: t("dominantMaterial", {
        fabric: fabricLabels[topFabric.fabric] || topFabric.fabric,
        ratio: topFabric.ratio,
      }),
    });
  }

  insightList.innerHTML = "";

  for (const item of items) {
    const row = document.createElement("article");
    row.className = "insight-item";
    row.innerHTML = `<strong>${item.title}</strong><p>${item.text}</p>`;
    insightList.appendChild(row);
  }

  insightBadge.textContent = fabric.is_valid ? t("explained") : t("review");
}

function renderHistory() {
  historyCount.textContent = `${historyEntries.length} ${t("entries")}`;
  historyList.innerHTML = "";

  if (!historyEntries.length) {
    historyList.innerHTML = `<p class="empty-state">${t("historyEmpty")}</p>`;
    return;
  }

  for (const entry of historyEntries) {
    const row = document.createElement("article");
    row.className = "history-item";
    row.innerHTML = `
      <div>
        <strong>${entry.title}</strong>
        <div class="history-meta">
          <span>${t(entry.sourceKey)}</span>
          <span>${t("grade")} ${entry.grade}</span>
          <span>${t("total")} ${entry.total}%</span>
        </div>
      </div>
      <div class="history-score">${entry.score}</div>
    `;
    historyList.appendChild(row);
  }
}

function pushHistory(data, sourceLabel) {
  const score = data.score || {};
  const fabric = data.fabric || {};
  const leadFabric = Array.isArray(fabric.composition) && fabric.composition.length
    ? fabricLabels[fabric.composition[0].fabric] || fabric.composition[0].fabric
    : t("noComposition");

  historyEntries.unshift({
    title: leadFabric,
    sourceKey: sourceKey(sourceLabel),
    grade: score.grade || "F",
    total: fabric.total_ratio || 0,
    score: score.quality_score || 0,
  });

  historyEntries.splice(4);
  renderHistory();
}

function renderResult(data, sourceLabel, options = {}) {
  const score = data.score || {};
  const fabric = data.fabric || {};
  const ocr = data.ocr || {};
  const qualityScore = Number(score.quality_score || 0);
  const confidence = Number(ocr.avg_confidence || 0);

  latestResult = data;
  latestSourceLabel = sourceLabel;

  scoreRing.style.setProperty("--score", String(qualityScore));
  scoreValue.textContent = String(qualityScore);
  gradeValue.textContent = `${t("grade")} ${score.grade || "F"}`;
  scoreNote.textContent = fabric.is_valid
    ? sourceKey(sourceLabel) === "labelOcr" && confidence > 0
      ? t("scoreValidOcr", { confidence: Math.round(confidence) })
      : t("scoreValidUrl")
    : data.advice || t("scoreInvalid");

  naturalRatio.textContent = `${score.natural_ratio || 0}%`;
  syntheticRatio.textContent = `${score.synthetic_ratio || 0}%`;
  totalRatio.textContent = `${fabric.total_ratio || 0}%`;
  resultSource.textContent = translatedSource(sourceLabel);
  validityBadge.textContent = fabric.is_valid ? t("validComposition") : t("needsReview");

  renderComposition(fabric.composition || []);
  renderInsights(score, fabric, confidence, sourceLabel);

  setActivity(
    fabric.is_valid ? t("complete") : t("review"),
    fabric.is_valid
      ? t("activityComplete", { source: translatedSource(sourceLabel) })
      : t("activityReview", { source: translatedSource(sourceLabel) }),
    translatedSource(sourceLabel),
    confidence > 0 ? `${Math.round(confidence)}%` : sourceKey(sourceLabel) === "labelOcr" ? t("lowNA") : t("parsedPage"),
  );

  if (!options.skipHistory) {
    pushHistory(data, sourceLabel);
  }

  const guidance = data.advice || fabric.warning;
  if ((!fabric.is_valid || data.advice) && guidance) {
    showMessage(guidance, "warning");
  } else {
    clearMessage();
  }
}

function renderError(payload) {
  const error = payload.error || {};
  const message = typeof error === "string" ? error : error.message || t("analysisError");
  setActivity(t("error"), message, activeMode === "url" ? t("productUrl") : t("labelOcr"));
  showMessage(message);
}

languageButtons.forEach((button) => {
  button.addEventListener("click", () => setLanguage(button.dataset.lang));
});

urlModeButton.addEventListener("click", () => setMode("url"));
labelModeButton.addEventListener("click", () => setMode("label"));

labelInput.addEventListener("change", () => {
  fileName.textContent = labelInput.files[0]?.name || t("noFile");
});

urlForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearMessage();
  setActivity(t("analyzing"), t("activityUrlAnalyzing"), t("productUrl"), t("readingPage"));
  setButtonLoading(urlButton, true, t("analyzing"), t("urlButton"));

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

    renderResult(payload, "Product URL");
  } catch {
    setActivity(t("error"), t("backendConnectError"), t("productUrl"));
    showMessage(t("backendConnectError"));
  } finally {
    setButtonLoading(urlButton, false, t("analyzing"), t("urlButton"));
  }
});

labelForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearMessage();

  if (!labelInput.files.length) {
    showMessage(t("selectFile"));
    return;
  }

  const formData = new FormData();
  formData.append("file", labelInput.files[0]);
  setActivity(t("analyzing"), t("activityLabelAnalyzing"), t("labelOcr"), t("ocrRunning"));
  setButtonLoading(labelButton, true, t("analyzing"), t("labelButton"));

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

    renderResult(payload, "Label OCR");
  } catch {
    setActivity(t("error"), t("backendConnectError"), t("labelOcr"));
    showMessage(t("backendConnectError"));
  } finally {
    setButtonLoading(labelButton, false, t("analyzing"), t("labelButton"));
  }
});

initializeScrollSequence();
updateStaticText();
setMode("url");
resetResults();
renderHistory();
checkHealth();
