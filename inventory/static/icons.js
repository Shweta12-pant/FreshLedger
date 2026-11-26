const paths = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  box: '<path d="M21 8.5 12 13 3 8.5m9 4.5v9M3 7l9-4 9 4v10l-9 5-9-5zM7.5 5l9 4.8"/>',
  chart: '<path d="M3 3v18h18M7 15l4-4 4 2 5-6m-4 0h4v4"/>',
  activity: '<path d="M3 12h4l3-7 4 14 3-7h4"/>',
  store: '<path d="M3 10l2-6h14l2 6M4 13v7h16v-7M9 20v-5h6v5M3 10a3 3 0 0 0 6 0 3 3 0 0 0 6 0 3 3 0 0 0 6 0"/>',
  theme: '<circle cx="12" cy="12" r="8"/><path d="M12 4v16M12 7a5 5 0 0 1 0 10"/>',
  drop: '<path d="M12 3c-3 4.1-6 7.3-6 10.5a6 6 0 0 0 12 0C18 10.3 15 7.1 12 3Z"/>',
  bread: '<path d="M5 11a3.4 3.4 0 0 1-.8-6.2 16.5 16.5 0 0 1 15.6 0A3.4 3.4 0 0 1 19 11v7a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2Z"/>',
  snow: '<path d="M12 2v20M3.3 7l17.4 10M3.3 17 20.7 7M9 4l3 3 3-3M9 20l3-3 3 3"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 10h18"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  leaf: '<path d="M5 19c.8-6.4 5.2-10.4 14-12M20 4c.6 8-1.8 14-8.5 14A6.5 6.5 0 0 1 5 12c0-5 6.1-7.4 15-8Z"/>',
  alert: '<path d="M10.5 4.8 3.1 18a1.4 1.4 0 0 0 1.2 2.1h15.4a1.4 1.4 0 0 0 1.2-2.1L13.5 4.8a1.7 1.7 0 0 0-3 0ZM12 9v4m0 3.5h.01"/>',
  arrow: '<path d="M5 12h14m-6-6 6 6-6 6"/>',
  chevron: '<path d="m9 18 6-6-6-6"/>',
  search: '<circle cx="10.5" cy="10.5" r="5.5"/><path d="m15 15 4 4"/>',
  x: '<path d="m6 6 12 12M18 6 6 18"/>',
  sale: '<path d="M12 4v12m-4-4 4 4 4-4M5 15v5h14v-5"/>',
  discard: '<path d="M4 7h16m-14 0 1 13h10l1-13M9 7V4h6v3m-5 4v5m4-5v5"/>',
  edit: '<path d="m4 16-1 5 5-1L20 8l-4-4L4 16Zm10-10 4 4"/>',
};

export function icon(name, size = 18) {
  return '<svg class="icon" width="' + size + '" height="' + size + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + paths[name] + '</svg>';
}
