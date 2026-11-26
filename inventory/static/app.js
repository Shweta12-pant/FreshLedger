import { createChart } from "./chart.js";
import { icon } from "./icons.js";
import {
  activity, count, dailyPanel, forecastPage, inventory, inventoryTable, method, modelPanel, movementTable,
  nextExpiry, options, overview, pages, productDetail, quantity, safe,
} from "./view.js";

const main = document.querySelector("#main");
const dialog = document.querySelector("#dialog");
const navigation = document.querySelector("#navigation");
const toast = document.querySelector("#toast");
const state = {
  data: null,
  product: null,
  page: "overview",
  filters: { query: "", category: "", status: "all", sort: "name" },
  movements: [],
  next: null,
  pageGeneration: 0,
  chartGeneration: 0,
  cleanChart: null,
  saving: false,
};
let toastTimer;
let lastPage = null;
let modalTrigger = null;
const catalogSort = new Intl.Collator("en-IN", { numeric: true });
const headerDate = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

function notify(message) {
  toast.textContent = message;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => { toast.textContent = ""; }, 6000);
}

async function api(path, init = {}) {
  const response = await fetch(path, {
    ...init,
    headers: { Accept: "application/json", ...(init.body ? { "Content-Type": "application/json" } : {}) },
    signal: AbortSignal.timeout(15000),
  });
  let payload;
  try { payload = await response.json(); } catch { payload = null; }
  if (!response.ok) {
    const detail = payload?.detail;
    throw new Error(Array.isArray(detail) ? detail.join(" · ") : detail || "Request failed (" + response.status + ").");
  }
  return payload;
}

function renderNavigation() {
  if (lastPage === state.page) return;
  lastPage = state.page;
  navigation.innerHTML = Object.entries(pages).map(([id, page]) =>
    `<a class="nav-link" href="#${id}" ${state.page === id ? 'aria-current="page"' : ""}>${icon(page.icon, 17)}${page.label}</a>`,
  ).join("");
  document.querySelector("#page-crumb").textContent = pages[state.page].label;
  document.title = "FreshLedger · " + pages[state.page].label;
}

function readRoute(focus = false) {
  const name = location.hash.slice(1);
  if (name === "main") return;
  state.page = Object.hasOwn(pages, name) ? name : "overview";
  render();
  if (focus && state.data) {
    window.scrollTo(0, 0);
    main.querySelector("h1")?.focus({ preventScroll: true });
  }
}

function currentProduct(id = state.product) {
  return state.data.products.find((product) => product.id === id);
}

async function loadDashboard() {
  const data = await api("/api/dashboard");
  state.data = data;
  if (!currentProduct()) state.product = (data.products.find(({ sku }) => sku === "DAI-101") || data.products[0])?.id ?? null;
  document.querySelector("#workspace-mode").textContent = data.data_mode === "demo" ? "Synthetic sales history" : "Live inventory";
  const date = document.querySelector("#store-date");
  date.dateTime = data.as_of;
  date.innerHTML = icon("calendar", 15) + headerDate.format(new Date(data.as_of));
  document.querySelector("#demo-label").hidden = data.data_mode !== "demo";
}

function render() {
  if (!state.data) return;
  state.cleanChart?.();
  state.cleanChart = null;
  state.pageGeneration += 1;
  state.chartGeneration += 1;
  renderNavigation();
  main.setAttribute("aria-busy", "false");
  if (state.page === "overview") {
    main.innerHTML = overview(state.data, state.product);
    void loadChart();
  } else if (state.page === "inventory") {
    main.innerHTML = inventory(state.data, state.filters);
    renderInventory();
  } else if (state.page === "forecast") {
    main.innerHTML = forecastPage(state.data, state.product);
    void loadChart();
  } else {
    main.innerHTML = activity();
    void loadMovements();
  }
}

function renderInventory() {
  const { query, category, status, sort } = state.filters;
  const search = query.trim().toLowerCase();
  const available = state.data.products.filter((item) => {
    const matchesSearch = (item.name + " " + item.sku).toLowerCase().includes(search);
    const matchesStatus = status === "all" ||
      (status === "expiry" && item.expiring_units > 0) ||
      (status === "expired" && item.expired_units > 0) ||
      (status === "low" && item.low_stock) ||
      (status === "risk" && item.shortfall_units > 0);
    return matchesSearch && matchesStatus && (!category || item.category === category);
  });
  const expiries = sort === "expiry" ? new Map(available.map((item) => [item.id, nextExpiry(item)?.days_to_expiry ?? Infinity])) : null;
  available.sort((a, b) => {
    const byExpiry = expiries ? expiries.get(a.id) - expiries.get(b.id) : 0;
    return byExpiry || catalogSort.compare(a.name, b.name) || a.id - b.id;
  });
  document.querySelector("#inventory-results").innerHTML = inventoryTable(available);
  document.querySelector("#result-count").textContent = quantity(available.length) + " of " + quantity(state.data.products.length) + " products";
}

