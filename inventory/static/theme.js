(() => {
  const key = "freshledger-theme";
  const system = matchMedia("(prefers-color-scheme: dark)");
  const choices = new Set(["system", "light", "dark"]);
  let preference = "system";
  try {
    const saved = localStorage.getItem(key);
    if (choices.has(saved)) preference = saved;
  } catch {
    // Theme still follows the system when storage is unavailable.
  }

  function apply() {
    const dark = preference === "dark" || (preference === "system" && system.matches);
    const theme = dark ? "dark" : "light";
    if (document.documentElement.dataset.theme !== theme) {
      document.documentElement.dataset.theme = theme;
      document.querySelector("#theme-color").content = dark ? "#171613" : "#f2efeb";
      document.dispatchEvent(new Event("freshledger-theme-change"));
    }
  }

  apply();
  system.addEventListener("change", apply);
  document.addEventListener("DOMContentLoaded", () => {
    const select = document.querySelector("#theme-select");
    select.value = preference;
    select.addEventListener("change", () => {
      preference = select.value;
      try { localStorage.setItem(key, preference); } catch { /* This page retains its selection. */ }
      apply();
    });
  });
})();
