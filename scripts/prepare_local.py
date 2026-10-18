"""Создать только новые ключи/секреты ДЗ04; credentials прежних проектов не копируются."""
import argparse
import base64
import json
import secrets
from pathlib import Path
import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cloud-id", required=True)
    parser.add_argument("--folder-id", required=True)
    parser.add_argument("--admin-cidr", required=True)
    args = parser.parse_args()
    import ipaddress
    network = ipaddress.IPv4Network(args.admin_cidr)
    if network.prefixlen != 32:
        parser.error("Нужен отдельный адрес администратора /32")
    local = ROOT / ".local"
    local.mkdir(exist_ok=True)
    key = local / "otus_dz04"
    if not key.exists():
        private = Ed25519PrivateKey.generate()
        key.write_bytes(private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                                             serialization.NoEncryption()))
        key.with_suffix(".pub").write_bytes(private.public_key().public_bytes(
            serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH) + b" otus-dz04\n")
        key.chmod(0o600)
    tfvars = ROOT / "terraform/terraform.tfvars.json"
    if not tfvars.exists():
        tfvars.write_text(json.dumps({"cloud_id": args.cloud_id, "folder_id": args.folder_id,
                                     "admin_cidrs": [str(network)]}, indent=2), encoding="utf-8")
    secret_file = local / "secrets.yml"
    if not secret_file.exists():
        secret_file.write_text(yaml.safe_dump({"db_password": secrets.token_hex(32),
            "django_secret_key": secrets.token_hex(48), "cluster_password": secrets.token_hex(24),
            "cluster_authkey_b64": base64.b64encode(secrets.token_bytes(128)).decode()}), encoding="utf-8")
        secret_file.chmod(0o600)
    print("Новые ключи, секреты и параметры ДЗ04 готовы; значения секретов скрыты.")

if __name__ == "__main__":
    main()

