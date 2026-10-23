"use strict";

const STAGES = [
  "Анализируем базу…",
  "Группируем точки…",
  "Строим маршруты…",
  "Проверяем цикличность…",
  "Формируем маршрутный лист…",
];

const state = {
  planningFile: null,
  planningFileId: null,
  jobId: null,
  routeEmployee: null,
};

const el = (id) => document.getElementById(id);
const planningInput = el("planning-file");
const optimizeBtn = el("optimize-btn");
const statusBox = el("status");
const stageEl = el("stage");
const resultBox = el("result");
const mapSection = el("map-section");
const daysSection = el("days-section");
const daysList = el("days-list");
const redoOptimizeBtn = el("redo-optimize-btn");

// Дни, отмеченные «Переделать» (красные) — переделываются пакетно кнопкой «Оптимизировать».
const pendingRedo = new Set();

// Прогресс обработки для машинки (0..1); реальную реализацию ставит блок с машинкой.
let setCarProgress = function () {};

// Месяц по умолчанию — следующий календарный.
(function () {
  const p = nextMonthPeriod();
  el("planning-month").value = p.start.slice(0, 7);
})();

function setStatus(text, isError = false) {
  statusBox.classList.remove("hidden");
  statusBox.classList.toggle("error", isError);
  statusBox.textContent = text;
}

// Фраза текущего этапа (под кнопкой, рядом с машинкой).
function setStage(text) {
  if (stageEl) stageEl.textContent = text || "";
}

function refreshButton() {
  const ready = !!state.planningFileId;
  optimizeBtn.disabled = !ready;
  el("hint").textContent = ready ? "Всё готово, можно упорядочивать." : "Загрузите базу планирования, чтобы начать.";
}

// Читает сообщение об ошибке из ответа, даже если это не JSON (текстовая 500).
async function readErrorMessage(resp) {
  const text = await resp.text();
  if (!text) return `HTTP ${resp.status}`;
  try {
    const data = JSON.parse(text);
    return data.error?.message || data.detail?.message || text;
  } catch {
    return text;
  }
}

async function uploadFile(file, endpoint) {
  const fd = new FormData();
  fd.append("file", file);
  const resp = await fetch(endpoint, { method: "POST", body: fd });
  if (!resp.ok) {
    throw new Error(await readErrorMessage(resp));
  }
  const data = await resp.json();
  return data.file_id;
}

planningInput.addEventListener("change", async () => {
  const file = planningInput.files[0];
  if (!file) return;
  try {
    state.planningFileId = await uploadFile(file, "/api/upload/planning");
    el("planning-label").textContent = file.name;
    el("planning-label").parentElement.classList.add("filled");
    refreshButton();
  } catch (err) {
    setStatus(err.message, true);
  }
});

// Сворачивание/разворачивание расширенных настроек.
(function () {
  const toggle = el("advanced-toggle");
  if (!toggle) return;
  toggle.addEventListener("click", () => {
    const adv = el("advanced");
    const nowHidden = adv.classList.toggle("hidden");
    toggle.setAttribute("aria-expanded", nowHidden ? "false" : "true");
  });
})();

function nextMonthPeriod() {
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth() + 1, 1);
  const end = new Date(now.getFullYear(), now.getMonth() + 2, 0);
  const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  return { start: iso(start), end: iso(end) };
}

