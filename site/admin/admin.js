(() => {
  "use strict";
  const BRANCH = "main";
  const WORKFLOW = "update.yml";
  const SETTINGS_PATH = "data/settings.json";
  const COURSES_PATH = "data/courses.json";
  const DEFAULTS = window.SETTINGS_DEFAULTS || {};
  const ROLES = window.SETTINGS_ROLES || {};
  const SECTION_PERMISSION = window.SECTION_PERMISSION || {};
  const ALL_PERMS = [...new Set(Object.values(SECTION_PERMISSION))];

  const PERM_LABELS = {
    courses: "الكورسات والفلاتر", sources: "المصادر", ads: "الإعلانات", appearance: "المظهر والنصوص",
    pages: "الصفحات والقائمة", seo: "السيو", settings: "إعدادات الموقع", users: "المستخدمون",
  };
  const ROLE_LABELS = { admin: "مدير (كل شيء ما عدا المستخدمين)", editor: "محرر (الكورسات والمصادر والصفحات)",
    marketer: "مسوّق (الإعلانات والسيو والمظهر)", viewer: "مشاهد فقط", custom: "مخصص" };
  const SECTION_LABELS = {
    site: "إعدادات الموقع", appearance: "المظهر", texts: "النصوص", announcement: "شريط الإعلان", nav: "القائمة",
    pages: "الصفحات", seo: "السيو", ads: "الإعلانات", sources: "المصادر", show_indirect_links: "المصادر",
    content: "قواعد الكورسات", pinned: "التثبيت", hidden: "الإخفاء", manual_courses: "كورسات يدوية", users: "المستخدمون",
  };
  const TABS = [
    { id: "overview", icon: "📊", label: "نظرة عامة" },
    { id: "courses", icon: "🎓", label: "الكورسات", perm: "courses" },
    { id: "sources", icon: "📡", label: "المصادر", perm: "sources" },
    { id: "ads", icon: "💰", label: "الإعلانات", perm: "ads" },
    { id: "appearance", icon: "🎨", label: "المظهر والنصوص", perm: "appearance" },
    { id: "pages", icon: "📄", label: "الصفحات والقائمة", perm: "pages" },
    { id: "seo", icon: "🔍", label: "السيو", perm: "seo" },
    { id: "settings", icon: "🛠️", label: "إعدادات الموقع", perm: "settings" },
    { id: "users", icon: "👥", label: "المستخدمون", perm: "users" },
    { id: "activity", icon: "🕘", label: "سجل النشاط" },
  ];
  const SITE_SOURCES = {
    realdiscount: { name: "real.discount", url: "https://www.real.discount/" },
    tutorialbar: { name: "tutorialbar", url: "https://www.tutorialbar.com/" },
    discudemy: { name: "discudemy", url: "https://www.discudemy.com/" },
    udemyfreebies: { name: "udemyfreebies", url: "https://www.udemyfreebies.com/" },
  };
  const LANG_AR = { English: "الإنجليزية", Arabic: "العربية", Spanish: "الإسبانية", French: "الفرنسية",
    Portuguese: "البرتغالية", German: "الألمانية", Turkish: "التركية", Italian: "الإيطالية", Hindi: "الهندية",
    Japanese: "اليابانية", Indonesian: "الإندونيسية", Russian: "الروسية", Vietnamese: "الفيتنامية",
    Polish: "البولندية", Urdu: "الأردية", Chinese: "الصينية", Korean: "الكورية" };

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (ch) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
  const rtf = new Intl.RelativeTimeFormat("ar", { numeric: "auto" });
  function timeAgo(iso) {
    if (!iso) return "—";
    const s = (new Date(iso) - Date.now()) / 1000;
    for (const [u, sec] of [["day", 86400], ["hour", 3600], ["minute", 60]])
      if (Math.abs(s) >= sec) return rtf.format(Math.round(s / sec), u);
    return "الآن";
  }
  const clone = (x) => JSON.parse(JSON.stringify(x));

  // ---------- storage (may be blocked: never rely on it) ----------
  const store = {
    get(k) { try { return localStorage.getItem(k) || sessionStorage.getItem(k); } catch { return null; } },
    set(k, v, remember) { try { (remember ? localStorage : sessionStorage).setItem(k, v); } catch {} },
    clear() { try { ["gh_token", "gh_repo"].forEach((k) => { localStorage.removeItem(k); sessionStorage.removeItem(k); }); } catch {} },
  };

  const S = {
    token: store.get("gh_token"),
    repo: store.get("gh_repo") || window.SITE_REPO || "",
    me: null, owner: "", perms: new Set(), isOwner: false, canInvite: false,
    settings: null, original: "", sha: null,
    data: { courses: [], sources: {} }, runs: [], commits: [], collaborators: null, invitations: null,
    tab: "overview",
    cf: { q: "", show: "all", limit: 100, selected: new Set(), editing: null },
    pageEditing: null,
  };

  // ---------- GitHub API ----------
  async function gh(path, opts = {}) {
    const url = path.startsWith("http") ? path : `https://api.github.com${path.startsWith("/user") ? "" : `/repos/${S.repo}`}${path}`;
    const res = await fetch(url, {
      ...opts,
      headers: {
        Authorization: `Bearer ${S.token}`,
        Accept: opts.raw ? "application/vnd.github.raw+json" : "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        ...(opts.body ? { "Content-Type": "application/json" } : {}),
      },
    });
    if (!res.ok) {
      const err = new Error(`GitHub ${res.status}`);
      err.status = res.status;
      try { err.detail = (await res.json()).message; } catch {}
      throw err;
    }
    if (res.status === 204) return null;
    return opts.raw ? res.text() : res.json();
  }
  const b64encode = (str) => {
    const bytes = new TextEncoder().encode(str);
    let bin = "";
    for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    return btoa(bin);
  };
  const b64decode = (b64) => new TextDecoder().decode(Uint8Array.from(atob(b64.replace(/\s/g, "")), (c) => c.charCodeAt(0)));

  // ---------- settings: defaults + migration (mirrors scraper/settings.py) ----------
  function merge(def, val) {
    if (def && typeof def === "object" && !Array.isArray(def) && val && typeof val === "object" && !Array.isArray(val)) {
      const out = {};
      for (const k of Object.keys(def)) out[k] = k in val ? merge(def[k], val[k]) : clone(def[k]);
      for (const k of Object.keys(val)) if (!(k in def)) out[k] = val[k];
      return out;
    }
    return val === undefined ? clone(def) : val;
  }
  function normalise(raw) {
    raw = clone(raw || {});
    const site = raw.site || (raw.site = {});
    const texts = raw.texts || (raw.texts = {});
    const seo = raw.seo || (raw.seo = {});
    const social = site.social || (site.social = {});
    const ap = raw.appearance || (raw.appearance = {});
    if ("tagline" in site) { texts.tagline ??= site.tagline; delete site.tagline; }
    if ("description" in site) { seo.description ??= site.description; delete site.description; }
    for (const n of ["facebook", "telegram"]) if (n in site) { social[n] ??= site[n]; delete site[n]; }
    for (const k of ["logo_emoji", "logo_url", "favicon_url"]) if (k in site) { ap[k] ??= site[k]; delete site[k]; }
    return merge(DEFAULTS, raw);
  }
  function permsFor(settings, login) {
    if (S.isOwner) return new Set(ALL_PERMS);
    const u = (settings.users || []).find((x) => (x.login || "").toLowerCase() === (login || "").toLowerCase());
    if (!u || u.disabled) return new Set();
    return new Set(u.role === "custom" ? (u.permissions || []) : (ROLES[u.role] || []));
  }
  const can = (perm) => !perm || S.perms.has(perm);

  async function loadSettings() {
    const file = await gh(`/contents/${SETTINGS_PATH}?ref=${BRANCH}`);
    S.sha = file.sha;
    S.settings = normalise(JSON.parse(b64decode(file.content)));
    S.original = JSON.stringify(S.settings);
  }
  async function loadCourses() {
    try { S.data = JSON.parse(await gh(`/contents/${COURSES_PATH}?ref=${BRANCH}`, { raw: true })); }
    catch { S.data = { courses: [], sources: {} }; }
    S.data.courses ||= [];
    S.data.sources ||= {};
  }
  async function loadRuns() {
    try { S.runs = (await gh(`/actions/workflows/${WORKFLOW}/runs?per_page=10`)).workflow_runs || []; } catch { S.runs = []; }
  }
  async function loadCommits() {
    try { S.commits = await gh(`/commits?path=${SETTINGS_PATH}&sha=${BRANCH}&per_page=40`); } catch { S.commits = []; }
  }

  // ---------- change tracking & saving ----------
  const dirty = () => S.settings && JSON.stringify(S.settings) !== S.original;
  function changedSections() {
    const before = JSON.parse(S.original);
    const keys = new Set([...Object.keys(before), ...Object.keys(S.settings)]);
    return [...keys].filter((k) => JSON.stringify(before[k]) !== JSON.stringify(S.settings[k]));
  }
  function changed() {
    const d = dirty();
    $("savebar").hidden = !d;
    if (d) {
      const names = [...new Set(changedSections().map((k) => SECTION_LABELS[k] || k))];
      $("savebar-text").textContent = `تغييرات غير محفوظة: ${names.join("، ")}`;
    }
  }

  async function save() {
    const sections = changedSections();
    const denied = sections.filter((k) => !S.perms.has(SECTION_PERMISSION[k] || "settings"));
    if (denied.length) {
      return toast(`ليس لديك صلاحية تعديل: ${denied.map((k) => SECTION_LABELS[k] || k).join("، ")}`, true);
    }
    const btn = $("save");
    btn.disabled = true;
    btn.textContent = "جاري الحفظ…";
    try {
      const names = [...new Set(sections.map((k) => SECTION_LABELS[k] || k))].join("، ");
      const res = await gh(`/contents/${SETTINGS_PATH}`, {
        method: "PUT",
        body: JSON.stringify({
          message: `لوحة التحكم (${S.me.login}): ${names}`,
          content: b64encode(JSON.stringify(S.settings, null, 2) + "\n"),
          sha: S.sha,
          branch: BRANCH,
        }),
      });
      S.sha = res.content.sha;
      S.original = JSON.stringify(S.settings);
      changed();
      toast("✓ تم الحفظ. سيتحدث الموقع تلقائياً خلال 3–5 دقائق.");
      setTimeout(() => Promise.all([loadRuns(), loadCommits()]).then(() => ["overview", "activity"].includes(S.tab) && softRender()), 4000);
    } catch (e) {
      if (e.status === 409 || e.status === 422) toast("تم تعديل الإعدادات من مكان آخر. حدّث الصفحة ثم أعد التعديل.", true);
      else if (e.status === 403 || e.status === 404) toast("المفتاح لا يملك صلاحية الكتابة على المستودع.", true);
      else toast(`تعذّر الحفظ (${e.detail || e.message})`, true);
    } finally {
      btn.disabled = false;
      btn.textContent = "💾 حفظ ونشر";
    }
  }

  let toastTimer;
  function toast(msg, bad = false) {
    const t = $("toast");
    t.textContent = msg;
    t.className = "toast" + (bad ? " bad" : "");
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (t.hidden = true), bad ? 7000 : 4500);
  }

  function setPath(obj, path, value) {
    const keys = path.split(".");
    const last = keys.pop();
    keys.reduce((o, k) => (o[k] ??= {}), obj)[last] = value;
  }
  function getPath(obj, path) { return path.split(".").reduce((o, k) => (o == null ? o : o[k]), obj); }

  // ---------- form helpers ----------
  // field("site.name", "اسم الموقع", {type, hint, options, dir, rows, placeholder})
  function field(path, label, o = {}) {
    const v = getPath(S.settings, path);
    const type = o.type || "text";
    const attrs = `data-bind="${path}" data-type="${type}" ${o.dir ? `dir="${o.dir}"` : ""} ${o.placeholder ? `placeholder="${esc(o.placeholder)}"` : ""}`;
    const hint = o.hint ? `<span class="hint">${o.hint}</span>` : "";
    if (type === "checkbox")
      return `<label class="switch line"><input type="checkbox" ${attrs} ${v ? "checked" : ""}> ${label}${hint}</label>`;
    let input;
    if (type === "textarea" || type === "code" || type === "list")
      input = `<textarea ${attrs} rows="${o.rows || 4}" class="${type === "code" ? "code" : ""}">${esc(type === "list" ? (v || []).join("\n") : v)}</textarea>`;
    else if (type === "select")
      input = `<select ${attrs}>${o.options.map(([val, txt]) => `<option value="${esc(val)}" ${String(v) === String(val) ? "selected" : ""}>${esc(txt)}</option>`).join("")}</select>`;
    else if (type === "color")
      input = `<span class="color-row"><input type="color" ${attrs} value="${esc(v)}"><code>${esc(v)}</code></span>`;
    else
      input = `<input type="${type === "number" ? "number" : type === "url" ? "url" : "text"}" ${attrs} value="${esc(v)}" ${o.min != null ? `min="${o.min}"` : ""} ${o.max != null ? `max="${o.max}"` : ""}>`;
    return `<label>${label}${input}${hint}</label>`;
  }
  const panel = (title, body, sub = "") => `<div class="panel"><h2>${title}</h2>${sub ? `<p class="muted">${sub}</p>` : ""}${body}</div>`;
  const grid2 = (...xs) => `<div class="row2">${xs.join("")}</div>`;

  function readInput(el) {
    const t = el.dataset.type;
    if (t === "checkbox") return el.checked;
    if (t === "number") return Number(el.value) || 0;
    if (t === "list") return el.value.split(/[\n,،]/).map((x) => x.trim()).filter(Boolean);
    return el.value;
  }

  // ---------- views ----------
  function siteUrl() {
    const s = S.settings.site;
    return s.custom_domain ? `https://${s.custom_domain.replace(/^https?:\/\//, "").replace(/\/+$/, "")}/` : (s.url || "#");
  }
  function bars(rows, max) {
    max = max || Math.max(1, ...rows.map((r) => r[1]));
    return `<div class="bars">${rows.map(([label, n]) =>
      `<div class="bar-row"><span class="bar-label" title="${esc(label)}">${esc(label)}</span><span class="bar"><i style="width:${(n / max) * 100}%"></i></span><b>${n}</b></div>`).join("")}</div>`;
  }
  function countBy(list, key) {
    const m = {};
    list.forEach((c) => { const k = typeof key === "function" ? key(c) : c[key]; if (k) m[k] = (m[k] || 0) + 1; });
    return Object.entries(m).sort((a, b) => b[1] - a[1]);
  }

  function seoChecks() {
    const s = S.settings, seo = s.seo;
    const d = seo.description || "";
    return [
      [d.length >= 70 && d.length <= 170, "وصف الموقع بطول مناسب (70–170 حرفاً)", "seo"],
      [!!seo.google_verification || /google-site-verification/.test(s.site.head_code), "التحقق من Google Search Console", "seo"],
      [!!seo.bing_verification, "التحقق من Bing Webmaster Tools", "seo"],
      [!!seo.ga_id || /gtag|googletagmanager/.test(s.site.head_code), "Google Analytics لقياس الزوار", "seo"],
      [!!seo.og_image, "صورة مشاركة افتراضية (تظهر عند مشاركة الموقع)", "seo"],
      [!!s.site.custom_domain, "دومين خاص (مهم لثقة جوجل وAdSense)", "settings"],
      [!!seo.indexnow, "IndexNow لإبلاغ محركات البحث فوراً", "seo"],
      [seo.category_pages, "صفحات التصنيفات", "seo"],
      [s.pages.some((p) => /privacy|خصوصية/.test(p.slug + p.title)), "صفحة سياسة الخصوصية (مطلوبة لـ AdSense)", "pages"],
      [s.pages.some((p) => /contact|اتصل/.test(p.slug + p.title)), "صفحة اتصل بنا", "pages"],
      [!seo.noindex, "الموقع مسموح لمحركات البحث (غير مخفي)", "seo"],
      [!!s.appearance.logo_url, "شعار الموقع كصورة (يظهر في نتائج جوجل)", "appearance"],
    ];
  }

  const views = {
    overview() {
      const courses = S.data.courses;
      const live = courses.filter((c) => !c.via || S.settings.show_indirect_links);
      const verified = courses.filter((c) => c.status === "free").length;
      const activeSources = S.settings.sources.filter((s) => s.enabled !== false).length;
      const running = S.runs.some((r) => r.status !== "completed");
      const checks = seoChecks();
      const score = Math.round((checks.filter((c) => c[0]).length / checks.length) * 100);
      const runRow = (r) => {
        const ok = r.conclusion === "success";
        const cls = r.status !== "completed" ? "run" : ok ? "ok" : r.conclusion === "skipped" ? "ok" : "bad";
        const label = r.status !== "completed" ? "يعمل الآن…" : ok ? "نجح" : r.conclusion === "cancelled" ? "أُلغي" : "فشل";
        const ev = { schedule: "تحديث تلقائي", workflow_dispatch: "تشغيل يدوي / نشر", push: "حفظ إعدادات / تعديل" }[r.event] || r.event;
        return `<div class="item"><div class="grow"><div class="t"><span class="dot ${cls}"></span>${label} — ${esc(ev)}</div>
          <div class="s">${timeAgo(r.created_at)}${r.actor ? ` • ${esc(r.actor.login)}` : ""}</div></div>
          <a class="btn sm" href="${esc(r.html_url)}" target="_blank" rel="noopener">التفاصيل</a></div>`;
      };
      const canRun = can("courses") || can("sources");
      return `
        <div class="page-head"><h1>أهلاً ${esc(S.me.name || S.me.login)} 👋</h1>
          ${canRun ? `<button class="btn primary" data-act="run" ${running ? "disabled" : ""}>${running ? "⏳ جاري السحب…" : "🔄 اسحب الكورسات الآن"}</button>` : ""}</div>
        <div class="tiles">
          <div class="tile"><div class="num">${live.length}</div><div class="lbl">كورس معروض</div></div>
          <div class="tile"><div class="num">${verified}</div><div class="lbl">مجاني مؤكد</div></div>
          <div class="tile"><div class="num">${activeSources}</div><div class="lbl">مصدر نشط</div></div>
          <div class="tile"><div class="num" style="font-size:1.15rem">${timeAgo(S.data.updated_at)}</div><div class="lbl">آخر سحب</div></div>
          <div class="tile ${score >= 75 ? "good" : score >= 50 ? "mid" : "low"}"><div class="num">${score}%</div><div class="lbl">جاهزية السيو</div></div>
        </div>
        <div class="row2">
          ${panel("الكورسات حسب المصدر", bars(countBy(live, "channel").slice(0, 8)))}
          ${panel("أكثر التصنيفات", bars(countBy(live, "category").slice(0, 8)))}
        </div>
        <div class="row2">
          ${panel("آخر عمليات التحديث", `<div class="list">${S.runs.slice(0, 6).map(runRow).join("") || '<p class="empty">لا توجد عمليات بعد.</p>'}</div>`,
            "يسحب الموقع الكورسات تلقائياً كل ساعة، وبعد كل حفظ.")}
          ${panel("قائمة تحسين السيو", `<ul class="checks">${checks.map(([ok, t]) => `<li class="${ok ? "ok" : ""}">${ok ? "✅" : "⬜"} ${t}</li>`).join("")}</ul>`)}
        </div>`;
    },

    courses() {
      const f = S.cf, st = S.settings;
      const pinned = new Set(st.pinned), hidden = new Set(st.hidden), ov = st.content.overrides;
      const q = f.q.trim().toLowerCase();
      const list = S.data.courses.filter((c) => {
        if (q && !`${c.title} ${c.category || ""} ${c.instructor || ""}`.toLowerCase().includes(q)) return false;
        if (f.show === "pinned") return pinned.has(c.id);
        if (f.show === "hidden") return hidden.has(c.id);
        if (f.show === "edited") return !!ov[c.id];
        if (f.show === "indirect") return !!c.via;
        if (f.show.startsWith("src:")) return c.channel === f.show.slice(4);
        return true;
      });
      const row = (c) => {
        const o = ov[c.id] || {};
        const title = o.title || c.title;
        const editing = f.editing === c.id;
        return `<div class="item ${hidden.has(c.id) ? "dim" : ""}">
          <input type="checkbox" class="pick" data-act="pick" data-id="${esc(c.id)}" ${f.selected.has(c.id) ? "checked" : ""}>
          ${(o.image || c.image) ? `<img src="${esc(o.image || c.image)}" alt="" loading="lazy">` : '<span class="noimg"></span>'}
          <div class="grow"><div class="t">${esc(title)}</div>
            <div class="s">${esc(c.channel)} • ${timeAgo(c.posted_at)}${c.category ? ` • ${esc(o.category || c.category)}` : ""}${c.via ? " • ⚠️ بدون رابط مباشر" : ""}
            ${pinned.has(c.id) ? " • 📌 مثبت" : ""}${hidden.has(c.id) ? " • 🙈 مخفي" : ""}${ov[c.id] ? " • ✏️ معدّل" : ""}</div></div>
          <div class="btns">
            <button class="btn sm ${pinned.has(c.id) ? "on" : ""}" data-act="pin" data-id="${esc(c.id)}" title="تثبيت في أول الصفحة">📌</button>
            <button class="btn sm ${hidden.has(c.id) ? "on" : ""}" data-act="hide" data-id="${esc(c.id)}" title="إخفاء من الموقع">🙈</button>
            <button class="btn sm ${editing ? "on" : ""}" data-act="edit" data-id="${esc(c.id)}" title="تعديل">✏️</button>
            <a class="btn sm" href="${esc(c.url)}" target="_blank" rel="noopener" title="فتح على يوديمي">🔗</a>
          </div></div>
          ${editing ? `<div class="editor">
            ${grid2(field(`content.overrides.${c.id}.title`, "العنوان", { placeholder: c.title }),
                    field(`content.overrides.${c.id}.category`, "التصنيف", { placeholder: c.category || "" }))}
            ${field(`content.overrides.${c.id}.image`, "رابط الصورة", { dir: "ltr", placeholder: c.image || "https://..." })}
            <button class="btn sm danger" data-act="clear-override" data-id="${esc(c.id)}">إلغاء كل التعديلات على هذا الكورس</button>
          </div>` : ""}`;
      };
      const sources = countBy(S.data.courses, "channel");
      const langs = countBy(S.data.courses, "language");
      const allowed = new Set(st.content.allowed_languages);
      const manual = st.manual_courses.map((m, i) => `
        <div class="item"><div class="grow"><div class="t">${esc(m.title || m.url)}</div><div class="s" dir="ltr">${esc(m.url)}</div></div>
          <button class="btn sm danger" data-act="del-manual" data-i="${i}">حذف</button></div>`).join("");
      const sel = f.selected.size;
      return `
        <div class="page-head"><h1>الكورسات</h1></div>
        <div class="panel">
          <div class="toolbar">
            <input id="course-q" type="search" placeholder="ابحث في الكورسات…" value="${esc(f.q)}">
            <select id="course-show">
              ${[["all", `الكل (${S.data.courses.length})`], ["pinned", `المثبتة (${pinned.size})`], ["hidden", `المخفية (${hidden.size})`],
                 ["edited", `المعدّلة (${Object.keys(ov).length})`], ["indirect", "بدون رابط مباشر"],
                 ...sources.map(([n, k]) => [`src:${n}`, `المصدر: ${n} (${k})`])]
                .map(([v, t]) => `<option value="${esc(v)}" ${f.show === v ? "selected" : ""}>${esc(t)}</option>`).join("")}
            </select>
          </div>
          <div class="bulk" ${sel ? "" : "hidden"}>
            <b>${sel} محدد</b>
            <button class="btn sm" data-act="bulk-hide">🙈 إخفاء</button>
            <button class="btn sm" data-act="bulk-show">👁 إظهار</button>
            <button class="btn sm" data-act="bulk-pin">📌 تثبيت</button>
            <button class="btn sm" data-act="bulk-unpin">إلغاء التثبيت</button>
            <button class="btn sm" data-act="bulk-clear">إلغاء التحديد</button>
          </div>
          <p class="muted small">📌 يظهر أولاً • 🙈 لا يظهر في الموقع • ✏️ تعديل العنوان/الصورة/التصنيف. <label class="check inline"><input type="checkbox" data-act="pick-all"> تحديد الظاهر</label></p>
          <div class="list">${list.slice(0, f.limit).map(row).join("") || '<p class="empty">لا توجد كورسات.</p>'}</div>
          ${list.length > f.limit ? `<div class="center"><button class="btn" data-act="more">عرض المزيد (${list.length - f.limit})</button></div>` : ""}
        </div>
        ${panel("➕ إضافة كورس يدوياً", `
          <form class="inline-form" id="manual-form">
            <label>رابط الكورس <input name="url" dir="ltr" required placeholder="https://www.udemy.com/course/...?couponCode=..."></label>
            <label>العنوان (اختياري) <input name="title"></label>
            <label>رابط الصورة (اختياري) <input name="image" dir="ltr"></label>
            <button class="btn primary" type="submit">إضافة</button>
          </form>${manual ? `<div class="list" style="margin-top:12px">${manual}</div>` : ""}`)}
        ${panel("⚙️ قواعد عرض الكورسات", `
          ${grid2(field("content.max_age_days", "مدة بقاء الكورس بالأيام", { type: "number", min: 1, max: 60, hint: "بعدها يُحذف الكورس من الموقع تلقائياً." }),
                  field("content.min_rating", "أقل تقييم يُعرض (0 = الكل)", { type: "number", min: 0, max: 5, hint: "مثلاً 4 لعرض الكورسات الجيدة فقط." }))}
          ${field("content.blocked_words", "كلمات محظورة (كل كلمة في سطر)", { type: "list", rows: 3, hint: "أي كورس يحتوي عنوانه أو تصنيفه على كلمة منها لن يظهر." })}
          <label>اللغات المعروضة <span class="hint">بدون تحديد = كل اللغات.</span></label>
          <div class="chips-select">${langs.map(([l, k]) => `<label class="chip-check"><input type="checkbox" data-act="lang" value="${esc(l)}" ${allowed.has(l) ? "checked" : ""}> ${esc(LANG_AR[l] || l)} <small>${k}</small></label>`).join("")}</div>
        `)}`;
    },

    sources() {
      const stats = S.data.sources || {};
      const st = S.settings;
      const row = (src, i) => {
        const s2 = stats[src.name];
        const tg = src.type === "telegram";
        const info = !s2 ? "لم يُسحب بعد (سيُسحب في التحديث القادم)"
          : s2.error ? `<span class="badge err">مشكلة</span> ${esc(s2.error)}`
          : tg ? `${s2.messages} رسالة • ${s2.courses} كورس في آخر سحب` : `${s2.courses} كورس في آخر سحب`;
        const view = tg ? `https://t.me/s/${encodeURIComponent(src.name)}` : (SITE_SOURCES[src.type]?.url || "#");
        return `<div class="item">
          <label class="switch"><input type="checkbox" data-act="toggle-source" data-i="${i}" ${src.enabled !== false ? "checked" : ""}></label>
          <div class="grow"><div class="t" dir="ltr" style="text-align:right">${tg ? "@" : ""}${esc(src.name)}</div>
            <div class="s">${tg ? "قناة تيليجرام" : "موقع كوبونات (روابط مباشرة)"} • ${info}</div></div>
          <div class="btns">
            <a class="btn sm" href="${view}" target="_blank" rel="noopener">👁 عرض</a>
            <button class="btn sm danger" data-act="del-source" data-i="${i}">حذف</button>
          </div></div>`;
      };
      const missing = Object.entries(SITE_SOURCES).filter(([t]) => !st.sources.some((s) => s.type === t));
      return `
        <div class="page-head"><h1>مصادر الكورسات</h1></div>
        ${panel(`المصادر (${st.sources.length})`, `<div class="list">${st.sources.map(row).join("") || '<p class="empty">لا توجد مصادر.</p>'}</div>`)}
        <div class="row2">
          ${panel("➕ إضافة قناة تيليجرام", `
            <form class="inline-form" id="source-form">
              <label>رابط القناة <input name="link" dir="ltr" required placeholder="https://t.me/..."></label>
              <button class="btn primary" type="submit">إضافة</button>
            </form>`, "يجب أن تكون القناة عامة. مثال: https://t.me/Udemy4U")}
          ${panel("➕ إضافة موقع كوبونات", missing.length ? `<div class="btns wrap">${missing.map(([t, m]) =>
            `<button class="btn" data-act="add-site" data-type="${t}">+ ${esc(m.name)}</button>`).join("")}</div>` : '<p class="muted">كل المواقع المدعومة مضافة.</p>')}
        </div>
        ${panel("كورسات بدون رابط يوديمي مباشر", field("show_indirect_links", "إظهار الكورسات التي لم نجد رابطها المباشر (تحوّل لموقع المصدر)", { type: "checkbox" }),
          "بعض القنوات (مثل قنوات courson) تضع رابط موقعها بدلاً من رابط يوديمي.")}`;
    },

    ads() {
      const a = S.settings.ads;
      const SLOTS = {
        header: ["أعلى الصفحة", "أعلى الصفحة الرئيسية وصفحات الكورسات."],
        in_feed: ["بين الكورسات", "بين بطاقات الكورسات."],
        countdown: ["إعلان العدّاد ⭐", "داخل النافذة المنبثقة أثناء العدّ التنازلي (أهم مكان)."],
        course_bottom: ["أسفل صفحة الكورس", "تحت معلومات الكورس."],
        footer: ["أسفل الصفحة", "نهاية الصفحة الرئيسية."],
      };
      const slot = (key) => `<div class="panel">
          <div class="slot-head"><div><h2>${SLOTS[key][0]}</h2><p class="muted small" style="margin:0">${SLOTS[key][1]}</p></div>
          ${field(`ads.slots.${key}.enabled`, "مفعّل", { type: "checkbox" })}</div>
          ${field(`ads.slots.${key}.html`, "", { type: "code", rows: 4, placeholder: "الصق كود الإعلان هنا" })}
        </div>`;
      return `
        <div class="page-head"><h1>الإعلانات</h1></div>
        ${panel("⏱ نافذة الإعلان قبل رابط الكورس", grid2(
          field("ads.countdown_seconds", "مدة الانتظار بالثواني (0 = بدون)", { type: "number", min: 0, max: 120, hint: "ننصح بـ 10–20 ثانية." }),
          field("ads.in_feed_every", "إعلان بين الكورسات بعد كل", { type: "number", min: 2, max: 30, hint: "عدد البطاقات." })),
          "نصوص النافذة تتغير من «المظهر والنصوص».")}
        ${Object.keys(SLOTS).map(slot).join("")}
        ${panel("ملف ads.txt", field("ads.ads_txt", "", { type: "code", rows: 4, placeholder: "google.com, pub-0000000000000000, DIRECT, f08c47fec0942fa0" }),
          "تطلبه شبكات الإعلانات مثل AdSense. انسخه من حسابك لديهم.")}
        <div class="panel help"><b>💰 كيف أبدأ الربح؟</b><ol>
          <li><b>Google AdSense</b>: يحتاج دومين خاص وصفحات (من نحن، الخصوصية، اتصل بنا — موجودة). سجّل في adsense.google.com والصق كود التحقق في «إعدادات الموقع ← كود الهيدر».</li>
          <li><b>Adsterra / Monetag</b>: تقبل المواقع الجديدة بسرعة. انسخ كود الإعلان والصقه في المكان المناسب.</li>
          <li><b>بيع مساحة مباشرة</b>: <code>&lt;a href="رابط"&gt;&lt;img src="صورة"&gt;&lt;/a&gt;</code></li>
        </ol></div>`;
    },

    appearance() {
      const ap = S.settings.appearance;
      return `
        <div class="page-head"><h1>المظهر والنصوص</h1></div>
        ${panel("🎨 الألوان والشكل", `
          <div class="row4">
            ${field("appearance.accent", "اللون الأساسي", { type: "color" })}
            ${field("appearance.accent2", "اللون الثانوي", { type: "color" })}
            ${field("appearance.hero_from", "خلفية الواجهة (من)", { type: "color" })}
            ${field("appearance.hero_to", "خلفية الواجهة (إلى)", { type: "color" })}
          </div>
          <div class="preview" style="--a:${esc(ap.accent)};--b:${esc(ap.accent2)};--h1:${esc(ap.hero_from)};--h2:${esc(ap.hero_to)}">
            <div class="pv-hero">معاينة الواجهة</div><button class="pv-btn" type="button">احصل عليه مجاناً</button></div>
          <div class="row4">
            ${field("appearance.radius", "استدارة الحواف", { type: "number", min: 0, max: 32 })}
            ${field("appearance.default_theme", "الوضع الافتراضي", { type: "select", options: [["auto", "حسب جهاز الزائر"], ["light", "فاتح"], ["dark", "داكن"]] })}
            ${field("appearance.cards_per_page", "عدد الكورسات في الصفحة", { type: "number", min: 6, max: 96 })}
            ${field("appearance.default_sort", "الترتيب الافتراضي", { type: "select", options: [["new", "الأحدث"], ["rating", "الأعلى تقييماً"], ["price", "الأغلى سعراً"], ["az", "أبجدياً"]] })}
          </div>`)}
        ${panel("🏷️ الشعار والأيقونة", grid2(
          field("appearance.logo_emoji", "شعار (إيموجي)", { hint: "يُستخدم إذا لم تضع صورة." }),
          field("appearance.logo_url", "رابط صورة الشعار", { dir: "ltr", placeholder: "https://.../logo.png" })) +
          field("appearance.favicon_url", "رابط أيقونة المتصفح (favicon)", { dir: "ltr", placeholder: "https://.../favicon.png" }))}
        ${panel("🧩 الأقسام الظاهرة", `<div class="row2">
          ${field("appearance.sections.stats", "عدد الكورسات ووقت التحديث في الواجهة", { type: "checkbox" })}
          ${field("appearance.sections.filters", "شريط الفلاتر والترتيب", { type: "checkbox" })}
          ${field("appearance.sections.categories", "أزرار التصنيفات", { type: "checkbox" })}
          ${field("appearance.sections.related", "«كورسات أخرى» في صفحة الكورس", { type: "checkbox" })}
          ${field("appearance.sections.footer_categories", "التصنيفات في أسفل الصفحة", { type: "checkbox" })}
          ${field("appearance.sections.theme_toggle", "زر الوضع الليلي", { type: "checkbox" })}</div>`)}
        ${panel("📢 شريط إعلان أعلى الموقع", `
          ${field("announcement.enabled", "إظهار الشريط", { type: "checkbox" })}
          ${grid2(field("announcement.text", "النص", { placeholder: "مثال: تابعنا على تيليجرام لتصلك الكورسات أولاً بأول" }),
                  field("announcement.link", "رابط (اختياري)", { dir: "ltr" }))}
          ${field("announcement.color", "لون الشريط", { type: "color" })}`)}
        ${panel("✍️ نصوص الصفحة الرئيسية", `
          ${grid2(field("texts.eyebrow", "الشارة الصغيرة"), field("texts.tagline", "العنوان الكبير"))}
          ${field("texts.lead", "الفقرة تحت العنوان", { type: "textarea", rows: 2 })}
          ${grid2(field("texts.search_placeholder", "نص خانة البحث"), field("texts.card_button", "زر البطاقة"))}
          ${field("texts.footer_text", "نص أسفل الصفحة", { type: "textarea", rows: 2 })}`)}
        ${panel("🎓 نصوص صفحة الكورس والنافذة المنبثقة", `
          ${grid2(field("texts.course_button", "زر صفحة الكورس"), field("texts.popup_go", "زر الذهاب للكورس"))}
          ${field("texts.course_hint", "ملاحظة تحت الزر", { type: "textarea", rows: 2 })}
          ${field("texts.popup_title", "عنوان النافذة")}
          ${field("texts.popup_message", "رسالة النافذة", { type: "textarea", rows: 2, hint: "{seconds} = عدد الثواني المتبقية." })}
          ${grid2(field("texts.popup_close", "زر الإغلاق"), field("texts.expired_notice", "رسالة الكوبون المنتهي"))}`)}
        ${panel("🧑‍💻 CSS مخصص (للمتقدمين)", field("appearance.custom_css", "", { type: "code", rows: 6, placeholder: ".hero h1 { font-size: 3rem; }" }))}`;
    },

    pages() {
      const st = S.settings;
      const editing = S.pageEditing;
      const row = (p, i) => `<div class="item">
          <div class="grow"><div class="t">${esc(p.title)}</div><div class="s" dir="ltr" style="text-align:right">/p/${esc(p.slug)}/
            ${p.in_nav ? " • في القائمة العلوية" : ""}${p.in_footer ? " • في الأسفل" : ""}</div></div>
          <div class="btns">
            <button class="btn sm ${editing === i ? "on" : ""}" data-act="edit-page" data-i="${i}">✏️ تعديل</button>
            <a class="btn sm" href="${esc(siteUrl())}p/${esc(p.slug)}/" target="_blank" rel="noopener">👁</a>
            <button class="btn sm danger" data-act="del-page" data-i="${i}">حذف</button>
          </div></div>
          ${editing === i ? `<div class="editor">
            ${grid2(field(`pages.${i}.title`, "العنوان"), field(`pages.${i}.slug`, "الرابط (إنجليزي بدون مسافات)", { dir: "ltr" }))}
            ${field(`pages.${i}.description`, "وصف للسيو (اختياري)")}
            ${field(`pages.${i}.body`, "المحتوى", { type: "textarea", rows: 12,
              hint: "تنسيق بسيط: <code>## عنوان</code> • <code>- عنصر قائمة</code> • <code>**عريض**</code> • <code>[نص](https://رابط)</code>" })}
            <div class="row2">${field(`pages.${i}.in_nav`, "يظهر في القائمة العلوية", { type: "checkbox" })}
              ${field(`pages.${i}.in_footer`, "يظهر في أسفل الموقع", { type: "checkbox" })}
              ${field(`pages.${i}.html`, "المحتوى HTML (للمتقدمين)", { type: "checkbox" })}</div>
          </div>` : ""}`;
      const navRow = (n, i) => `<div class="item"><div class="grow">${grid2(field(`nav.${i}.label`, "النص"), field(`nav.${i}.url`, "الرابط", { dir: "ltr" }))}</div>
          <button class="btn sm danger" data-act="del-nav" data-i="${i}">حذف</button></div>`;
      return `
        <div class="page-head"><h1>الصفحات والقائمة</h1><button class="btn primary" data-act="add-page">+ صفحة جديدة</button></div>
        ${panel(`الصفحات (${st.pages.length})`, `<div class="list">${st.pages.map(row).join("") || '<p class="empty">لا توجد صفحات.</p>'}</div>`,
          "صفحات «من نحن» و«سياسة الخصوصية» و«اتصل بنا» مهمة لثقة الزوار ولقبول AdSense.")}
        ${panel("🔗 روابط إضافية في القائمة العلوية", `<div class="list">${st.nav.map(navRow).join("")}</div>
          <button class="btn" data-act="add-nav">+ رابط</button>`, "مثلاً رابط قناتك على تيليجرام أو مجموعة فيسبوك.")}`;
    },

    seo() {
      const st = S.settings, seo = st.seo;
      const d = seo.description || "";
      const checks = seoChecks();
      const url = siteUrl();
      return `
        <div class="page-head"><h1>السيو ومحركات البحث</h1></div>
        ${panel("✅ قائمة التحسين", `<ul class="checks">${checks.map(([ok, t]) => `<li class="${ok ? "ok" : ""}">${ok ? "✅" : "⬜"} ${t}</li>`).join("")}</ul>`)}
        ${panel("📝 العناوين والوصف", `
          ${field("seo.description", "وصف الموقع (يظهر في جوجل)", { type: "textarea", rows: 2, hint: `<span id="desc-count">${d.length}</span> حرف — الأفضل بين 120 و 160.` })}
          ${field("seo.title_home", "عنوان الصفحة الرئيسية", { hint: "{site} = اسم الموقع" })}
          ${field("seo.title_course", "عنوان صفحة الكورس", { hint: "{title} = اسم الكورس • {site} • {category}" })}
          ${field("seo.title_category", "عنوان صفحة التصنيف", { hint: "{category} • {site}" })}
          <div class="serp"><div class="serp-url">${esc(url)}</div><div class="serp-title">${esc((seo.title_home || "").replace("{site}", st.site.name))}</div><div class="serp-desc">${esc(d)}</div></div>`,
          "هكذا تقريباً يظهر موقعك في نتائج جوجل:")}
        ${panel("🔐 التحقق من ملكية الموقع", `
          ${field("seo.google_verification", "Google Search Console", { dir: "ltr", placeholder: "الكود فقط من content=\"...\"" })}
          ${field("seo.bing_verification", "Bing Webmaster Tools", { dir: "ltr" })}
          ${field("seo.yandex_verification", "Yandex Webmaster", { dir: "ltr" })}`,
          "اختر طريقة التحقق «HTML tag»، وانسخ قيمة content فقط.")}
        ${panel("📈 التحليلات والمشاركة", `
          ${grid2(field("seo.ga_id", "Google Analytics (Measurement ID)", { dir: "ltr", placeholder: "G-XXXXXXXXXX" }),
                  field("seo.twitter", "حساب X/تويتر", { dir: "ltr", placeholder: "@username" }))}
          ${field("seo.og_image", "صورة المشاركة الافتراضية", { dir: "ltr", placeholder: "https://.../share.jpg (1200×630)" })}`)}
        ${panel("⚙️ خيارات متقدمة", `<div class="row2">
          ${field("seo.category_pages", "صفحات مستقلة لكل تصنيف (يُنصح بها)", { type: "checkbox" })}
          ${field("seo.rss", "خلاصة RSS ‏(feed.xml)", { type: "checkbox" })}
          ${field("seo.indexnow", "IndexNow: إبلاغ Bing وYandex فوراً بالكورسات الجديدة", { type: "checkbox" })}
          ${field("seo.noindex", "⛔ إخفاء الموقع عن محركات البحث", { type: "checkbox" })}</div>
          ${grid2(field("seo.keep_expired_days", "إبقاء صفحات الكوبونات المنتهية (أيام)", { type: "number", min: 0, max: 60,
                    hint: "تبقى الصفحة وتقول «انتهى الكوبون» وتعرض بدائل، بدل خطأ 404." }),
                  field("seo.indexnow_key", "مفتاح IndexNow", { dir: "ltr", hint: '<button class="linklike inline" type="button" data-act="gen-key">توليد مفتاح جديد</button>' }))}`)}
        <div class="panel help"><b>🔍 خطوات مرة واحدة:</b><ol>
          <li>افتح <a href="https://search.google.com/search-console" target="_blank" rel="noopener">Google Search Console</a> وأضف الموقع (URL prefix).</li>
          <li>اختر «HTML tag»، والصق قيمة content في الخانة أعلاه، واحفظ، وبعد 3 دقائق اضغط Verify.</li>
          <li>من Sitemaps أضف: <code dir="ltr">${esc(url)}sitemap.xml</code></li>
          <li>كرر نفس الخطوات في <a href="https://www.bing.com/webmasters" target="_blank" rel="noopener">Bing Webmaster</a> (يمكنه استيراد الموقع من جوجل مباشرة).</li>
        </ol>
        <p>روابط مفيدة: <a href="${esc(url)}sitemap.xml" target="_blank">sitemap.xml</a> • <a href="${esc(url)}feed.xml" target="_blank">feed.xml</a> • <a href="${esc(url)}robots.txt" target="_blank">robots.txt</a></p></div>`;
    },

    settings() {
      const owner = (S.repo.split("/")[0] || "username").toLowerCase();
      return `
        <div class="page-head"><h1>إعدادات الموقع</h1></div>
        ${panel("ℹ️ معلومات أساسية", `
          ${field("site.name", "اسم الموقع")}
          ${grid2(field("site.url", "رابط الموقع الحالي", { dir: "ltr" }),
                  field("site.custom_domain", "دومين خاص (اختياري)", { dir: "ltr", placeholder: "www.example.com",
                    hint: `في إعدادات الدومين أضف سجل CNAME يشير إلى <code>${esc(owner)}.github.io</code>` }))}`)}
        ${panel("🌐 حسابات التواصل", `<div class="row2">
          ${[["facebook", "فيسبوك"], ["telegram", "تيليجرام"], ["whatsapp", "واتساب"], ["youtube", "يوتيوب"], ["instagram", "إنستجرام"], ["x", "X / تويتر"], ["tiktok", "تيك توك"]]
            .map(([k, l]) => field(`site.social.${k}`, l, { dir: "ltr", placeholder: "https://..." })).join("")}</div>`)}
        ${panel("🧑‍💻 كود الهيدر", field("site.head_code", "", { type: "code", rows: 5, placeholder: '<meta name="..." content="...">' }),
          "أي كود يُطلب وضعه داخل &lt;head&gt; (AdSense، Pixel، أدوات أخرى).")}
        ${panel("💾 نسخة احتياطية", `<div class="btns wrap">
            <button class="btn" data-act="export">⬇️ تنزيل نسخة من الإعدادات</button>
            <label class="btn">⬆️ استعادة من ملف<input type="file" accept="application/json" id="import-file" hidden></label>
          </div>`, "الاستعادة تستبدل الإعدادات الحالية، ثم تضغط «حفظ ونشر».")}`;
    },

    users() {
      const st = S.settings;
      const collab = S.collaborators ? new Set(S.collaborators.map((c) => c.login.toLowerCase())) : null;
      const invited = S.invitations ? new Set(S.invitations.map((i) => i.invitee?.login?.toLowerCase())) : new Set();
      const status = (login) => {
        const l = login.toLowerCase();
        if (!collab) return "";
        if (collab.has(l)) return '<span class="badge ok">✓ لديه وصول للمستودع</span>';
        if (invited.has(l)) return '<span class="badge unknown">⏳ الدعوة بانتظار القبول</span>';
        return `<span class="badge err">ليس عضواً بعد</span> <button class="linklike inline" data-act="invite" data-login="${esc(login)}">إرسال دعوة</button>`;
      };
      const row = (u, i) => `<div class="item user-row ${u.disabled ? "dim" : ""}">
          <img class="avatar" src="https://github.com/${encodeURIComponent(u.login)}.png?size=64" alt="" onerror="this.style.visibility='hidden'">
          <div class="grow">
            <div class="t" dir="ltr" style="text-align:right">@${esc(u.login)} ${u.name ? `<span class="muted">— ${esc(u.name)}</span>` : ""}</div>
            <div class="s">${status(u.login)}</div>
            <div class="row2 tight">
              ${field(`users.${i}.name`, "الاسم")}
              ${field(`users.${i}.role`, "الدور", { type: "select", options: Object.entries(ROLE_LABELS) })}
            </div>
            ${u.role === "custom" ? `<div class="chips-select">${ALL_PERMS.map((p) =>
              `<label class="chip-check"><input type="checkbox" data-act="perm" data-i="${i}" value="${p}" ${(u.permissions || []).includes(p) ? "checked" : ""}> ${PERM_LABELS[p] || p}</label>`).join("")}</div>` : ""}
          </div>
          <div class="btns col">
            ${field(`users.${i}.disabled`, "موقوف", { type: "checkbox" })}
            <button class="btn sm danger" data-act="del-user" data-i="${i}">حذف</button>
          </div></div>`;
      return `
        <div class="page-head"><h1>المستخدمون والصلاحيات</h1></div>
        ${panel("👑 صاحب الموقع", `<div class="item"><img class="avatar" src="https://github.com/${encodeURIComponent(S.owner)}.png?size=64" alt="">
          <div class="grow"><div class="t" dir="ltr" style="text-align:right">@${esc(S.owner)}</div><div class="s">كل الصلاحيات دائماً</div></div></div>`)}
        ${panel(`👥 الفريق (${st.users.length})`, `<div class="list">${st.users.map(row).join("") || '<p class="empty">لم تُضف أحداً بعد.</p>'}</div>`)}
        ${panel("➕ إضافة مستخدم", `
          <form class="inline-form" id="user-form">
            <label>اسم المستخدم على GitHub <input name="login" dir="ltr" required placeholder="username"></label>
            <label>الدور <select name="role">${Object.entries(ROLE_LABELS).map(([v, t]) => `<option value="${v}" ${v === "editor" ? "selected" : ""}>${t}</option>`).join("")}</select></label>
            <button class="btn primary" type="submit">إضافة</button>
          </form>`, "ليس لديه حساب؟ يمكنه إنشاء حساب مجاني على github.com.")}
        <div class="panel help"><b>كيف يعمل نظام الصلاحيات؟</b><ol>
          <li>أضف اسم المستخدم هنا واختر دوره، ثم اضغط «حفظ ونشر».</li>
          <li>اضغط «إرسال دعوة» ليصله طلب انضمام للمستودع (يحتاج مفتاحك صلاحية <b>Administration</b>)، أو أضفه يدوياً من
            <a href="https://github.com/${esc(S.repo)}/settings/access" target="_blank" rel="noopener">إعدادات المستودع ← Collaborators</a>.</li>
          <li>بعد قبول الدعوة، يدخل اللوحة بمفتاحه الخاص (الخطوات في صفحة الدخول) ويرى فقط الأقسام المسموحة له.</li>
          <li>🛡️ أي تعديل على قسم غير مسموح له يُلغى تلقائياً على GitHub ويظهر في «سجل النشاط».</li>
          <li>⚠️ الأعضاء يملكون صلاحية كتابة على المستودع نفسه، لذا أضف فقط من تثق بهم.</li>
        </ol></div>`;
    },

    activity() {
      const row = (c) => {
        const who = c.author?.login || c.commit?.author?.name || "—";
        const msg = (c.commit?.message || "").split("\n")[0];
        const bad = /Restore settings changed without permission/.test(msg);
        return `<div class="item ${bad ? "warn-row" : ""}">
          <img class="avatar" src="${esc(c.author?.avatar_url || "")}" alt="" onerror="this.style.visibility='hidden'">
          <div class="grow"><div class="t">${bad ? "⛔ " : ""}${esc(msg)}</div><div class="s">@${esc(who)} • ${timeAgo(c.commit?.author?.date)}</div></div>
          <a class="btn sm" href="${esc(c.html_url)}" target="_blank" rel="noopener">التفاصيل</a></div>`;
      };
      return `
        <div class="page-head"><h1>سجل النشاط</h1><button class="btn" data-act="reload-activity">🔄 تحديث</button></div>
        ${panel("تعديلات الإعدادات", `<div class="list">${S.commits.map(row).join("") || '<p class="empty">لا يوجد نشاط بعد.</p>'}</div>`,
          "كل حفظ من لوحة التحكم يُسجَّل هنا مع اسم صاحبه. التعديلات غير المسموحة تظهر بعلامة ⛔.")}`;
    },
  };

  // For background refreshes: don't wipe what the user is typing.
  function softRender() {
    const a = document.activeElement;
    const typing = a && $("view").contains(a) && /INPUT|TEXTAREA|SELECT/.test(a.tagName);
    const filled = [...$("view").querySelectorAll("form input")].some((i) => i.value);
    if (!typing && !filled) render();
  }

  function render() {
    const visible = TABS.filter((t) => can(t.perm));
    if (!visible.some((t) => t.id === S.tab)) S.tab = "overview";
    $("nav").innerHTML = visible.map((t) => `<a href="#${t.id}" data-tab="${t.id}" class="${t.id === S.tab ? "active" : ""}">${t.icon} ${t.label}</a>`).join("");
    $("view").innerHTML = views[S.tab]();
    $("open-site").href = siteUrl();
    changed();
  }

  // ---------- actions ----------
  function parseChannel(input) {
    let v = input.trim();
    const m = v.match(/(?:t\.me|telegram\.me)\/(?:s\/)?([A-Za-z0-9_]+)/i);
    if (m) v = m[1];
    v = v.replace(/^@/, "");
    return /^[A-Za-z][A-Za-z0-9_]{3,31}$/.test(v) ? v : null;
  }
  function toggleIn(list, id, on) {
    const i = list.indexOf(id);
    if (on === undefined) on = i < 0;
    if (on && i < 0) list.push(id);
    if (!on && i >= 0) list.splice(i, 1);
  }
  function cleanOverride(id) {
    const ov = S.settings.content.overrides;
    if (ov[id] && Object.values(ov[id]).every((v) => v === "" || v == null)) delete ov[id];
  }

  async function runNow(btn) {
    btn.disabled = true;
    btn.textContent = "⏳ جاري التشغيل…";
    try {
      await gh(`/actions/workflows/${WORKFLOW}/dispatches`, { method: "POST", body: JSON.stringify({ ref: S.defaultBranch || BRANCH }) });
      toast("✓ بدأ سحب الكورسات. يستغرق عادةً من 2 إلى 6 دقائق.");
      setTimeout(async () => { await loadRuns(); if (S.tab === "overview") softRender(); }, 4000);
    } catch (e) {
      toast(e.status === 403 ? "المفتاح لا يملك صلاحية Actions (Read and write)." : `تعذّر التشغيل (${e.detail || e.message})`, true);
      btn.disabled = false;
    }
  }

  async function invite(login) {
    try {
      await gh(`/collaborators/${encodeURIComponent(login)}`, { method: "PUT", body: JSON.stringify({ permission: "push" }) });
      toast(`✓ تم إرسال دعوة إلى @${login}.`);
      await loadCollaborators();
      render();
    } catch (e) {
      toast(e.status === 403 || e.status === 404
        ? "مفتاحك لا يملك صلاحية Administration. أضفه يدوياً من إعدادات المستودع ← Collaborators."
        : `تعذّر الإرسال (${e.detail || e.message})`, true);
    }
  }
  async function loadCollaborators() {
    try {
      S.collaborators = await gh("/collaborators?per_page=100");
      S.invitations = await gh("/invitations?per_page=100").catch(() => []);
    } catch { S.collaborators = null; }
  }

  document.addEventListener("click", (e) => {
    const el = e.target.closest("[data-act]");
    if (!el || (el.tagName === "INPUT" && !["pick", "pick-all"].includes(el.dataset.act))) return;
    const act = el.dataset.act, st = S.settings, id = el.dataset.id, i = +el.dataset.i;
    const f = S.cf;
    switch (act) {
      case "run": return runNow(el);
      case "pin": toggleIn(st.pinned, id); break;
      case "hide": toggleIn(st.hidden, id); break;
      case "edit": f.editing = f.editing === id ? null : id; if (f.editing) st.content.overrides[id] ||= {}; else cleanOverride(id); break;
      case "clear-override": delete st.content.overrides[id]; f.editing = null; break;
      case "more": f.limit += 100; break;
      case "pick": el.checked ? f.selected.add(id) : f.selected.delete(id); break;
      case "pick-all": document.querySelectorAll(".pick").forEach((p) => el.checked ? f.selected.add(p.dataset.id) : f.selected.delete(p.dataset.id)); break;
      case "bulk-hide": f.selected.forEach((x) => toggleIn(st.hidden, x, true)); break;
      case "bulk-show": f.selected.forEach((x) => toggleIn(st.hidden, x, false)); break;
      case "bulk-pin": f.selected.forEach((x) => toggleIn(st.pinned, x, true)); break;
      case "bulk-unpin": f.selected.forEach((x) => toggleIn(st.pinned, x, false)); break;
      case "bulk-clear": f.selected.clear(); break;
      case "del-manual": if (!confirm("حذف هذا الكورس؟")) return; st.manual_courses.splice(i, 1); break;
      case "del-source": if (!confirm(`حذف المصدر ${st.sources[i].name}؟`)) return; st.sources.splice(i, 1); break;
      case "add-site": st.sources.push({ type: el.dataset.type, name: SITE_SOURCES[el.dataset.type].name, enabled: true }); break;
      case "add-page": st.pages.push({ slug: `page-${st.pages.length + 1}`, title: "صفحة جديدة", body: "", in_footer: true, in_nav: false, html: false });
        S.pageEditing = st.pages.length - 1; break;
      case "edit-page": S.pageEditing = S.pageEditing === i ? null : i; break;
      case "del-page": if (!confirm(`حذف صفحة «${st.pages[i].title}»؟`)) return; st.pages.splice(i, 1); S.pageEditing = null; break;
      case "add-nav": st.nav.push({ label: "", url: "" }); break;
      case "del-nav": st.nav.splice(i, 1); break;
      case "gen-key": st.seo.indexnow_key = [...crypto.getRandomValues(new Uint8Array(16))].map((b) => b.toString(16).padStart(2, "0")).join("");
        st.seo.indexnow = true; break;
      case "del-user": if (!confirm(`حذف @${st.users[i].login}؟`)) return; st.users.splice(i, 1); break;
      case "invite": return invite(el.dataset.login);
      case "export": {
        const blob = new Blob([JSON.stringify(st, null, 2)], { type: "application/json" });
        const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: `settings-${new Date().toISOString().slice(0, 10)}.json` });
        a.click(); URL.revokeObjectURL(a.href); return;
      }
      case "reload-activity": loadCommits().then(render); return;
      default: return;
    }
    if (!["pick", "pick-all"].includes(act)) render(); else {
      const bulk = document.querySelector(".bulk");
      if (bulk) { bulk.hidden = !f.selected.size; bulk.querySelector("b").textContent = `${f.selected.size} محدد`; }
    }
  });

  document.addEventListener("change", (e) => {
    const el = e.target, st = S.settings;
    if (el.dataset.act === "toggle-source") { st.sources[+el.dataset.i].enabled = el.checked; return changed(); }
    if (el.dataset.act === "lang") { toggleIn(st.content.allowed_languages, el.value, el.checked); return changed(); }
    if (el.dataset.act === "perm") { const u = st.users[+el.dataset.i]; u.permissions ||= []; toggleIn(u.permissions, el.value, el.checked); return changed(); }
    if (el.id === "course-show") { S.cf.show = el.value; S.cf.limit = 100; return render(); }
    if (el.id === "import-file" && el.files[0]) {
      el.files[0].text().then((txt) => {
        try { S.settings = normalise(JSON.parse(txt)); render(); toast("تم تحميل النسخة. راجعها ثم اضغط «حفظ ونشر»."); }
        catch { toast("الملف غير صالح.", true); }
      });
      return;
    }
    if (el.dataset.bind && (el.type === "checkbox" || el.tagName === "SELECT")) {
      setPath(st, el.dataset.bind, readInput(el));
      if (/^users\.\d+\.role$/.test(el.dataset.bind) || el.dataset.bind === "seo.indexnow") render(); else changed();
    }
  });

  document.addEventListener("input", (e) => {
    const el = e.target;
    if (el.id === "course-q") {
      S.cf.q = el.value; S.cf.limit = 100;
      const pos = el.selectionStart;
      render();
      const q = $("course-q"); q.focus(); q.setSelectionRange(pos, pos);
      return;
    }
    if (!el.dataset.bind || el.type === "checkbox" || el.tagName === "SELECT") return;
    setPath(S.settings, el.dataset.bind, readInput(el));
    if (el.dataset.bind.startsWith("content.overrides.")) cleanOverride(el.dataset.bind.split(".")[2]);
    if (el.type === "color") {
      el.nextElementSibling.textContent = el.value;
      const pv = document.querySelector(".preview");
      const ap = S.settings.appearance;
      if (pv) pv.style.cssText = `--a:${ap.accent};--b:${ap.accent2};--h1:${ap.hero_from};--h2:${ap.hero_to}`;
    }
    if (el.dataset.bind === "seo.description" && $("desc-count")) $("desc-count").textContent = el.value.length;
    changed();
  });

  document.addEventListener("submit", (e) => {
    const form = e.target;
    if (form.id === "login-form") return;
    e.preventDefault();
    const fd = new FormData(form), st = S.settings;
    if (form.id === "source-form") {
      const name = parseChannel(fd.get("link"));
      if (!name) return toast("الرابط غير صحيح. مثال صحيح: https://t.me/Udemy4U", true);
      if (st.sources.some((s) => s.name.toLowerCase() === name.toLowerCase())) return toast("هذه القناة موجودة بالفعل.", true);
      st.sources.push({ type: "telegram", name, enabled: true });
      toast(`تمت إضافة @${name}. اضغط "حفظ ونشر" لتفعيلها.`);
    }
    if (form.id === "manual-form") {
      const url = String(fd.get("url")).trim();
      if (!/^https?:\/\//.test(url)) return toast("الرابط يجب أن يبدأ بـ https://", true);
      if (/udemy\.com/i.test(url) && !/couponCode=/i.test(url)) return toast("رابط يوديمي يجب أن يحتوي على الكوبون (couponCode=...).", true);
      st.manual_courses.unshift({ url, title: String(fd.get("title")).trim(), image: String(fd.get("image")).trim(),
        added_at: new Date().toISOString().replace(/\.\d+Z$/, "+00:00") });
      toast('تمت الإضافة. اضغط "حفظ ونشر" ليظهر في الموقع.');
    }
    if (form.id === "user-form") {
      const login = String(fd.get("login")).trim().replace(/^@/, "").replace(/^https?:\/\/github\.com\//, "").replace(/\/.*$/, "");
      if (!/^[A-Za-z0-9-]{1,39}$/.test(login)) return toast("اسم المستخدم غير صحيح.", true);
      if (login.toLowerCase() === S.owner.toLowerCase() || st.users.some((u) => u.login.toLowerCase() === login.toLowerCase()))
        return toast("هذا المستخدم موجود بالفعل.", true);
      st.users.push({ login, name: "", role: String(fd.get("role")), permissions: [], disabled: false });
      toast(`تمت إضافة @${login}. اضغط "حفظ ونشر"، ثم «إرسال دعوة».`);
    }
    render();
  });

  $("save").addEventListener("click", save);
  $("discard").addEventListener("click", () => {
    if (!confirm("التراجع عن كل التغييرات غير المحفوظة؟")) return;
    S.settings = JSON.parse(S.original);
    S.cf.editing = null; S.pageEditing = null;
    render();
  });
  window.addEventListener("beforeunload", (e) => { if (dirty()) { e.preventDefault(); e.returnValue = ""; } });
  window.addEventListener("hashchange", () => {
    const tab = location.hash.slice(1);
    if (views[tab]) { S.tab = tab; render(); if (tab === "users" && !S.collaborators) loadCollaborators().then(softRender); }
  });
  $("logout").addEventListener("click", () => {
    if (dirty() && !confirm("لديك تغييرات غير محفوظة. خروج على أي حال؟")) return;
    store.clear();
    location.reload();
  });
  $("theme-admin").addEventListener("click", () => {
    const root = document.documentElement;
    const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("theme", root.dataset.theme); } catch {}
  });
  setInterval(async () => {
    if (S.tab === "overview" && document.visibilityState === "visible" && S.runs.some((r) => r.status !== "completed")) {
      await loadRuns();
      if (!S.runs.some((r) => r.status !== "completed")) await loadCourses();
      softRender();
    }
  }, 15000);

  // ---------- login & start ----------
  async function start() {
    $("login").hidden = true;
    $("app").hidden = false;
    $("view").innerHTML = '<p class="empty">جاري التحميل…</p>';
    const [info, me] = await Promise.all([gh(""), gh("/user")]);
    S.me = me;
    S.owner = info.owner.login;
    S.defaultBranch = info.default_branch;
    S.isOwner = me.login.toLowerCase() === S.owner.toLowerCase();
    await Promise.all([loadSettings(), loadCourses(), loadRuns(), loadCommits()]);
    S.perms = permsFor(S.settings, me.login);
    const user = S.settings.users.find((u) => u.login.toLowerCase() === me.login.toLowerCase());
    const role = S.isOwner ? "👑 صاحب الموقع" : user ? (user.disabled ? "⛔ موقوف" : ROLE_LABELS[user.role] || user.role) : "⛔ بدون صلاحيات";
    $("me").innerHTML = `<img class="avatar" src="${esc(me.avatar_url)}" alt=""><div><b dir="ltr">@${esc(me.login)}</b><small>${esc(role)}</small></div>`;
    if (!S.isOwner && !user) toast("حسابك غير مضاف في قائمة المستخدمين. اطلب من صاحب الموقع إضافتك.", true);
    const tab = location.hash.slice(1);
    if (views[tab]) S.tab = tab;
    render();
    if (S.tab === "users") loadCollaborators().then(softRender);
  }

  function showLogin(error) {
    $("app").hidden = true;
    $("login").hidden = false;
    $("login-repo").value = S.repo;
    if (S.repo) document.querySelectorAll(".repo-hint").forEach((x) => (x.textContent = S.repo.split("/")[1] || S.repo));
    const err = $("login-error");
    err.hidden = !error;
    err.textContent = error || "";
  }

  $("login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    S.repo = $("login-repo").value.trim().replace(/^https?:\/\/github\.com\//, "").replace(/\/+$/, "");
    S.token = $("login-token").value.trim();
    const btn = e.target.querySelector("button");
    btn.disabled = true;
    try {
      const info = await gh("");
      if (!info.permissions || !info.permissions.push) throw Object.assign(new Error("perm"), { status: 403 });
      const remember = $("login-remember").checked;
      store.set("gh_token", S.token, remember);
      store.set("gh_repo", S.repo, remember);
      await start();
    } catch (err) {
      showLogin(err.status === 401 ? "المفتاح غير صحيح أو منتهي."
        : err.status === 404 ? "لم نجد المستودع. تأكد من الاسم ومن أن لديك وصولاً إليه."
        : err.status === 403 ? "المفتاح لا يملك صلاحية الكتابة على المستودع."
        : "تعذّر الاتصال بـ GitHub، تأكد من الإنترنت.");
    } finally { btn.disabled = false; }
  });

  if (S.token && S.repo) start().catch((e) => showLogin(e.status === 401 ? "انتهت صلاحية المفتاح، أدخل مفتاحاً جديداً." : "تعذّر التحميل، حاول مرة أخرى."));
  else showLogin();
})();
