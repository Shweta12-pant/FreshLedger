import { icon } from "./icons.js";

const num = new Intl.NumberFormat("en-IN");
const shortDate = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", timeZone: "UTC" });
const fullDate = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
const longDate = new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" });

export const pages = {
  overview: { label: "Overview", icon: "grid" },
  inventory: { label: "Inventory", icon: "box" },
  forecast: { label: "Forecast", icon: "chart" },
  activity: { label: "Activity", icon: "activity" },
};

export function safe(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

export const quantity = (value) => value == null ? "—" : num.format(value);
export const count = (value, singular, plural = singular + "s") => quantity(value) + " " + (value === 1 ? singular : plural);
export const dateText = (value) => value ? shortDate.format(new Date(value)) : "—";
export const dateHeading = (value) => value ? fullDate.format(new Date(value)) : "";
export const timeText = (value) => value ? longDate.format(new Date(value)) : "—";
export const method = (value) => ({ random_forest: "Random forest", moving_average: "7-day moving average" })[value] ?? "Awaiting history";

export function action(task, label, symbol, style = "", id = "", accessibleLabel = "") {
  return `<button class="button ${style}" type="button" data-action="${task}" ${id !== "" ? `data-id="${id}"` : ""}${accessibleLabel ? ' aria-label="' + safe(accessibleLabel) + '"' : ""}>${symbol ? icon(symbol, 16) : ""}${label}</button>`;
}

function routeLink(page, text) {
  return `<a class="text-link" href="#${page}">${text}${icon("arrow", 14)}</a>`;
}

function header(title, description, actions = "") {
  return `<div class="page-head"><div><h1 tabindex="-1">${title}</h1><p>${description}</p></div>${actions ? '<div class="action-group">' + actions + '</div>' : ""}</div>`;
}

function kpi({ label, value, unit, caption, symbol, tone = "", extra = "" }) {
  const reading = quantity(value);
  return `<article class="card ${tone === "accent" ? "emphasis" : ""}">
    <h3 class="kpi-label" data-tone="${tone}">${icon(symbol, 16)}${label}</h3>
    <p class="kpi-reading"><strong class="kpi-value${reading.length > 7 ? " long-value" : ""}">${reading}</strong>${value == null ? "" : '<span class="kpi-unit">' + unit + '</span>'}</p>
    <p class="kpi-caption">${caption}</p>${extra}</article>`;
}

function expiryDistribution(products) {
  const days = [0, 0, 0, 0];
  for (const product of products) {
    for (const batch of product.batches) {
      if (batch.days_to_expiry >= 0 && batch.days_to_expiry < days.length) days[batch.days_to_expiry] += batch.quantity;
    }
  }
  if (!days.some(Boolean)) return "";
  const labels = ["0d", "1d", "2d", "3d"];
  const max = Math.max(...days);
  return `<div class="mini-expiry" role="group" aria-label="Units expiring by day">${days.map((units, index) => {
    const label = index === 0 ? "Today" : "In " + count(index, "day");
    return `<span><meter min="0" max="${max}" value="${units}" aria-label="${label}: ${count(units, "unit")} expiring" title="${label}: ${count(units, "unit")}"></meter><small aria-hidden="true">${labels[index]}</small></span>`;
  }).join("")}</div>`;
}

export function options(products, current) {
  return products.map((product) => `<option value="${product.id}" ${product.id === current ? "selected" : ""}>${safe(product.name)}</option>`).join("");
}

function chart(products, current, large = false) {
  const title = large ? "Sales and projections" : "Demand forecast";
  return `<section class="panel chart-panel"><div class="panel-head chart-head"><div>
      <h2>${title}</h2><p>14 days recorded · 7 days projected</p>
    </div>${products.length ? `<select id="chart-product" class="chart-select" aria-label="Forecast product">${options(products, current)}</select>` : ""}</div>
    ${products.length ? `<div class="legend">
      <span><i aria-hidden="true"></i>Recorded sales</span>
      <span><i class="legend-projected" aria-hidden="true"></i>Forecast</span>
      <span id="stockout-legend" hidden><i class="legend-stockout" aria-hidden="true"></i>Stockout day</span>
    </div>
    <div class="chart-area ${large ? "large" : ""}"><canvas id="demand-chart" role="img" aria-label="Daily sales and forecast in units. Daily values are available on the forecast page."></canvas><div id="chart-tip" class="chart-tip" aria-hidden="true" hidden></div></div>
    <div class="chart-foot"><div class="chart-summary" id="chart-foot" role="status">Loading sales history…</div>
    ${large ? "" : routeLink("forecast", "Daily values")}</div>` : '<p class="empty">Add a product to start tracking demand.</p>'}</section>`;
}

function priorityItems(products) {
  const rows = [];
  const expired = products.filter((item) => item.expired_units).sort((a, b) => b.expired_units - a.expired_units)[0];
  if (expired) {
    const batch = expired.batches.find((entry) => entry.days_to_expiry < 0);
    rows.push([expired, batch?.expires_on, "Expired", count(expired.expired_units, "unit") + " to review", "urgent"]);
  }
  const upcoming = products.filter((item) => item.expiring_units).map((item) => ({
    item, batch: item.batches.find((entry) => entry.days_to_expiry >= 0),
  })).filter((entry) => entry.batch);
  upcoming.sort((a, b) => a.batch.expires_on.localeCompare(b.batch.expires_on) || b.batch.quantity - a.batch.quantity);
  if (upcoming.length) {
    const { item, batch } = upcoming[0];
    rows.push([item, batch.expires_on, "Expiry", count(batch.quantity, "unit") + (batch.days_to_expiry === 0 ? (batch.quantity === 1 ? " expires today" : " expire today") : " in the next batch due"), "soon"]);
  }
  const waste = products.filter((item) => item.estimated_waste_units).sort((a, b) => b.estimated_waste_units - a.estimated_waste_units)[0];
  if (waste) {
    const batch = waste.batches.find((entry) => entry.estimated_waste_units > 0);
    rows.push([waste, batch?.expires_on, "Waste risk", count(waste.estimated_waste_units, "unit") + " may remain at expiry", "risk"]);
  }
  const shortfall = products.filter((item) => item.shortfall_units)
    .sort((a, b) => a.first_shortfall.localeCompare(b.first_shortfall) || b.shortfall_units - a.shortfall_units)[0];
  if (shortfall) rows.push([shortfall, shortfall.first_shortfall, "Stockout", count(shortfall.shortfall_units, "unit") + " short over 7 days", "neutral"]);
  return rows;
}

function alerts(products) {
  const candidates = priorityItems(products);
  return `<section class="panel alert-panel"><div class="panel-head"><div><h2>Needs attention</h2><p>${candidates.length ? "First item to review in each category" : "Expiry and stockout alerts"}</p></div></div>
    ${candidates.length ? '<ul class="alert-list">' + candidates.map(([product, date, label, message, tone]) => `<li><button class="alert-item" data-action="detail" data-id="${product.id}" type="button">
      <span class="stock-stamp ${tone}"><small>${label}</small><time datetime="${safe(date)}">${dateText(date)}</time></span>
      <span class="alert-copy"><strong>${safe(product.name)}</strong><small>${safe(message)}</small></span>${icon("chevron", 15)}</button></li>`).join("") + '</ul>' : '<p class="empty">No expiry or stockout alerts today.</p>'}</section>`;
}

function stockStatus(item) {
  if (item.expired_units) return ["Expired", "urgent"];
  if (item.low_stock) return ["Low stock", "urgent"];
  if (item.expiring_units) return ["Expiring soon", "soon"];
  if (item.shortfall_units) return ["Stockout risk", "risk"];
  return ["In range", "good"];
}

const categoryIcon = { Dairy: "drop", Produce: "leaf", Bakery: "bread", Chilled: "snow" };

export const nextExpiry = (product) => product.batches.find((batch) => batch.days_to_expiry >= 0);

export function inventoryTable(items) {
  if (!items.length) return '<p class="empty">No products match this view. Try a different search or filter.</p>';
  return `<div class="table-wrap" tabindex="0" role="region" aria-label="Inventory table"><table class="catalog-table">
    <caption class="sr-only">Inventory by product</caption>
    <thead><tr><th scope="col">Product</th><th scope="col" class="optional-column">Category</th><th scope="col" class="numeric">Sellable stock</th>
    <th scope="col" class="optional-column">Next expiry</th><th scope="col" class="optional-column numeric">7-day demand</th><th scope="col">Status</th></tr></thead>
    <tbody>${items.map((item) => {
      const [status, tone] = stockStatus(item);
      const expiry = nextExpiry(item);
      const symbol = Object.hasOwn(categoryIcon, item.category) ? categoryIcon[item.category] : "box";
      return `<tr><td><div class="table-name"><span class="category-icon">${icon(symbol, 17)}</span>
        <span><button type="button" data-action="detail" data-id="${item.id}">${safe(item.name)}<small aria-hidden="true">${safe(item.sku)}</small></button></span></div></td>
        <td class="optional-column">${safe(item.category)}</td><td class="numeric"><strong>${quantity(item.sellable_units)}</strong><span class="unit-word"> units</span></td>
        <td class="optional-column mono-text">${dateText(expiry?.expires_on)}</td><td class="optional-column numeric">${quantity(item.forecast?.units)}</td><td><span class="pill ${tone}">${status}</span>${expiry ? `<small class="mobile-expiry">Exp. ${dateText(expiry.expires_on)}</small>` : ""}</td></tr>`;
    }).join("")}</tbody></table></div>`;
}

export function overview(data, current) {
  const { products, summary } = data;
  const expiring = products.filter((item) => item.expiring_units).length;
  const description = summary.expiring_units
    ? "<strong>" + count(summary.expiring_units, "unit") + "</strong> due to expire within 3 days across " + count(expiring, "product") + "."
    : products.length ? "No units are due to expire within the next 3 days." : "Add a product and receive a batch to start tracking expiry.";
  return header("Inventory overview", description, action("sale", "Record sale", "sale") + action("receipt", "Receive stock", "plus", "primary")) +
    `<section class="metric-tray" aria-labelledby="metrics-heading"><h2 class="tray-title" id="metrics-heading">Stock summary</h2><div class="kpi-grid">
      ${kpi({label: "Sellable stock", value: summary.sellable_units, unit: "units", caption: count(summary.products, "product") + " in the catalog", symbol: "box"})}
      ${kpi({label: "Expiring soon", value: summary.expiring_units, unit: "units", caption: "Today through the next 3 days", symbol: "clock", tone: "accent", extra: expiryDistribution(products)})}
      ${kpi({label: "Projected waste", value: summary.estimated_waste_units, unit: "units", caption: "May remain when a batch expires", symbol: "leaf", tone: "warning"})}
      ${kpi({label: "Stockout risk", value: summary.projected_stockout_products, unit: "products", caption: "At risk over 7 days", symbol: "alert", tone: "danger"})}
    </div></section><div class="overview-grid">${alerts(products)}${chart(products, current)}</div>
    <section class="panel"><div class="panel-head snapshot-head"><h2>Inventory snapshot</h2>${routeLink("inventory", "View inventory")}</div>
      ${products.length ? inventoryTable(products.slice(0, 5)) : '<p class="empty"><strong>Your catalog is empty.</strong>' + action("product", "Add your first product", "plus") + '</p>'}</section>`;
}

export function inventory(data, filters) {
  const categories = [...new Set(data.products.map((product) => product.category))].sort();
  const choices = [["all", "All statuses"], ["expiry", "Expiring soon"], ["expired", "Expired stock"], ["low", "Low stock"], ["risk", "Stockout risk"]];
  const sorting = [["name", "Product name"], ["expiry", "Next expiry"]];
  return header("Inventory", "Find products and review what's left in each batch.", action("product", "Add product", "plus") + action("receipt", "Receive stock", "plus", "primary")) +
    `<section class="panel"><div class="panel-head"><h2>Product catalog</h2></div>
      <div class="filters"><label class="search">${icon("search", 17)}<input type="search" id="filter-query" aria-label="Search products" placeholder="Search name or SKU" value="${safe(filters.query)}"></label>
      <select id="filter-category" aria-label="Filter by category"><option value="">All categories</option>
      ${categories.map((category) => `<option value="${safe(category)}" ${filters.category === category ? "selected" : ""}>${safe(category)}</option>`).join("")}</select>
      <select id="filter-status" aria-label="Filter by stock status">${choices.map(([value, label]) => `<option value="${value}" ${filters.status === value ? "selected" : ""}>${label}</option>`).join("")}</select>
      <select id="filter-sort" aria-label="Sort inventory">${sorting.map(([value, label]) => `<option value="${value}" ${filters.sort === value ? "selected" : ""}>${label}</option>`).join("")}</select></div>
      <div id="inventory-results"></div><p class="table-caption" id="result-count" role="status"></p></section>`;
}

export function forecastPage(data, current) {
  const run = data.forecast_run;
  const detail = run ? "Updated " + timeText(run.completed_at) + " · " + count(run.products_forecast, "product") + " forecast" : "Forecasts appear once the daily forecast job runs.";
  return header("Demand forecast", safe(detail)) +
    `<div class="forecast-layout">${chart(data.products, current, true)}
      <section class="panel" id="model-panel"><div class="panel-head"><h2>Model evaluation</h2></div><p class="empty">Select a product to see forecast accuracy.</p></section></div>
    <section class="panel" id="daily-panel"><div class="panel-head"><h2>Daily sales and projections</h2></div><p class="empty">Daily values appear when sales history is available.</p></section>`;
}

function metric(value) {
  return value == null ? "—" : Number(value).toFixed(2) + " units";
}

export function modelPanel(record) {
  const result = record?.forecast;
  return `<div class="panel-head"><div><h2>Model evaluation</h2><p>Mean absolute error (MAE) on recent sales</p></div></div>
    ${result ? `<dl class="model-list">
    <div><dt>Published method</dt><dd>${method(result.method)}</dd></div>
    <div><dt>Moving average MAE</dt><dd>${metric(result.baseline_mae)}</dd></div>
    <div><dt>Random forest MAE</dt><dd>${metric(result.forest_mae)}</dd></div>
    <div><dt>Usable history</dt><dd>${count(result.history_days, "day")}</dd></div>
    <div><dt>Validation predictions</dt><dd>${quantity(result.evaluation_points)}</dd></div>
    </dl><p class="model-note">${result.evaluation_points ? "Lower MAE means predictions were closer to recorded sales." : "More recorded days are needed to compare both methods."}</p>`
    : '<p class="empty">More recent sales history is needed to forecast demand for this product.</p>'}`;
}

export function dailyPanel(record) {
  const future = record.prediction.map((point) => ({ ...point, label: "Forecast", tone: "risk" }));
  const past = [...record.history].reverse().map((point) => ({
    ...point, label: point.stockout ? "Stockout day" : point.units == null ? "No record" : "Recorded sale",
    tone: point.stockout ? "urgent" : point.units == null ? "neutral" : "good",
  }));
  return `<div class="panel-head"><div><h2>Daily sales and projections</h2><p>${safe(record.product.name)} · Units per day</p></div></div>
    <div class="table-wrap" role="region" aria-label="Daily sales and projections table" tabindex="0"><table>
    <caption class="sr-only">Daily units for ${safe(record.product.name)}</caption>
    <thead><tr><th scope="col">Date</th><th scope="col" class="numeric">Units</th><th scope="col">Source</th></tr></thead>
    <tbody>${[...future, ...past].map((point) => `<tr><td class="mono-text"><time datetime="${safe(point.day)}">${dateHeading(point.day)}</time></td><td class="numeric">${quantity(point.units)}</td>
    <td><span class="pill ${point.tone}">${point.label}</span></td></tr>`).join("")}</tbody></table></div>`;
}

const movementTypes = { receipt: ["Receipt", "good"], sale: ["Sale", "neutral"], discard: ["Discard", "urgent"] };

export function activity() {
  return header("Stock activity", "Review what came in, what sold, and what was discarded.", action("sale", "Record sale", "sale") + action("receipt", "Receive stock", "plus", "primary")) +
    '<section class="panel"><div class="panel-head"><h2>Movement ledger</h2></div><div id="activity-results" aria-busy="true"><p class="loading" role="status">Loading activity…</p></div></section>';
}

export function movementTable(items, more) {
  if (!items.length) return '<p class="empty">No movements yet. Receive stock to make the first ledger entry.</p>';
  return `<div class="table-wrap" role="region" aria-label="Movement ledger" tabindex="0"><table class="movement-table">
    <caption class="sr-only">Inventory movements, newest first</caption>
    <thead><tr><th scope="col" class="activity-extra">Time</th><th scope="col">Product</th><th scope="col">Type</th><th scope="col" class="numeric">Units</th><th scope="col" class="activity-extra">Details</th></tr></thead>
    <tbody>${items.map((item) => {
      const [label, tone] = movementTypes[item.kind];
      const details = item.kind === "sale"
        ? item.details.allocations.map((row) => row.batch_code + " × " + row.units).join(", ")
        : item.details.batch_code + (item.kind === "discard" ? " · " + item.details.reason : " · Expires " + dateText(item.details.expires_on));
      const timestamp = `<time datetime="${safe(item.created_at)}">${timeText(item.created_at)}</time>`;
      return `<tr><td class="activity-extra mono-text">${timestamp}</td><td><strong>${safe(item.product_name)}</strong>
        <span class="activity-compact">${timestamp}<small>${safe(details)}</small></span></td>
        <td><span class="pill ${tone}">${label}</span></td><td class="numeric">${item.kind === "receipt" ? "+" : "−"}${quantity(item.units)}</td>
        <td class="movement-details activity-extra">${safe(details)}</td></tr>`;
    }).join("")}</tbody></table></div>${more ? '<div class="activity-footer">' + action("more", "Load older activity") + '</div>' : ""}`;
}

export function productDetail(item) {
  const alerts = [];
  if (item.expired_units) alerts.push(count(item.expired_units, "expired unit") + " still in stock.");
  if (item.estimated_waste_units) alerts.push(count(item.estimated_waste_units, "unit") + " may remain at expiry.");
  if (item.shortfall_units) alerts.push("Projected shortfall of " + count(item.shortfall_units, "unit") + ", starting " + dateText(item.first_shortfall) + ".");
  return `<div class="dialog-body"><div class="action-group">${action("receipt", "Receive stock", "plus", "primary", item.id)}
    ${action("sale", "Record sale", "sale", "", item.id)}
    ${action("product", "Edit product", "edit", "quiet", item.id)}
    ${action("show-forecast", "Forecast", "chart", "quiet", item.id)}</div>
    ${alerts.length ? '<p class="notice">' + safe(alerts.join(" ")) + '</p>' : ""}
    ${item.batches.length ? `<div class="table-wrap" role="region" aria-label="Stock batches" tabindex="0"><table>
      <caption class="sr-only">Batches for ${safe(item.name)}</caption>
      <thead><tr><th scope="col">Batch</th><th scope="col" class="numeric">Units</th><th scope="col">Expiry</th><th scope="col" class="numeric">Projected waste</th><th scope="col">Action</th></tr></thead>
      <tbody>${item.batches.map((batch) => `<tr><td class="sku">${safe(batch.code)}</td><td class="numeric">${quantity(batch.quantity)}</td>
        <td><span class="stock-stamp ${batch.days_to_expiry < 0 ? "urgent" : "neutral"}"><small>${batch.days_to_expiry < 0 ? "Expired" : "Expires"}</small><time datetime="${safe(batch.expires_on)}">${dateText(batch.expires_on)}</time></span></td>
        <td class="numeric">${quantity(batch.estimated_waste_units)}</td><td>${action("discard", "Discard", "", "quiet", batch.id, "Discard units from batch " + batch.code)}</td></tr>`).join("")}</tbody></table></div>`
    : '<p class="empty">No units are left in this product’s batches.</p>'}</div>`;
}