function iso(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function currentPeriod() {
  const v = el("planning-month").value;  // "YYYY-MM"
  if (v) {
    const [y, m] = v.split("-").map(Number);
    return { start: iso(new Date(y, m - 1, 1)), end: iso(new Date(y, m, 0)) };
  }
  return nextMonthPeriod();
}

function buildCapacity() {
  const def = el("capacity-default").value;
  const overrides = {};
  for (let w = 0; w < 5; w++) {
    const v = el("cap-" + w).value;
    if (v) overrides[w] = parseInt(v, 10);
  }
  if (!def && !Object.keys(overrides).length) return {};
  // Лимиты по дням работают и без «Общего»: общий тогда — авто-баланс.
  return {
    points_per_day: def ? parseInt(def, 10) : null,
    points_per_day_overrides: overrides,
  };
}

function buildHomeOverrides() {
  const overrides = {};
  for (let w = 0; w < 5; w++) {
    const v = el("home-" + w).value.trim();
    if (v) overrides[w] = v;
  }
  return overrides;
}

const WEEKDAYS_RU = [
  "Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье",
];

let mapInstance = null;

function formatDayLabel(iso, weekday) {
  const [y, m, d] = iso.split("-");
  const name = WEEKDAYS_RU[weekday] || "";
  return `${d}.${m}.${y}${name ? " · " + name : ""}`;
}

const MONTHS_SHORT = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];

function shortDate(iso) {
  const d = new Date(iso + "T00:00:00");
  return `${d.getDate()} ${MONTHS_SHORT[d.getMonth()]}`;
}

function formatWeekLabel(week, dates) {
  const sorted = [...dates].sort();
  return `Неделя ${week} · ${shortDate(sorted[0])} – ${shortDate(sorted[sorted.length - 1])}`;
}

function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// Цвет точки по цикличности: зелёный — 1 раз/мес, жёлтый — 2, красный — 3 и больше.
function freqColor(freq) {
  const f = Number(freq) || 1;
  if (f >= 3) return "#e11d48";   // красный — 3 раза и чаще
  if (f === 2) return "#f59e0b";  // жёлтый — 2 раза
  return "#16a34a";               // зелёный — 1 раз
}

function fitMap(map, bounds) {
  if (!bounds || !bounds.length) return;
  try {
    map.fitBounds(bounds, { padding: [16, 16] });
  } catch (err) {
    console.error("fitBounds error:", err);
  }
}

