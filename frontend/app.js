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
  templateFile: null,
  planningFileId: null,
  templateFileId: null,
  jobId: null,
};

const el = (id) => document.getElementById(id);
const planningInput = el("planning-file");
const templateInput = el("template-file");
const optimizeBtn = el("optimize-btn");
const statusBox = el("status");
const resultBox = el("result");
const mapSection = el("map-section");

// Прогресс обработки для машинки (0..1); реальную реализацию ставит блок с машинкой.
let setCarProgress = function () {};

// Период по умолчанию — следующий календарный месяц (можно изменить в форме).
(function () {
  const p = nextMonthPeriod();
  el("period-start").value = p.start;
  el("period-end").value = p.end;
})();

function setStatus(text, isError = false) {
  statusBox.classList.remove("hidden");
  statusBox.classList.toggle("error", isError);
  statusBox.textContent = text;
}

function refreshButton() {
  const ready = state.planningFileId && state.templateFileId;
  optimizeBtn.disabled = !ready;
  el("hint").textContent = ready ? "Всё готово, можно упорядочивать." : "Загрузите оба файла, чтобы начать.";
}

async function uploadFile(file, endpoint) {
  const fd = new FormData();
  fd.append("file", file);
  const resp = await fetch(endpoint, { method: "POST", body: fd });
  const data = await resp.json();
  if (!resp.ok) {
    throw new Error(data.error?.message || "Ошибка загрузки файла");
  }
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

templateInput.addEventListener("change", async () => {
  const file = templateInput.files[0];
  if (!file) return;
  try {
    state.templateFileId = await uploadFile(file, "/api/upload/route-template");
    el("template-label").textContent = file.name;
    el("template-label").parentElement.classList.add("filled");
    refreshButton();
  } catch (err) {
    setStatus(err.message, true);
  }
});

function nextMonthPeriod() {
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth() + 1, 1);
  const end = new Date(now.getFullYear(), now.getMonth() + 2, 0);
  const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  return { start: iso(start), end: iso(end) };
}

function currentPeriod() {
  const start = el("period-start").value;
  const end = el("period-end").value;
  if (start && end) {
    return { start, end };
  }
  return nextMonthPeriod();
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

      // Точки — всегда видимые маркеры с подсказкой по наведению.
      const pointsLayer = L.layerGroup();
      const pointsBounds = [];
      pointFeatures.forEach((p) => {
        const [lon, lat] = p.geometry.coordinates;
        const marker = L.circleMarker([lat, lon], {
          radius: 5,
          color: "#ffffff",
          weight: 1.5,
          fillColor: "#d62828",
          fillOpacity: 1,
        });
        marker.bindTooltip(
          `<span class="pt-code">${escapeHtml(p.properties.code)}</span>` +
          `<span class="pt-addr">${escapeHtml(p.properties.address)}</span>`,
          { direction: "top", offset: [0, -6], className: "point-tooltip", opacity: 1 }
        );
        pointsLayer.addLayer(marker);
        pointsBounds.push([lat, lon]);
      });
      pointsLayer.addTo(map);

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
      setStatus(STAGES[i]);
      // Машинка едет вправо по мере прохождения этапов (до 80% — финальный
      // рывок происходит по факту готовности маршрута).
      setCarProgress(0.8 * ((i + 1) / STAGES.length));
      i += 1;
    } else {
      clearInterval(timer);
    }
  }, 700);
  return () => clearInterval(timer);
}

optimizeBtn.addEventListener("click", async () => {
  resultBox.classList.add("hidden");
  mapSection.classList.add("hidden");
  const stopStages = runStageSequence();
  try {
    const period = currentPeriod();
    const resp = await fetch("/api/optimize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        planning_file_id: state.planningFileId,
        route_template_file_id: state.templateFileId,
        period_start: period.start,
        period_end: period.end,
        home_address: el("home-address").value.trim() || null,
        focus: el("focus").value,
      }),
    });
    if (!resp.ok) {
      const data = await resp.json();
      throw new Error(data.error?.message || "Ошибка оптимизации");
    }
    const { job_id } = await resp.json();
    state.jobId = job_id;
    stopStages();
    setStatus("Маршрут готов!");
    setCarProgress(1);
    setTimeout(() => setCarProgress(0), 2600);
    resultBox.classList.remove("hidden");
    el("download-link").href = `/api/download/${job_id}`;
    renderMap(job_id);

    fetch(`/api/result/${job_id}`)
      .then((r) => r.json())
      .then((data) => {
        const stats = data.stats && data.stats[0];
        const meta = el("result-meta");
        if (stats && typeof stats.total_km === "number") {
          meta.textContent = `Километраж по маршруту: ~${stats.total_km} км`;
          meta.classList.remove("hidden");
        }
      })
      .catch(() => {});
  } catch (err) {
    stopStages();
    setCarProgress(0);
    setStatus(err.message, true);
  }
});

// Кабриолет с лисом ездит только по красному фону (hero) слева направо,
// отражая прогресс формирования маршрута, и возвращается на место.
(function () {
  const car = document.getElementById("car");
  const hero = document.querySelector(".hero");
  if (!car || !hero) return;

  const state = { target: 0, shown: 0 };

  window.setCarProgress = function (p) {
    state.target = Math.max(0, Math.min(1, Number(p) || 0));
  };
  setCarProgress = window.setCarProgress;

  function tick() {
    // Плавное сглаживание к целевому прогрессу.
    state.shown += (state.target - state.shown) * 0.08;
    if (Math.abs(state.target - state.shown) < 0.0005) state.shown = state.target;

    const rect = hero.getBoundingClientRect();
    const carW = car.offsetWidth || 200;
    const carH = car.offsetHeight || 90;
    const pad = 14;

    const minX = rect.left + pad;
    const maxX = rect.right - carW - pad;
    const y = rect.bottom - carH - pad;
    const x = minX + (maxX - minX) * state.shown;

    car.style.transform = `translate3d(${x}px, ${y}px, 0)`;
    requestAnimationFrame(tick);
  }

  requestAnimationFrame(tick);
})();
