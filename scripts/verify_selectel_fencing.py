"""Sequential stop/start tests on two empty backend VMs; restore each before next."""
import argparse
import datetime
import json
import shlex
import sys
import time
from pathlib import Path

import yaml
import controller
import selectel_controller
from selectel_api import NovaClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--empty-storage', action='store_true', required=True)
    parser.parse_args()
    selectel_controller.configure(controller)
    lab = controller.terraform_output()
    lab['lb_public_ip'] = lab['public_ips']['nginx1']
    local = controller.ROOT / '.local/selectel'
    config = yaml.safe_load((local / 'secrets.yml').read_text(encoding='utf-8'))['selectel_fence_auth']
    api = NovaClient(config)
    results = []

    def status(node):
        server = api.request('/servers/' + lab['instance_ids'][node])['server']
        if server['id'] != lab['instance_ids'][node]:
            raise RuntimeError('Unexpected UUID')
        return server

    with controller.connect(lab) as front:
        def remote(node, command):
            argv = ['ssh', '-i', '/home/otus/otus-dz04/.local/otus_dz04',
                '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=5',
                '-o', 'UserKnownHostsFile=/home/otus/otus-dz04/.local/known_hosts',
                lab['ssh_user'] + '@' + lab['private_ips'][node], command]
            _, stdout, stderr = front.exec_command(shlex.join(argv), timeout=160)
            output = stdout.read().decode(errors='replace')
            error = stderr.read().decode(errors='replace')
            if stdout.channel.recv_exit_status():
                raise RuntimeError('Remote check failed on ' + node)
            return output

        # Both nodes must be empty and unmanaged by Pacemaker before any stop.
        for node in ('backend1', 'backend2'):
            remote(node, "sudo test ! -e /var/lib/otus-dz04/initialized && ! sudo mountpoint -q /srv/otus && test \"$(systemctl is-active pacemaker)\" != active")
            if status(node)['status'] != 'ACTIVE':
                raise RuntimeError(node + ' is not ACTIVE before test')
            remote(node, 'sudo /usr/sbin/fence_selectel --action monitor')

        for executor, target in [('backend1', 'backend2'), ('backend2', 'backend1')]:
            started = time.monotonic()
            item = {'executor': executor, 'target': target, 'passed': False,
                    'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
            results.append(item)
            print('Fencing: ' + executor + ' -> ' + target, flush=True)
            try:
                remote(executor, 'sudo /usr/sbin/fence_selectel --action off --plug ' + target)
                server = status(target)
                if server['status'] != 'SHUTOFF' or server.get('OS-EXT-STS:power_state') != 4:
                    raise RuntimeError('Independent Nova power-off check failed')
                item['off_seconds'] = round(time.monotonic() - started, 2)
                print(target + ': SHUTOFF, power_state=4 confirmed independently.', flush=True)
                item['passed'] = True
            finally:
                print('Restoring ' + target, flush=True)
                server = status(target)
                if server['status'] == 'SHUTOFF':
                    api.request('/servers/' + lab['instance_ids'][target] + '/action', {'os-start': None})
                deadline = time.monotonic() + 180
                restored = False
                while time.monotonic() < deadline:
                    server = status(target)
                    if server['status'] == 'ACTIVE':
                        try:
                            remote(target, 'sudo -n true')
                            restored = True
                            break
                        except (RuntimeError, OSError):
                            pass
                    time.sleep(3)
                item['restored'] = restored
                (local / 'fencing-results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
                if not restored:
                    raise RuntimeError('Backend not restored; inspect cloud immediately: ' + target)
                print(target + ': ACTIVE and trusted SSH restored.', flush=True)
    print('Both directions passed; this validates empty-VM Stop only, not isolation during a storage/network failure.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, RuntimeError) as error:
        sys.exit('Fencing test failed: ' + type(error).__name__ + '. Inspect VM states; do not initialize storage.')
