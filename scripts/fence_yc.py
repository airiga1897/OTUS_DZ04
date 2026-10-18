#!/usr/bin/python3
"""Экспериментальный STONITH: allowlist ID, IAM из metadata, подтверждение STOPPED."""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

METADATA = """<?xml version="1.0"?>
<resource-agent name="fence_yc" shortdesc="YC backend fencing">
<longdesc>Experimental YC Stop agent. Success requires confirmed STOPPED state.</longdesc>
<parameters>
<parameter name="config" required="0"><shortdesc>Root-owned node allowlist</shortdesc><content type="string" default="/etc/otus-fence.json"/></parameter>
<parameter name="plug" required="0"><shortdesc>Backend hostname</shortdesc><content type="string"/></parameter>
</parameters>
<actions><action name="off" timeout="150"/><action name="status" timeout="30"/><action name="monitor" timeout="30"/><action name="list" timeout="30"/><action name="metadata" timeout="5"/></actions>
</resource-agent>"""

class FenceClient:
    def __init__(self, nodes: dict[str, str], api: Callable, *, sleep: Callable = time.sleep,
                 clock: Callable = time.monotonic, timeout: int = 120):
        self.nodes, self.api, self.sleep, self.clock, self.timeout = nodes, api, sleep, clock, timeout

    def _path(self, node: str) -> str:
        if node not in self.nodes:
            raise ValueError("Узел отсутствует в разрешённом списке")
        return "/instances/" + self.nodes[node]

    def status(self, node: str) -> str:
        return self.api("GET", self._path(node))["status"]

    def off(self, node: str) -> None:
        path = self._path(node)
        deadline = self.clock() + self.timeout
        if self.status(node) == "STOPPED":
            return
        result = self.api("POST", path + ":stop")
        if "error" in result or not result.get("id"):
            raise RuntimeError("API не подтвердил принятие операции остановки")
        while self.clock() < deadline:
            if self.status(node) == "STOPPED":
                return
            self.sleep(2)
        raise TimeoutError("Остановка ВМ не подтверждена")

def metadata_token() -> str:
    req = urllib.request.Request("http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/token",
                                 headers={"Metadata-Flavor": "Google"})
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.load(response)["access_token"]

def api_for(token: str) -> Callable:
    def api(method: str, path: str) -> dict:
        request = urllib.request.Request("https://compute.api.cloud.yandex.net/compute/v1" + path,
                    data=b"{}" if method == "POST" else None, method=method,
                    headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)
    return api

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", "-o", default=None)
    parser.add_argument("--plug", "-n")
    parser.add_argument("--config", default="/etc/otus-fence.json")
    args = parser.parse_args()
    options = vars(args)
    if not sys.stdin.isatty() and len(sys.argv) == 1:
        for line in sys.stdin:
            key, separator, value = line.strip().partition("=")
            if separator and key in options:
                options[key] = value
    action = options["action"] or "off"
    if action in ("metadata", "meta-data"):
        print(METADATA)
        return 0
    try:
        nodes = json.loads(Path(options["config"]).read_text())
        if set(nodes) != {"backend1", "backend2"}:
            raise ValueError("Разрешены только два backend стенда")
        if action == "list":
            for node in nodes:
                print(node + "," + node)
            return 0
        if action not in ("monitor", "status", "off"):
            raise ValueError("Неподдерживаемое действие")
        client = FenceClient(nodes, api_for(metadata_token()))
        if action == "monitor":
            for node in nodes:
                client.status(node)
            return 0
        if action == "status":
            return 2 if client.status(options["plug"]) == "STOPPED" else 0
        client.off(options["plug"])
        return 0
    except (ValueError, KeyError, OSError, RuntimeError, urllib.error.URLError) as error:
        print("Fencing failed: " + type(error).__name__, file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())

