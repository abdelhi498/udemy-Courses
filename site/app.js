(() => {
  const PAGE = 24;
  const $ = (id) => document.getElementById(id);
  const state = { all: [], provider: "الكل", query: "", sort: "new", verified: false, lang: "", shown: PAGE };

  // ---------- theme ----------
  const root = document.documentElement;
  try { const t = localStorage.getItem("theme"); if (t) root.dataset.theme = t; } catch {}
  const isDark = () => root.dataset.theme
    ? root.dataset.theme === "dark"
    : matchMedia("(prefers-color-scheme: dark)").matches;
  const syncThemeIcon = () => { $("theme").textContent = isDark() ? "☀️" : "🌙"; };
  $("theme").addEventListener("click", () => {
    root.dataset.theme = isDark() ? "light" : "dark";
    try { localStorage.setItem("theme", root.dataset.theme); } catch {}
    syncThemeIcon();
  });
  syncThemeIcon();

  // ---------- helpers ----------
  const rtf = new Intl.RelativeTimeFormat("ar", { numeric: "auto" });
  function timeAgo(iso) {
    const s = (new Date(iso) - Date.now()) / 1000;
    for (const [u, sec] of [["day", 86400], ["hour", 3600], ["minute", 60]])
      if (Math.abs(s) >= sec) return rtf.format(Math.round(s / sec), u);
    return "الآن";
  }
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (ch) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
  const b64 = (s) => btoa(String.fromCharCode(...new TextEncoder().encode(s)));
  const isNew = (c) => Date.now() - new Date(c.posted_at) < 12 * 3600 * 1000;

  // Times in the pre-rendered HTML are plain dates; make them relative.
  function relativeTimes(scope) {
    scope.querySelectorAll("time[datetime]").forEach((t) => { t.textContent = timeAgo(t.getAttribute("datetime")); });
  }

  // ---------- rendering (keep in sync with card_html in scraper/build.py) ----------
  function cardHtml(c) {
    const href = `course/${encodeURIComponent(c.page)}/`;
    const img = c.image ? `<img src="${esc(c.image)}" alt="${esc(c.title)}" loading="lazy" onerror="this.remove()">` : "";
    const status = c.status === "free" ? '<span class="badge ok">✓ مجاني مؤكد</span>' : "";
    const cat = c.category ? `<span class="badge">${esc(c.category)}</span>` : "";
    const facts = [
      c.rating ? `⭐ ${c.rating.toFixed(1)}${c.reviews ? ` (${c.reviews.toLocaleString("en")})` : ""}` : "",
      c.uses_left ? `⏳ ${c.uses_left} كوبون متبقي` : "",
      c.price ? `كان $${c.price}` : "",
    ].filter(Boolean).join(" • ");
    return `<article class="card"><a class="thumb" href="${href}">${img}<span class="ph">${esc(c.provider)}</span></a>
      <div class="body"><div class="meta"><span class="badge provider">${esc(c.provider)}</span>
      ${c.pinned ? '<span class="badge pin">📌 مميز</span>' : ""}${isNew(c) ? '<span class="badge new">جديد</span>' : ""}${status}${cat}</div>
      <h3 class="title"><a href="${href}">${esc(c.title)}</a></h3>
      ${facts ? `<p class="facts">${esc(facts)}</p>` : ""}
      <p class="time"><time datetime="${esc(c.posted_at)}"></time> • ${esc(c.channel)}</p>
      <div class="actions"><a class="btn primary go" href="${href}" data-unlock data-target="${esc(b64(c.url))}"
        data-title="${esc(c.title)}" data-coupon="${esc(c.coupon || "")}">احصل عليه مجاناً</a></div></div></article>`;
  }

  function filtered() {
    const q = state.query.trim().toLowerCase();
    const list = state.all.filter((c) =>
      (state.provider === "الكل" || c.provider === state.provider) &&
      (!state.verified || c.status === "free") &&
      (!state.lang || c.language === state.lang) &&
      (!q || `${c.title} ${c.slug} ${c.category || ""} ${c.instructor || ""}`.toLowerCase().includes(q)));
    const by = {
      new: (a, b) => (b.pinned - a.pinned) || b.posted_at.localeCompare(a.posted_at),
      old: (a, b) => a.posted_at.localeCompare(b.posted_at),
      az: (a, b) => a.title.localeCompare(b.title),
    }[state.sort];
    return list.sort(by);
  }

  const grid = $("grid");
  const adEvery = Number(grid.dataset.adEvery) || 6;
  const adTpl = $("ad-infeed");
  const hasInFeedAd = adTpl && adTpl.content.childElementCount > 0;

  function render() {
    const list = filtered();
    grid.innerHTML = list.slice(0, state.shown).map(cardHtml).join("");
    if (hasInFeedAd) {
      const cards = [...grid.children];
      cards.forEach((card, i) => {
        if ((i + 1) % adEvery === 0) card.after(document.importNode(adTpl.content, true));
      });
    }
    relativeTimes(grid);
    $("more").hidden = list.length <= state.shown;
    const msg = $("message");
    msg.hidden = list.length > 0;
    if (!list.length) msg.textContent = state.all.length
      ? "لا توجد نتائج مطابقة لبحثك."
      : "لا توجد كورسات حالياً، تابعنا فالقائمة تتحدث كل ساعة.";
  }

  function renderProviders() {
    const counts = {};
    state.all.forEach((c) => (counts[c.provider] = (counts[c.provider] || 0) + 1));
    const names = ["الكل", ...Object.keys(counts).sort((a, b) => counts[b] - counts[a])];
    $("providers").replaceChildren(...names.map((name) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip";
      b.textContent = name === "الكل" ? `الكل (${state.all.length})` : `${name} (${counts[name]})`;
      b.setAttribute("aria-pressed", String(name === state.provider));
      b.addEventListener("click", () => { state.provider = name; state.shown = PAGE; renderProviders(); render(); });
      return b;
    }));
  }

  // ---------- events ----------
  let t;
  $("search").addEventListener("input", (e) => {
    clearTimeout(t);
    t = setTimeout(() => { state.query = e.target.value; state.shown = PAGE; render(); }, 150);
  });
  $("sort").addEventListener("change", (e) => { state.sort = e.target.value; render(); });
  const LANG_AR = { English: "الإنجليزية", Arabic: "العربية", Spanish: "الإسبانية", French: "الفرنسية",
    Portuguese: "البرتغالية", German: "الألمانية", Turkish: "التركية", Italian: "الإيطالية", Hindi: "الهندية",
    Japanese: "اليابانية", Indonesian: "الإندونيسية", Russian: "الروسية", Vietnamese: "الفيتنامية",
    Polish: "البولندية", Urdu: "الأردية", Chinese: "الصينية", Korean: "الكورية" };
  function renderLanguages() {
    const counts = {};
    state.all.forEach((c) => c.language && (counts[c.language] = (counts[c.language] || 0) + 1));
    const sel = $("lang");
    sel.length = 1;
    Object.keys(counts).sort((a, b) => counts[b] - counts[a]).forEach((l) =>
      sel.add(new Option(`${LANG_AR[l] || l} (${counts[l]})`, l)));
    sel.hidden = sel.length <= 2;
  }
  $("lang").addEventListener("change", (e) => { state.lang = e.target.value; state.shown = PAGE; render(); });
  $("verified").addEventListener("change", (e) => { state.verified = e.target.checked; state.shown = PAGE; render(); });
  $("more").addEventListener("click", () => { state.shown += PAGE; render(); });

  // ---------- load ----------
  // The first cards are already in the HTML (good for Google); here we only add
  // search/filters and the "load more" button on top of them.
  relativeTimes(grid);
  const updated = $("updated");
  if (updated.dataset.iso) updated.textContent = timeAgo(updated.dataset.iso);

  fetch(`data/courses.json?v=${Date.now()}`)
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((data) => {
      state.all = data.courses || [];
      $("count").textContent = state.all.length;
      if (data.updated_at) updated.textContent = timeAgo(data.updated_at);
      renderProviders();
      renderLanguages();
      $("more").hidden = state.all.length <= state.shown;
      if (!state.all.length) render();
    })
    .catch(() => {
      if (!grid.children.length) {
        const msg = $("message");
        msg.hidden = false;
        msg.textContent = "تعذّر تحميل البيانات، حاول تحديث الصفحة.";
      }
    });
})();
