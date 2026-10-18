"""Validate live Selectel access and the boot image before creating paid resources."""
import json
import datetime
import socket
import subprocess
import os
import re
import time
import urllib.error
import urllib.parse
from pathlib import Path

from selectel_api import authenticate, config_from_env, request_json

ROOT = Path(__file__).resolve().parents[1]
IMAGE_NAME = 'Ubuntu 24.04 LTS 64-bit'


def retry_read(operation, attempts=3, sleep=time.sleep):
    for attempt in range(attempts):
        try:
            return operation()
        except urllib.error.HTTPError as error:
            if error.code not in (408, 429, 500, 502, 503, 504):
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, socket.gaierror):
            pass
        if attempt + 1 < attempts:
            print(f'Временная ошибка сети/API; повтор {attempt + 2}/{attempts}.', flush=True)
            sleep(2 ** attempt)
    raise RuntimeError('Сеть или API недоступны после трёх попыток. Платные ресурсы не создавались.')


def select_image(images, boot_size):
    matches = [i for i in images if i.get('name') == IMAGE_NAME
               and i.get('status') == 'active' and i.get('visibility') == 'public'
               and i.get('os_distro', 'ubuntu') == 'ubuntu'
               and i.get('architecture') in (None, 'x86_64', 'amd64')
               and i.get('min_disk', 0) <= boot_size]
    if len(matches) != 1:
        raise ValueError('Не найден единственный подходящий публичный Ubuntu 24.04. Автоматическая замена запрещена.')
    return matches[0]


def main():
    config = config_from_env()
    discovery = json.loads((ROOT / '.local/selectel/discovery.json').read_text(encoding='utf-8-sig'))
    if config['project_id'] != discovery['project_id'] or config['region'] != discovery['region']:
        raise ValueError('Окружение отличается от проверенного проекта/региона.')
    variables_path = ROOT / 'terraform-selectel/terraform.tfvars.json'
    hcl = ROOT / 'terraform-selectel/terraform.tfvars'
    if variables_path.exists() and hcl.exists():
        raise ValueError('Оставьте один локальный формат tfvars: HCL или JSON.')
    # HCL is parsed by Terraform itself, avoiding a second, incomplete HCL parser.
    if variables_path.exists():
        variables = json.loads(variables_path.read_text(encoding='utf-8-sig'))
    else:
        env = dict(os.environ, TF_CLI_CONFIG_FILE=str(ROOT / 'terraform-selectel.rc'))
        evaluated = subprocess.run([str(ROOT / '.tools/terraform.exe'), '-chdir=' + str(ROOT / 'terraform-selectel'), 'console', '-no-color'],
                                   input='jsonencode({image_id=var.image_id,boot_disk_gb=var.boot_disk_gb})\n',
                                   capture_output=True, text=True, env=env, timeout=30)
        if evaluated.returncode:
            raise ValueError('Terraform не смог прочитать HCL tfvars. Проверьте init и обязательные параметры.')
        variables = json.loads(json.loads(evaluated.stdout.strip()))
    retry_read(lambda: socket.getaddrinfo('cloud.api.selcloud.ru', 443))
    token, catalog = retry_read(lambda: authenticate(config))
    endpoints = [e['url'].rstrip('/') for service in catalog if service['type'] == 'image'
                 for e in service['endpoints'] if e.get('interface') == 'public' and e.get('region') == config['region']
                 and urllib.parse.urlsplit(e['url']).scheme == 'https']
    if len(set(endpoints)) != 1:
        raise ValueError('Не определён единственный HTTPS endpoint Glance выбранного региона.')
    base = endpoints[0]
    image = None
    try:
        image, _ = retry_read(lambda: request_json(base + '/v2/images/' + variables['image_id'], token=token))
        image = image.get('image', image)
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
    metadata = {'configured_image_id': variables['image_id'], 'boot_disk_gb': variables.get('boot_disk_gb', 10),
                'image': image}
    (ROOT / '.local/selectel/image-metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    if image:
        print(f"Образ: status={image.get('status')}, min_disk={image.get('min_disk')}, диск={variables.get('boot_disk_gb', 10)} ГБ.", flush=True)
    if not image or image.get('status') != 'active' or image.get('min_disk', 0) > variables.get('boot_disk_gb', 10):
        state_path = ROOT / 'terraform-selectel/terraform.tfstate'
        state = json.loads(state_path.read_text(encoding='utf-8-sig')) if state_path.exists() else {}
        if any(r.get('mode') == 'managed' and r.get('instances') for r in state.get('resources', [])):
            raise ValueError('Образ недоступен; замена image_id на существующем стенде запрещена.')
        query = urllib.parse.urlencode({'name': IMAGE_NAME, 'status': 'active', 'limit': 100})
        images, _ = retry_read(lambda: request_json(base + '/v2/images?' + query, token=token))
        (ROOT / '.local/selectel/image-candidates.json').write_text(json.dumps(images, indent=2), encoding='utf-8')
        image = select_image(images.get('images', []), variables.get('boot_disk_gb', 10))
        if variables_path.exists():
            variables['image_id'] = image['id']
            variables_path.write_text(json.dumps(variables, indent=2) + '\n', encoding='utf-8')
        else:
            content, count = re.subn(r'(?m)^(\s*image_id\s*=\s*)"' + re.escape(variables['image_id']) + r'"',
                                     lambda m: m[1] + '"' + image['id'] + '"', hcl.read_text(encoding='utf-8'))
            if count != 1:
                raise ValueError('Не удалось безопасно заменить image_id в HCL. Обновите его вручную.')
            hcl.write_text(content, encoding='utf-8')
        print('Недоступный или неактивный image_id заменён единственным актуальным публичным Ubuntu 24.04. Изменение войдёт в новый план.', flush=True)
    result = {'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'project_id': config['project_id'], 'region': config['region'], 'image_id': image['id'],
              'image_name': image['name'], 'network_and_identity': True}
    (ROOT / '.local/selectel/preflight-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('Preflight: DNS, Identity и загрузочный образ проверены. Платные ресурсы не создавались.')


if __name__ == '__main__':
    try:
        main()
    except urllib.error.HTTPError as error:
        raise SystemExit(f'Preflight: HTTP {error.code}; проверьте права и доступность API. Credentials скрыты.') from None
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        if isinstance(error, (ValueError, RuntimeError)):
            raise SystemExit(str(error)) from None
        raise SystemExit('Preflight не выполнен: проверьте окружение и локальные файлы. Credentials скрыты.') from None
