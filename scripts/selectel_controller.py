"""Selectel adapter for controller.py: Nova console trust and Cinder disk identity."""
import base64
import json
import re
import subprocess
import time
import uuid

import paramiko
from selectel_api import NovaClient, config_from_env


def select_disk(volume_id, disks, by_ids):
    expected = uuid.UUID(volume_id).hex
    matches = []
    def used(disk):
        return any(p and p != '/srv/otus' for p in (disk.get("mountpoints") or [])) or any(used(c) for c in disk.get("children", []))
    for disk in disks:
        serial = re.sub(r"[^0-9a-f]", "", str(disk.get("serial", "")).lower())
        if disk.get("type") != "disk" or not (len(serial) >= 16 and expected.startswith(serial)):
            continue
        if used(disk):
            raise ValueError("Data disk is mounted; refusing initialization")
        paths = sorted(p for p, target in by_ids.items() if target == disk["name"] and "-part" not in p)
        if not paths:
            raise ValueError("Data disk has no stable by-id path")
        matches.append(paths[0])
    if len(matches) != 1:
        raise ValueError("Cannot uniquely identify Cinder data volume")
    return matches[0]


def configure(core):
    core.LOCAL = core.ROOT / ".local/selectel"
    original_upload = core.upload

    def terraform_output():
        executable = core.ROOT / ".tools/terraform.exe"
        return json.loads(subprocess.check_output([str(executable), "-chdir=" + str(core.ROOT / "terraform-selectel"), "output", "-json", "lab"]))

    def host_keys(lab):
        api = NovaClient(config_from_env())
        lines = []
        for node, instance_id in lab["instance_ids"].items():
            uuid.UUID(instance_id)
            found = None
            for attempt in range(30):
                contents = api.request("/servers/" + instance_id + "/action", {"os-getConsoleOutput": {"length": 1000}})["output"]
                section = re.search(r"BEGIN SSH HOST KEY KEYS.*?END SSH HOST KEY KEYS", contents, re.S)
                found = re.search(r"ssh-ed25519\s+([A-Za-z0-9+/=]+)", section.group()) if section else None
                if found:
                    break
                if attempt == 0:
                    print("Ожидание SSH host key в Nova console: " + node, flush=True)
                time.sleep(5)
            if not found:
                raise RuntimeError("Нет доверенного SSH host key: " + node)
            paramiko.Ed25519Key(data=base64.b64decode(found[1]))
            addresses = [lab["private_ips"][node]]
            if node in lab["public_ips"]:
                public = lab["public_ips"][node]
                port = lab.get("admin_ssh_port", 22)
                addresses.append(public if port == 22 else f"[{public}]:{port}")
            lines.append(",".join(addresses) + " ssh-ed25519 " + found[1] + "\n")
        (core.LOCAL / "known_hosts").write_text("".join(lines), encoding="utf-8")
        print("SSH host keys получены через авторизованный Nova API.", flush=True)

    def upload(front, lab):
        if lab.get("cloud_provider") != "selectel":
            raise ValueError("Wrong cloud output")
        # Identify each data disk over a trusted SSH jump, before writing inventory.
        lab["host_vars"] = {}
        for node, volume_id in lab["data_volume_ids"].items():
            private_ip = lab["private_ips"][node]
            jump = front.get_transport().open_channel("direct-tcpip", (private_ip, 22), ("127.0.0.1", 0))
            with paramiko.SSHClient() as backend:
                backend.load_host_keys(str(core.LOCAL / "known_hosts"))
                backend.set_missing_host_key_policy(paramiko.RejectPolicy())
                backend.connect(private_ip, sock=jump, username=lab["ssh_user"], key_filename=str(core.LOCAL / "otus_dz04"),
                                look_for_keys=False, allow_agent=False, timeout=20)
                command = "sudo python3 -c \"import json,subprocess,glob,os; print(json.dumps({'disks':json.loads(subprocess.check_output(['lsblk','--json','--paths','--output','NAME,TYPE,SERIAL,MOUNTPOINTS']))['blockdevices'],'by_ids':{p:os.path.realpath(p) for p in glob.glob('/dev/disk/by-id/*')}}))\""
                _, stdout, _ = backend.exec_command(command)
                result = json.loads(stdout.read())
                if stdout.channel.recv_exit_status():
                    raise RuntimeError("Cannot read backend disks")
            path = select_disk(volume_id, result["disks"], result["by_ids"])
            lab["host_vars"][node] = {"drbd_backing_device": path}
        original_upload(front, lab)

    core.terraform_output = terraform_output
    core.host_keys = host_keys
    core.upload = upload
