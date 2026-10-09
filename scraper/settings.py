"""Default values for data/settings.json and migration of older layouts.

The dashboard (site/admin/admin.js → normalise) mirrors these defaults; keep both in sync.
Every section maps to one permission, used by the dashboard and by scraper/guard.py.
"""

import copy

# Permission needed to change each top-level section of settings.json.
SECTION_PERMISSION = {
    "site": "settings",
    "appearance": "appearance",
    "texts": "appearance",
    "announcement": "appearance",
    "nav": "pages",
    "pages": "pages",
    "seo": "seo",
    "ads": "ads",
    "sources": "sources",
    "show_indirect_links": "sources",
    "content": "courses",
    "pinned": "courses",
    "hidden": "courses",
    "manual_courses": "courses",
    "users": "users",
}
PERMISSIONS = sorted(set(SECTION_PERMISSION.values()))

DEFAULT_PAGES = [
    {"slug": "about", "title": "من نحن", "in_footer": True, "in_nav": False, "html": False, "body": (
        "نحن موقع يجمع لك كوبونات الكورسات المدفوعة على يوديمي التي تنزل بخصم 100%، "
        "من عدة مصادر موثوقة، وتتحدث تلقائياً كل ساعة.\n\n"
        "هدفنا أن يتعلم أي شخص مهارات جديدة مجاناً: البرمجة، والتصميم، والتسويق، واللغات وغيرها.\n\n"
        "- كل الروابط تذهب إلى يوديمي مباشرة.\n- لا نطلب أي بيانات شخصية.\n"
        "- الكوبونات محدودة العدد والمدة، لذلك سارع بالتسجيل.")},
    {"slug": "privacy", "title": "سياسة الخصوصية", "in_footer": True, "in_nav": False, "html": False, "body": (
        "نحترم خصوصيتك. لا يطلب هذا الموقع إنشاء حساب ولا يجمع بيانات شخصية بشكل مباشر.\n\n"
        "### ملفات تعريف الارتباط (Cookies) والإعلانات\n\n"
        "قد نستخدم خدمات طرف ثالث مثل Google Analytics وشبكات الإعلانات (مثل Google AdSense)، "
        "وهي قد تستخدم ملفات تعريف الارتباط لعرض إعلانات مناسبة لك وقياس الزيارات. "
        "يمكنك تعطيل ملفات تعريف الارتباط من إعدادات متصفحك.\n\n"
        "### الروابط الخارجية\n\nيحتوي الموقع على روابط لمواقع أخرى مثل يوديمي، ولسنا مسؤولين عن سياسات الخصوصية الخاصة بها.\n\n"
        "### التواصل\n\nلأي استفسار بخصوص الخصوصية تواصل معنا من صفحة \"اتصل بنا\".")},
    {"slug": "terms", "title": "شروط الاستخدام", "in_footer": True, "in_nav": False, "html": False, "body": (
        "- الموقع يعرض روابط لكورسات على منصات خارجية ولا يستضيف أي محتوى.\n"
        "- الكوبونات يضعها المدرّبون وقد تنتهي في أي وقت دون إشعار.\n"
        "- جميع العلامات التجارية مملوكة لأصحابها، والموقع غير تابع ليوديمي.\n"
        "- باستخدامك للموقع فأنت توافق على هذه الشروط.")},
    {"slug": "contact", "title": "اتصل بنا", "in_footer": True, "in_nav": True, "html": False, "body": (
        "يسعدنا تواصلك معنا لأي اقتراح أو إعلان أو بلاغ عن كوبون لا يعمل.\n\n"
        "- فيسبوك: [صفحتنا على فيسبوك](https://www.facebook.com/profile.php?id=61575779696971)")},
]

