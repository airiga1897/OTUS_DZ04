"""Prepare an independent SSH key and a tfvars template without cloud operations."""
import shutil
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]


def main():
    local = ROOT / '.local/selectel'
    local.mkdir(parents=True, exist_ok=True)
    key = local / 'otus_dz04'
    public = key.with_suffix('.pub')
    if key.exists() != public.exists():
        raise SystemExit('Неполная пара SSH-ключей. Существующий ключ не изменён.')
    if not key.exists():
        private = Ed25519PrivateKey.generate()
        key.write_bytes(private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH, serialization.NoEncryption()))
        key.chmod(0o600)
        public.write_bytes(private.public_key().public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH) + b' otus-dz04-selectel\n')
    variables = ROOT / 'terraform-selectel/terraform.tfvars'
    if not variables.exists() and not variables.with_suffix('.tfvars.json').exists():
        shutil.copyfile(ROOT / 'terraform-selectel/terraform.tfvars.example', variables)
    print('Ключ Selectel и шаблон tfvars готовы. Существующие файлы сохранены; облачных операций нет.')


if __name__ == '__main__':
    main()
