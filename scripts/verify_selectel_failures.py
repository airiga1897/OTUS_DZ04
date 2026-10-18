"""Stop each application/front VM in turn and restore it before continuing."""
import datetime
import json
import time
import urllib.request
from pathlib import Path

import yaml
import controller
import selectel_controller
from selectel_api import NovaClient


def main():
    selectel_controller.configure(controller)
    lab = controller.terraform_output()
    local = controller.ROOT / '.local/selectel'
    api = NovaClient(yaml.safe_load((local / 'secrets.yml').read_text())['selectel_fence_auth'])
    results = []

    def server(node):
        return api.request('/servers/' + lab['instance_ids'][node])['server']

    def wait_state(node, state, seconds=180):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if server(node)['status'] == state:
                return
            time.sleep(3)
        raise RuntimeError(node + ': timed out waiting for ' + state)

    def check_http(excluded=None):
        for path in ('/', '/health/ready', '/static/knowledge/site.css?fault=' + str(time.time_ns())):
            with urllib.request.urlopen(lab['site_url'] + path, timeout=25) as response:
                if response.status != 200 or not response.read():
                    raise RuntimeError('HTTP check failed')
                if excluded and excluded in (response.headers.get('X-Frontend-Node'), response.headers.get('X-Backend-Node')):
                    raise RuntimeError('Response from stopped node')

    # A healthy baseline is required before any destructive test.
    check_http()
    for node in ('backend1', 'backend2', 'nginx2', 'nginx1'):
        if any(server(n)['status'] != 'ACTIVE' for n in lab['instance_ids']):
            raise RuntimeError('All VMs must be ACTIVE before each test')
        item = {'node': node, 'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'passed': False}
        results.append(item)
        print('Stopping ' + node, flush=True)
        started = time.monotonic()
        try:
            api.request('/servers/' + lab['instance_ids'][node] + '/action', {'os-stop': None})
            wait_state(node, 'SHUTOFF')
            deadline = time.monotonic() + 180
            while True:
                try:
                    check_http(node)
                    item['recovery_observed_s'] = round(time.monotonic() - started, 2)
                    break
                except (OSError, RuntimeError):
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Website did not recover while ' + node + ' was off')
                    time.sleep(3)
            for _ in range(10):
                check_http(node)
            item['passed'] = True
            print(node + ': dynamic, readiness and uncached static passed while off', flush=True)
        finally:
            print('Restoring ' + node, flush=True)
            if server(node)['status'] == 'SHUTOFF':
                api.request('/servers/' + lab['instance_ids'][node] + '/action', {'os-start': None})
            wait_state(node, 'ACTIVE')
            # Let quorum, DRBD and application rejoin; verify through trusted controller.
            time.sleep(45)
            lab['lb_public_ip'] = lab['public_ips']['nginx1']
            (local / 'failure-results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
            deadline = time.monotonic() + 240
            while True:
                try:
                    with controller.connect(lab) as front:
                        controller.remote_exec(front, 'cd /home/otus/otus-dz04/ansible && ../.venv/bin/ansible-playbook verify.yml')
                    item['restored'] = True
                    break
                except (OSError, RuntimeError):
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(15)
            (local / 'failure-results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        if not item['passed']:
            break
    return int(not all(r['passed'] and r.get('restored') for r in results) or len(results) != 4)


if __name__ == '__main__':
    raise SystemExit(main())
