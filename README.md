# كورسات مجانية — كوبونات يوديمي 100%

موقع يعرض الكورسات التي عليها خصم 100%، ويسحبها **تلقائياً كل ساعة** من قنوات تيليجرام عامة،
مع لوحة تحكم لإدارة الموقع بدون برمجة.

- **بدون سيرفر وبدون تكلفة:** GitHub Actions يسحب الكورسات ويبني الموقع، وGitHub Pages يستضيفه.
- **لوحة تحكم:** `/admin/` لإضافة المصادر، وتثبيت أو إخفاء الكورسات، والإعلانات، والسيو.
- **سيو:** صفحة مستقلة لكل كورس، وبيانات Schema.org، وخريطة موقع `sitemap.xml`.
- **إعلانات:** خمس مساحات إعلانية، وعدّاد انتظار (افتراضياً 30 ثانية) قبل رابط الكورس.

## التشغيل لأول مرة

1. من **Settings ← Pages** اختر **Source: GitHub Actions**.
2. من **Actions ← Update courses** اضغط **Run workflow**.
3. الموقع: `https://abdelhi498.github.io/udemy-Courses/`
   ولوحة التحكم: `https://abdelhi498.github.io/udemy-Courses/admin/` (تشرح لك صفحة الدخول كيف تحصل على المفتاح).

## كيف يعمل؟

```
قنوات تيليجرام ──► scraper/scrape.py ──► data/courses.json ──┐
                                                          ├─► scraper/build.py ──► _site/ ──► GitHub Pages
لوحة التحكم ─────────────────────────► data/settings.json ──┘
```

| الملف | وظيفته |
|---|---|
| `scraper/scrape.py` | يقرأ القنوات من `t.me/s/<قناة>`، ويستخرج روابط الكوبونات، ويتحقق منها عند يوديمي |
| `scraper/build.py` | يبني صفحات الموقع، و`sitemap.xml` و`robots.txt` و`ads.txt` |
| `site/` | قوالب الموقع (`index.html` و`course.html`) ولوحة التحكم `site/admin/` |
| `data/settings.json` | كل الإعدادات: المصادر، الإعلانات، السيو، المثبّت والمخفي (تعدّلها لوحة التحكم) |
| `data/courses.json` | الكورسات المسحوبة (يحدّثها السكربت تلقائياً) |
| `scraper/config.json` | إعدادات تقنية: عدد الصفحات، ومدة بقاء الكورس، وحدود التحقق |

## محلياً (للمطورين)

```bash
python -m scraper.scrape      # سحب الكورسات
python -m scraper.build       # بناء الموقع في _site/
python -m http.server -d _site
python -m unittest discover -s scraper/tests -t .
```

لتشخيص قناة جديدة: شغّل الـ workflow مع خيار **debug**، فتُحفظ عينة من رسائل كل قناة في `data/debug-messages.json`.
