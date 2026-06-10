import unittest

from api.routes import _nickname_exists, check_nickname


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
    def test_nickname_exists_uses_query_result(self):
        db = FakeDb(result=(1,))

        self.assertTrue(_nickname_exists(db, "Logy"))
        self.assertTrue(db.query_obj.filter_called)

    def test_check_nickname_reports_duplicate_as_unavailable(self):
        response = check_nickname("  Logy  ", FakeDb(result=(1,)))

        self.assertEqual(response.nickname, "Logy")
        self.assertFalse(response.available)

    def test_check_nickname_reports_missing_as_available(self):
        response = check_nickname("Logy", FakeDb(result=None))

        self.assertTrue(response.available)


if __name__ == "__main__":
    unittest.main()
