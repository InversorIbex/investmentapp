const view = document.querySelector("#view");
const nav = document.querySelector("#nav");
const nf = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 2 });
const nf0 = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 0 });

const SECTORS = [
  ["", "Todos los sectores"],
  ["Technology", "Tecnología"],
  ["Healthcare", "Salud"],
  ["Financial Services", "Finanzas"],
  ["Consumer Defensive", "Consumo básico"],
  ["Consumer Cyclical", "Consumo cíclico"],
  ["Industrials", "Industria"],
  ["Energy", "Energía"],
  ["Utilities", "Servicios públicos"],
  ["Real Estate", "Inmobiliario"],
  ["Basic Materials", "Materiales"],
  ["Communication Services", "Comunicación"],
];
const REGIONS = [
  ["us", "EEUU"], ["ca", "Canadá"], ["eu", "Europa"],
  ["es", "España"], ["de", "Alemania"], ["fr", "Francia"], ["gb", "Reino Unido"],
  ["it", "Italia"], ["nl", "Países Bajos"], ["ch", "Suiza"], ["se", "Suecia"],
  ["dk", "Dinamarca"], ["be", "Bélgica"], ["fi", "Finlandia"], ["no", "Noruega"],
  ["pt", "Portugal"], ["at", "Austria"], ["ie", "Irlanda"],
];
const REGION = Object.fromEntries(REGIONS);
const SESSION = { BMO: "Antes de abrir", AMC: "Tras el cierre", TNS: "Sin hora" };

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}
function num(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return new Intl.NumberFormat("es-ES", { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(Number(value));
}
function pct(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  const n = Number(value);
  const cls = n > 0 ? "up" : n < 0 ? "down" : "";
  const sign = n > 0 ? "+" : "";
  return `<span class="${cls}">${sign}${num(n, digits)}%</span>`;
}
function cap(value) {
  if (value === null || value === undefined) return "—";
  const abs = Math.abs(value);
  if (abs >= 1e12) return `${num(value / 1e12, 2)} bill.`;
  if (abs >= 1e9) return `${num(value / 1e9, 1)} mil mill.`;
  return `${num(value / 1e6, 0)} mill.`;
}
function when(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return esc(iso);
  return date.toLocaleString("es-ES", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}
function spark(values, width = 92, height = 28) {
  const pts = (values || []).filter((v) => typeof v === "number");
  if (pts.length < 2) return "";
  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const span = max - min || 1;
  const d = pts.map((v, i) => {
    const x = (i / (pts.length - 1)) * width;
    const y = height - ((v - min) / span) * (height - 2) - 1;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const up = pts[pts.length - 1] >= pts[0];
  return `<svg class="spark" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" aria-hidden="true"><polyline fill="none" stroke="${up ? "#1d6b45" : "#9d342c"}" stroke-width="1.6" points="${d}"></polyline></svg>`;
}
function growthChart(curve) {
  const pts = (curve || []).filter((p) => typeof p.portfolio === "number");
  if (!pts.length) return "<p class='meta'>Todavía no hay un cierre apuntado.</p>";
  const w = 680;
  const h = 250;
  const left = 42;
  const right = 12;
  const top = 16;
  const bottom = 28;
  const values = pts.flatMap((p) => [p.portfolio, p.blend]).filter((v) => typeof v === "number");
  values.push(100);
  let lo = Math.min(...values);
  let hi = Math.max(...values);
  if (hi - lo < 0.8) {
    lo -= 0.6;
    hi += 0.6;
  } else {
    const pad = (hi - lo) * 0.12;
    lo -= pad;
    hi += pad;
  }
  const span = hi - lo || 1;
  const x = (i) => (pts.length === 1 ? (left + w - right) / 2 : left + (i / (pts.length - 1)) * (w - left - right));
  const y = (v) => top + (1 - (v - lo) / span) * (h - top - bottom);
  const pathFor = (key) => pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p[key]).toFixed(1)}`).join(" ");
  const yTicks = [lo, 100, hi].filter((v, i, all) => all.findIndex((n) => Math.abs(n - v) < span * 0.08) === i);
  const grid = yTicks.map((v) => {
    const yy = y(v);
    return `<line x1="${left}" y1="${yy.toFixed(1)}" x2="${w - right}" y2="${yy.toFixed(1)}" stroke="#e3d9c8" stroke-width="1"></line><text x="${left - 6}" y="${(yy + 4).toFixed(1)}" text-anchor="end" fill="#6e655b" font-size="11">${v.toFixed(v >= 100 ? 1 : 1)}</text>`;
  }).join("");
  const dots = pts.map((p, i) => `<circle cx="${x(i).toFixed(1)}" cy="${y(p.portfolio).toFixed(1)}" r="3.5" fill="#9a4e2c"></circle>`).join("");
  const blend = pts.length > 1 ? `<path d="${pathFor("blend")}" fill="none" stroke="#1c1712" stroke-width="1.6" stroke-dasharray="4 3"></path>` : "";
  const line = pts.length > 1 ? `<path d="${pathFor("portfolio")}" fill="none" stroke="#9a4e2c" stroke-width="2.4"></path>` : "";
  const first = pts[0];
  const last = pts[pts.length - 1];
  const dates = `<text x="${x(0).toFixed(1)}" y="${h - 8}" text-anchor="${pts.length === 1 ? "middle" : "start"}" fill="#6e655b" font-size="11">${esc(first.date)}</text>`
    + (pts.length > 1 ? `<text x="${x(pts.length - 1).toFixed(1)}" y="${h - 8}" text-anchor="end" fill="#6e655b" font-size="11">${esc(last.date)}</text>` : "");
  const labelX = x(pts.length - 1);
  const labelAnchor = labelX > w - 72 ? "end" : "start";
  const lastLabel = `<text x="${(labelAnchor === "end" ? labelX - 8 : labelX + 8).toFixed(1)}" y="${(y(last.portfolio) - 8).toFixed(1)}" text-anchor="${labelAnchor}" fill="#9a4e2c" font-size="12">${num(last.portfolio, 1)}</text>`;
  return `<div class="chart-wrap"><svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Crecimiento de la cartera, base 100">${grid}${blend}${line}${dots}${dates}${lastLabel}</svg><p class="meta">Cobre: la cartera, base 100 el día de salida. Línea discontinua: 50% S&P 500, 30% Euro Stoxx 50 y 20% TSX, en euros. Cada día de Madrid en que se abre Hoy o Cartera se añade un punto. El último vale ${nf0.format(last.value_eur)} € (${pct(last.day_pct)} ese día).</p></div>`;
}
function tradeRows(trades) {
  if (!trades || !trades.length) return "<p class='meta'>Todavía no hay compras ni ventas apuntadas.</p>";
  return `<table><thead>${th(["Fecha", "Operación", "Empresa", "Precio*", "Importe €*"])}</thead><tbody>
    ${trades.map((row) => `<tr class="clickable" data-symbol="${esc(row.symbol)}"><td>${esc(row.date)}</td><td class="${row.side === "venta" ? "side-sell" : "side-buy"}">${row.side === "venta" ? "Venta" : "Compra"}</td><td><div class="name">${esc(row.name)}</div><div class="sym">${esc(row.symbol)}${row.shares ? " · " + num(row.shares, row.shares >= 1 ? 2 : 4) + " títulos" : ""}</div></td>${tdNum(row.price == null ? "—" : num(row.price) + (row.currency ? " " + esc(row.currency) : ""))}${tdNum(nf0.format(row.value_eur || 0))}</tr>`).join("")}
  </tbody></table>`;
}
function area(points) {
  const pts = (points || []).filter((p) => p && typeof p.c === "number");
  if (pts.length < 2) return "";
  const w = 680;
  const h = 220;
  const min = Math.min(...pts.map((p) => p.c));
  const max = Math.max(...pts.map((p) => p.c));
  const span = max - min || 1;
  const xy = pts.map((p, i) => {
    const x = (i / (pts.length - 1)) * (w - 8) + 4;
    const y = h - 18 - ((p.c - min) / span) * (h - 36);
    return [x, y];
  });
  const d = xy.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const fill = `${d} L${xy[xy.length - 1][0].toFixed(1)},${h} L${xy[0][0].toFixed(1)},${h} Z`;
  return `<div class="chart-wrap"><svg viewBox="0 0 ${w} ${h}"><path d="${fill}" fill="#f3e2d4"></path><path d="${d}" fill="none" stroke="#9a4e2c" stroke-width="2"></path></svg></div>`;
}

function banner(data) {
  const bits = [];
  if (data && data.error) bits.push(data.error);
  if (data && data.stale) bits.push("Dato anterior: la fuente no respondió en este refresco.");
  if (data && data.warnings && data.warnings.length) bits.push(data.warnings.slice(0, 2).join(" · "));
  if (!bits.length) return "";
  return `<p class="warn">${esc(bits.join(" "))}</p>`;
}
function head(kicker, title, lead) {
  return `<p class="kicker">${esc(kicker)}</p><h1>${esc(title)}</h1>${lead ? `<p class="lead">${lead}</p>` : ""}`;
}
function th(labels) {
  return `<tr>${labels.map((label) => `<th class="${label.endsWith("*") ? "num" : ""}">${esc(label.replace("*", ""))}</th>`).join("")}</tr>`;
}
function tdNum(html) { return `<td class="num">${html}</td>`; }

async function api(path) {
  const response = await fetch(path);
  const text = await response.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = {};
  }
  if (!response.ok) {
    const detail = typeof data.error === "string" ? data.error : text.replace(/\s+/g, " ").trim();
    throw new Error(detail.slice(0, 180) || "No se pudo cargar");
  }
  return data;
}
function loading(text) {
  view.innerHTML = `<p class="loading">${esc(text)}</p>`;
}
function companyCell(row) {
  const badges = [
    row.king ? `<span class="badge">Rey</span>` : "",
    row.aristocrat ? `<span class="badge green">Aristócrata</span>` : "",
  ].join("");
  return `<td><div class="name">${esc(row.name)}${badges}</div><div class="sym">${esc(row.symbol)} · ${esc(row.region_label || row.exchange || "")}</div></td>`;
}

const routes = {
  hoy: renderHoy,
  indices: renderIndices,
  screener: renderScreener,
  gangas: renderGangas,
  calidad: renderCalidad,
  dividendos: renderDividendos,
  termometro: renderTermometro,
  noticias: renderNoticias,
  resultados: renderResultados,
  sentimiento: renderSentimiento,
  cartera: renderCartera,
};

async function renderHoy() {
  loading("Leyendo el día…");
  const data = await api("/api/home");
  const book = data.portfolio || {};
  const decision = book.decision || {};
  view.innerHTML = `
    ${head("Hoy", "El mercado, en una página", "Termómetro, índices, titulares, resultados que vienen y la cartera de papel.")}
    ${banner(data)}
    <div class="hero-temp card">
      <div class="temp"><div><strong>${data.temperature == null ? "—" : num(data.temperature, 0)}</strong><span>${esc(data.label || "")}</span></div></div>
      <div>
        <h2>Temperatura del mercado</h2>
        <p class="lead">Miedo y codicia de CNN ${data.fear && data.fear.score != null ? num(data.fear.score, 0) + " · " + esc(data.fear.label || "") : "sin dato"}. VIX ${num(data.vix, 1)}. Curva 10 años menos 3 meses: ${num(data.curve, 2)} puntos.</p>
        <div class="row">${(data.sessions || []).map((s) => `<span class="pill ${s.state === "abierto" ? "on" : "off"}">${esc(s.label)} ${esc(s.clock)} · ${esc(s.state)}</span>`).join("")}</div>
      </div>
    </div>
    <div class="grid four">
      ${(data.indices || []).map((row) => `<article class="card stat"><div class="label">${esc(row.name)}</div><div class="value">${num(row.price, row.price > 100 ? 0 : 2)}</div><div class="sub">${pct(row.change_pct)} hoy · ${pct(row.month_pct)} mes</div>${spark(row.spark)}</article>`).join("")}
    </div>
    <div class="split" style="margin-top:14px">
      <section class="card">
        <h2>Titulares</h2>
        <ul class="news-list">${(data.news || []).map(newsItem).join("") || "<li>Sin titulares</li>"}</ul>
      </section>
      <section>
        <article class="card">
          <h2>Cartera modelo</h2>
          <p class="value" style="font-family:var(--serif);font-size:32px;margin:0">${book.value_eur == null ? "—" : nf0.format(book.value_eur) + " €"}</p>
          <p>${pct(book.day_pct)} hoy · ${pct(book.vs_blend)} frente a la referencia</p>
          <p>${esc(decision.reason || book.error || "")}</p>
          <p><a href="#cartera">Ver las diez posiciones</a></p>
        </article>
        <article class="card" style="margin-top:14px">
          <h2>Próximos resultados</h2>
          <ul class="news-list">${(data.earnings || []).map((row) => `<li><a href="#ficha/${encodeURIComponent(row.symbol)}"><b>${esc(row.symbol)}</b> ${esc(row.name)}</a><div class="meta">${esc(row.date)} · ${esc(SESSION[row.session] || row.session)} · ${esc(REGION[row.region] || row.region)}</div></li>`).join("") || "<li>Sin fechas</li>"}</ul>
        </article>
      </section>
    </div>`;
  bindRows();
}

function newsItem(item) {
  return `<li><a href="${esc(item.url)}" target="_blank" rel="noreferrer">${esc(item.title)}</a><div class="meta">${esc(item.source)} · ${when(item.published)}</div></li>`;
}

async function renderIndices() {
  loading("Cargando índices…");
  const data = await api("/api/indices");
  const zones = ["América", "Europa", "Asia-Pacífico", "Referencias"];
  view.innerHTML = `
    ${head("Mundo", "Índices y referencias", data.note || "")}
    ${banner(data)}
    <div class="row">${(data.sessions || []).map((s) => `<span class="pill ${s.state === "abierto" ? "on" : "off"}">${esc(s.label)} ${s.state}</span>`).join("")}</div>
    ${zones.map((zone) => {
      const rows = (data.items || []).filter((row) => row.zone === zone);
      if (!rows.length) return "";
      return `<section class="card" style="margin-bottom:14px"><h2>${esc(zone)}</h2><table><thead>${th(["Índice", "Último*", "Hoy*", "Mes*", ""])}</thead><tbody>
        ${rows.map((row) => `<tr><td><div class="name">${esc(row.name)}</div><div class="sym">${esc(row.code)}</div></td>${tdNum(num(row.price, row.symbol.includes("=X") || row.price < 20 ? 3 : row.price > 200 ? 0 : 2))}${tdNum(pct(row.change_pct))}${tdNum(pct(row.month_pct))}<td>${spark(row.spark)}</td></tr>`).join("")}
      </tbody></table></section>`;
    }).join("")}`;
}

function screenerForm(params) {
  const val = (key, fallback = "") => esc(params.get(key) || fallback);
  return `<form class="filters" id="screen-form">
    <label>Mercado<select name="region">${REGIONS.map(([id, label]) => `<option value="${id}" ${params.get("region") === id || (!params.get("region") && id === "us") ? "selected" : ""}>${label}</option>`).join("")}</select></label>
    <label>Sector<select name="sector">${SECTORS.map(([id, label]) => `<option value="${id}" ${params.get("sector") === id ? "selected" : ""}>${label}</option>`).join("")}</select></label>
    <label>Capital mín. (mil mill.)<input name="cap" value="${val("cap", "10")}" inputmode="decimal"></label>
    <label>PER máximo<input name="pe" value="${val("pe")}" inputmode="decimal"></label>
    <label>Dividendo mín. %<input name="dy" value="${val("dy")}" inputmode="decimal"></label>
    <label>ROE mín. %<input name="roe" value="${val("roe")}" inputmode="decimal"></label>
    <label>Ingresos mín. %<input name="growth" value="${val("growth")}" inputmode="decimal"></label>
    <label>12 meses desde %<input name="chg_min" value="${val("chg_min")}" inputmode="decimal"></label>
    <label>12 meses hasta %<input name="chg_max" value="${val("chg_max")}" inputmode="decimal"></label>
    <label>Orden<select name="sort">
      ${[["intradaymarketcap", "Capitalización"], ["percentchange", "Hoy"], ["fiftytwowkpercentchange", "12 meses"], ["peratio.lasttwelvemonths", "PER"], ["returnonequity.lasttwelvemonths", "ROE"], ["forward_dividend_yield", "Dividendo"], ["totalrevenues1yrgrowth.lasttwelvemonths", "Ingresos"], ["consecutive_years_of_dividend_growth_count", "Años de dividendo"]].map(([id, label]) => `<option value="${id}" ${params.get("sort") === id ? "selected" : ""}>${label}</option>`).join("")}
    </select></label>
    <label>Dirección<select name="dir"><option value="desc" ${params.get("dir") !== "asc" ? "selected" : ""}>Mayor a menor</option><option value="asc" ${params.get("dir") === "asc" ? "selected" : ""}>Menor a mayor</option></select></label>
    <label>Filas<input name="size" value="${val("size", "40")}" inputmode="numeric"></label>
    <button type="submit">Filtrar</button>
  </form>`;
}

function stockTable(items, extra) {
  return `<table><thead>${th(["Empresa", "Sector", "Precio*", "Hoy*", "12 meses*", "PER*", "ROE*", "Div.%*", "Capital*", ...extra.map((col) => col[0])])}</thead><tbody>
    ${(items || []).map((row) => `<tr class="clickable" data-symbol="${esc(row.symbol)}">${companyCell(row)}<td>${esc(row.sector_label || "—")}</td>${tdNum(num(row.price))}${tdNum(pct(row.change_pct))}${tdNum(pct(row.change_52w))}${tdNum(num(row.pe, 1))}${tdNum(num(row.roe, 1))}${tdNum(num(row.dividend_yield, 2))}${tdNum(cap(row.market_cap))}${extra.map((col) => tdNum(col[1](row))).join("")}</tr>`).join("") || `<tr><td colspan="12">Sin resultados con ese filtro.</td></tr>`}
  </tbody></table>`;
}

async function renderScreener() {
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  loading("Filtrando el mercado…");
  const query = params.toString();
  const data = await api("/api/screener" + (query ? `?${query}` : ""));
  view.innerHTML = `
    ${head("Screener", "EEUU, Canadá y Europa", "Grandes y medianas cotizadas. Los filtros se aplican en Yahoo y la puntuación de calidad se calcula aquí, con las reglas de la sección Calidad.")}
    ${screenerForm(params)}
    ${banner(data)}
    <p class="meta">Mostrando ${(data.items || []).length} cotizaciones de la bolsa de origen.</p>
    <div class="card">${stockTable(data.items, [["Nota*", (row) => num(row.score, 0)]])}</div>`;
  document.querySelector("#screen-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const next = new URLSearchParams(new FormData(event.target));
    location.hash = `#screener?${next.toString()}`;
  });
  bindRows();
}

async function renderGangas() {
  loading("Buscando negocios que crecen con la acción cayendo. La primera vez tarda un minuto…");
  const data = await api("/api/gangas");
  const table = (items) => `<table><thead>${th(["Empresa", "Racha*", "12 meses*", "Bajo el máximo*", "Ingresos*", "PER*", "Capital*"])}</thead><tbody>
    ${items.map((row) => `<tr class="clickable" data-symbol="${esc(row.symbol)}">${companyCell(row)}${tdNum(row.streak + " años")}${tdNum(pct(row.change_52w, 1))}${tdNum(pct(row.drawdown_pct, 1))}${tdNum(pct(row.revenue_yoy_sec, 1))}${tdNum(num(row.pe, 1))}${tdNum(cap(row.market_cap))}</tr>`).join("") || "<tr><td colspan='7'>Ninguna cumple hoy la regla.</td></tr>"}
  </tbody></table>`;
  view.innerHTML = `
    ${head("Gangas", "Crecen, y la bolsa no", data.rule || "")}
    ${banner(data)}
    <section class="card" style="margin-bottom:14px"><h2>EEUU · cinco ejercicios o más, fuente SEC</h2><p class="meta">Revisadas ${data.scanned_us || 0} candidatas que ya caen más de un 8% y crecieron los ingresos el último año.</p>${table(data.us || [])}</section>
    <section class="card"><h2>Canadá y Europa · tres subidas seguidas</h2><p class="meta">Yahoo solo publica cuatro ejercicios fuera de la SEC. No se presentan como si fueran cinco.</p>${table(data.international || [])}</section>`;
  bindRows();
}

async function renderCalidad() {
  loading("Puntuando la calidad…");
  const data = await api("/api/calidad");
  view.innerHTML = `
    ${head("Calidad", "Empresas con números sólidos", data.note || "")}
    ${banner(data)}
    <ol class="rules">${(data.rules || []).map((rule) => `<li>${esc(rule)}</li>`).join("")}</ol>
    <div class="card" style="margin-top:14px">${stockTable(data.items, [["Nota*", (row) => num(row.score, 0)], ["Deuda*", (row) => row.debt == null ? "—" : num(row.debt, 2) + "×"]])}</div>`;
  bindRows();
}

async function renderDividendos() {
  loading("Ordenando las rachas de dividendo…");
  const data = await api("/api/dividendos");
  const tabs = [
    ["reyes", "Reyes · 50 años"],
    ["aristocratas", "Aristócratas S&P"],
    ["usa", "Racha USA · 25"],
    ["canada", "Canadá · 5"],
    ["europa", "Europa · 10"],
  ];
  let current = "reyes";
  const paint = () => {
    let items = data.items || [];
    if (current === "reyes") items = items.filter((row) => (row.dividend_years || 0) >= 50);
    if (current === "aristocratas") items = items.filter((row) => row.aristocrat);
    if (current === "usa") items = items.filter((row) => row.group === "us" && (row.dividend_years || 0) >= 25);
    if (current === "canada") items = items.filter((row) => row.group === "ca");
    if (current === "europa") items = items.filter((row) => row.group === "eu");
    items = [...items].sort((a, b) => (b.dividend_years || 0) - (a.dividend_years || 0));
    view.innerHTML = `
      ${head("Dividendos", "Reyes y aristócratas", data.note || "")}
      ${banner(data)}
      <div class="tabs">${tabs.map(([id, label]) => `<button type="button" data-tab="${id}" class="${id === current ? "on" : ""}">${label}</button>`).join("")}</div>
      <div class="card">${stockTable(items, [["Años*", (row) => row.dividend_years == null ? "—" : String(row.dividend_years)]])}</div>
      ${current === "aristocratas" && (data.missing_aristocrats || []).length ? `<p class="meta">Aristócratas sin cotización ahora: ${esc(data.missing_aristocrats.join(", "))}</p>` : ""}
      ${current === "reyes" && (data.missing_kings || []).length ? `<p class="meta">Reyes sin cotización ahora: ${esc(data.missing_kings.join(", "))}</p>` : ""}`;
    view.querySelectorAll("[data-tab]").forEach((button) => {
      button.addEventListener("click", () => { current = button.dataset.tab; paint(); });
    });
    bindRows();
  };
  paint();
}

async function renderTermometro() {
  loading("Tomando la temperatura…");
  const data = await api("/api/termometro");
  view.innerHTML = `
    ${head("Termómetro", data.label ? data.label[0].toUpperCase() + data.label.slice(1) : "Mercado", data.note || "")}
    ${banner(data)}
    <div class="hero-temp card">
      <div class="temp"><div><strong>${data.temperature == null ? "—" : num(data.temperature, 0)}</strong><span>de 100</span></div></div>
      <div class="grid three">
        <article class="stat"><div class="label">VIX</div><div class="value">${num(data.vix, 1)}</div></article>
        <article class="stat"><div class="label">EEUU que suben</div><div class="value">${data.breadth ? num(data.breadth.pct_up, 0) + "%" : "—"}</div><div class="sub">${data.breadth ? `${nf0.format(data.breadth.up)} al alza · ${nf0.format(data.breadth.down)} a la baja` : ""}</div></article>
        <article class="stat"><div class="label">Curva 10a − 3m</div><div class="value">${num(data.curve, 2)}</div><div class="sub">10 años ${num(data.us10y, 2)}% · 3 meses ${num(data.us3m, 2)}%</div></article>
      </div>
    </div>
    <div class="split">
      <section class="card"><h2>De qué sale el número</h2><table><tbody>${(data.parts || []).map((part) => `<tr><td>${esc(part.name)}</td>${tdNum(num(part.score, 0))}<td class="num">${num(part.weight * 100, 0)}%</td></tr>`).join("")}</tbody></table>
        <p class="meta">Dólar hoy ${pct(data.dollar)} · Oro ${pct(data.gold)} · Brent ${pct(data.brent)} · Sesgo de siete índices ${pct(data.day_change)}</p>
      </section>
      <section class="card"><h2>Sectores de EEUU, hoy</h2><table><tbody>${(data.sectors || []).map((row) => `<tr><td>${esc(row.name)}</td>${tdNum(pct(row.change_pct))}</tr>`).join("")}</tbody></table></section>
    </div>`;
}

async function renderNoticias() {
  loading("Reuniendo titulares…");
  const data = await api("/api/noticias");
  view.innerHTML = `
    ${head("Noticias", "Al minuto, en español", data.note || "")}
    ${banner(data)}
    <div class="grid two">${(data.sections || []).map((section) => `<section class="card"><h2>${esc(section.title)}</h2><ul class="news-list">${(section.items || []).map(newsItem).join("") || "<li>Sin piezas</li>"}</ul></section>`).join("")}</div>`;
}

async function renderResultados() {
  loading("Montando el calendario…");
  const data = await api("/api/resultados");
  const groups = new Map();
  for (const item of data.items || []) {
    if (!groups.has(item.date)) groups.set(item.date, []);
    groups.get(item.date).push(item);
  }
  view.innerHTML = `
    ${head("Resultados", "Quién presenta, y el consenso", data.note || "")}
    ${banner(data)}
    ${[...groups.entries()].map(([date, items]) => `<section class="card" style="margin-bottom:12px"><h2>${esc(new Date(date + "T12:00:00").toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long" }))}</h2>
      <table><thead>${th(["Empresa", "Plaza", "Hora", "BPA est.*", "BPA real*", "Sorpresa*"])}</thead><tbody>
        ${items.map((row) => `<tr class="clickable" data-symbol="${esc(row.symbol)}"><td><div class="name">${esc(row.name)}</div><div class="sym">${esc(row.symbol)}</div></td><td>${esc(REGION[row.region] || row.region)}</td><td>${esc(SESSION[row.session] || "")}</td>${tdNum(num(row.eps_estimate))}${tdNum(num(row.eps_actual))}${tdNum(pct(row.surprise_pct, 1))}</tr>`).join("")}
      </tbody></table></section>`).join("") || "<p>Sin presentaciones en la ventana.</p>"}`;
  bindRows();
}

async function renderSentimiento() {
  loading("Leyendo el ánimo…");
  const data = await api("/api/sentimiento");
  const fear = data.fear || {};
  const prev = fear.previous || {};
  view.innerHTML = `
    ${head("Sentimiento", fear.label ? fear.label[0].toUpperCase() + fear.label.slice(1) : "Ánimo", data.note || "")}
    ${banner(data)}
    <div class="grid four">
      <article class="card stat"><div class="label">CNN ahora</div><div class="value">${num(fear.score, 0)}</div><div class="sub">${esc(fear.label || "")}</div></article>
      <article class="card stat"><div class="label">Hace una semana</div><div class="value">${num(prev.semana, 0)}</div></article>
      <article class="card stat"><div class="label">Hace un mes</div><div class="value">${num(prev.mes, 0)}</div></article>
      <article class="card stat"><div class="label">Hace un año</div><div class="value">${num(prev["año"], 0)}</div></article>
    </div>
    <section class="card" style="margin-top:14px"><h2>VIX, seis meses</h2>${spark(data.vix_spark, 680, 120)}<p class="meta">Último ${num(data.vix, 2)}. La temperatura compuesta está en ${num(data.temperature, 0)} (${esc(data.label || "")}).</p></section>`;
}

async function renderCartera() {
  loading("Marcando la cartera de papel…");
  const data = await api("/api/cartera");
  const decision = data.decision || {};
  view.innerHTML = `
    ${head("Cartera modelo", "Diez nombres, reglas a la vista", "No es una recomendación. Es un papel de 100.000 euros que esta terminal revisa cada día laborable.")}
    <p class="warn">${esc(data.disclaimer || "")}</p>
    ${banner(data)}
    <div class="decision"><strong>${esc(decision.date || "")} · ${esc(decision.action || "")}</strong><p>${esc(decision.reason || "")}</p></div>
    <div class="grid four">
      <article class="card stat"><div class="label">Valor</div><div class="value">${data.value_eur == null ? "—" : nf0.format(data.value_eur) + " €"}</div><div class="sub">desde el ${esc(data.inception || "")}</div></article>
      <article class="card stat"><div class="label">Hoy</div><div class="value">${pct(data.day_pct)}</div></article>
      <article class="card stat"><div class="label">Cartera, base 100</div><div class="value">${num(data.portfolio_index, 1)}</div></article>
      <article class="card stat"><div class="label">Frente a la referencia</div><div class="value">${pct(data.vs_blend, 1)}</div><div class="sub">referencia ${num(data.blend_index, 1)}</div></article>
    </div>
    <section class="card" style="margin:14px 0">
      <h2>Crecimiento</h2>
      ${growthChart(data.curve)}
    </section>
    <section class="card" style="margin-bottom:14px">
      <h2>Compras y ventas</h2>
      <p class="meta">La lista la escribe el propio programa, no una persona ni un modelo. Un día laborable, como mucho una venta y su compra.</p>
      ${tradeRows(data.trades)}
    </section>
    <section class="card"><table><thead>${th(["Empresa", "Peso*", "Precio*", "Hoy*", "Desde la compra*", "Nota*", "Valor €*"])}</thead><tbody>
      ${(data.holdings || []).map((row) => `<tr class="clickable" data-symbol="${esc(row.symbol)}"><td><div class="name">${esc(row.name)}</div><div class="sym">${esc(row.symbol)} · ${esc(row.region_label || "")} · ${esc(row.sector_label || "")}</div></td>${tdNum(num(row.weight, 1) + "%")}${tdNum(num(row.price))}${tdNum(pct(row.change_pct))}${tdNum(pct(row.gain_pct, 1))}${tdNum(num(row.score, 0))}${tdNum(nf0.format(row.value_eur || 0))}</tr>`).join("")}
    </tbody></table></section>
    <section class="card" style="margin-top:14px"><h2>Las reglas</h2><ol class="rules">${(data.rules || []).map((rule) => `<li>${esc(rule)}</li>`).join("")}</ol>
      <p class="meta">S&P ${num((data.benchmarks || {}).spx, 1)} · Euro Stoxx ${num((data.benchmarks || {}).stoxx, 1)} · TSX ${num((data.benchmarks || {}).tsx, 1)}. Miedo CNN ${data.fear && data.fear.score != null ? num(data.fear.score, 0) : "—"}.</p>
    </section>`;
  bindRows();
}

async function renderFicha(symbol) {
  loading(`Abriendo ${symbol}…`);
  const data = await api(`/api/ficha?symbol=${encodeURIComponent(symbol)}`);
  const reco = data.recommendation;
  const recoText = reco ? `compra fuerte ${reco.strong_buy || 0} · compra ${reco.buy || 0} · mantener ${reco.hold || 0} · venta ${reco.sell || 0} · venta fuerte ${reco.strong_sell || 0}` : "Sin recuento";
  view.innerHTML = `
    <p class="kicker">${esc(data.exchange || "")} · ${esc(data.sector || "")}${data.industry ? " · " + esc(data.industry) : ""}</p>
    <div class="ficha-top">
      <h1>${esc(data.name)}</h1>
      <div><div class="value" style="font-family:var(--serif);font-size:40px">${num(data.price)} <small style="font-size:16px">${esc(data.currency || "")}</small></div><div>${pct(data.change_pct)} hoy</div></div>
    </div>
    ${banner(data)}
    <p class="note">${esc(data.note || "")}</p>
    ${area(data.points)}
    <div class="grid four" style="margin-top:14px">
      ${[["Capital", cap(data.market_cap)], ["PER", num(data.pe, 1)], ["PER fwd", num(data.forward_pe, 1)], ["Dividendo", data.dividend_yield == null ? "—" : num(data.dividend_yield, 2) + "%"], ["ROE", data.roe == null ? "—" : num(data.roe, 1) + "%"], ["Margen", data.margin == null ? "—" : num(data.margin, 1) + "%"], ["Ingresos", pct(data.revenue_growth, 1)], ["Deuda", data.debt == null ? "—" : num(data.debt, 2) + "×"]].map(([label, value]) => `<article class="card stat"><div class="label">${label}</div><div class="value" style="font-size:22px">${value}</div></article>`).join("")}
    </div>
    <div class="split" style="margin-top:14px">
      <section class="card">
        <h2>Qué hace</h2>
        <p class="summary">${esc(data.summary || "Sin descripción en la fuente.")}</p>
        <p class="meta">Máximo 52 semanas ${num(data.fifty_two_high)} · mínimo ${num(data.fifty_two_low)} · próxima presentación ${esc(data.earnings_date || "sin fecha")}</p>
        <h2 style="margin-top:16px">Consenso de analistas</h2>
        <p>${esc(recoText)}</p>
        <table><thead>${th(["Periodo", "BPA*", "Hace un año*", "Ingresos*", "Analistas*"])}</thead><tbody>
          ${(data.trend || []).map((row) => `<tr><td>${esc(row.period)}</td>${tdNum(num(row.eps))}${tdNum(num(row.eps_year_ago))}${tdNum(row.revenue == null ? "—" : cap(row.revenue))}${tdNum(row.analysts == null ? "—" : String(row.analysts))}</tr>`).join("") || "<tr><td colspan='5'>Sin estimaciones</td></tr>"}
        </tbody></table>
      </section>
      <section class="card"><h2>Noticias</h2><ul class="news-list">${(data.news || []).map(newsItem).join("") || "<li>Sin titulares recientes en español</li>"}</ul></section>
    </div>`;
}

function bindRows() {
  view.querySelectorAll("tr.clickable").forEach((row) => {
    row.addEventListener("click", () => {
      location.hash = `#ficha/${encodeURIComponent(row.dataset.symbol)}`;
    });
  });
}

async function show() {
  const raw = (location.hash || "#hoy").slice(1);
  const [path, query] = raw.split("?");
  const [route, arg] = path.split("/");
  nav.querySelectorAll("a").forEach((link) => {
    link.classList.toggle("active", link.dataset.route === (route === "ficha" ? "" : route));
  });
  try {
    if (route === "ficha" && arg) await renderFicha(decodeURIComponent(arg));
    else if (routes[route]) await routes[route]();
    else await renderHoy();
  } catch (error) {
    view.innerHTML = `<h1>No se pudo cargar</h1><p class="warn">${esc(error.message || error)}</p>`;
  }
}

const input = document.querySelector("#q");
const suggest = document.querySelector("#suggest");
let timer = 0;
input.addEventListener("input", () => {
  clearTimeout(timer);
  const q = input.value.trim();
  if (q.length < 1) { suggest.hidden = true; return; }
  timer = setTimeout(async () => {
    try {
      const data = await api(`/api/buscar?q=${encodeURIComponent(q)}`);
      const items = data.items || [];
      if (!items.length) { suggest.hidden = true; return; }
      suggest.innerHTML = items.map((item) => `<button type="button" data-symbol="${esc(item.symbol)}"><b>${esc(item.symbol)}</b> ${esc(item.name)}<span>${esc(item.exchange || "")}</span></button>`).join("");
      suggest.hidden = false;
      suggest.querySelectorAll("button").forEach((button) => {
        button.addEventListener("click", () => {
          suggest.hidden = true;
          input.value = "";
          location.hash = `#ficha/${encodeURIComponent(button.dataset.symbol)}`;
        });
      });
    } catch {
      suggest.hidden = true;
    }
  }, 180);
});
document.querySelector("#search").addEventListener("submit", (event) => {
  event.preventDefault();
  const first = suggest.querySelector("button");
  if (first) first.click();
});
document.addEventListener("click", (event) => {
  if (!event.target.closest("#search")) suggest.hidden = true;
});
function tick() {
  const now = new Date();
  document.querySelector("#clock").textContent = now.toLocaleString("es-ES", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}
tick();
setInterval(tick, 30000);
window.addEventListener("hashchange", show);
if (!location.hash) location.hash = "#hoy";
else show();
