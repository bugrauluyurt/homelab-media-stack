import importlib.machinery
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


path = Path(__file__).resolve().parents[1] / "scripts/host-firewall"
loader = importlib.machinery.SourceFileLoader("firewall", str(path))
firewall = importlib.util.module_from_spec(importlib.util.spec_from_loader("firewall", loader))

with patch.dict(sys.modules, {"stack_env": types.SimpleNamespace(ENV={"LAN_CIDR": "192.168.1.0/24"})}):
    loader.exec_module(firewall)


class FirewallTests(unittest.TestCase):
    def home_port_sources(self, rules):
        home_port_lines = [line for chain in ("ARR-IN", "ARR-FWD") for line in rules[chain]
                           if any(f"port {port} " in line for port in firewall.HOME_APPS)]

        self.assertTrue(home_port_lines)
        self.assertTrue(all(line.startswith("-s ") for line in home_port_lines), home_port_lines)

        return {line.split()[1] for line in home_port_lines}

    def test_home_ports_answer_only_home_sources(self):
        with patch.object(firewall, "default_gateway", return_value=None), \
                patch.object(firewall, "ipv6_lan_prefixes", return_value=["2001:db8:1::/64"]):
            ipv4_rules = firewall.rules_v4()
            ipv6_rules = firewall.rules_v6()

        self.assertEqual(self.home_port_sources(ipv4_rules), {"192.168.1.0/24"})
        self.assertEqual(self.home_port_sources(ipv6_rules), {"fe80::/10", "2001:db8:1::/64"})

    def test_every_home_port_is_open_to_every_home_source(self):
        rules = firewall.home_port_rules("--dport", ["192.168.1.0/24", "fe80::/10"])

        self.assertEqual(len(rules), 2 * len(firewall.HOME_APPS))


if __name__ == "__main__":
    unittest.main()