function renderMap(jobId) {
  fetch(`/api/result/${jobId}/geojson`)
    .then((r) => r.json())
    .then((geojson) => {
      const features = geojson.features || [];
      if (!features.length) {
        return;
      }
      mapSection.classList.remove("hidden");

      if (!mapInstance) {
        mapInstance = L.map("map");
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19,
          attribution: "© OpenStreetMap",
        }).addTo(mapInstance);
        // Дефолтный центр (Москва), чтобы карта не осталась пустой до fitBounds.
        mapInstance.setView([55.7558, 37.6173], 10);
      }
      const map = mapInstance;
      map.invalidateSize();

      // Разделяем линии маршрутов и точки-маркеры.
      const routeFeatures = features.filter((f) => f.geometry && f.geometry.type === "LineString");
      const pointFeatures = features.filter((f) => f.geometry && f.geometry.type === "Point");

      // Убираем старые слои (тайлы не трогаем).
      map.eachLayer((layer) => {
        if (!(layer instanceof L.TileLayer)) {
          map.removeLayer(layer);
        }
      });

      const layersByDate = {};
      const layersByWeek = {};
      const boundsByDate = {};
      const boundsByWeek = {};
      const weekdayByDate = {};
      const datesInWeek = {};
      const routeBounds = [];

      routeFeatures.forEach((f) => {
        const date = f.properties.date;
        const week = f.properties.week;
        const line = f.geometry.coordinates.map((c) => [c[1], c[0]]);
        const layer = L.polyline(line, { color: "#7c3aed", weight: 3 }).bindPopup(
          `${f.properties.employee || ""} · ${formatDayLabel(date, f.properties.weekday)}`
        );

        if (!layersByDate[date]) { layersByDate[date] = []; boundsByDate[date] = []; }
        if (!layersByWeek[week]) { layersByWeek[week] = []; boundsByWeek[week] = []; datesInWeek[week] = []; }
        layersByDate[date].push(layer);
        boundsByDate[date].push(...line);
        layersByWeek[week].push(layer);
        boundsByWeek[week].push(...line);
        if (!datesInWeek[week].includes(date)) datesInWeek[week].push(date);
        weekdayByDate[date] = f.properties.weekday;
        routeBounds.push(...line);
      });

      // Точки — всегда видимые маркеры, раскрашенные по оценке (рейтингу).
      const pointsLayer = L.layerGroup();
      const pointsBounds = [];
      pointFeatures.forEach((p) => {
        const pr = p.properties;
        const [lon, lat] = p.geometry.coordinates;
        const marker = L.circleMarker([lat, lon], {
          radius: 6,
          color: "#ffffff",
          weight: 1.5,
          fillColor: freqColor(pr.frequency),
          fillOpacity: 1,
        });

        const scoreTxt = pr.score_text && pr.score_text !== "—" ? pr.score_text : "";
        const resultTxt = pr.result_text && pr.result_text !== "—" ? pr.result_text : "";
        let meta = "";
        if (pr.partner && pr.partner !== "—") meta += `<span class="pt-meta">Партнер: <b>${escapeHtml(pr.partner)}</b></span>`;
        meta += `<span class="pt-meta">Цикличность: <b>${pr.frequency}</b> раз/мес</span>`;
        if (scoreTxt) meta += `<span class="pt-meta">Оценка: <b>${escapeHtml(scoreTxt)}</b></span>`;
        if (resultTxt) meta += `<span class="pt-meta">Результат: <b>${escapeHtml(resultTxt)}</b></span>`;
        if (pr.priority > 0) meta += `<span class="pt-meta">Приоритет: <b>${pr.priority}</b></span>`;

        marker.bindTooltip(
          `<span class="pt-code">${escapeHtml(pr.code)}</span>` +
          `<span class="pt-addr">${escapeHtml(pr.address)}</span>` + meta,
          { direction: "top", offset: [0, -6], className: "point-tooltip", opacity: 1 }
        );
        pointsLayer.addLayer(marker);
        pointsBounds.push([lat, lon]);
      });
      pointsLayer.addTo(map);

      // Легенда цикличности (цвета точек).
      if (!map._freqLegend) {
        const legend = L.control({ position: "bottomright" });
        legend.onAdd = function () {
          const div = L.DomUtil.create("div", "freq-legend");
          div.innerHTML =
            '<div class="freq-legend-title">Цикличность</div>' +
            '<span class="freq-legend-row"><i style="background:#16a34a"></i>1 раз/мес</span>' +
            '<span class="freq-legend-row"><i style="background:#f59e0b"></i>2 раза/мес</span>' +
            '<span class="freq-legend-row"><i style="background:#e11d48"></i>3 раза и больше</span>';
          return div;
        };
        legend.addTo(map);
        map._freqLegend = legend;
      }

      // Наполняем селектор: все / по дням / по неделям.
      const dates = Object.keys(layersByDate).sort();
      const weeks = Object.keys(layersByWeek).sort((a, b) => a - b);
      const select = el("view-select");
      select.innerHTML =
        '<option value="all">Все дни</option>' +
        '<optgroup label="По дням">' +
        dates.map((d) => `<option value="${d}">${formatDayLabel(d, weekdayByDate[d])}</option>`).join("") +
        '</optgroup>' +
        '<optgroup label="По неделям">' +
        weeks.map((w) => `<option value="week:${w}">${formatWeekLabel(w, datesInWeek[w])}</option>`).join("") +
        '</optgroup>';
      select.value = "all";

      dates.forEach((d) => layersByDate[d].forEach((l) => l.addTo(map)));
      const allBounds = [...pointsBounds, ...routeBounds];
      fitMap(map, allBounds);

      select.onchange = () => {
        const value = select.value;
        dates.forEach((d) => layersByDate[d].forEach((l) => {
          if (map.hasLayer(l)) map.removeLayer(l);
        }));

        let target = pointsBounds;
        if (value === "all") {
          dates.forEach((d) => layersByDate[d].forEach((l) => l.addTo(map)));
          target = allBounds;
        } else if (value.startsWith("week:")) {
          const w = value.slice(5);
          (layersByWeek[w] || []).forEach((l) => l.addTo(map));
          target = [...pointsBounds, ...(boundsByWeek[w] || [])];
        } else {
          (layersByDate[value] || []).forEach((l) => l.addTo(map));
          target = [...pointsBounds, ...(boundsByDate[value] || [])];
        }
        if (target.length) fitMap(map, target);
      };
    })
    .catch((err) => console.error("Ошибка отрисовки карты:", err));
}

