import base64
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
IMPORTER = REPO / "scripts/vpn-import-servers"


class VpnImportTests(unittest.TestCase):
    def setUp(self):
        self.config_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.config_directory.cleanup)
        self.config_root = Path(self.config_directory.name)
        self.output_dir = self.config_root / "gluetun/verified-servers"
        self.private_key = base64.b64encode(bytes(range(32))).decode()
        self.peer_public_key = base64.b64encode(bytes(range(32, 64))).decode()
        self.primary_config = self._write_config("NL#1", "1.1.1.1")
        self.secondary_config = self._write_config("NL#2", "9.9.9.9")

    def test_imports_only_public_peer_data_with_private_file_permissions(self):
        import_result = self._run_import()

        self.assertEqual(import_result.returncode, 0, import_result.stderr)
        self.assertIn("VPN_SERVER_NAMES=NL#1,NL#2", import_result.stdout)

        provider_path = self.output_dir / "protonvpn.json"
        provider_metadata = json.loads(provider_path.read_text())
        self.assertEqual(provider_metadata["version"], 4)
        self.assertTrue(provider_metadata["preferred"])
        self.assertGreater(provider_metadata["timestamp"], 0)
        self.assertEqual([server["server_name"] for server in provider_metadata["servers"]], ["NL#1", "NL#2"])
        self.assertEqual([server["ips"] for server in provider_metadata["servers"]], [["1.1.1.1"], ["9.9.9.9"]])
        self.assertTrue(all(server["port_forward"] for server in provider_metadata["servers"]))
        self.assertTrue(all(server["country"] == "Netherlands" for server in provider_metadata["servers"]))
        self.assertTrue(all(server["wgpubkey"] == self.peer_public_key for server in provider_metadata["servers"]))

        manifest_path = self.output_dir / "manifest.json"
        self.assertEqual(json.loads(manifest_path.read_text()), {
            "version": 1, "protonvpn": {"filepath": "/gluetun/verified-servers/protonvpn.json"},
        })
        self.assertEqual(stat.S_IMODE(self.output_dir.stat().st_mode), 0o700)

        for output_path in [provider_path, manifest_path]:
            self.assertEqual(stat.S_IMODE(output_path.stat().st_mode), 0o600)
            self.assertNotIn(self.private_key, output_path.read_text())
            self.assertNotIn("PrivateKey", output_path.read_text())

        self.assertNotIn(self.private_key, import_result.stdout + import_result.stderr)

    def test_reimport_keeps_contents_timestamp_and_file_inodes(self):
        self.assertEqual(self._run_import().returncode, 0)
        previous_files = {output_path.name: (output_path.read_bytes(), output_path.stat().st_ino)
                          for output_path in self.output_dir.iterdir()}

        import_result = self._run_import()

        self.assertEqual(import_result.returncode, 0, import_result.stderr)
        self.assertNotIn("+ ", import_result.stdout)
        self.assertEqual(previous_files, {
            output_path.name: (output_path.read_bytes(), output_path.stat().st_ino)
            for output_path in self.output_dir.iterdir()
        })

    def test_invalid_second_config_leaves_existing_pool_unchanged(self):
        self.assertEqual(self._run_import().returncode, 0)
        previous_files = {output_path.name: output_path.read_bytes() for output_path in self.output_dir.iterdir()}
        self.secondary_config.write_text(self.secondary_config.read_text().replace("PublicKey =", "InvalidKey ="))

        import_result = self._run_import()

        self.assertNotEqual(import_result.returncode, 0)
        self.assertEqual(previous_files, {
            output_path.name: output_path.read_bytes() for output_path in self.output_dir.iterdir()
        })

    def test_validation_rejects_unsupported_configs_before_creating_output(self):
        original_config = self.secondary_config.read_text()
        invalid_configs = {
            "missing forwarding option": original_config.replace("NAT-PMP (Port Forwarding) = on", "NAT-PMP (Port Forwarding) = off"),
            "moderate NAT": original_config.replace("Moderate NAT = off", "Moderate NAT = on"),
            "wrong address": original_config.replace("10.2.0.2/32", "10.5.0.2/32"),
            "wrong port": original_config.replace(":51820", ":443"),
            "private endpoint": original_config.replace("9.9.9.9", "192.168.1.2"),
            "multicast endpoint": original_config.replace("9.9.9.9", "224.0.0.1"),
            "hostname endpoint": original_config.replace("9.9.9.9", "vpn.example.com"),
            "ipv6 endpoint": original_config.replace("9.9.9.9", "[2001:db8::1]"),
            "missing default route": original_config.replace("0.0.0.0/0", "10.0.0.0/8"),
            "preshared key": original_config + "PresharedKey = " + self.private_key + "\n",
            "mismatched server label": original_config.replace("# NL#2", "# NL#3"),
            "invalid public key": original_config.replace(self.peer_public_key, "not-a-key"),
            "duplicate endpoint": original_config.replace("9.9.9.9", "1.1.1.1"),
            "malformed input": "[Interface]\n" + self.private_key,
        }

        for config_case, config_text in invalid_configs.items():
            with self.subTest(config_case=config_case):
                self.secondary_config.write_text(config_text)
                import_result = self._run_import()

                self.assertNotEqual(import_result.returncode, 0)
                self.assertFalse(self.output_dir.exists())
                self.assertNotIn(self.private_key, import_result.stdout + import_result.stderr)

    def test_requires_two_distinct_standard_server_names_in_one_permitted_country(self):
        us_config = self._write_config("US#1", "9.9.9.9")
        other_country_config = self._write_config("FR#1", "9.9.9.9")
        invalid_arguments = [
            ("Netherlands", [f"NL#1={self.primary_config}"]),
            ("Netherlands", [f"NL#1={self.primary_config}", f"NL#1={self.primary_config}"]),
            ("United States", [f"NL#1={self.primary_config}", f"NL#2={self.secondary_config}"]),
            ("Netherlands", [f"NL#1={self.primary_config}", f"US#1={us_config}"]),
            ("Netherlands", [f"NL#1={self.primary_config}", f"FR#1={other_country_config}"]),
            ("Netherlands", [f"NL#1={self.primary_config}", f"NL-FREE#2={self.secondary_config}"]),
        ]

        for country_name, server_references in invalid_arguments:
            with self.subTest(country_name=country_name, server_references=server_references):
                import_result = self._run_import(country=country_name, server_references=server_references)

                self.assertNotEqual(import_result.returncode, 0)
                self.assertFalse(self.output_dir.exists())

    def test_staging_failure_keeps_previous_files_and_cleans_temporary_files(self):
        self.assertEqual(self._run_import().returncode, 0)
        previous_files = {output_path.name: output_path.read_bytes() for output_path in self.output_dir.iterdir()}
        importer_loader = importlib.machinery.SourceFileLoader("vpn_import_under_test", str(IMPORTER))
        importer_spec = importlib.util.spec_from_loader(importer_loader.name, importer_loader)
        importer_module = importlib.util.module_from_spec(importer_spec)
        importer_loader.exec_module(importer_module)
        replacement_servers = json.loads((self.output_dir / "protonvpn.json").read_text())["servers"]
        replacement_servers[1]["ips"] = ["8.8.8.8"]

        with patch.object(importer_module.os, "fsync", side_effect=OSError("simulated disk failure")):
            with self.assertRaisesRegex(OSError, "simulated disk failure"):
                importer_module.write_server_pool(self.output_dir, replacement_servers)

        self.assertEqual(previous_files, {
            output_path.name: output_path.read_bytes() for output_path in self.output_dir.iterdir()
        })

    def _write_config(self, server_name, endpoint_ip):
        config_path = self.config_root / (server_name.replace("#", "-") + ".conf")
        config_path.write_text(
            "[Interface]\n"
            "# NAT-PMP (Port Forwarding) = on\n"
            "# Moderate NAT = off\n"
            f"PrivateKey = {self.private_key}\n"
            "Address = 10.2.0.2/32, 2a07:b944::2:2/128\n"
            "DNS = 10.2.0.1\n\n"
            "[Peer]\n"
            f"# {server_name}\n"
            f"PublicKey = {self.peer_public_key}\n"
            "AllowedIPs = 0.0.0.0/0, ::/0\n"
            f"Endpoint = {endpoint_ip}:51820\n"
            "PersistentKeepalive = 25\n"
        )

        return config_path

    def _run_import(self, *, country="Netherlands", server_references=None):
        if server_references is None:
            server_references = [f"NL#1={self.primary_config}", f"NL#2={self.secondary_config}"]

        import_command = [sys.executable, str(IMPORTER), "--country", country, "--output-dir", str(self.output_dir)]

        for server_reference in server_references:
            import_command.extend(["--server", server_reference])

        return subprocess.run(import_command, capture_output=True, text=True, timeout=10)


if __name__ == "__main__":
    unittest.main()
