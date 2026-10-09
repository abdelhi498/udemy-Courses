// "Watch the ad to get the course" popup.
// Any element with data-unlock opens it. It reads:
//   data-target  base64 of the course link (so it isn't sitting in plain text)
//   data-title   course title
//   data-coupon  coupon code (optional)
// The wait time comes from <body data-countdown="30"> and the ad from <template id="ad-countdown">.
(() => {
  const seconds = Math.max(0, Number(document.body.dataset.countdown) || 0);
  const T = Object.assign({
    popup_title: "🎁 شاهد الإعلان للحصول على الكورس مجاناً",
    popup_message: "للحصول على الكورس والتحويل إلى رابطه، شاهد الإعلان حتى ينتهي العدّاد ({seconds} ثانية). الإعلانات هي ما يُبقي هذا الموقع مجانياً.",
    popup_go: "🎓 اذهب إلى الكورس الآن",
    popup_close: "إغلاق الإعلان وعدم الحصول على الكورس",
  }, window.SITE_TEXTS || {});
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (ch) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
  let modal, timer, lastFocus;

  function build() {
    modal = document.createElement("div");
    modal.className = "modal";
    modal.hidden = true;
    modal.innerHTML = `
      <div class="modal-box" role="dialog" aria-modal="true" aria-labelledby="m-head">
        <button class="modal-x" type="button" data-close aria-label="إغلاق">✕</button>
        <h2 id="m-head">${esc(T.popup_title)}</h2>
        <p class="m-course"></p>
        <div class="m-ad"></div>
        <div class="m-wait">
          <div class="ring" style="--p:0"><span class="m-left"></span></div>
          <p>${esc(T.popup_message).replace("{seconds}", '<b class="m-left"></b>')}</p>
        </div>
        <div class="m-ready" hidden>
          <a class="btn primary big m-go" target="_blank" rel="noopener nofollow sponsored">${esc(T.popup_go)}</a>
          <p class="m-coupon" hidden>الكوبون: <button class="btn copy" type="button"></button></p>
        </div>
        <button class="m-close" type="button" data-close>${esc(T.popup_close)}</button>
      </div>`;
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => {
      if (e.target === modal || e.target.closest("[data-close]")) close();
    });
    modal.querySelector(".m-go").addEventListener("click", () => setTimeout(close, 300));
    const copy = modal.querySelector(".m-coupon .copy");
    copy.addEventListener("click", async () => {
      const code = copy.dataset.code;
      try { await navigator.clipboard.writeText(code); copy.textContent = "تم النسخ ✓"; } catch {}
      setTimeout(() => (copy.textContent = code), 1500);
    });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !modal.hidden) close(); });
  }

  function setLeft(left) {
    modal.querySelectorAll(".m-left").forEach((el) => (el.textContent = left));
    modal.querySelector(".ring").style.setProperty("--p", seconds ? (seconds - left) / seconds : 1);
  }

  function ready() {
    clearInterval(timer);
    modal.querySelector(".m-wait").hidden = true;
    modal.querySelector(".m-ready").hidden = false;
    modal.querySelector(".m-close").textContent = "إغلاق";
    modal.querySelector(".m-go").focus();
  }

  function open(el) {
    if (!modal) build();
    lastFocus = el;
    modal.querySelector(".m-course").textContent = el.dataset.title || "";
    modal.querySelector(".m-go").href = atob(el.dataset.target);
    const couponBox = modal.querySelector(".m-coupon");
    const copy = couponBox.querySelector(".copy");
    couponBox.hidden = !el.dataset.coupon;
    copy.textContent = copy.dataset.code = el.dataset.coupon || "";

    // Fresh copy of the ad each time (ad scripts run again).
    const ad = modal.querySelector(".m-ad");
    const tpl = document.getElementById("ad-countdown");
    ad.replaceChildren();
    if (tpl && tpl.content.childElementCount) ad.appendChild(document.importNode(tpl.content, true));
    ad.hidden = !ad.childElementCount;

    modal.querySelector(".m-wait").hidden = false;
    modal.querySelector(".m-ready").hidden = true;
    modal.querySelector(".m-close").textContent = T.popup_close;
    modal.hidden = false;
    document.body.classList.add("modal-open");

    let left = seconds;
    setLeft(left);
    clearInterval(timer);
    if (left <= 0) return ready();
    timer = setInterval(() => {
      // Only counts while the visitor is actually on the page.
      if (document.visibilityState !== "visible") return;
      left -= 1;
      setLeft(left);
      if (left <= 0) ready();
    }, 1000);
  }

  function close() {
    clearInterval(timer);
    modal.hidden = true;
    modal.querySelector(".m-ad").replaceChildren();
    document.body.classList.remove("modal-open");
    if (lastFocus) lastFocus.focus();
  }

  document.addEventListener("click", (e) => {
    const el = e.target.closest("[data-unlock]");
    if (!el || !el.dataset.target) return;
    e.preventDefault();
    open(el);
  });
})();