async function loadChart() {
  if (!state.product) return;
  const generation = ++state.chartGeneration;
  const foot = document.querySelector("#chart-foot");
  foot.textContent = "Loading sales history…";
  const canvas = document.querySelector("#demand-chart");
  canvas.parentElement.setAttribute("aria-busy", "true");
  try {
    const record = await api("/api/products/" + state.product + "/forecast");
    if (generation !== state.chartGeneration) return;
    state.cleanChart?.();
    state.cleanChart = createChart(canvas, document.querySelector("#chart-tip"), record.history, record.prediction);
    document.querySelector("#stockout-legend").hidden = !record.history.some((point) => point.stockout);
    const result = record.forecast;
    foot.innerHTML = result
      ? "<strong>" + quantity(result.units) + " units forecast</strong><span>" + method(result.method) + "</span>"
      : "No current forecast for this product.";
    if (state.page === "forecast") {
      document.querySelector("#model-panel").innerHTML = modelPanel(record);
      document.querySelector("#daily-panel").innerHTML = dailyPanel(record);
    }
  } catch (error) {
    if (generation !== state.chartGeneration) return;
    state.cleanChart?.();
    state.cleanChart = null;
    canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
    document.querySelector("#stockout-legend").hidden = true;
    foot.textContent = "Could not load the forecast. " + error.message;
    if (state.page === "forecast") {
      document.querySelector("#model-panel").innerHTML = '<div class="panel-head"><h2>Model evaluation</h2></div><p class="empty">No model details loaded.</p>';
      document.querySelector("#daily-panel").innerHTML = '<div class="panel-head"><h2>Daily sales and projections</h2></div><p class="empty">No daily values loaded.</p>';
    }
  } finally {
    if (generation === state.chartGeneration) canvas.parentElement.setAttribute("aria-busy", "false");
  }
}

async function loadMovements(append = false) {
  const generation = state.pageGeneration;
  const element = document.querySelector("#activity-results");
  const before = append && state.next ? "?before=" + state.next : "";
  element.setAttribute("aria-busy", "true");
  try {
    const result = await api("/api/movements" + before);
    if (generation !== state.pageGeneration) return;
    state.movements = append ? [...state.movements, ...result.items] : result.items;
    state.next = result.next_before;
    element.innerHTML = movementTable(state.movements, state.next);
    if (append) (element.querySelector('[data-action="more"]') ?? element.querySelector(".table-wrap"))?.focus({ preventScroll: true });
  } catch (error) {
    if (generation !== state.pageGeneration) return;
    if (append) {
      notify("Could not load older activity. " + error.message);
      element.querySelector('[data-action="more"]').disabled = false;
    } else {
      element.innerHTML = '<p class="empty" role="alert">Could not load activity. ' + safe(error.message) + ' <button type="button" class="button" data-action="retry-activity">Retry activity</button></p>';
    }
  } finally {
    if (generation === state.pageGeneration) element.setAttribute("aria-busy", "false");
  }
}

function modal(title, subtitle, content) {
  if (!dialog.open) modalTrigger = document.activeElement;
  dialog.setAttribute("aria-labelledby", "dialog-title");
  if (subtitle) dialog.setAttribute("aria-describedby", "dialog-subtitle");
  else dialog.removeAttribute("aria-describedby");
  dialog.innerHTML = `<div class="dialog-head"><div><h2 id="dialog-title">${safe(title)}</h2>
    ${subtitle ? '<p id="dialog-subtitle">' + safe(subtitle) + "</p>" : ""}</div>
    <button type="button" class="icon-button" data-action="close" aria-label="Close dialog">${icon("x", 18)}</button></div>${content}`;
  if (!dialog.open) dialog.showModal();
  (dialog.querySelector("input, select") ?? dialog.querySelector('[data-action="close"]'))?.focus();
}

