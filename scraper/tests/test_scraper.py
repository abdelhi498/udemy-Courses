import unittest
from pathlib import Path

from scraper import links, realdiscount, telegram
from scraper.scrape import courses_from_message, link_coupon_site_courses, title_from_message

FIXTURE = Path(__file__).parent / "fixtures" / "channel.html"
CFG = {"resolve_redirects": False, "resolve_timeout": 1}


class TelegramParserTest(unittest.TestCase):
    def setUp(self):
        self.messages = telegram.parse_channel_page(FIXTURE.read_text(encoding="utf-8"))
        for m in self.messages:
            m["channel"] = "FreeCoursesDemo"

    def test_parses_all_messages(self):
        self.assertEqual([m["id"] for m in self.messages], [1201, 1202, 1203])
        first = self.messages[0]
        self.assertEqual(first["date"], "2026-10-08T10:15:00+00:00")
        self.assertEqual(first["photo"], "https://cdn4.telesco.pe/file/photo1.jpg")
        self.assertIn("Complete Python Bootcamp 2026", first["text"])
        self.assertNotIn("10:15", first["text"])  # footer is not part of the text

    def test_extracts_udemy_courses(self):
        found = []
        for m in self.messages:
            found += list(courses_from_message(m, [0, 0], {}, CFG, print))
        self.assertEqual(
            sorted((c["slug"], c["coupon"]) for c in found),
            [("complete-python-bootcamp", "OCT2026FREE"),
             ("docker-basics", "DK99"),
             ("excel-mastery", "FREE-XL1")],
        )
        self.assertEqual(found[0]["title"], "Complete Python Bootcamp 2026")
        self.assertEqual(found[0]["url"],
                         "https://www.udemy.com/course/complete-python-bootcamp/?couponCode=OCT2026FREE")
        self.assertEqual(found[0]["source"], "https://t.me/FreeCoursesDemo/1201")


REAL_POST = {
    "post": "Udemy4U/87969", "channel": "Udemy4U", "date": "2026-10-07T13:36:29+00:00", "photo": "https://cdn/p.jpg",
    "text": ("Mastering Social Media Management and Marketing | Udemy\n"
             "Equip Yourself with the Skills, Strategies and Tools to become an Effective Social Media Manager\n\n"
             "1.5 hours • 24 lectures • 7 quizzes.\n\n⏳ 39 coupon uses left ⚠️\n📶 Rating: 4.7 ⭐️ (248 reviews)\n"
             "📅 Last updated: 09/26\n🎓 Instructor: Growth School\n\n#social_media_marketing"),
    "links": ["https://t.me/Udemy4U", "https://t.me/Udemy4U/87969", "https://www.udemy.com/user/hamzat-baliqis-2/",
              "?q=%23social_media_marketing",
              "https://courson.xyz/coupon/mastering-social-media-management-and-marketing?utm_source=social&utm_medium=telegram"],
}


class CoursonPostTest(unittest.TestCase):
    def test_lists_course_even_when_coupon_site_is_unreachable(self):
        cfg = {"resolve_redirects": False, "resolve_timeout": 1}
        [c] = list(courses_from_message(REAL_POST, [0, 0], {}, cfg, print))
        self.assertEqual(c["title"], "Mastering Social Media Management and Marketing")
        self.assertEqual(c["url"], "https://courson.xyz/coupon/mastering-social-media-management-and-marketing")
        self.assertEqual(c["via"], "courson.xyz")
        self.assertEqual(c["id"], "tg:Udemy4U/87969")
        self.assertEqual(c["uses_left"], 39)
        self.assertEqual(c["rating"], 4.7)
        self.assertEqual(c["reviews"], 248)
        self.assertEqual(c["instructor"], "Growth School")
        self.assertEqual(c["category"], "Social Media Marketing")
        self.assertEqual(c["duration"], "1.5 hours • 24 lectures • 7 quizzes")
        self.assertTrue(c["subtitle"].startswith("Equip Yourself"))

    def test_uses_resolved_udemy_link_from_cache(self):
        cfg = {"resolve_redirects": True, "resolve_timeout": 1}
        cache = {"https://courson.xyz/coupon/mastering-social-media-management-and-marketing":
                 "https://www.udemy.com/course/social-media-mm/?couponCode=OCT39"}
        [c] = list(courses_from_message(REAL_POST, [0, 0], cache, cfg, print))
        self.assertEqual((c["slug"], c["coupon"]), ("social-media-mm", "OCT39"))
        self.assertNotIn("via", c)


RD_ITEM = {"id": 79501, "name": "ChatGPT Pinterest Masterclass", "price": 84.99, "sale_price": 0,
           "sale_start": "2026-10-09 05:16:19", "lectures": 6, "rating": 4.61,
           "image": "https://img-c.udemycdn.com/course/750x422/6017558_fab7.jpg",
           "url": "https://www.udemy.com/course/mastering-social-media-management-and-marketing/?couponCode=BDD5",
           "store": "Udemy", "type": "external", "category": "Marketing", "subcategory": "Affiliate Marketing",
           "language": "English"}


class RealDiscountTest(unittest.TestCase):
    def test_item(self):
        c = realdiscount.course_from_item(RD_ITEM)
        self.assertEqual((c["id"], c["coupon"], c["price"], c["rating"]), ("rd:79501", "BDD5", 84.99, 4.6))
        self.assertEqual(c["posted_at"], "2026-10-09T05:16:19+00:00")
        self.assertEqual(c["category"], "Affiliate Marketing")

    def test_skips_ads_and_paid(self):
        self.assertIsNone(realdiscount.course_from_item({"id": "ad-1", "type": "ad", "store": "Sponsored"}))
        self.assertIsNone(realdiscount.course_from_item(dict(RD_ITEM, sale_price=9.99)))

    def test_coupon_site_course_gets_direct_link(self):
        cfg = {"resolve_redirects": False, "resolve_timeout": 1}
        [tg] = list(courses_from_message(REAL_POST, [0, 0], {}, cfg, print))
        rd = realdiscount.course_from_item(RD_ITEM)
        fresh = {tg["id"]: tg, rd["id"]: rd}
        link_coupon_site_courses(fresh, lambda *_: None)
        self.assertEqual(list(fresh), ["tg:Udemy4U/87969"])
        c = fresh["tg:Udemy4U/87969"]
        self.assertEqual(c["url"], RD_ITEM["url"].replace("www.udemy.com", "www.udemy.com"))
        self.assertNotIn("via", c)
        self.assertEqual(c["uses_left"], 39)  # Telegram details kept
        self.assertEqual(c["image"], RD_ITEM["image"])


class LinksTest(unittest.TestCase):
    def test_udemy_without_coupon_is_ignored(self):
        self.assertIsNone(links.normalise_udemy("https://www.udemy.com/course/foo/"))

    def test_provider_detection(self):
        self.assertEqual(links.provider_for("https://www.udemy.com/course/x/"), "Udemy")
        self.assertEqual(links.provider_for("https://www.linkedin.com/learning/abc"), "LinkedIn Learning")
        self.assertIsNone(links.provider_for("https://www.linkedin.com/in/someone"))
        self.assertIsNone(links.provider_for("https://example.com/udemy.com"))

    def test_title_fallback_to_slug(self):
        self.assertEqual(title_from_message("FREE\nhttps://x.y", "learn-sql-fast"), "Learn Sql Fast")


if __name__ == "__main__":
    unittest.main()
