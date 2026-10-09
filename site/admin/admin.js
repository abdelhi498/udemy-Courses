(() => {
  "use strict";
  const BRANCH = "main";
  const WORKFLOW = "update.yml";
  const SETTINGS_PATH = "data/settings.json";
  const COURSES_PATH = "data/courses.json";

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

  // ---------- storage (may be blocked: never rely on it) ----------
  const store = {
    get(k) { try { return localStorage.getItem(k) || sessionStorage.getItem(k); } catch { return null; } },
    set(k, v, remember) { try { (remember ? localStorage : sessionStorage).setItem(k, v); } catch {} },
    clear() { try { ["gh_token", "gh_repo"].forEach((k) => { localStorage.removeItem(k); sessionStorage.removeItem(k); }); } catch {} },
  };
  try { const t = localStorage.getItem("theme"); if (t) document.documentElement.dataset.theme = t; } catch {}

  const S = {
    token: store.get("gh_token"),
    repo: store.get("gh_repo") || window.SITE_REPO || "",
    settings: null,      // working copy
    original: "",        // JSON of last saved version (to detect changes)
    sha: null,
    data: { courses: [], sources: {} },
    runs: [],
    tab: "overview",
    courseFilter: { q: "", show: "all" },
  };

  // ---------- GitHub API ----------
  async function gh(path, opts = {}) {
    const res = await fetch(`https://api.github.com/repos/${S.repo}${path}`, {
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

  async function loadSettings() {
    const file = await gh(`/contents/${SETTINGS_PATH}?ref=${BRANCH}`);
    S.sha = file.sha;
    S.settings = normalise(JSON.parse(b64decode(file.content)));
    S.original = JSON.stringify(S.settings);
  }
  async function loadCourses() {
    try {
      S.data = JSON.parse(await gh(`/contents/${COURSES_PATH}?ref=${BRANCH}`, { raw: true }));
    } catch { S.data = { courses: [], sources: {} }; }
    S.data.courses ||= [];
    S.data.sources ||= {};
  }
  async function loadRuns() {
    try {
      const r = await gh(`/actions/workflows/${WORKFLOW}/runs?per_page=10`);
      S.runs = r.workflow_runs || [];
    } catch { S.runs = []; }
  }

  function normalise(s) {
    s.site ||= {};
    s.sources ||= [];
    s.ads ||= {};
    s.ads.slots ||= {};
    for (const k of Object.keys(SLOTS)) s.ads.slots[k] ||= { enabled: false, html: "" };
    s.ads.countdown_seconds ??= 30;
    s.ads.in_feed_every ??= 6;
    s.ads.ads_txt ??= "";
    s.pinned ||= [];
    s.hidden ||= [];
    s.manual_courses ||= [];
    s.show_indirect_links ??= false;
    return s;
  }

  // ---------- saving ----------
  const dirty = () => S.settings && JSON.stringify(S.settings) !== S.original;
  function changed() { $("savebar").hidden = !dirty(); }

  async function save() {
    const btn = $("save");
    btn.disabled = true;
    btn.textContent = "جاري الحفظ…";
    try {
      const body = JSON.stringify(S.settings, null, 2) + "\n";
      const res = await gh(`/contents/${SETTINGS_PATH}`, {
        method: "PUT",
        body: JSON.stringify({
          message: "Update settings from the dashboard",
          content: b64encode(body),
          sha: S.sha,
          branch: BRANCH,
        }),
      });
      S.sha = res.content.sha;
      S.original = JSON.stringify(S.settings);
      changed();
      toast("✓ تم الحفظ. سيتحدث الموقع تلقائياً خلال 2–5 دقائق.");
      setTimeout(() => loadRuns().then(() => S.tab === "overview" && render()), 4000);
    } catch (e) {
      if (e.status === 409 || e.status === 422)
        toast("تم تعديل الإعدادات من مكان آخر. حدّث الصفحة ثم أعد التعديل.", true);
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

  // Inputs with data-bind="a.b.c" write straight into S.settings.
  function setPath(obj, path, value) {
    const keys = path.split(".");
    const last = keys.pop();
    keys.reduce((o, k) => (o[k] ||= {}), obj)[last] = value;
  }
  function getPath(obj, path) { return path.split(".").reduce((o, k) => (o == null ? o : o[k]), obj); }

  // ---------- views ----------
  const SLOTS = {
    header: ["أعلى الصفحة", "يظهر أعلى الصفحة الرئيسية وصفحات الكورسات."],
    in_feed: ["بين الكورسات", "يظهر بين بطاقات الكورسات في الصفحة الرئيسية."],
    countdown: ["إعلان العدّاد ⭐", "يظهر داخل النافذة المنبثقة أثناء العدّ التنازلي قبل رابط الكورس (أهم مكان)."],
    course_bottom: ["أسفل صفحة الكورس", "يظهر تحت زر الحصول على الكورس."],
    footer: ["أسفل الصفحة", "يظهر في نهاية الصفحة الرئيسية."],
  };

  function siteUrl() {
    const s = S.settings.site;
    return s.custom_domain ? `https://${s.custom_domain.replace(/\/+$/, "")}/` : (s.url || "#");
  }

  const views = {
    overview() {
      const courses = S.data.courses;
      const verified = courses.filter((c) => c.status === "free").length;
      const activeSources = S.settings.sources.filter((s) => s.enabled !== false).length;
      const running = S.runs.some((r) => r.status !== "completed");
      const runRow = (r) => {
        const ok = r.conclusion === "success";
        const cls = r.status !== "completed" ? "run" : ok ? "ok" : "bad";
        const label = r.status !== "completed" ? "يعمل الآن…" : ok ? "نجح" : r.conclusion === "cancelled" ? "أُلغي" : "فشل";
        const ev = { schedule: "تحديث تلقائي", workflow_dispatch: "تشغيل يدوي", push: "حفظ إعدادات/تعديل" }[r.event] || r.event;
        return `<div class="item"><div class="grow"><div class="t"><span class="dot ${cls}"></span>${label} — ${esc(ev)}</div>
          <div class="s">${timeAgo(r.created_at)}</div></div>
          <a class="btn sm" href="${esc(r.html_url)}" target="_blank" rel="noopener">التفاصيل</a></div>`;
      };
      return `
        <div class="page-head"><h1>نظرة عامة</h1>
          <button class="btn primary" data-act="run" ${running ? "disabled" : ""}>${running ? "⏳ جاري السحب…" : "🔄 اسحب الكورسات الآن"}</button></div>
        <div class="tiles">
          <div class="tile"><div class="num">${courses.length}</div><div class="lbl">كورس متاح</div></div>
          <div class="tile"><div class="num">${verified}</div><div class="lbl">مجاني مؤكد</div></div>
          <div class="tile"><div class="num">${activeSources}</div><div class="lbl">مصدر نشط</div></div>
          <div class="tile"><div class="num" style="font-size:1.2rem">${timeAgo(S.data.updated_at)}</div><div class="lbl">آخر سحب للكورسات</div></div>
        </div>
        <div class="panel"><h2>آخر عمليات التحديث</h2>
          <p class="muted">الموقع يسحب الكورسات تلقائياً كل ساعة، وبعد كل حفظ من لوحة التحكم.</p>
          <div class="list">${S.runs.map(runRow).join("") || '<p class="empty">لا توجد عمليات بعد.</p>'}</div>
        </div>
        <div class="panel help"><b>💡 نصيحة:</b> لمعرفة عدد الزوار ومن أين يأتون، أضف كود Google Analytics من صفحة "السيو والإعدادات".</div>`;
    },

    courses() {
      const f = S.courseFilter;
      const pinned = new Set(S.settings.pinned);
      const hidden = new Set(S.settings.hidden);
      const q = f.q.trim().toLowerCase();
      const list = S.data.courses.filter((c) =>
        (!q || c.title.toLowerCase().includes(q)) &&
        (f.show === "all" || (f.show === "pinned" && pinned.has(c.id)) || (f.show === "hidden" && hidden.has(c.id))));
      const row = (c) => `
        <div class="item">
          ${c.image ? `<img src="${esc(c.image)}" alt="" loading="lazy">` : '<span class="noimg"></span>'}
          <div class="grow"><div class="t">${esc(c.title)}</div>
            <div class="s">${esc(c.channel)} • ${timeAgo(c.posted_at)} • ${c.status === "free" ? "✓ مؤكد" : "غير مؤكد"}
            ${pinned.has(c.id) ? " • 📌 مثبت" : ""}${hidden.has(c.id) ? " • 🙈 مخفي" : ""}</div></div>
          <div class="btns">
            <button class="btn sm ${pinned.has(c.id) ? "on" : ""}" data-act="pin" data-id="${esc(c.id)}" title="تثبيت في أول الصفحة">📌</button>
            <button class="btn sm ${hidden.has(c.id) ? "on" : ""}" data-act="hide" data-id="${esc(c.id)}" title="إخفاء من الموقع">🙈</button>
            <a class="btn sm" href="${esc(c.url)}" target="_blank" rel="noopener" title="فتح على المنصة">🔗</a>
          </div></div>`;
      const manual = S.settings.manual_courses.map((m, i) => `
        <div class="item"><div class="grow"><div class="t">${esc(m.title || m.url)}</div><div class="s" dir="ltr">${esc(m.url)}</div></div>
          <button class="btn sm danger" data-act="del-manual" data-i="${i}">حذف</button></div>`).join("");
      return `
        <div class="page-head"><h1>الكورسات</h1></div>
        <div class="panel"><h2>➕ إضافة كورس يدوياً</h2>
          <p class="muted">الصق رابط الكورس مع الكوبون، مثل: <code>https://www.udemy.com/course/python/?couponCode=FREE123</code></p>
          <form class="inline-form" id="manual-form">
            <label>رابط الكورس <input name="url" dir="ltr" required placeholder="https://www.udemy.com/course/...?couponCode=..."></label>
            <label>العنوان (اختياري) <input name="title"></label>
            <label>رابط الصورة (اختياري) <input name="image" dir="ltr"></label>
            <button class="btn primary" type="submit">إضافة</button>
          </form>
          ${manual ? `<div class="list" style="margin-top:12px">${manual}</div>` : ""}
        </div>
        <div class="panel">
          <div class="toolbar">
            <input id="course-q" type="search" placeholder="ابحث في الكورسات…" value="${esc(f.q)}">
            <select id="course-show">
              <option value="all" ${f.show === "all" ? "selected" : ""}>الكل (${S.data.courses.length})</option>
              <option value="pinned" ${f.show === "pinned" ? "selected" : ""}>المثبتة (${pinned.size})</option>
              <option value="hidden" ${f.show === "hidden" ? "selected" : ""}>المخفية (${hidden.size})</option>
            </select>
          </div>
          <p class="muted small">📌 = يظهر أولاً في الموقع &nbsp;•&nbsp; 🙈 = لا يظهر في الموقع. لا تنسَ الضغط على "حفظ ونشر".</p>
          <div class="list">${list.slice(0, 200).map(row).join("") || '<p class="empty">لا توجد كورسات.</p>'}</div>
        </div>`;
    },

    sources() {
      const stats = S.data.sources || {};
      const row = (src, i) => {
        const st = stats[src.name];
        const info = !st ? "لم يُسحب بعد (سيُسحب في التحديث القادم)"
          : st.error ? `<span class="badge err">مشكلة</span> ${esc(st.error)}`
          : `${st.messages} رسالة • ${st.courses} كورس في آخر سحب`;
        const tg = src.type === "telegram";
        const label = tg ? `@${esc(src.name)}` : esc(src.name);
        const kind = tg ? "تيليجرام" : "موقع كوبونات (روابط يوديمي مباشرة)";
        const view = tg ? `https://t.me/s/${encodeURIComponent(src.name)}` : `https://${esc(src.name)}`;
        return `<div class="item">
          <label class="switch" title="تفعيل/إيقاف"><input type="checkbox" data-act="toggle-source" data-i="${i}" ${src.enabled !== false ? "checked" : ""}></label>
          <div class="grow"><div class="t" dir="ltr" style="text-align:right">${label}</div><div class="s">${kind} • ${info}</div></div>
          <div class="btns">
            <a class="btn sm" href="${view}" target="_blank" rel="noopener">👁 عرض</a>
            <button class="btn sm danger" data-act="del-source" data-i="${i}">حذف</button>
          </div></div>`;
      };
      return `
        <div class="page-head"><h1>مصادر الكورسات</h1></div>
        <div class="panel"><h2>➕ إضافة قناة تيليجرام</h2>
          <p class="muted">الصق رابط القناة أو اسمها، مثل <code>https://t.me/Udemy4U</code> أو <code>@Udemy4U</code>. يجب أن تكون القناة <b>عامة</b>.</p>
          <form class="inline-form" id="source-form">
            <label>رابط القناة <input name="link" dir="ltr" required placeholder="https://t.me/..."></label>
            <button class="btn primary" type="submit">إضافة</button>
          </form>
        </div>
        <div class="panel"><h2>المصادر (${S.settings.sources.length})</h2>
          <div class="list">${S.settings.sources.map(row).join("") || '<p class="empty">لا توجد مصادر بعد.</p>'}</div>
        </div>
        <div class="panel">
          <div class="slot-head"><div><h2>كورسات بدون رابط يوديمي مباشر</h2>
            <p class="muted small" style="margin:0">بعض القنوات (مثل قنوات courson) تضع رابط موقعها بدلاً من رابط يوديمي. عند الإيقاف، لا تظهر هذه الكورسات إلا إذا وجدنا رابطها المباشر في مصدر آخر.</p></div>
            <label class="switch"><input type="checkbox" data-bind="show_indirect_links" ${S.settings.show_indirect_links ? "checked" : ""}> إظهار</label></div>
        </div>
        <div class="panel help">💡 للتأكد أن القناة تعمل: اضغط "👁 عرض". إذا ظهرت الرسائل في المتصفح فالموقع يستطيع سحبها.</div>`;
    },

    ads() {
      const a = S.settings.ads;
      const slot = (key) => {
        const [title, desc] = SLOTS[key];
        return `<div class="panel">
          <div class="slot-head"><div><h2>${title}</h2><p class="muted small" style="margin:0">${desc}</p></div>
            <label class="switch"><input type="checkbox" data-bind="ads.slots.${key}.enabled" ${a.slots[key].enabled ? "checked" : ""}> مفعّل</label></div>
          <textarea data-bind="ads.slots.${key}.html" placeholder="الصق كود الإعلان هنا (من AdSense أو أي شبكة إعلانات، أو كود صورة ورابط)">${esc(a.slots[key].html)}</textarea>
        </div>`;
      };
      return `
        <div class="page-head"><h1>الإعلانات</h1></div>
        <div class="panel"><h2>⏱ نافذة الإعلان قبل رابط الكورس</h2>
          <p class="muted">عند الضغط على "احصل عليه مجاناً" تظهر نافذة منبثقة فيها "إعلان العدّاد" وعدّاد تنازلي، مع رسالة للزائر بأن يشاهد الإعلان ليحصل على الكورس،
          أو يغلق الإعلان بدون الحصول عليه. بعد انتهاء العدّاد يظهر زر "اذهب إلى الكورس". العدّاد يتوقف إذا ترك الزائر الصفحة.</p>
          <div class="row2">
            <label>مدة الانتظار بالثواني (0 = بدون انتظار)
              <input type="number" min="0" max="120" data-bind="ads.countdown_seconds" data-num value="${esc(a.countdown_seconds)}">
              <span class="hint">ننصح بـ 10–20 ثانية؛ 30 ثانية قد تجعل بعض الزوار يغادرون.</span></label>
            <label>إعلان "بين الكورسات" يظهر بعد كل
              <input type="number" min="2" max="30" data-bind="ads.in_feed_every" data-num value="${esc(a.in_feed_every)}">
              <span class="hint">عدد البطاقات بين كل إعلان والذي يليه.</span></label>
          </div>
        </div>
        ${Object.keys(SLOTS).map(slot).join("")}
        <div class="panel"><h2>ملف ads.txt</h2>
          <p class="muted">تطلبه شبكات الإعلانات مثل AdSense. ستجد محتواه في حسابك لديهم، الصقه هنا كما هو.</p>
          <textarea data-bind="ads.ads_txt" placeholder="google.com, pub-0000000000000000, DIRECT, f08c47fec0942fa0">${esc(a.ads_txt)}</textarea>
        </div>
        <div class="panel help"><b>💰 كيف أبدأ الربح من الإعلانات؟</b>
          <ol>
            <li><b>Google AdSense</b> (الأفضل): يحتاج دومين خاص بك (مثل <code>freecourses.com</code>، حوالي 10$ سنوياً) ولا يقبل روابط github.io.
              اربط الدومين من صفحة "السيو والإعدادات"، ثم سجّل في <a href="https://adsense.google.com" target="_blank" rel="noopener">adsense.google.com</a>، والصق كود التحقق في "كود الهيدر"، وبعد القبول الصق أكواد الوحدات الإعلانية هنا.</li>
            <li><b>شبكات بديلة</b> تقبل المواقع الجديدة بسرعة، مثل Adsterra و Monetag: سجّل كناشر، وأضف الموقع، وانسخ كود الإعلان والصقه في المكان المناسب هنا.</li>
            <li><b>بيع مساحة مباشرة</b>: الصق كود صورة بسيط، مثل: <code>&lt;a href="رابط المعلن"&gt;&lt;img src="رابط الصورة"&gt;&lt;/a&gt;</code></li>
          </ol>
        </div>`;
    },

    seo() {
      const s = S.settings.site;
      const desc = s.description || "";
      return `
        <div class="page-head"><h1>السيو والإعدادات</h1></div>
        <div class="panel"><h2>معلومات الموقع</h2>
          <div class="row2">
            <label>اسم الموقع <input data-bind="site.name" value="${esc(s.name)}"></label>
            <label>العنوان الكبير في الصفحة الرئيسية <input data-bind="site.tagline" value="${esc(s.tagline)}"></label>
          </div>
          <label>وصف الموقع (يظهر في نتائج جوجل)
            <textarea data-bind="site.description" style="direction:rtl;font-family:inherit;min-height:70px">${esc(desc)}</textarea>
            <span class="hint" id="desc-count">${desc.length} حرف — الأفضل بين 120 و 160 حرفاً.</span></label>
          <div class="row2">
            <label>رابط صفحة فيسبوك <input dir="ltr" data-bind="site.facebook" value="${esc(s.facebook)}"></label>
            <label>رابط قناة تيليجرام الخاصة بك <input dir="ltr" data-bind="site.telegram" value="${esc(s.telegram)}"></label>
          </div>
        </div>
        <div class="panel"><h2>الدومين</h2>
          <div class="row2">
            <label>رابط الموقع الحالي <input dir="ltr" data-bind="site.url" value="${esc(s.url)}"></label>
            <label>دومين خاص (اختياري) <input dir="ltr" data-bind="site.custom_domain" value="${esc(s.custom_domain)}" placeholder="www.example.com">
              <span class="hint">بعد الشراء: أضف في إعدادات الدومين سجل CNAME يشير إلى <code>${esc((S.repo.split("/")[0] || "username").toLowerCase())}.github.io</code></span></label>
          </div>
        </div>
        <div class="panel"><h2>كود الهيدر (Google Analytics / AdSense / Search Console)</h2>
          <p class="muted">أي كود يُطلب منك وضعه داخل <code>&lt;head&gt;</code>: كود التحقق من Search Console، أو Google Analytics، أو AdSense.</p>
          <textarea data-bind="site.head_code" placeholder="<meta name=&quot;google-site-verification&quot; content=&quot;...&quot;>">${esc(s.head_code)}</textarea>
        </div>
        <div class="panel help"><b>🔍 ما الذي يفعله الموقع للسيو تلقائياً؟</b>
          <ul>
            <li>صفحة مستقلة لكل كورس، بعنوان ووصف خاصين بها.</li>
            <li>بيانات منظمة (Schema.org) تساعد جوجل على فهم أن الصفحة كورس مجاني.</li>
            <li>خريطة موقع <code dir="ltr">${esc(siteUrl())}sitemap.xml</code> تتحدث كل ساعة.</li>
            <li>روابط داخلية بين الكورسات، وصور مشاركة (Open Graph) لفيسبوك وتيليجرام.</li>
          </ul>
          <b>خطوات عليك تنفيذها مرة واحدة:</b>
          <ol>
            <li>افتح <a href="https://search.google.com/search-console" target="_blank" rel="noopener">Google Search Console</a> وأضف موقعك (اختر "URL prefix" والصق رابط الموقع).</li>
            <li>اختر طريقة التحقق "HTML tag"، وانسخ الكود والصقه في "كود الهيدر" أعلاه، ثم اضغط حفظ ونشر، وانتظر 3 دقائق ثم اضغط Verify.</li>
            <li>من قائمة Sitemaps أضف الرابط: <code dir="ltr">${esc(siteUrl())}sitemap.xml</code></li>
          </ol>
        </div>`;
    },
  };

  function render() {
    document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.tab === S.tab));
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

  function toggleIn(list, id) {
    const i = list.indexOf(id);
    if (i >= 0) list.splice(i, 1); else list.push(id);
  }

  async function runNow(btn) {
    btn.disabled = true;
    btn.textContent = "⏳ جاري التشغيل…";
    try {
      // Pages only deploys runs started from the default branch.
      await gh(`/actions/workflows/${WORKFLOW}/dispatches`, { method: "POST", body: JSON.stringify({ ref: S.defaultBranch || BRANCH }) });
      toast("✓ بدأ سحب الكورسات. يستغرق عادةً من 2 إلى 6 دقائق.");
      setTimeout(async () => { await loadRuns(); if (S.tab === "overview") render(); }, 4000);
    } catch (e) {
      toast(e.status === 403 ? "المفتاح لا يملك صلاحية Actions (Read and write)." : `تعذّر التشغيل (${e.detail || e.message})`, true);
      btn.disabled = false;
    }
  }

  document.addEventListener("click", (e) => {
    const el = e.target.closest("[data-act]");
    if (!el || el.tagName === "INPUT") return;
    const act = el.dataset.act;
    const s = S.settings;
    if (act === "run") return runNow(el);
    if (act === "pin") { toggleIn(s.pinned, el.dataset.id); render(); }
    if (act === "hide") { toggleIn(s.hidden, el.dataset.id); render(); }
    if (act === "del-manual" && confirm("حذف هذا الكورس؟")) { s.manual_courses.splice(+el.dataset.i, 1); render(); }
    if (act === "del-source" && confirm(`حذف القناة @${s.sources[+el.dataset.i].name}؟`)) { s.sources.splice(+el.dataset.i, 1); render(); }
  });

  document.addEventListener("change", (e) => {
    const el = e.target;
    if (el.dataset.act === "toggle-source") { S.settings.sources[+el.dataset.i].enabled = el.checked; changed(); }
    if (el.id === "course-show") { S.courseFilter.show = el.value; render(); }
    if (el.matches("[data-bind][type=checkbox]")) { setPath(S.settings, el.dataset.bind, el.checked); changed(); }
  });

  document.addEventListener("input", (e) => {
    const el = e.target;
    if (el.id === "course-q") {
      S.courseFilter.q = el.value;
      const pos = el.selectionStart;
      render();
      const q = $("course-q"); q.focus(); q.setSelectionRange(pos, pos);
      return;
    }
    if (!el.dataset.bind || el.type === "checkbox") return;
    let v = el.value;
    if ("num" in el.dataset) v = Math.max(0, parseInt(v, 10) || 0);
    setPath(S.settings, el.dataset.bind, v);
    if (el.dataset.bind === "site.description")
      $("desc-count").textContent = `${v.length} حرف — الأفضل بين 120 و 160 حرفاً.`;
    changed();
  });

  document.addEventListener("submit", (e) => {
    const form = e.target;
    if (form.id === "login-form") return;
    e.preventDefault();
    const fd = new FormData(form);
    if (form.id === "source-form") {
      const name = parseChannel(fd.get("link"));
      if (!name) return toast("الرابط غير صحيح. مثال صحيح: https://t.me/Udemy4U", true);
      if (S.settings.sources.some((s) => s.name.toLowerCase() === name.toLowerCase()))
        return toast("هذه القناة موجودة بالفعل.", true);
      S.settings.sources.push({ type: "telegram", name, enabled: true });
      render();
      toast(`تمت إضافة @${name}. اضغط "حفظ ونشر" لتفعيلها.`);
    }
    if (form.id === "manual-form") {
      const url = String(fd.get("url")).trim();
      if (!/^https?:\/\//.test(url)) return toast("الرابط يجب أن يبدأ بـ https://", true);
      if (/udemy\.com/i.test(url) && !/couponCode=/i.test(url))
        return toast("رابط يوديمي يجب أن يحتوي على الكوبون (couponCode=...).", true);
      S.settings.manual_courses.unshift({
        url, title: String(fd.get("title")).trim(), image: String(fd.get("image")).trim(),
        added_at: new Date().toISOString().replace(/\.\d+Z$/, "+00:00"),
      });
      render();
      toast('تمت الإضافة. اضغط "حفظ ونشر" ليظهر في الموقع.');
    }
  });

  $("save").addEventListener("click", save);
  $("discard").addEventListener("click", () => {
    if (!confirm("التراجع عن كل التغييرات غير المحفوظة؟")) return;
    S.settings = JSON.parse(S.original);
    render();
  });
  window.addEventListener("beforeunload", (e) => { if (dirty()) { e.preventDefault(); e.returnValue = ""; } });
  window.addEventListener("hashchange", () => {
    const tab = location.hash.slice(1);
    if (views[tab]) { S.tab = tab; render(); }
  });
  $("logout").addEventListener("click", () => {
    if (dirty() && !confirm("لديك تغييرات غير محفوظة. خروج على أي حال؟")) return;
    store.clear();
    location.reload();
  });
  // Refresh run status while something is running.
  setInterval(async () => {
    if (S.tab === "overview" && document.visibilityState === "visible" && S.runs.some((r) => r.status !== "completed")) {
      await loadRuns();
      if (!S.runs.some((r) => r.status !== "completed")) await loadCourses();
      render();
    }
  }, 15000);

  // ---------- login & start ----------
  async function start() {
    $("login").hidden = true;
    $("app").hidden = false;
    $("view").innerHTML = '<p class="empty">جاري التحميل…</p>';
    const [info] = await Promise.all([gh(""), loadSettings(), loadCourses(), loadRuns()]);
    S.defaultBranch = info.default_branch;
    const tab = location.hash.slice(1);
    if (views[tab]) S.tab = tab;
    render();
  }

  function showLogin(error) {
    $("app").hidden = true;
    $("login").hidden = false;
    $("login-repo").value = S.repo;
    if (S.repo) $("repo-hint").textContent = S.repo.split("/")[1] || S.repo;
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
        : err.status === 404 ? "لم نجد المستودع. تأكد من الاسم ومن اختيار المستودع عند إنشاء المفتاح."
        : err.status === 403 ? "المفتاح لا يملك صلاحية الكتابة (Contents: Read and write)."
        : "تعذّر الاتصال بـ GitHub، تأكد من الإنترنت.");
    } finally { btn.disabled = false; }
  });

  if (S.token && S.repo) start().catch((e) => showLogin(e.status === 401 ? "انتهت صلاحية المفتاح، أدخل مفتاحاً جديداً." : "تعذّر التحميل، حاول مرة أخرى."));
  else showLogin();
})();
