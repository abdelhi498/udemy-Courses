(() => {
  const PAGE = 24;
  const $ = (id) => document.getElementById(id);
  const state = { all: [], provider: "الكل", query: "", sort: "new", verified: false, shown: PAGE };

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
    const units = [["day", 86400], ["hour", 3600], ["minute", 60]];
    for (const [u, sec] of units) if (Math.abs(s) >= sec) return rtf.format(Math.round(s / sec), u);
    return "الآن";
  }
  const isNew = (c) => Date.now() - new Date(c.posted_at) < 12 * 3600 * 1000;

  // ---------- rendering ----------
  function filtered() {
    const q = state.query.trim().toLowerCase();
    let list = state.all.filter((c) =>
      (state.provider === "الكل" || c.provider === state.provider) &&
      (!state.verified || c.status === "free") &&
      (!q || `${c.title} ${c.slug} ${c.description || ""}`.toLowerCase().includes(q)));
    const by = {
      new: (a, b) => b.posted_at.localeCompare(a.posted_at),
      old: (a, b) => a.posted_at.localeCompare(b.posted_at),
      az: (a, b) => a.title.localeCompare(b.title),
    }[state.sort];
    return list.sort(by);
  }

  function card(c) {
    const node = $("card-tpl").content.firstElementChild.cloneNode(true);
    const thumb = node.querySelector(".thumb");
    thumb.href = c.url;
    const img = node.querySelector("img");
    node.querySelector(".ph").textContent = c.provider;
    if (c.image) {
      img.src = c.image;
      img.onerror = () => img.removeAttribute("src");
    }
    img.alt = c.title;

    node.querySelector(".provider").textContent = c.provider;
    node.querySelector(".new").hidden = !isNew(c);
    const st = node.querySelector(".status");
    if (c.status === "free") { st.textContent = "✓ مجاني مؤكد"; st.classList.add("ok"); }
    else { st.textContent = "غير مؤكد"; st.classList.add("unknown"); st.title = "لم نتمكن من التحقق من الكوبون تلقائياً"; }

    node.querySelector(".title").textContent = c.title;
    node.querySelector(".time").textContent = `نُشر ${timeAgo(c.posted_at)} • ${c.channel}`;
    node.querySelector(".go").href = c.url;
    node.querySelector(".src").href = c.source;

    const copy = node.querySelector(".copy");
    if (c.coupon) {
      copy.textContent = c.coupon;
      copy.addEventListener("click", async () => {
        try { await navigator.clipboard.writeText(c.coupon); copy.textContent = "تم النسخ ✓"; }
        catch { copy.textContent = c.coupon; }
        setTimeout(() => (copy.textContent = c.coupon), 1500);
      });
    } else copy.hidden = true;
    return node;
  }

  function render() {
    const list = filtered();
    const grid = $("grid");
    grid.replaceChildren(...list.slice(0, state.shown).map(card));
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
  $("verified").addEventListener("change", (e) => { state.verified = e.target.checked; state.shown = PAGE; render(); });
  $("more").addEventListener("click", () => { state.shown += PAGE; render(); });

  // ---------- load ----------
  fetch(`data/courses.json?v=${Date.now()}`)
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((data) => {
      state.all = data.courses || [];
      $("count").textContent = state.all.length;
      $("updated").textContent = data.updated_at ? timeAgo(data.updated_at) : "—";
      renderProviders();
      render();
    })
    .catch(() => {
      const msg = $("message");
      msg.hidden = false;
      msg.textContent = "تعذّر تحميل البيانات، حاول تحديث الصفحة.";
    });
})();
