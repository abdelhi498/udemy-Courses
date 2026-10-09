(() => {
  const $ = (id) => document.getElementById(id);
  const PAGE = Number(document.body.dataset.perPage) || 24;
  const ALL = "";
  const params = new URLSearchParams(location.search);
  const state = { all: [], cat: ALL, query: params.get("q") || "", sort: document.body.dataset.sort || "new",
                  verified: false, lang: "", shown: PAGE };

  const timeAgo = window.timeAgo;
  const TEXTS = window.SITE_TEXTS || {};
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (ch) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
  const b64 = (s) => btoa(String.fromCharCode(...new TextEncoder().encode(s)));
  const isNew = (c) => Date.now() - new Date(c.posted_at) < 12 * 3600 * 1000;
  const LANG_AR = { English: "الإنجليزية", Arabic: "العربية", Spanish: "الإسبانية", French: "الفرنسية",
    Portuguese: "البرتغالية", German: "الألمانية", Turkish: "التركية", Italian: "الإيطالية", Hindi: "الهندية",
    Japanese: "اليابانية", Indonesian: "الإندونيسية", Russian: "الروسية", Vietnamese: "الفيتنامية",
    Polish: "البولندية", Urdu: "الأردية", Chinese: "الصينية", Korean: "الكورية" };
  const langAr = (l) => LANG_AR[l] || l;

  const relativeTimes = window.relativeTimes;

  // ---------- rendering (keep in sync with card_html in scraper/build.py) ----------
  function cardHtml(c) {
    const href = `course/${encodeURIComponent(c.page)}/`;
    const img = c.image ? `<img src="${esc(c.image)}" alt="${esc(c.title)}" loading="lazy" onerror="this.remove()">` : "";
    const old = c.price ? `<span class="old-price">$${c.price}</span>` : "";
    const badges = [
      c.category ? `<span class="badge cat">${esc(c.category)}</span>` : "",
      c.pinned ? '<span class="badge pin">📌 مميز</span>' : "",
      isNew(c) ? '<span class="badge new">جديد</span>' : "",
      c.status === "free" ? '<span class="badge ok">✓ مؤكد</span>' : "",
    ].join("");
    const facts = [
      c.rating ? `<span class="rate">${c.rating.toFixed(1)}${c.reviews ? ` (${c.reviews.toLocaleString("en")})` : ""}</span>` : "",
      c.uses_left ? `<span class="left">⏳ باقي ${c.uses_left} كوبون</span>` : "",
      c.language ? `<span>🌐 ${esc(langAr(c.language))}</span>` : "",
    ].join("");
    return `<article class="card"><a class="thumb" href="${href}" tabindex="-1">${img}<span class="ph">${esc(c.provider)}</span><span class="ribbon">مجاناً</span>${old}</a>
      <div class="body"><div class="meta">${badges}</div>
      <h3 class="title"><a href="${href}">${esc(c.title)}</a></h3>
      ${c.instructor ? `<p class="by">👤 ${esc(c.instructor)}</p>` : ""}
      ${facts ? `<p class="facts">${facts}</p>` : ""}
      <div class="card-foot"><p class="time"><time datetime="${esc(c.posted_at)}"></time></p>
      <a class="btn primary go" href="${href}" data-unlock data-target="${esc(b64(c.url))}"
        data-title="${esc(c.title)}" data-coupon="${esc(c.coupon || "")}">${esc(TEXTS.card_button || "احصل عليه مجاناً")}</a></div></div></article>`;
  }

  function filtered() {
    const q = state.query.trim().toLowerCase();
    const list = state.all.filter((c) =>
      (state.cat === ALL || c.category === state.cat) &&
      (!state.verified || c.status === "free") &&
      (!state.lang || c.language === state.lang) &&
      (!q || `${c.title} ${c.slug} ${c.category || ""} ${c.instructor || ""}`.toLowerCase().includes(q)));
    const by = {
      new: (a, b) => (b.pinned - a.pinned) || b.posted_at.localeCompare(a.posted_at),
      rating: (a, b) => (b.rating || 0) - (a.rating || 0) || (b.reviews || 0) - (a.reviews || 0),
      price: (a, b) => (b.price || 0) - (a.price || 0),
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
      [...grid.children].forEach((card, i) => {
        if ((i + 1) % adEvery === 0) card.after(document.importNode(adTpl.content, true));
      });
    }
    relativeTimes(grid);
    $("more").hidden = list.length <= state.shown;
    $("result-count").textContent = `${list.length} كورس`;
    const msg = $("message");
    msg.hidden = list.length > 0;
    if (!list.length) msg.textContent = state.all.length
      ? "لا توجد نتائج مطابقة لبحثك."
      : "لا توجد كورسات حالياً، تابعنا فالقائمة تتحدث كل ساعة.";
  }

  function renderCategories() {
    const counts = {};
    state.all.forEach((c) => c.category && (counts[c.category] = (counts[c.category] || 0) + 1));
    const top = Object.keys(counts).sort((a, b) => counts[b] - counts[a]).slice(0, 14);
    const chip = (value, label, n) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip";
      b.innerHTML = `${esc(label)} <small>${n}</small>`;
      b.setAttribute("aria-pressed", String(value === state.cat));
      b.addEventListener("click", () => { state.cat = value; state.shown = PAGE; renderCategories(); render(); });
      return b;
    };
    $("cats").replaceChildren(chip(ALL, "الكل", state.all.length), ...top.map((c) => chip(c, c, counts[c])));
  }

  function renderLanguages() {
    const counts = {};
    state.all.forEach((c) => c.language && (counts[c.language] = (counts[c.language] || 0) + 1));
    const sel = $("lang");
    sel.length = 1;
    Object.keys(counts).sort((a, b) => counts[b] - counts[a]).forEach((l) =>
      sel.add(new Option(`${langAr(l)} (${counts[l]})`, l)));
    sel.hidden = sel.length <= 2;
  }

  // ---------- events ----------
  let t;
  $("search").addEventListener("input", (e) => {
    clearTimeout(t);
    t = setTimeout(() => { state.query = e.target.value; state.shown = PAGE; render(); }, 150);
  });
  $("search").closest("form").addEventListener("submit", () => grid.scrollIntoView({ behavior: "smooth" }));
  $("sort").addEventListener("change", (e) => { state.sort = e.target.value; render(); });
  $("lang").addEventListener("change", (e) => { state.lang = e.target.value; state.shown = PAGE; render(); });
  $("verified").addEventListener("change", (e) => { state.verified = e.target.checked; state.shown = PAGE; render(); });
  $("more").addEventListener("click", () => { state.shown += PAGE; render(); });

  // ---------- load ----------
  // The first cards are already in the HTML (good for Google); here we only add
  // search/filters and the "load more" button on top of them.
  const updated = $("updated");
  if (updated.dataset.iso) updated.textContent = timeAgo(updated.dataset.iso);

  fetch(`data/courses.json?v=${Date.now()}`)
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((data) => {
      state.all = data.courses || [];
      $("count").textContent = state.all.length;
      if (data.updated_at) updated.textContent = timeAgo(data.updated_at);
      renderCategories();
      renderLanguages();
      $("sort").value = state.sort;
      $("result-count").textContent = `${state.all.length} كورس`;
      $("more").hidden = state.all.length <= state.shown;
      // Re-render only when needed, so the pre-rendered cards (and their ads) stay.
      if (!state.all.length || state.query || state.sort !== "new") {
        $("search").value = state.query;
        render();
      }
    })
    .catch(() => {
      if (!grid.children.length) {
        const msg = $("message");
        msg.hidden = false;
        msg.textContent = "تعذّر تحميل البيانات، حاول تحديث الصفحة.";
      }
    });
})();
