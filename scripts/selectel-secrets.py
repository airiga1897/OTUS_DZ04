"""Read dedicated fencing credentials from stdin; create separate application secrets."""
import base64
import json
import secrets
import sys
import urllib.error
from pathlib import Path
import yaml
from selectel_api import authenticate

ROOT = Path(__file__).resolve().parents[1]


def main():
    try:
        auth = json.loads(sys.stdin.buffer.read().decode('utf-8-sig'))
    except (UnicodeError, json.JSONDecodeError):
        raise SystemExit("Не удалось прочитать параметры из PowerShell: ошибка JSON/UTF-8. Credentials скрыты.") from None
    discovery = json.loads((ROOT / ".local/selectel/discovery.json").read_text(encoding="utf-8"))
    if auth["username"] != "otus-dz04-fence" or auth["project_id"] != discovery["project_id"] or auth["region"] != discovery["region"]:
        raise SystemExit("Нужны отдельный пользователь fencing и тот же проект/регион.")
    authenticate(auth)  # Read-only authorization check before saving credentials.
    path = ROOT / ".local/selectel/secrets.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {
        "db_password": secrets.token_hex(32), "django_secret_key": secrets.token_hex(48),
        "cluster_password": secrets.token_hex(24), "cluster_authkey_b64": base64.b64encode(secrets.token_bytes(128)).decode()}
    data["selectel_fence_auth"] = auth
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    path.chmod(0o600)
    print("Авторизация fencing проверена. Секреты Selectel сохранены отдельно, значения скрыты.")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as error:
        hints = {
            401: "Проверьте пароль, имя otus-dz04-fence, номер аккаунта и назначение роли на проект.",
            403: "API отказал в доступе: проверьте область проекта и назначение роли пользователю.",
            404: "Проверьте адрес Identity API и ID проекта.",
        }
        sys.exit(f"Авторизация fencing: HTTP {error.code}. " + hints.get(error.code, "Ошибка Identity API.") + " Credentials скрыты.")
    except urllib.error.URLError:
        sys.exit("Нет соединения с Identity API: проверьте сеть, прокси и TLS. Credentials скрыты.")
    except TimeoutError:
        sys.exit("Identity API не ответил вовремя. Credentials скрыты.")
    except KeyError:
        sys.exit("В параметрах или ответе Identity API отсутствует обязательное поле. Credentials скрыты.")
    except ValueError:
        sys.exit("Параметры или ответ Identity API не прошли проверку. Credentials скрыты.")
    except OSError:
        sys.exit("Ошибка сети или записи .local/selectel/secrets.yml. Credentials скрыты.")
