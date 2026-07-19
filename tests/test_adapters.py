import json
import unittest

from shadowquic_interop.adapters import (
    PASSWORD,
    SERVER_PORT,
    SOCKS_PORT,
    USERNAME,
    IMPLEMENTATIONS,
    select_implementations,
)


class AdapterTests(unittest.TestCase):
    def test_shadowquic_configs_share_credentials_and_address(self) -> None:
        implementation = IMPLEMENTATIONS["shadowquic"]
        server = implementation.render_server()
        client = implementation.render_client("server-under-test")
        self.assertIn(f'bind-addr: "0.0.0.0:{SERVER_PORT}"', server)
        self.assertIn(f'username: "{USERNAME}"', server)
        self.assertIn(f'password: "{PASSWORD}"', server)
        self.assertIn(f'bind-addr: "0.0.0.0:{SOCKS_PORT}"', client)
        self.assertIn(f'addr: "server-under-test:{SERVER_PORT}"', client)

    def test_quicproxy_configs_are_valid_json(self) -> None:
        implementation = IMPLEMENTATIONS["quicproxy"]
        server = json.loads(implementation.render_server())
        client = json.loads(implementation.render_client("sq-server"))
        self.assertEqual(server["inbounds"]["shadowquic"]["port"], SERVER_PORT)
        self.assertEqual(client["inbounds"]["socks"]["port"], SOCKS_PORT)
        self.assertEqual(
            client["outbounds"]["servers"]["shadowquic"]["address"], "sq-server"
        )
        self.assertEqual(
            client["outbounds"]["servers"]["shadowquic"]["tls"]["jls_password"],
            PASSWORD,
        )

    def test_mihomo_is_explicitly_unsupported(self) -> None:
        implementation = IMPLEMENTATIONS["mihomo"]
        self.assertFalse(implementation.client)
        self.assertFalse(implementation.server)
        self.assertIn("does not implement", implementation.note or "")

    def test_selection_rejects_unknown_keys(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown implementations"):
            select_implementations(["missing"])

    def test_selection_preserves_order_without_duplicates(self) -> None:
        selected = select_implementations(["quicproxy", "shadowquic", "quicproxy"])
        self.assertEqual([item.key for item in selected], ["quicproxy", "shadowquic"])


if __name__ == "__main__":
    unittest.main()
