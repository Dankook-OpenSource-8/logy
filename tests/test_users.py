import unittest

from fastapi.testclient import TestClient

from api.routes import _nickname_exists, check_nickname, check_nickname_path
from db.database import get_db
from main import app


class FakeQuery:
    def __init__(self, result):
        self.result = result
        self.filter_called = False

    def filter(self, *_args):
        self.filter_called = True
        return self

    def first(self):
        return self.result


class FakeDb:
    def __init__(self, result):
        self.query_obj = FakeQuery(result)

    def query(self, *_args):
        return self.query_obj


class UserRouteTest(unittest.TestCase):
    def tearDown(self):
        app.dependency_overrides.clear()

    def test_nickname_exists_uses_query_result(self):
        db = FakeDb(result=(1,))

        self.assertTrue(_nickname_exists(db, "Logy"))
        self.assertTrue(db.query_obj.filter_called)

    def test_check_nickname_reports_duplicate_as_unavailable(self):
        response = check_nickname("  Logy  ", FakeDb(result=(1,)))

        self.assertEqual(response.nickname, "Logy")
        self.assertFalse(response.available)
        self.assertFalse(response.isAvailable)
        self.assertTrue(response.exists)

    def test_check_nickname_reports_missing_as_available(self):
        response = check_nickname("Logy", FakeDb(result=None))

        self.assertTrue(response.available)
        self.assertTrue(response.isAvailable)
        self.assertFalse(response.exists)

    def test_check_nickname_path_uses_same_duplicate_response(self):
        response = check_nickname_path("Logy", FakeDb(result=(1,)))

        self.assertFalse(response.available)
        self.assertFalse(response.isAvailable)
        self.assertTrue(response.exists)

    def test_check_nickname_http_query_returns_compatibility_fields(self):
        app.dependency_overrides[get_db] = lambda: FakeDb(result=(1,))
        client = TestClient(app)

        response = client.get("/users/check-nickname", params={"nickname": "Logy"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "nickname": "Logy",
                "available": False,
                "isAvailable": False,
                "exists": True,
            },
        )

    def test_check_nickname_http_path_returns_compatibility_fields(self):
        app.dependency_overrides[get_db] = lambda: FakeDb(result=None)
        client = TestClient(app)

        response = client.get("/users/check-nickname/Logy")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "nickname": "Logy",
                "available": True,
                "isAvailable": True,
                "exists": False,
            },
        )


if __name__ == "__main__":
    unittest.main()
