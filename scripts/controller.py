"""Подготовка Linux-контроллера и запуск Ansible с доверенными SSH-ключами YC/Selectel."""

import argparse
import base64
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

import paramiko
from yc_auth import get_token

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"


def terraform_output():
    if "OTUS_LAB_JSON" in os.environ:
        return json.loads(os.environ["OTUS_LAB_JSON"])
    executable = ROOT / ".tools" / ("terraform.exe" if sys.platform == "win32" else "terraform")
    return json.loads(subprocess.check_output(
        [str(executable), "-chdir=terraform", "output", "-json", "lab"], cwd=ROOT))


def remote_exec(client, command):
    print(f"Выполнение на контроллере: {command}", flush=True)
    channel = client.get_transport().open_session()
    channel.set_combine_stderr(True)
    channel.exec_command(command)
    while not channel.exit_status_ready() or channel.recv_ready():
        if channel.recv_ready():
            sys.stdout.write(channel.recv(65536).decode("utf-8", errors="replace"))
            sys.stdout.flush()
        else:
            time.sleep(0.2)
    result = channel.recv_exit_status()
    if result:
        raise RuntimeError(f"Удалённая команда завершилась с кодом {result}")


def host_keys(lab):
    """Доверенный источник ключей — serial console через авторизованный API YC."""
    executable = ROOT / ".tools" / ("yc.exe" if sys.platform == "win32" else "yc")
    env = dict(os.environ)
    env["YC_IAM_TOKEN"] = get_token()
    lines = []
    for node, instance_id in lab["instance_ids"].items():
        found = None
        for attempt in range(30):
            raw = subprocess.check_output(
                [str(executable), "--no-browser", "--config", os.environ.get("OTUS_YC_CONFIG", str(LOCAL / "yc-config.yaml")),
                 "compute", "instance", "get-serial-port-output", "--id", instance_id,
                 "--format", "json"], env=env)
            contents = json.loads(raw)["contents"]
            section = re.search(r"BEGIN SSH HOST KEY KEYS.*?END SSH HOST KEY KEYS", contents, re.S)
            found = re.search(r"ssh-ed25519\s+([A-Za-z0-9+/=]+)", section.group()) if section else None
            if found:
                break
            if attempt == 0:
                print(f"Ожидание ключа SSH в serial console: {node}", flush=True)
            time.sleep(5)
        if not found:
            raise RuntimeError(f"В доверенном выводе YC нет SSH host key для {node}; подключение запрещено")
        key = found[1]
        paramiko.Ed25519Key(data=base64.b64decode(key))
        addresses = [lab["private_ips"][node]]
        if node in ("nginx1", "nginx2"):
            addresses.append(lab["public_ips"][node])
        lines.append(f"{','.join(addresses)} ssh-ed25519 {key}\n")
        print(f"Ключ {node} получен из YC serial console.", flush=True)
    (LOCAL / "known_hosts").write_text("".join(lines), encoding="utf-8")


def connect(lab):
    for attempt in range(6):
        client = paramiko.SSHClient()
        try:
            client.load_host_keys(str(LOCAL / "known_hosts"))
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
            client.connect(lab["lb_public_ip"], port=lab.get("admin_ssh_port", 22), username=lab["ssh_user"], key_filename=str(LOCAL / "otus_dz04"),
                           look_for_keys=False, allow_agent=False, timeout=10, banner_timeout=30)
            return client
        except (OSError, paramiko.ssh_exception.NoValidConnectionsError):
            client.close()
            if attempt == 5:
                raise RuntimeError(f"SSH недоступен после 6 попыток: проверьте маршрут TCP/{lab.get('admin_ssh_port', 22)}, VPN, admin_cidrs и готовность ВМ.") from None
            print(f"Ожидание TCP/{lab.get('admin_ssh_port', 22)} контроллера; попытка {attempt + 2}/6.", flush=True)
            time.sleep(5)
        except Exception:
            client.close()
            raise


