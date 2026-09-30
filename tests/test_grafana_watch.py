import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


path = Path(__file__).resolve().parents[1] / "scripts/configure-grafana-watch.py"
spec = importlib.util.spec_from_file_location("grafana_watch", path)
watch = importlib.util.module_from_spec(spec)

with patch.dict(sys.modules, {"stack_env": types.SimpleNamespace(
        ENV={"GRAFANA_USER": "test", "GRAFANA_PASSWORD": "test"}, require_service=lambda name: None)}):
    spec.loader.exec_module(watch)


class GrafanaWatchTests(unittest.TestCase):
    def datasource(self):
        return {"user": watch.ROLE, "url": "jellystat-db:5432",
                "type": "grafana-postgresql-datasource",
                "jsonData": {"database": "jfstat"}}

    def test_create_scoped_reader_and_datasource(self):
        output = io.StringIO()
        with patch.object(watch, "sql", side_effect=["", "", "t", "f"]) as sql, \
                patch.object(watch, "api", side_effect=[None, {}, {"status": "OK"}]) as api, \
                patch.object(watch.secrets, "token_hex", return_value="test-password"), \
                contextlib.redirect_stdout(output):
            watch.main()

        statements = sql.call_args_list[1].args[0]
        self.assertIn(f"CREATE ROLE {watch.ROLE} LOGIN NOSUPERUSER", statements)
        self.assertIn('GRANT SELECT ("Id", "UserId"', statements)
        self.assertNotIn("GRANT SELECT ON", statements)
        self.assertIn("default_transaction_read_only=on", statements)
        self.assertIn("statement_timeout='10s'", statements)
        self.assertIn("BEGIN;", statements)
        self.assertTrue(statements.endswith("COMMIT;"))

        body = api.call_args_list[1].args[1]
        self.assertEqual(body["secureJsonData"], {"password": "test-password"})
        self.assertNotIn("test-password", output.getvalue())

    def test_existing_configuration_is_idempotent(self):
        output = io.StringIO()
        with patch.object(watch, "sql", side_effect=[watch.ROLE, "f", "", "t", "f"]) as sql, \
                patch.object(watch, "api", side_effect=[self.datasource(), {"status": "OK"}]) as api, \
                patch.object(watch.secrets, "token_hex") as password, \
                contextlib.redirect_stdout(output):
            watch.main()

        password.assert_not_called()
        self.assertNotIn("PASSWORD", sql.call_args_list[2].args[0])
        self.assertTrue(all(len(call.args) == 1 for call in api.call_args_list))
        self.assertTrue(all(line.startswith("  =") for line in output.getvalue().splitlines()))

    def test_reject_mismatched_datasource_before_mutation(self):
        for change in ({"user": "other"}, {"url": "other:5432"}, {"type": "mysql"},
                       {"jsonData": {"database": "other"}}, {"jsonData": {}}):
            with self.subTest(change=change), \
                    patch.object(watch, "sql", side_effect=[watch.ROLE, "f"]) as sql, \
                    patch.object(watch, "api", return_value=self.datasource() | change), \
                    self.assertRaisesRegex(SystemExit, "differs"):
                watch.main()

            self.assertEqual(sql.call_count, 2)

    def test_reject_missing_or_elevated_existing_role(self):
        for responses, message in (([""], "differs"), ([watch.ROLE, "t"], "privileges")):
            with self.subTest(responses=responses), \
                    patch.object(watch, "sql", side_effect=responses), \
                    patch.object(watch, "api", return_value=self.datasource()), \
                    self.assertRaisesRegex(SystemExit, message):
                watch.main()

    def test_recover_missing_datasource_with_existing_role(self):
        with patch.object(watch, "sql", side_effect=[watch.ROLE, "f", "", "t", "f"]) as sql, \
                patch.object(watch, "api", side_effect=[None, {}, {"status": "OK"}]), \
                patch.object(watch.secrets, "token_hex", return_value="test-password"), \
                contextlib.redirect_stdout(io.StringIO()):
            watch.main()

        statements = sql.call_args_list[2].args[0]
        self.assertNotIn("CREATE ROLE", statements)
        self.assertIn("PASSWORD 'test-password'", statements)

    def test_permissions_cover_all_columns_and_write_privileges(self):
        with patch.object(watch, "sql", side_effect=["t", "f"]) as sql:
            watch.verify_permissions()

        self.assertIn("FROM pg_attribute", sql.call_args_list[0].args[0])
        for column in watch.COLUMNS:
            self.assertIn(f"'{column}'", sql.call_args_list[0].args[0])

        self.assertIn("TRUNCATE,REFERENCES,TRIGGER", sql.call_args_list[1].args[0])
        self.assertIn("has_any_column_privilege", sql.call_args_list[1].args[0])

        for result in (["f", "f"], ["t", "t"], ["", "f"]):
            with self.subTest(result=result), patch.object(watch, "sql", side_effect=result), \
                    self.assertRaisesRegex(SystemExit, "permissions"):
                watch.verify_permissions()

    def test_bad_permissions_do_not_publish_datasource(self):
        with patch.object(watch, "sql", side_effect=["", "", "f", "f"]), \
                patch.object(watch, "api", return_value=None) as api, \
                self.assertRaisesRegex(SystemExit, "permissions"):
            watch.main()

        api.assert_called_once_with(f"/api/datasources/uid/{watch.UID}")

    def test_unhealthy_datasource_fails(self):
        with patch.object(watch, "sql", side_effect=[watch.ROLE, "f", "", "t", "f"]), \
                patch.object(watch, "api", side_effect=[self.datasource(), {"status": "ERROR"}]), \
                contextlib.redirect_stdout(io.StringIO()), \
                self.assertRaisesRegex(SystemExit, "health check failed"):
            watch.main()

    def test_sql_failure_does_not_expose_output(self):
        with patch.object(watch.subprocess, "run", return_value=types.SimpleNamespace(
                returncode=1, stdout="sensitive-output", stderr="sensitive-output")), \
                self.assertRaises(SystemExit) as error:
            watch.sql("SELECT 1;")

        self.assertNotIn("sensitive-output", str(error.exception))


if __name__ == "__main__":
    unittest.main()