function runStageSequence() {
  let i = 0;
  setCarProgress(0);
  const timer = setInterval(() => {
    if (i < STAGES.length) {
      setStage(STAGES[i]);
      // Машинка едет по дорожке под кнопкой по мере прохождения этапов
      // (до 80% — финальный рывок по факту готовности маршрута).
      setCarProgress(0.8 * ((i + 1) / STAGES.length));
      i += 1;
    } else {
      clearInterval(timer);
    }
  }, 700);
  return () => clearInterval(timer);
}

function buildOptimizeBody(confirmAddress, confirmDuplicates) {
  const period = currentPeriod();
  return JSON.stringify({
    planning_file_id: state.planningFileId,
    period_start: period.start,
    period_end: period.end,
    home_address: el("home-address").value.trim() || null,
    home_address_overrides: buildHomeOverrides(),
    focus: el("focus").value,
    ...buildCapacity(),
    confirm_address: confirmAddress,
    confirm_duplicates: confirmDuplicates,
  });
}

async function runOptimize(confirmAddress, confirmDuplicates) {
  const resp = await fetch("/api/optimize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: buildOptimizeBody(confirmAddress, confirmDuplicates),
  });
  if (!resp.ok) throw new Error(await readErrorMessage(resp));
  return await resp.json();
}

// Спрашивает подтверждение, когда есть дубли кода (точка учтётся один раз).
function confirmDuplicates(data) {
  return new Promise((resolve) => {
    const modal = el("confirm-modal");
    const text = el("confirm-text");
    const okBtn = el("confirm-ok");
    const cancelBtn = el("confirm-cancel");
    const rows = (data.duplicates || []).slice(0, 10).map((d) => `${d.code} (строка ${d.row})`).join(", ");
    const more = data.duplicate_count > 10 ? ` и ещё ${data.duplicate_count - 10}` : "";
    text.textContent =
      `Найдено ${data.duplicate_count} дублей кода (${rows}${more}). ` +
      `Каждая точка будет учтена один раз. Продолжить?`;
    modal.classList.remove("hidden");
    const cleanup = () => {
      modal.classList.add("hidden");
      okBtn.onclick = null;
      cancelBtn.onclick = null;
    };
    okBtn.onclick = () => { cleanup(); resolve(true); };
    cancelBtn.onclick = () => { cleanup(); resolve(false); };
  });
}

// Спрашивает подтверждение, когда у части точек нет полного адреса.
function confirmAddress(data) {
  return new Promise((resolve) => {
    const modal = el("confirm-modal");
    const text = el("confirm-text");
    const okBtn = el("confirm-ok");
    const cancelBtn = el("confirm-cancel");
    const rows = (data.incomplete || []).slice(0, 10).map((p) => p.row).join(", ");
    const more = data.incomplete_count > 10 ? ` и ещё ${data.incomplete_count - 10}` : "";
    text.textContent =
      `У ${data.incomplete_count} из ${data.total_points} точек нет полного адреса (строки: ${rows}${more}). ` +
      `Они попадут в лист «Неопределенные точки» и не войдут в маршрут. Продолжить?`;
    modal.classList.remove("hidden");
    const cleanup = () => {
      modal.classList.add("hidden");
      okBtn.onclick = null;
      cancelBtn.onclick = null;
    };
    okBtn.onclick = () => { cleanup(); resolve(true); };
    cancelBtn.onclick = () => { cleanup(); resolve(false); };
  });
}