def upload(client, lab):
    base = f"/home/{lab['ssh_user']}/otus-dz04"
    remote_exec(client, f"mkdir -p {base}/.local {base}/ansible {base}/scripts && chmod 700 {base}/.local")
    sftp = client.open_sftp()

    def mkdir(path):
        try:
            sftp.stat(path)
        except FileNotFoundError:
            mkdir(str(Path(path).parent).replace('\\', '/'))
            sftp.mkdir(path, mode=0o755)

    for directory in ("ansible", "scripts", "app"):
        for path in (ROOT / directory).rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            relative = path.relative_to(ROOT).as_posix()
            remote = f"{base}/{relative}"
            mkdir(remote.rsplit("/", 1)[0])
            # Текстовые файлы всегда LF, независимо от рабочего дерева Windows.
            with sftp.open(remote, "w") as target:
                target.write(path.read_text(encoding="utf-8").replace("\r\n", "\n"))
            sftp.chmod(remote, 0o644)
    for name in ("otus_dz04", "secrets.yml", "known_hosts"):
        sftp.put(str(LOCAL / name), f"{base}/.local/{name}")
        sftp.chmod(f"{base}/.local/{name}", 0o600)
    inventory = {"all": {"vars": {
        "cloud_provider": lab.get("cloud_provider", "yandex"),
        "ansible_user": lab["ssh_user"], "ansible_become": True,
        "ansible_ssh_private_key_file": f"{base}/.local/otus_dz04",
        "ansible_ssh_common_args": f"-o StrictHostKeyChecking=yes -o UserKnownHostsFile={base}/.local/known_hosts",
        "app_allowed_hosts": [lab["site_url"].split("//", 1)[1], "127.0.0.1", "localhost",
                              *lab["private_ips"].values(), *lab["public_ips"].values()],
    }, "children": {group: {"hosts": {node: {
        "ansible_host": lab["private_ips"][node],
        "private_ip": lab["private_ips"][node],
        "instance_id": lab["instance_ids"][node],
        **lab.get("host_vars", {}).get(node, {}),
        **({"ansible_connection": "local", "ansible_host": "127.0.0.1"} if node == lab["controller"] else {}),
    } for node in nodes}} for group, nodes in {
        "front": ["nginx1", "nginx2"], "backend": ["backend1", "backend2"], "database": ["db"]
    }.items()}}}
    with sftp.open(f"{base}/ansible/inventory.json", "w") as target:
        target.write(json.dumps(inventory, indent=2))
    sftp.chmod(f"{base}/ansible/inventory.json", 0o600)
    sftp.close()
    print("Исходники и секреты приложения DZ04 загружены. Credentials оператора не копировались.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controller", choices=["nginx1", "nginx2"], default="nginx1")
    parser.add_argument("--cloud", choices=["yandex", "selectel"], default="yandex")
    parser.add_argument("action", choices=["trust", "prepare", "bootstrap", "upload", "run", "exec"])
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.cloud == "selectel":
        import selectel_controller
        selectel_controller.configure(sys.modules[__name__])
    lab = terraform_output()
    lab["controller"] = args.controller
    lab["lb_public_ip"] = lab["public_ips"][args.controller]
    print(f"Контроллер: {args.controller} | Сайт: {lab['site_url']}", flush=True)
    if args.action in ("trust", "prepare"):
        host_keys(lab)
    if args.action == "trust":
        return
    with connect(lab) as client:
        base = f"/home/{lab['ssh_user']}/otus-dz04"
        if args.action in ("prepare", "bootstrap", "upload"):
            upload(client, lab)
        if args.action in ("prepare", "bootstrap"):
            remote_exec(client, f"sudo python3 {base}/scripts/check_cloud_init.py && sudo -n true && sudo apt-get update -qq && "
                        "sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv")
            remote_exec(client, f"cd {base} && python3 -m venv .venv && "
                        ".venv/bin/python -m pip install -r ansible/requirements.txt")
        if args.action == "run":
            if not args.arguments:
                raise SystemExit("Укажите playbook, например site.yml --syntax-check")
            remote_exec(client, f"cd {base}/ansible && ../.venv/bin/ansible-playbook " + shlex.join(args.arguments))
        if args.action == "exec":
            remote_exec(client, " ".join(args.arguments))


if __name__ == "__main__":
    main()
