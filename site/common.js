// Shared by every page: theme toggle and relative dates.
(() => {
  const root = document.documentElement;
  const btn = document.getElementById("theme");
  const isDark = () => root.dataset.theme
    ? root.dataset.theme === "dark"
    : matchMedia("(prefers-color-scheme: dark)").matches;
  const sync = () => { if (btn) btn.textContent = isDark() ? "☀️" : "🌙"; };
  if (btn) btn.addEventListener("click", () => {
    root.dataset.theme = isDark() ? "light" : "dark";
    try { localStorage.setItem("theme", root.dataset.theme); } catch {}
    sync();
  });
  sync();

  const rtf = new Intl.RelativeTimeFormat("ar", { numeric: "auto" });
  window.timeAgo = (iso) => {
    const s = (new Date(iso) - Date.now()) / 1000;
    for (const [u, sec] of [["day", 86400], ["hour", 3600], ["minute", 60]])
      if (Math.abs(s) >= sec) return rtf.format(Math.round(s / sec), u);
    return "الآن";
  };
  window.relativeTimes = (scope) => scope.querySelectorAll("time[datetime]").forEach((t) => {
    t.textContent = window.timeAgo(t.getAttribute("datetime"));
  });
  window.relativeTimes(document);
})();
