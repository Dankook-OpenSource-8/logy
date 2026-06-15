import unittest

from db.schema_migrations import _split_sql_statements


class SchemaMigrationTest(unittest.TestCase):
    def test_split_sql_statements_skips_comments_and_empty_lines(self):
        sql = """
        -- comment
        CREATE TABLE example (
            id INTEGER PRIMARY KEY
        );

        ALTER TABLE example
            ADD COLUMN IF NOT EXISTS name VARCHAR;
        """

        statements = _split_sql_statements(sql)

        self.assertEqual(len(statements), 2)
        self.assertIn("CREATE TABLE example", statements[0])
        self.assertIn("ADD COLUMN IF NOT EXISTS name", statements[1])


if __name__ == "__main__":
    unittest.main()
