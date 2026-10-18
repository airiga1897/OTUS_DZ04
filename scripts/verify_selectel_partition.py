"""Isolate backend peers with temporary rules; retain SSH, qdevice and cloud API."""
import datetime
import json
import shlex
import time
import urllib.request

import yaml
import controller
import selectel_controller
from selectel_api import NovaClient


def main():
    selectel_controller.configure(controller)
    lab = controller.terraform_output()
    lab['lb_public_ip'] = lab['public_ips']['nginx1']
    local = controller.ROOT / '.local/selectel'
    api = NovaClient(yaml.safe_load((local / 'secrets.yml').read_text())['selectel_fence_auth'])
    result = {'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'passed': False}
    peer = lab['private_ips']['backend1']
    rules = [('INPUT', '-s'), ('OUTPUT', '-d')]
    # Rules affect only backend-to-backend traffic; no default policy or other rules change.
    rollback = '\n'.join('iptables -D ' + chain + ' ' + flag + ' ' + peer + ' -m comment --comment otus-dz04-partition -j DROP || true' for chain, flag in rules)

    def state(node):
        return api.request('/servers/' + lab['instance_ids'][node])['server']['status']

    with controller.connect(lab) as front:
        def remote(node, command):
            argv = ['ssh', '-i', '/home/otus/otus-dz04/.local/otus_dz04', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=5', '-o', 'UserKnownHostsFile=/home/otus/otus-dz04/.local/known_hosts', lab['ssh_user'] + '@' + lab['private_ips'][node], command]
            controller.remote_exec(front, shlex.join(argv))

        controller.remote_exec(front, 'cd /home/otus/otus-dz04/ansible && ../.venv/bin/ansible-playbook verify.yml')
        if any(state(n) != 'ACTIVE' for n in ('backend1', 'backend2')):
            raise RuntimeError('Healthy baseline required')
        # Arm rollback BEFORE applying the two temporary rules.
        remote('backend2', 'printf %s ' + shlex.quote(rollback + '\n') + ' | sudo tee /root/otus-partition-rollback.sh >/dev/null && sudo systemd-run --unit=otus-partition-rollback --on-active=180s /bin/sh /root/otus-partition-rollback.sh')
        started = time.monotonic()
        try:
            commands = ['sudo iptables -I ' + chain + ' 1 ' + flag + ' ' + peer + ' -m comment --comment otus-dz04-partition -j DROP' for chain, flag in rules]
            remote('backend2', ' && '.join(commands))
            deadline = time.monotonic() + 150
            while time.monotonic() < deadline:
                stopped = [n for n in ('backend1', 'backend2') if state(n) == 'SHUTOFF']
                if stopped:
                    if len(stopped) != 1:
                        raise RuntimeError('Both peers were fenced')
                    result['fenced_node'] = stopped[0]
                    result['fencing_observed_s'] = round(time.monotonic() - started, 2)
                    break
                time.sleep(3)
            else:
                raise RuntimeError('No fencing observed before automatic rollback')
            # Verify survivor can actually read dynamic data and uncached GFS2 static.
            for path in ('/', '/health/ready', '/static/knowledge/site.css?partition=' + str(time.time_ns())):
                with urllib.request.urlopen(lab['site_url'] + path, timeout=30) as response:
                    if response.status != 200 or not response.read():
                        raise RuntimeError('Survivor HTTP check failed')
            result['passed'] = True
        finally:
            if state('backend2') == 'ACTIVE':
                remote('backend2', 'sudo /bin/sh /root/otus-partition-rollback.sh')
            for node in ('backend1', 'backend2'):
                if state(node) == 'SHUTOFF':
                    api.request('/servers/' + lab['instance_ids'][node] + '/action', {'os-start': None})
            (local / 'partition-results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        time.sleep(60)
        deadline = time.monotonic() + 240
        while True:
            try:
                controller.remote_exec(front, 'cd /home/otus/otus-dz04/ansible && ../.venv/bin/ansible-playbook verify.yml')
                result['restored'] = True
                break
            except RuntimeError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(15)
        (local / 'partition-results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