function form(title, subtitle, fields, submit, help = "") {
  modal(title, subtitle, `<form><div class="dialog-body"><div class="form-grid">${fields}</div>
    ${help ? '<p class="form-help" id="form-help">' + safe(help) + '</p>' : ""}
    <p class="form-error" role="alert" tabindex="-1" hidden></p></div><div class="dialog-footer">
    <button class="button" type="button" data-action="close">Cancel</button>
    <button class="button ${title === "Discard units" ? "danger" : "primary"}" type="submit">${submit}</button></div></form>`);
  const node = dialog.querySelector("form");
  if (help) node.setAttribute("aria-describedby", "form-help");
  return node;
}

function openProduct(id) {
  const product = currentProduct(id);
  const fields = `<label>Product name<input name="name" value="${safe(product?.name)}" maxlength="100" required></label>
    ${product ? "" : '<label>SKU<input name="sku" maxlength="32" pattern="[A-Za-z0-9][A-Za-z0-9_\\-]{0,31}" placeholder="DAI-104" required></label>'}
    <label>Category<input name="category" value="${safe(product?.category)}" maxlength="40" placeholder="Dairy" required></label>
    <label>Reorder point<input name="reorder_point" type="number" min="0" max="100000" value="${product?.reorder_point ?? 10}" required></label>`;
  const node = form(product ? "Edit product" : "Add product", product?.sku, fields, product ? "Save changes" : "Add product", "The product is flagged as low stock at or below its reorder point.");
  node.dataset.task = "product";
  if (product) node.dataset.id = product.id;
}

function openMovement(task, id) {
  if (!state.data.products.length) {
    openProduct(0);
    return;
  }
  const selection = id || (task === "sale"
    ? state.data.products.find((item) => item.sellable_units > 0)?.id
    : state.product) || state.data.products[0].id;
  const sale = task === "sale";
  const fields = `<label class="full">Product<select name="product_id" required>${options(state.data.products, selection)}</select></label>
    ${sale ? "" : '<label>Batch code<input name="batch_code" maxlength="32" pattern="[A-Za-z0-9][A-Za-z0-9_\\-]{0,31}" placeholder="LOT-202" required></label>'}
    <label>Units<input name="units" type="number" min="1" max="100000" inputmode="numeric" required></label>
    ${sale ? "" : `<label>Expiry date<input name="expires_on" type="date" min="${safe(state.data.as_of)}" required></label>`}`;
  const help = sale ? "Sales use the earliest-expiring sellable batches first." : "Use a unique batch code for this product.";
  const node = form(sale ? "Record sale" : "Receive stock", "", fields, sale ? "Record sale" : "Receive stock", help);
  node.dataset.task = task;
}

function openDiscard(id) {
  const product = state.data.products.find((item) => item.batches.some((batch) => batch.id === id));
  const batch = product?.batches.find((item) => item.id === id);
  if (!batch) return;
  const fields = `<label>Units<input name="units" type="number" min="1" max="${Math.min(batch.quantity, 100000)}" value="${Math.min(batch.quantity, 100000)}" required></label>
    <label>Reason<input name="reason" maxlength="120" value="${batch.days_to_expiry < 0 ? "Expired" : ""}" placeholder="Damaged packaging" required></label>`;
  const node = form("Discard units", product.name + " · " + batch.code, fields, "Confirm discard", "This reduces the batch quantity and records the reason in the activity ledger.");
  node.dataset.task = "discard";
  node.dataset.id = id;
}

function uuid() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join("-");
}