// Показывает, что именно изменилось после «Переделать» (какие станции ушли/пришли).
function showDayChanged(data) {
  const modal = el("day-changed-modal");
  const text = el("day-changed-text");
  const okBtn = el("day-changed-ok");
  if (!modal || !text) return;
  if (typeof data.summary === "string") {
    text.textContent = data.summary;
  } else {
    const parts = [];
    if (Array.isArray(data.added_metros) && data.added_metros.length) {
      parts.push("Добавил: " + data.added_metros.join(", "));
    }
    if (Array.isArray(data.removed_metros) && data.removed_metros.length) {
      parts.push("Убрал: " + data.removed_metros.join(", "));
    }
    if (!parts.length) {
      parts.push("Порядок объезда обновлён (станции остались те же).");
    }
    if (Array.isArray(data.metros) && data.metros.length) {
      parts.push("Теперь в дне: " + data.metros.join(", "));
    }
    text.textContent = parts.join("\n");
  }
  text.style.whiteSpace = "pre-line";
  modal.classList.remove("hidden");
  okBtn.onclick = () => modal.classList.add("hidden");
}

if (redoOptimizeBtn) {
  redoOptimizeBtn.addEventListener("click", optimizeDays);
}

optimizeBtn.addEventListener("click", async () => {
  resultBox.classList.add("hidden");
  mapSection.classList.add("hidden");
  const stopStages = runStageSequence();
  try {
    let confirmAddressFlag = false;
    let confirmDuplicatesFlag = false;
    let data = await runOptimize(confirmAddressFlag, confirmDuplicatesFlag);
    if (data.needs_duplicate_confirmation) {
      const ok = await confirmDuplicates(data);
      if (!ok) {
        stopStages();
        setCarProgress(0);
        setStage("");
        return;
      }
      confirmDuplicatesFlag = true;
      data = await runOptimize(confirmAddressFlag, confirmDuplicatesFlag);
    }
    if (data.needs_address_confirmation) {
      const ok = await confirmAddress(data);
      if (!ok) {
        stopStages();
        setCarProgress(0);
        setStage("");
        return;
      }
      confirmAddressFlag = true;
      data = await runOptimize(confirmAddressFlag, confirmDuplicatesFlag);
    }
    const job_id = data.job_id;
    state.jobId = job_id;
    stopStages();
    setStage("");
    setStatus("Маршрут готов!");
    setCarProgress(1);
    setTimeout(() => setCarProgress(0), 2600);
    resultBox.classList.remove("hidden");
    el("download-link").href = `/api/download/${job_id}`;
    renderMap(job_id);
    renderDays(job_id);

    fetch(`/api/result/${job_id}`)
      .then((r) => r.json())
      .then((data) => renderMeta(data.stats && data.stats[0]))
      .catch(() => {});
  } catch (err) {
    stopStages();
    setCarProgress(0);
    setStage("");
    setStatus(err.message, true);
  }
});

// ── Дни маршрута: согласование и переделка ─────────────────────────────
let dayVariants = {}; // дата -> сколько раз нажимали «Переделать»

let lastStats = null;
function renderMeta(stats) {
  if (stats) lastStats = Object.assign({}, lastStats, stats);
  const meta = el("result-meta");
  if (!meta || !lastStats) return;
  const parts = [];
  if (typeof lastStats.total_km === "number") {
    parts.push(`Километраж по маршруту: ~${lastStats.total_km} км`);
  }
  if (Array.isArray(lastStats.warnings) && lastStats.warnings.length) {
    parts.push("Внимание: " + lastStats.warnings[0]);
  }
  if (parts.length) {
    meta.textContent = parts.join(". ");
    meta.style.whiteSpace = "pre-line";
    meta.classList.remove("hidden");
  }
}

function pluralPoints(n) {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return "точка";
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return "точки";
  return "точек";
}

