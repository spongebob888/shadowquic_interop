from __future__ import annotations

import json
from dataclasses import dataclass

from .models import ImplementationRecord


USERNAME = "interop"
PASSWORD = "shadowquic-interop"
SNI = "cloudflare.com"
SERVER_PORT = 1443
SOCKS_PORT = 1080


@dataclass(slots=True, frozen=True)
class Implementation:
    key: str
    name: str
    source: str
    image: str
    config_format: str
    client: bool = True
    server: bool = True
    note: str | None = None

    @property
    def config_name(self) -> str:
        return f"config.{self.config_format}"

    def record(self) -> ImplementationRecord:
        return ImplementationRecord(
            key=self.key,
            name=self.name,
            source=self.source,
            image=self.image,
            client=self.client,
            server=self.server,
            note=self.note,
        )

    def command(self) -> list[str]:
        return ["-c", f"/config/{self.config_name}"]

    def render_server(self) -> str:
        if self.key == "shadowquic":
            return _shadowquic_server()
        if self.key == "quicproxy":
            return _quicproxy_server()
        raise ValueError(f"{self.name} has no ShadowQUIC server adapter")

    def render_client(self, server_host: str) -> str:
        if self.key == "shadowquic":
            return _shadowquic_client(server_host)
        if self.key == "quicproxy":
            return _quicproxy_client(server_host)
        raise ValueError(f"{self.name} has no ShadowQUIC client adapter")


IMPLEMENTATIONS: dict[str, Implementation] = {
    "shadowquic": Implementation(
        key="shadowquic",
        name="shadowquic",
        source="https://github.com/spongebob888/shadowquic",
        image="ghcr.io/spongebob888/shadowquic:latest",
        config_format="yaml",
    ),
    "quicproxy": Implementation(
        key="quicproxy",
        name="QuicProxy",
        source="https://github.com/RealBikiniBottom/QuicProxy",
        image="shadowquic-interop/quicproxy:latest",
        config_format="json",
    ),
    "mihomo": Implementation(
        key="mihomo",
        name="mihomo",
        source="https://github.com/MetaCubeX/mihomo",
        image="docker.io/metacubex/mihomo:latest",
        config_format="yaml",
        client=False,
        server=False,
        note=(
            "The current upstream does not implement a ShadowQUIC proxy or listener. "
            "The endpoint remains in the matrix and will become runnable when upstream adds it."
        ),
    ),
}


def select_implementations(values: list[str] | None) -> list[Implementation]:
    if not values:
        return list(IMPLEMENTATIONS.values())
    unknown = sorted(set(values) - IMPLEMENTATIONS.keys())
    if unknown:
        raise ValueError(f"unknown implementations: {', '.join(unknown)}")
    return [IMPLEMENTATIONS[key] for key in dict.fromkeys(values)]


def _shadowquic_server() -> str:
    return f"""inbound:
  type: shadowquic
  bind-addr: \"0.0.0.0:{SERVER_PORT}\"
  users:
    - username: \"{USERNAME}\"
      password: \"{PASSWORD}\"
  jls-upstream:
    addr: \"{SNI}:443\"
  alpn: [\"h3\"]
  congestion-control: cubic
  zero-rtt: true
  gso: false
outbound:
  type: direct
  dns-strategy: prefer-ipv4
log-level: info
"""


def _shadowquic_client(server_host: str) -> str:
    return f"""inbound:
  type: socks
  bind-addr: \"0.0.0.0:{SOCKS_PORT}\"
outbound:
  type: shadowquic
  addr: \"{server_host}:{SERVER_PORT}\"
  username: \"{USERNAME}\"
  password: \"{PASSWORD}\"
  server-name: \"{SNI}\"
  alpn: [\"h3\"]
  initial-mtu: 1300
  congestion-control: cubic
  zero-rtt: true
  gso: false
  over-stream: false
log-level: info
"""


def _quicproxy_server() -> str:
    return _json_config(
        {
            "inbounds": {
                "shadowquic": {
                    "type": "shadowquic",
                    "address": "0.0.0.0",
                    "port": SERVER_PORT,
                    "idle_timeout": 60,
                    "mtu_discoveriy": False,
                    "gso": False,
                    "tls": {
                        "enable_jls": True,
                        "jls_username": USERNAME,
                        "jls_password": PASSWORD,
                        "zero_rtt": True,
                        "sni": SNI,
                        "alpn": ["h3"],
                    },
                }
            },
            "outbounds": {
                "default_server": "direct",
                "servers": {"direct": {"type": "direct"}},
            },
            "router": {"default_mode": "proxy"},
            "dns": _quicproxy_dns("direct"),
            "log": {"level": "info", "color": False},
        }
    )


def _quicproxy_client(server_host: str) -> str:
    return _json_config(
        {
            "inbounds": {
                "socks": {
                    "type": "socks5",
                    "address": "0.0.0.0",
                    "port": SOCKS_PORT,
                }
            },
            "outbounds": {
                "default_server": "shadowquic",
                "servers": {
                    "shadowquic": {
                        "type": "shadowquic",
                        "address": server_host,
                        "port": SERVER_PORT,
                        "dns": "docker_dns",
                        "idle_timeout": 60,
                        "udp_mod": "datagram",
                        "mtu_discoveriy": False,
                        "gso": False,
                        "tls": {
                            "enable_jls": True,
                            "jls_username": USERNAME,
                            "jls_password": PASSWORD,
                            "insecure": False,
                            "zero_rtt": True,
                            "sni": SNI,
                            "alpn": ["h3"],
                        },
                    },
                    "direct": {"type": "direct"},
                },
            },
            "router": {"default_mode": "proxy"},
            "dns": _quicproxy_docker_dns(),
            "log": {"level": "info", "color": False},
        }
    )


def _quicproxy_dns(outbound: str) -> dict[str, object]:
    return {
        "default_server": "dns",
        "servers": {
            "dns": {
                "type": "udp",
                "address": "1.1.1.1",
                "port": 53,
                "timeout": 10,
                "outbound": outbound,
                "strategy": "ipv4_only",
            }
        },
    }


def _quicproxy_docker_dns() -> dict[str, object]:
    return {
        "default_server": "docker_dns",
        "servers": {
            "docker_dns": {
                "type": "udp",
                "address": "127.0.0.11",
                "port": 53,
                "outbound": "direct",
            }
        },
    }


def _json_config(value: dict[str, object]) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"
