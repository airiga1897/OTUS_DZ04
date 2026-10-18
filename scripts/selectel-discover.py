"""Read-only discovery: credentials/token stay in memory, catalogs saved locally."""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def select_endpoints(catalog, region, required_services):
    endpoints, rejected = {}, set()
    for service in catalog:
        kind = service["type"]
        if kind not in required_services:
            continue
        for endpoint in service["endpoints"]:
            if endpoint.get("interface") != "public" or endpoint.get("region") != region:
                continue
            url = endpoint["url"].rstrip("/")
            parsed = urllib.parse.urlsplit(url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                rejected.add(kind)
                continue
            endpoints.setdefault(kind, url)
    return endpoints, rejected - endpoints.keys()


def main():
    required = ("OS_AUTH_URL", "OS_PROJECT_ID", "OS_USER_DOMAIN_NAME", "OS_USERNAME", "OS_PASSWORD", "OS_REGION_NAME")
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise SystemExit("Сначала загрузите selectel-env.ps1. Не заданы: " + ", ".join(missing))
    auth_url = os.environ["OS_AUTH_URL"].rstrip("/")
    if auth_url != "https://cloud.api.selcloud.ru/identity/v3":
        raise SystemExit("Неожиданный адрес авторизации; запрос с паролем не отправлен.")
    project = os.environ["OS_PROJECT_ID"]
    region = os.environ["OS_REGION_NAME"]
    body = {"auth": {"identity": {"methods": ["password"], "password": {"user": {
        "name": os.environ["OS_USERNAME"], "domain": {"name": os.environ["OS_USER_DOMAIN_NAME"]},
        "password": os.environ["OS_PASSWORD"]}}}, "scope": {"project": {"id": project}}}}
    request = urllib.request.Request(auth_url + "/auth/tokens", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        token = response.headers["X-Subject-Token"]
        data = json.load(response)["token"]
    if data.get("project", {}).get("id") != project:
        raise SystemExit("Авторизация вернула другой проект; проверка остановлена.")

    queries = {
        "flavors": ("compute", "/flavors/detail"),
        "compute_quotas": ("compute", "/os-quota-sets/" + project),
        "availability_zones": ("compute", "/os-availability-zone"),
        "images": ("image", "/v2/images?limit=100"),
        "volume_types": ("volumev3", "/types"),
        "volume_quotas": ("volumev3", "/os-quota-sets/" + project),
        "external_networks": ("network", "/v2.0/networks?router:external=true"),
        "network_quotas": ("network", "/v2.0/quotas/" + project),
        "lb_flavors": ("load-balancer", "/v2/lbaas/flavors"),
    }
    # Ignore unrelated services; never send the token to HTTP endpoints.
    endpoints, rejected = select_endpoints(data["catalog"], region, {q[0] for q in queries.values()})
    output = {"project_id": project, "region": region, "endpoints": endpoints, "catalogs": {}, "errors": {}}
    for name, (kind, suffix) in queries.items():
        base = endpoints.get(kind)
        if not base:
            reason = "No acceptable HTTPS public endpoint: " if kind in rejected else "Service absent from selected region catalog: "
            output["errors"][name] = reason + kind
            continue
        # Glance catalogs may already include /v2.
        if kind == "image" and base.endswith("/v2"):
            suffix = suffix.removeprefix("/v2")
        try:
            req = urllib.request.Request(base + suffix, headers={"X-Auth-Token": token})
            with urllib.request.urlopen(req, timeout=30) as response:
                output["catalogs"][name] = json.load(response)
            print(name + ": OK", flush=True)
        except urllib.error.HTTPError as error:
            output["errors"][name] = "HTTP " + str(error.code)
        except (OSError, ValueError):
            output["errors"][name] = "Network or JSON error"
    local = ROOT / ".local/selectel"
    local.mkdir(parents=True, exist_ok=True)
    (local / "discovery.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Каталоги сохранены в .local/selectel/discovery.json. Платные ресурсы не создавались.")
    if output["errors"]:
        print("Часть каталогов недоступна; причины сохранены без credentials.")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as error:
        sys.exit("Авторизация Selectel не выполнена: HTTP " + str(error.code) + ". Credentials скрыты.")
    except (OSError, ValueError, KeyError):
        sys.exit("Не удалось проверить API Selectel. Проверьте сеть и параметры; credentials скрыты.")
