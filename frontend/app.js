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

const WEEKDAYS_RU = [
  "Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье",
];

let mapInstance = null;

function formatDayLabel(iso, weekday) {
  const [y, m, d] = iso.split("-");
  const name = WEEKDAYS_RU[weekday] || "";
  return `${d}.${m}.${y}${name ? " · " + name : ""}`;
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
          attribution: "© OpenStreetMap",
        }).addTo(mapInstance);
      }
      const map = mapInstance;

      // Убираем старые маршрутные линии (тайлы не трогаем).
      map.eachLayer((layer) => {
        if (!(layer instanceof L.TileLayer)) {
          map.removeLayer(layer);
        }
      });

      const layersByDate = {};
      const boundsByDate = {};
      const allBounds = [];
      const weekdayByDate = {};

      features.forEach((f) => {
        const date = f.properties.date;
        const line = f.geometry.coordinates.map((c) => [c[1], c[0]]);
        const layer = L.polyline(line, { color: "#7c3aed", weight: 3 }).bindPopup(
          `${f.properties.employee || ""} · ${formatDayLabel(date, f.properties.weekday)}`
        );

        if (!layersByDate[date]) layersByDate[date] = [];
        if (!boundsByDate[date]) boundsByDate[date] = [];
        layersByDate[date].push(layer);
        boundsByDate[date].push(...line);
        allBounds.push(...line);
        weekdayByDate[date] = f.properties.weekday;
      });

      const dates = Object.keys(layersByDate).sort();
      const select = el("day-select");
      select.innerHTML = '<option value="all">Все дни</option>' +
        dates.map((d) =>
          `<option value="${d}">${formatDayLabel(d, weekdayByDate[d])}</option>`
        ).join("");
      select.value = "all";

      dates.forEach((d) => layersByDate[d].forEach((l) => l.addTo(map)));
      if (allBounds.length) map.fitBounds(allBounds);

      select.onchange = () => {
        const value = select.value;
        dates.forEach((d) => {
          layersByDate[d].forEach((l) => {
            const show = value === "all" || value === d;
            if (show && !map.hasLayer(l)) l.addTo(map);
            if (!show && map.hasLayer(l)) map.removeLayer(l);
          });
        });
        const target = value === "all" ? allBounds : boundsByDate[value];
        if (target && target.length) map.fitBounds(target);
      };
    })
    .catch(() => {});
}

function runStageSequence() {
  let i = 0;
  const timer = setInterval(() => {
    if (i < STAGES.length) {
      setStatus(STAGES[i]);
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
    const period = nextMonthPeriod();
    const resp = await fetch("/api/optimize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        planning_file_id: state.planningFileId,
        route_template_file_id: state.templateFileId,
        period_start: period.start,
        period_end: period.end,
        home_address: el("home-address").value.trim() || null,
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
    setStatus(err.message, true);
  }
});

// Кабриолет катается по сайту: дрейфует и разворачивается по направлению движения.
(function () {
  const car = document.getElementById("car");
  if (!car) return;

  const MAX_SPEED = 3.2;
  const MIN_SPEED = 1.0;

  let x = window.innerWidth * 0.2;
  let y = window.innerHeight * 0.75;
  let vx = 1.6;
  let vy = 0.4;

  function tick() {
    vx += (Math.random() - 0.5) * 0.4;
    vy += (Math.random() - 0.5) * 0.4;

    const speed = Math.hypot(vx, vy);
    if (speed > MAX_SPEED) {
      vx = (vx / speed) * MAX_SPEED;
      vy = (vy / speed) * MAX_SPEED;
    } else if (speed < MIN_SPEED) {
      const s = speed || 1;
      vx = (vx / s) * MIN_SPEED;
      vy = (vy / s) * MIN_SPEED;
    }

    x += vx;
    y += vy;

    const w = car.offsetWidth;
    const h = car.offsetHeight;
    if (x < 0) { x = 0; vx = Math.abs(vx); }
    if (x > window.innerWidth - w) { x = window.innerWidth - w; vx = -Math.abs(vx); }
    if (y < 0) { y = 0; vy = Math.abs(vy); }
    if (y > window.innerHeight - h) { y = window.innerHeight - h; vy = -Math.abs(vy); }

    const dir = vx < 0 ? -1 : 1;
    car.style.transform = `translate3d(${x}px, ${y}px, 0) scaleX(${dir})`;

    requestAnimationFrame(tick);
  }

  requestAnimationFrame(tick);
})();