DEFAULTS = {
    "site": {
        "name": "كورسات مجانية",
        "url": "https://example.github.io/",
        "custom_domain": "",
        "head_code": "",
        "social": {"facebook": "", "telegram": "", "whatsapp": "", "youtube": "", "instagram": "", "x": "", "tiktok": ""},
    },
    "appearance": {
        "logo_emoji": "🎓",
        "logo_url": "",
        "favicon_url": "",
        "accent": "#6d28d9",
        "accent2": "#a435f0",
        "hero_from": "#2e1065",
        "hero_to": "#a435f0",
        "radius": 16,
        "default_theme": "auto",
        "cards_per_page": 24,
        "default_sort": "new",
        "sections": {"stats": True, "filters": True, "categories": True, "related": True,
                     "footer_categories": True, "theme_toggle": True},
        "custom_css": "",
    },
    "texts": {
        "eyebrow": "تحديث تلقائي كل ساعة",
        "tagline": "كورسات مدفوعة… مجاناً 100%",
        "lead": "نجمع لك كوبونات يوديمي بخصم 100% لحظة نزولها من أكثر من مصدر. الكوبونات محدودة العدد والمدة، فسارع بالتسجيل قبل انتهائها.",
        "search_placeholder": "ابحث عن كورس… Python, Excel, تصميم",
        "card_button": "احصل عليه مجاناً",
        "course_button": "🎁 احصل على الكورس مجاناً",
        "course_hint": "إذا ظهر السعر على المنصة غير صفر فهذا يعني أن الكوبون انتهى، جرّب كورساً آخر.",
        "popup_title": "🎁 شاهد الإعلان للحصول على الكورس مجاناً",
        "popup_message": "للحصول على الكورس والتحويل إلى رابطه، شاهد الإعلان حتى ينتهي العدّاد ({seconds} ثانية). الإعلانات هي ما يُبقي هذا الموقع مجانياً.",
        "popup_go": "🎓 اذهب إلى الكورس الآن",
        "popup_close": "إغلاق الإعلان وعدم الحصول على الكورس",
        "footer_text": "الموقع لا يستضيف أي كورسات؛ كل الروابط تذهب إلى يوديمي مباشرة.",
        "expired_notice": "انتهى هذا الكوبون أو نفدت استخداماته. تصفّح الكورسات المجانية المتاحة الآن بالأسفل.",
    },
    "announcement": {"enabled": False, "text": "", "link": "", "color": "#f59e0b"},
    "nav": [],
    "pages": DEFAULT_PAGES,
    "seo": {
        "description": "أحدث كورسات يوديمي بخصم 100% — كوبونات مجانية تتحدث تلقائياً كل ساعة.",
        "title_home": "{site} | كوبونات يوديمي مجانية 100%",
        "title_course": "{title} — مجاناً بكوبون 100% | {site}",
        "title_category": "كورسات {category} مجانية بكوبون 100% | {site}",
        "og_image": "",
        "twitter": "",
        "google_verification": "",
        "bing_verification": "",
        "yandex_verification": "",
        "ga_id": "",
        "noindex": False,
        "category_pages": True,
        "rss": True,
        "keep_expired_days": 30,
        "indexnow": False,
        "indexnow_key": "",
    },
    "ads": {
        "countdown_seconds": 30,
        "in_feed_every": 6,
        "slots": {name: {"enabled": False, "html": ""}
                  for name in ("header", "in_feed", "countdown", "course_bottom", "footer")},
        "ads_txt": "",
    },
    "sources": [],
    "show_indirect_links": False,
    "content": {
        "max_age_days": 7,
        "blocked_words": [],
        "allowed_languages": [],
        "min_rating": 0,
        "overrides": {},
    },
    "pinned": [],
    "hidden": [],
    "manual_courses": [],
    "users": [],
}


def _merge(defaults, value):
    if isinstance(defaults, dict) and isinstance(value, dict):
        out = {k: _merge(v, value[k]) if k in value else copy.deepcopy(v) for k, v in defaults.items()}
        out.update({k: v for k, v in value.items() if k not in defaults})
        return out
    return value


def normalise(raw):
    """Fill in defaults and move fields from older layouts to their new place."""
    raw = copy.deepcopy(raw or {})
    site = raw.get("site", {})
    texts = raw.setdefault("texts", {})
    seo = raw.setdefault("seo", {})
    social = site.setdefault("social", {})
    if "tagline" in site:
        texts.setdefault("tagline", site.pop("tagline"))
    if "description" in site:
        seo.setdefault("description", site.pop("description"))
    for net in ("facebook", "telegram"):
        if net in site:
            social.setdefault(net, site.pop(net))
    appearance = raw.setdefault("appearance", {})
    for k in ("logo_emoji", "logo_url", "favicon_url"):
        if k in site:
            appearance.setdefault(k, site.pop(k))
    return _merge(DEFAULTS, raw)


# Ready-made roles for the dashboard's users screen ("custom" uses the user's own list).
ROLES = {
    "admin": [p for p in PERMISSIONS if p != "users"],
    "editor": ["courses", "sources", "pages"],
    "marketer": ["ads", "seo", "appearance"],
    "viewer": [],
}


def user_permissions(settings, login, owner):
    """Permissions of a GitHub login. The repository owner can do everything."""
    if login and owner and login.lower() == owner.lower():
        return set(PERMISSIONS)
    for u in settings.get("users", []):
        if (u.get("login") or "").lower() == (login or "").lower():
            if u.get("disabled"):
                return set()
            role = u.get("role") or "viewer"
            return set(u.get("permissions") or []) if role == "custom" else set(ROLES.get(role, []))
    return set()
