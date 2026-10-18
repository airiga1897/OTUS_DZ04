#!/usr/bin/python3
"""Experimental Nova Stop fencing: two UUID allowlist, SHUTOFF + power state 4."""
import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from selectel_api import NovaClient

METADATA = '''<?xml version="1.0"?>
<resource-agent name="fence_selectel" shortdesc="Selectel backend fencing">
<longdesc>Experimental Nova Stop agent. Requires SHUTOFF and power_state 4; validate I/O isolation before use.</longdesc>
<parameters>
<parameter name="config" required="0"><shortdesc>Root-owned configuration</shortdesc><content type="string" default="/etc/otus-selectel-fence.json"/></parameter>
<parameter name="plug" required="0"><shortdesc>Backend hostname</shortdesc><content type="string"/></parameter>
</parameters>
<actions><action name="off" timeout="150"/><action name="status" timeout="30"/><action name="monitor" timeout="60"/><action name="list" timeout="5"/><action name="metadata" timeout="5"/></actions>
</resource-agent>'''


class FenceClient:
    def __init__(self, nodes, api, *, timeout=100, sleep=time.sleep, clock=time.monotonic):
        if set(nodes) != {"backend1", "backend2"} or len(set(nodes.values())) != 2:
            raise ValueError("Exactly two distinct backend UUIDs required")
        for value in nodes.values():
            uuid.UUID(value)
        self.nodes, self.api = nodes, api
        self.timeout, self.sleep, self.clock = timeout, sleep, clock

    def path(self, node):
        if node not in self.nodes:
            raise ValueError("Node absent from allowlist")
        return "/servers/" + self.nodes[node]

    def server(self, node):
        result = self.api(self.path(node))["server"]
        if result.get("id") != self.nodes[node]:
            raise ValueError("Unexpected server UUID")
        return result

    @staticmethod
    def powered_off(server):
        return server.get("status") == "SHUTOFF" and server.get("OS-EXT-STS:power_state") == 4

    def off(self, node):
        path = self.path(node)
        deadline = self.clock() + self.timeout
        if self.powered_off(self.server(node)):
            return
        self.api(path + "/action", {"os-stop": None})
        while self.clock() < deadline:
            if self.powered_off(self.server(node)):
                return
            self.sleep(2)
        raise TimeoutError("Power-off not confirmed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", "-o")
    parser.add_argument("--plug", "-n")
    parser.add_argument("--config", default="/etc/otus-selectel-fence.json")
    options = vars(parser.parse_args())
    if len(sys.argv) == 1 and not sys.stdin.isatty():
        for line in sys.stdin:
            key, separator, value = line.strip().partition("=")
            if separator and key in options:
                options[key] = value
    action = options["action"] or "off"
    if action in ("metadata", "meta-data"):
        print(METADATA)
        return 0
    try:
        config = json.loads(Path(options["config"]).read_text())
        # Validate allowlist before authorization or any Nova API request.
        client = FenceClient(config["nodes"], None)
        if action == "list":
            for node in client.nodes:
                print(node + "," + node)
            return 0
        if action not in ("monitor", "status", "off"):
            raise ValueError("Unsupported action")
        if action in ("off", "status"):
            client.path(options["plug"])
        client.api = NovaClient(config["auth"]).request
        if action == "monitor":
            for node in client.nodes:
                client.server(node)
        elif action == "status":
            return 2 if client.powered_off(client.server(options["plug"])) else 0
        else:
            client.off(options["plug"])
        return 0
    except (ValueError, KeyError, OSError, RuntimeError) as error:
        print("Selectel fencing failed: " + type(error).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