async function renderDays(jobId) {
  if (!daysSection || !daysList) return;
  let data;
  try {
    const resp = await fetch(`/api/result/${jobId}/days`);
    if (!resp.ok) return;
    data = await resp.json();
  } catch (e) {
    return;
  }
  const routes = data.routes || [];
  const route = routes[0]; // одна база = один торговый представитель (обычный случай)
  if (!route) return;
  state.routeEmployee = route.employee;
  daysSection.classList.remove("hidden");
  daysList.innerHTML = "";
  route.days.forEach((day) => daysList.appendChild(buildDayRow(day)));
  renderMeta({ total_km: route.total_km });
  if (redoOptimizeBtn) {
    redoOptimizeBtn.disabled = pendingRedo.size === 0;
    redoOptimizeBtn.textContent = pendingRedo.size
      ? `Оптимизировать отмеченные (${pendingRedo.size})`
      : "Оптимизировать отмеченные";
  }
}

function buildDayRow(day) {
  const row = document.createElement("div");
  const marked = pendingRedo.has(day.date);
  row.className = "day-row" + (day.locked ? " locked" : "") + (marked ? " marked" : "");
  row.dataset.date = day.date;

  const main = document.createElement("div");
  main.className = "day-main";

  const title = document.createElement("div");
  title.className = "day-title";
  const dateEl = document.createElement("span");
  dateEl.className = "day-date";
  dateEl.textContent = formatDayLabel(day.date, day.weekday);
  const countEl = document.createElement("span");
  countEl.className = "day-count";
  countEl.textContent = `${day.count} ${pluralPoints(day.count)}`;
  title.appendChild(dateEl);
  title.appendChild(countEl);
  if (day.locked) {
    const stateEl = document.createElement("span");
    stateEl.className = "day-state";
    stateEl.textContent = "✓ согласован";
    title.appendChild(stateEl);
  } else if (marked) {
    const stateEl = document.createElement("span");
    stateEl.className = "day-state marked";
    stateEl.textContent = "⚠ на переделку";
    title.appendChild(stateEl);
  }
  main.appendChild(title);

  const points = document.createElement("p");
  points.className = "day-points";
  const labels = day.visits
    .map((v) => v.metro || v.street || v.code)
    .filter(Boolean);
  points.textContent = labels.join(" · ") || "—";
  main.appendChild(points);
  row.appendChild(main);

  const actions = document.createElement("div");
  actions.className = "day-actions";

  if (day.locked) {
    const unlockBtn = document.createElement("button");
    unlockBtn.className = "day-btn";
    unlockBtn.textContent = "Разблокировать";
    unlockBtn.onclick = () => unlockDay(day.date);
    actions.appendChild(unlockBtn);
  } else {
    const approveBtn = document.createElement("button");
    approveBtn.className = "day-btn approve";
    approveBtn.textContent = "Согласовать";
    approveBtn.onclick = () => lockDay(day.date);
    actions.appendChild(approveBtn);

    const redoBtn = document.createElement("button");
    redoBtn.className = "day-btn redo";
    redoBtn.textContent = marked ? "Отменить отметку" : "Переделать";
    redoBtn.onclick = () => markRedo(day.date);
    actions.appendChild(redoBtn);
  }
  row.appendChild(actions);
  return row;
}

async function postDayAction(action, date) {
  const resp = await fetch(`/api/result/${state.jobId}/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ employee: state.routeEmployee, date }),
  });
  if (!resp.ok) {
    setStatus(await readErrorMessage(resp), true);
    return false;
  }
  return true;
}

async function lockDay(date) {
  if (await postDayAction("lock", date)) {
    pendingRedo.delete(date);
    setStatus("День согласован — он больше не меняется");
    await renderDays(state.jobId);
  }
}

async function unlockDay(date) {
  if (await postDayAction("unlock", date)) {
    setStatus("День разблокирован");
    await renderDays(state.jobId);
  }
}

function markRedo(date) {
  if (pendingRedo.has(date)) {
    pendingRedo.delete(date);
  } else {
    pendingRedo.add(date);
  }
  renderDays(state.jobId);
}

async function optimizeDays() {
  if (!pendingRedo.size) return;
  const dates = Array.from(pendingRedo).sort();
  redoOptimizeBtn.disabled = true;
  setStatus(`Переделываю ${dates.length} отмеченных дней…`);
  const resp = await fetch(`/api/result/${state.jobId}/optimize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ employee: state.routeEmployee, dates }),
  });
  if (!resp.ok) {
    setStatus(await readErrorMessage(resp), true);
    redoOptimizeBtn.disabled = false;
    return;
  }
  const data = await resp.json();
  const redone = data.redone || [];
  pendingRedo.clear();
  setStatus(`Переделано дней: ${redone.length}. Проверь новые варианты.`);
  await renderDays(state.jobId);
  renderMap(state.jobId);
  if (redone.length) {
    const summary = redone
      .map((d) => {
        const rem = d.removed_metros && d.removed_metros.length ? `Убрал: ${d.removed_metros.join(", ")}` : "";
        const add = d.added_metros && d.added_metros.length ? `Добавил: ${d.added_metros.join(", ")}` : "";
        return `${d.date}: ${[rem, add].filter(Boolean).join(" · ") || "без изменений"}`;
      })
      .join("\n");
    showDayChanged({ summary });
  }
}

