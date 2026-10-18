"""Bounded retry of transient Terraform failures, always with a fresh checked plan."""
import argparse
import json
import os
import subprocess
import time
from pathlib import Path

from run_logged import run
from selectel_plan import validate_creation

ROOT = Path(__file__).resolve().parents[1]


def transient(log):
    text = log.read_text(encoding='utf-8', errors='replace').lower()
    return any(s in text for s in ('no such host', 'temporary failure in name resolution', 'connection reset',
                                  'connection error, retries exhausted', 'i/o timeout', 'tls handshake timeout',
                                  'context deadline exceeded', 'bad gateway', 'service unavailable', 'gateway timeout'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    os.environ['TF_CLI_CONFIG_FILE'] = str(ROOT / 'terraform-selectel.rc')
    local = ROOT / '.local/selectel'
    local.mkdir(parents=True, exist_ok=True)
    terraform = [str(ROOT / '.tools/terraform.exe'), '-chdir=' + str(ROOT / 'terraform-selectel')]
    plan = ROOT / '.local/selectel.tfplan'
    for attempt in range(1, 4):
        log = local / f'provision-plan-{attempt}.log'
        code = run(terraform + ['plan', '-input=false', '-no-color', '-out=' + str(plan)], log)
        if code == 0:
            data = json.loads(subprocess.check_output(terraform + ['show', '-json', str(plan)]))
            validate_creation(data)
            print('План проверен: пять ВМ, только создание или уже созданные ресурсы.', flush=True)
            if not args.apply:
                return 0
            log = local / f'provision-apply-{attempt}.log'
            code = run(terraform + ['apply', '-input=false', '-no-color', str(plan)], log)
            if code == 0:
                return 0
        if attempt == 3 or not transient(log):
            raise RuntimeError('Terraform не завершён. Полная причина сохранена: ' + str(log))
        print('Временный сетевой сбой Terraform. Состояние сохраняется; следующий запуск построит НОВЫЙ план без изменений и удалений.', flush=True)
        time.sleep(5 * attempt)
    return 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError) as error:
        raise SystemExit(str(error)) from None
