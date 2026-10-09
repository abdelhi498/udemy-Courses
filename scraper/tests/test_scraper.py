import unittest
from pathlib import Path

from scraper import links, telegram
from scraper.scrape import courses_from_message, title_from_message

FIXTURE = Path(__file__).parent / "fixtures" / "channel.html"
CFG = {"resolve_redirects": False}


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