async function save(event) {
  const formNode = event.target;
  if (!formNode.matches("form")) return;
  event.preventDefault();
  if (state.saving) return;
  const { task, id } = formNode.dataset;
  const data = Object.fromEntries(new FormData(formNode));
  if ("units" in data) data.units = Number(data.units);
  if ("reorder_point" in data) data.reorder_point = Number(data.reorder_point);
  const errorNode = formNode.querySelector(".form-error");
  const submit = formNode.querySelector('[type="submit"]');
  const fingerprint = JSON.stringify(data);
  if (task !== "product") {
    if (formNode.dataset.fingerprint !== fingerprint) {
      formNode.dataset.fingerprint = fingerprint;
      formNode.dataset.operation = uuid();
    }
    data.operation_id = formNode.dataset.operation;
  }

  let path;
  if (task === "product") path = "/api/products" + (id ? "/" + id : "");
  else if (task === "discard") path = "/api/batches/" + id + "/discards";
  else {
    path = "/api/products/" + data.product_id + "/" + (task === "sale" ? "sales" : "receipts");
    delete data.product_id;
  }
  const confirmation = {
    product: id ? "Product updated." : "Product added.",
    receipt: "Stock received.",
    sale: "Sale recorded.",
    discard: "Units discarded.",
  };
  const submitLabel = submit.textContent;
  submit.disabled = true;
  submit.textContent = "Saving…";
  state.saving = true;
  const trigger = modalTrigger;
  const activePage = state.page;
  formNode.setAttribute("aria-busy", "true");
  errorNode.hidden = true;
  try {
    await api(path, { method: task === "product" && id ? "PATCH" : "POST", body: JSON.stringify(data) });
    dialog.close();
    notify(confirmation[task]);
    try {
      await loadDashboard();
      render();
      if (activePage === state.page && !dialog.open) {
        const newTrigger = Array.from(main.querySelectorAll("[data-action]")).find(
          (element) => element.dataset.action === trigger?.dataset.action && element.dataset.id === trigger?.dataset.id,
        );
        (newTrigger ?? main.querySelector("h1"))?.focus({ preventScroll: true });
      }
    } catch {
      notify(confirmation[task] + " Reload the page to refresh the dashboard.");
    }
  } catch (error) {
    errorNode.textContent = error.name === "TimeoutError"
      ? "The server took too long. Retry with the same details to confirm this update."
      : error.message;
    errorNode.hidden = false;
    formNode.setAttribute("aria-busy", "false");
    errorNode.focus();
  } finally {
    formNode.setAttribute("aria-busy", "false");
    submit.disabled = false;
    submit.textContent = submitLabel;
    state.saving = false;
  }
}

function react(event) {
  const button = event.target.closest("[data-action]");
  if (!button || state.saving) return;
  const id = Number(button.dataset.id || 0);
  switch (button.dataset.action) {
    case "detail": {
      const product = currentProduct(id);
      if (product) modal(product.name, product.sku + " · " + product.category + " · " + count(product.sellable_units, "sellable unit"), productDetail(product));
      break;
    }
    case "close":
      dialog.close();
      break;
    case "product":
      openProduct(id);
      break;
    case "sale":
    case "receipt":
      openMovement(button.dataset.action, id);
      break;
    case "discard":
      openDiscard(id);
      break;
    case "show-forecast":
      state.product = id;
      dialog.close();
      if (state.page === "forecast") render();
      else location.hash = "forecast";
      break;
    case "more":
      button.disabled = true;
      void loadMovements(true);
      break;
    case "retry-activity":
      void loadMovements();
      break;
    case "retry":
      void boot();
      break;
  }
}

async function boot() {
  const slug = location.hash.slice(1);
  state.page = Object.hasOwn(pages, slug) ? slug : "overview";
  renderNavigation();
  try {
    await loadDashboard();
    readRoute();
    if (location.hash === "#main") render();
  } catch (error) {
    main.setAttribute("aria-busy", "false");
    main.innerHTML = '<div class="page-head"><h1>Inventory unavailable</h1></div>' +
      '<p class="notice error" role="alert">Could not load inventory. ' + safe(error.message) + '</p>' +
      '<button class="button" type="button" data-action="retry">Retry</button>';
  }
}

document.querySelector("#store-icon").innerHTML = icon("store", 17);
document.querySelector("#theme-icon").innerHTML = icon("theme", 14);
window.addEventListener("hashchange", () => readRoute(true));
dialog.addEventListener("close", () => {
  if (modalTrigger?.isConnected) modalTrigger.focus({ preventScroll: true });
  modalTrigger = null;
});
main.addEventListener("click", react);
dialog.addEventListener("click", react);
dialog.addEventListener("submit", save);
dialog.addEventListener("cancel", (event) => { if (state.saving) event.preventDefault(); });
main.addEventListener("input", (event) => {
  if (event.target.id !== "filter-query") return;
  state.filters.query = event.target.value;
  renderInventory();
});
main.addEventListener("change", (event) => {
  switch (event.target.id) {
    case "chart-product":
      state.product = Number(event.target.value);
      void loadChart();
      break;
    case "filter-category":
      state.filters.category = event.target.value;
      renderInventory();
      break;
    case "filter-status":
      state.filters.status = event.target.value;
      renderInventory();
      break;
    case "filter-sort":
      state.filters.sort = event.target.value;
      renderInventory();
      break;
  }
});

void boot();
