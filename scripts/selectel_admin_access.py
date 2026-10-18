"""Check operator IPv4 before provisioning; keep SSH restricted to one /32."""
import ipaddress
import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def observed_ipv4(fetch=None):
    def fetch_url(url):
        with urllib.request.urlopen(url, timeout=15) as response:
            return response.read(128).decode().strip()
    fetch = fetch or fetch_url
    addresses = [ipaddress.IPv4Address(fetch(url)) for url in
                 ('https://checkip.amazonaws.com', 'https://icanhazip.com')]
    if addresses[0] != addresses[1] or not addresses[0].is_global:
        raise ValueError('Внешний IPv4 не определён однозначно. Проверьте VPN/прокси; ресурсы не создавались.')
    return addresses[0]


def choose_cidrs(cidrs, address, existing=False):
    networks = [ipaddress.IPv4Network(value, strict=True) for value in cidrs]
    if not networks or any(n.prefixlen == 0 for n in networks):
        raise ValueError('admin_cidrs должен ограничивать SSH адресами оператора; 0.0.0.0/0 запрещён.')
    if any(address in network for network in networks):
        return cidrs
    if existing or len(networks) != 1 or networks[0].prefixlen != 32:
        raise ValueError('Текущий IPv4 не входит в admin_cidrs. Обновите правила вручную; ресурсы не создавались.')
    return [str(address) + '/32']


def main():
    folder = ROOT / 'terraform-selectel'
    json_path, hcl_path = folder / 'terraform.tfvars.json', folder / 'terraform.tfvars'
    if json_path.exists() and hcl_path.exists():
        raise ValueError('Оставьте один локальный формат tfvars: HCL или JSON.')
    if json_path.exists():
        variables = json.loads(json_path.read_text(encoding='utf-8-sig'))
        cidrs = variables['admin_cidrs']
    else:
        evaluated = subprocess.run(
            [str(ROOT / '.tools/terraform.exe'), '-chdir=' + str(folder), 'console', '-no-color'],
            input='jsonencode(var.admin_cidrs)\n', capture_output=True, text=True, timeout=30,
            env=dict(os.environ, TF_CLI_CONFIG_FILE=str(ROOT / 'terraform-selectel.rc')))
        if evaluated.returncode:
            raise ValueError('Не удалось прочитать admin_cidrs через Terraform console.')
        cidrs = json.loads(json.loads(evaluated.stdout.strip()))
    state_path = folder / 'terraform.tfstate'
    state = json.loads(state_path.read_text(encoding='utf-8-sig')) if state_path.exists() else {}
    existing = any(r.get('mode') == 'managed' and r.get('instances') for r in state.get('resources', []))
    address = observed_ipv4()
    selected = choose_cidrs(cidrs, address, existing)
    if selected != cidrs:
        if json_path.exists():
            variables['admin_cidrs'] = selected
            json_path.write_text(json.dumps(variables, indent=2) + '\n', encoding='utf-8')
        else:
            content, count = re.subn(
                r'(?m)^(\s*admin_cidrs\s*=\s*)\[\s*"' + re.escape(cidrs[0]) + r'"\s*\]',
                lambda match: match[1] + json.dumps(selected), hcl_path.read_text(encoding='utf-8'))
            if count != 1:
                raise ValueError('Обновите admin_cidrs вручную: безопасная замена HCL невозможна.')
            hcl_path.write_text(content, encoding='utf-8')
        print('Устаревший одиночный admin_cidrs заменён текущим IPv4 /32 на пустом state.', flush=True)
    print('SSH: текущий внешний IPv4 входит в admin_cidrs. Проверено до создания ресурсов.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error) if isinstance(error, ValueError) else
                         'Не удалось проверить внешний IPv4/admin_cidrs. Ресурсы не создавались.') from None