async function regenerateDay(date) {
  dayVariants[date] = (dayVariants[date] || 0) + 1;
  const resp = await fetch(`/api/result/${state.jobId}/regenerate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ employee: state.routeEmployee, date, variant: dayVariants[date], swap: true }),
  });
  if (!resp.ok) {
    setStatus(await readErrorMessage(resp), true);
    return;
  }
  const data = await resp.json();
  setStatus("День переделан — проверь новый вариант");
  await renderDays(state.jobId);
  renderMap(state.jobId);
  showDayChanged(data);
}

// Машинка с лисом ездит по дорожке под кнопкой (прогресс) + тонкий прогресс-бар.
(function () {
  const car = document.getElementById("car");
  const track = document.getElementById("car-track");
  const bar = document.getElementById("progress");
  const fill = document.getElementById("progress-fill");

  const state = { target: 0, shown: 0 };

  window.setCarProgress = function (p) {
    const v = Math.max(0, Math.min(1, Number(p) || 0));
    state.target = v;
    if (fill) fill.style.width = Math.round(v * 100) + "%";
    if (bar) bar.classList.toggle("active", v > 0 && v < 1);
  };
  setCarProgress = window.setCarProgress;

  if (car && track) {
    function tick() {
      state.shown += (state.target - state.shown) * 0.08;
      if (Math.abs(state.target - state.shown) < 0.0005) state.shown = state.target;

      const tw = track.clientWidth || 1;
      const cw = car.offsetWidth || 130;
      const maxX = Math.max(0, tw - cw);
      car.style.transform = `translateX(${maxX * state.shown}px)`;
      requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }
})();

// ── Автодополнение адресов (DaData) ─────────────────────────────
function setupAddressAutocomplete(input) {
  if (!input) return;
  let timer = null;
  let dropdown = null;

  function close() {
    if (dropdown) { dropdown.remove(); dropdown = null; }
  }

  function show(items) {
    close();
    if (!items || !items.length) return;
    dropdown = document.createElement("div");
    dropdown.className = "address-suggest";
    items.forEach((text) => {
      const row = document.createElement("div");
      row.className = "address-suggest-item";
      row.textContent = text;
      row.onmousedown = (e) => {
        e.preventDefault();       // не даём полю потерять фокус до подстановки
        input.value = text;
        close();
      };
      dropdown.appendChild(row);
    });
    const host = input.parentElement;
    if (host) {
      host.style.position = "relative";
      host.appendChild(dropdown);
    }
  }

  input.addEventListener("input", () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 3) { close(); return; }
    timer = setTimeout(async () => {
      try {
        const resp = await fetch("/api/suggest/address?query=" + encodeURIComponent(q));
        if (resp.ok) {
          const data = await resp.json();
          show(data.suggestions || []);
        }
      } catch (e) { /* тихо — автодополнение не критично */ }
    }, 300);
  });

  input.addEventListener("blur", () => { setTimeout(close, 150); });
  input.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
}

setupAddressAutocomplete(el("home-address"));
for (let w = 0; w < 5; w++) setupAddressAutocomplete(el("home-" + w));
