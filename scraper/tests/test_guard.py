import unittest

from scraper import guard, settings as sm


def base():
    return {"site": {"name": "A"}, "ads": {"countdown_seconds": 30},
            "users": [{"login": "Ali", "role": "editor"}, {"login": "sara", "role": "custom", "permissions": ["ads"]},
                      {"login": "off", "role": "admin", "disabled": True}]}


class GuardTest(unittest.TestCase):
    def test_owner_can_change_anything(self):
        new = dict(base(), site={"name": "B"}, users=[])
        self.assertEqual(guard.check(base(), new, "Owner", "owner"), (None, []))

    def test_editor_cannot_change_ads_or_grant_himself(self):
        new = base()
        new["ads"] = {"countdown_seconds": 5}
        new["pinned"] = ["x"]
        new["users"] = [{"login": "ali", "role": "admin"}]
        fixed, reverted = guard.check(base(), new, "ali", "owner")
        self.assertEqual(reverted, ["ads", "users"])
        self.assertEqual(fixed["ads"], {"countdown_seconds": 30})
        self.assertEqual(fixed["pinned"], ["x"])  # editors may pin courses
        self.assertEqual(fixed["users"], base()["users"])

    def test_custom_and_disabled_users(self):
        new = lambda: dict(base(), ads={"countdown_seconds": 10})  # noqa: E731
        self.assertEqual(guard.check(base(), new(), "sara", "owner"), (None, []))
        self.assertEqual(guard.check(base(), new(), "off", "owner")[1], ["ads"])
        self.assertEqual(guard.check(base(), new(), "stranger", "owner")[1], ["ads"])

    def test_new_section_needs_permission(self):
        new = dict(base(), seo={"noindex": True})
        fixed, reverted = guard.check(base(), new, "ali", "owner")
        self.assertEqual(reverted, ["seo"])
        self.assertNotIn("seo", fixed)

    def test_roles(self):
        self.assertNotIn("users", sm.ROLES["admin"])
        self.assertEqual(sm.user_permissions(base(), "OWNER", "owner"), set(sm.PERMISSIONS))


if __name__ == "__main__":
    unittest.main()
