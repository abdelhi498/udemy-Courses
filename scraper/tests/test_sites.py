import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from scraper import http, sites

# A course object the way tutorialbar's Next.js page embeds it: JSON inside a JS string.
COURSE = ('39:["$","$L1f","x",{"course":{"id":"cmuz","slug":"aws-ai-m","title":"AWS AI Practitioner AIF-C01 Practice Tests 2026",'
          '"headline":"AWS AI Practitioner practice exams","description":"$51","instructorName":"ADE - ACADEMY",'
          '"rating":4.7,"ratingCount":100,"studentsCount":1000,"language":"English","duration":"0s",'
          '"category":"IT \\u0026 Software","imageUrl":"https://img-c.udemycdn.com/course/480x270/7300149_7992.jpg",'
          '"couponCode":"B06E","couponUrl":"https://www.udemy.com/course/aws-ai-practitioner-aif-c01-practice-tests-2026-m/?couponCode=B06E",'
          '"originalPrice":"$$84.99","discountPrice":"Free (100% OFF)","is100PercentOff":true}}]')


def next_page(payload):
    half = len(payload) // 2  # objects can be split across two chunks
    chunks = [json.dumps(payload[:half]), json.dumps(payload[half:])]
    return "<html><body>" + "".join(f"<script>self.__next_f.push([1,{c}])</script>" for c in chunks) + "</body></html>"


class TutorialbarTest(unittest.TestCase):
    def test_parse(self):
        [c] = sites.parse_tutorialbar(next_page(COURSE))
        self.assertEqual(c["slug"], "aws-ai-practitioner-aif-c01-practice-tests-2026-m")
        self.assertEqual(c["coupon"], "B06E")
        self.assertEqual(c["title"], "AWS AI Practitioner AIF-C01 Practice Tests 2026")
        self.assertEqual(c["category"], "IT & Software")
        self.assertEqual((c["rating"], c["reviews"], c["price"]), (4.7, 100, 84.99))
        self.assertEqual(c["instructor"], "ADE - ACADEMY")
        self.assertTrue(c["image"].startswith("https://img-c.udemycdn.com/"))

    def test_skips_not_free(self):
        self.assertEqual(sites.parse_tutorialbar(next_page(COURSE.replace('"is100PercentOff":true', '"is100PercentOff":false'))), [])


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.startswith("/out/"):
            self.send_response(302)
            self.send_header("Location", "https://www.udemy.com/course/python-x/?couponCode=FREE1")
            self.end_headers()
        elif self.path.startswith("/go/"):
            body = b'<a href="https://www.udemy.com/course/js-y/?couponCode=GO2">Enroll</a>'
            self.send_response(200); self.end_headers(); self.wfile.write(body)
        else:
            body = (b'<a href="http://127.0.0.1:%d/free-udemy-course/python-x"><img></a>'
                    b'<a href="http://127.0.0.1:%d/free-udemy-course/python-x">Learn Python X</a>' % (PORT, PORT))
            self.send_response(200); self.end_headers(); self.wfile.write(body)

    def log_message(self, *a):
        pass


server = HTTPServer(("127.0.0.1", 0), _Handler)
PORT = server.server_address[1]


class ListingSourcesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        threading.Thread(target=server.serve_forever, daemon=True).start()

    def test_redirect_target_does_not_follow(self):
        self.assertEqual(http.redirect_target(f"http://127.0.0.1:{PORT}/out/a"),
                         "https://www.udemy.com/course/python-x/?couponCode=FREE1")
        self.assertIsNone(http.redirect_target(f"http://127.0.0.1:{PORT}/go/a"))

    def test_listing_to_udemy(self):
        base = f"http://127.0.0.1:{PORT}"
        for go in (base + "/out/{slug}", base + "/go/{slug}"):
            cache = {}
            [c] = sites._from_listing("x", "x", base + "/list", r"http://127\.0\.0\.1:\d+/free-udemy-course/([\w\-]+)",
                                      go, cache, lambda *_: None, [])
            self.assertEqual(c["title"], "Learn Python X")
            self.assertIn(c["coupon"], ("FREE1", "GO2"))
            self.assertEqual(len(cache), 1)


if __name__ == "__main__":
    unittest.main()
