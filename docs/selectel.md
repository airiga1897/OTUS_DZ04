# Развёртывание в Selectel

## Terraform-провайдер

Используется `terraform-provider-openstack/openstack` версии 3.4.0;
настройка приведена в terraform-selectel/versions.tf. Он управляет
инфраструктурой через OpenStack API Selectel. Проект и пользователи
подготавливаются отдельно, поэтому `selectel/selectel` не подключается.
Обоснование выбора облака и провайдера приведено в
[architecture-review.md](architecture-review.md).

## Требования

Используется отдельный облачный проект Selectel, пул ru-9, сегмент ru-9a.
На управляющем компьютере нужны PowerShell, Python 3.12 и доступ по SSH
к фронтам. Ansible устанавливается на nginx1 в отдельное Linux-окружение.
Все команды выполняются из корня репозитория.

## Подготовка инструментов

```powershell
.\scripts\setup.ps1
. .\scripts\env.ps1
.\.tools\venv\Scripts\python.exe scripts/prepare_selectel_local.py
```

Создаются локальные инструменты, SSH-ключ и пример параметров Terraform.
Каталоги .tools и .local исключены из Git. Существующие ключи сохраняются.

## Доступ к проекту

В панели Selectel необходимо создать отдельный проект и двух сервисных пользователей:

- otus-dz04-terraform — оператор с ролью member в проекте стенда;
- otus-dz04-fence — роль compute.server.user в этом же проекте.

Оператору нужны права на Compute, Cinder, Neutron и Octavia.
Агент fencing разрешает выключение только двух backend-серверов,
проверяя их идентификаторы. Права сервисного пользователя распространяются
на проект целиком; ограничение проверяется внутри агента,
а не правами доступа облака.

Окружение оператора загружается командой:

```powershell
. .\scripts\selectel-env.ps1 -AccountNumber ACCOUNT_NUMBER -ProjectId PROJECT_UUID -UserName otus-dz04-terraform -Region ru-9
.\.tools\venv\Scripts\python.exe scripts/selectel-discover.py
```

ACCOUNT_NUMBER — номер аккаунта в панели, PROJECT_UUID — ID облачного проекта.
Пароль запрашивается скрытым вводом и остаётся в текущем процессе PowerShell.
Discovery сохраняет доступные образы, типы ВМ, дисков и квоты локально;
платные ресурсы на этом этапе не создаются.

При наличии локальной конфигурации достаточно:

```powershell
. .\scripts\selectel-env.ps1
```

Регион берётся из tfvars или discovery.json, проект — из discovery.json.
Номер аккаунта и имя оператора могут использоваться из текущего окружения.
Для недостающих значений выводятся подсказки; пароль запрашивается заново.

## Параметры инфраструктуры

В terraform-selectel/terraform.tfvars заменяются значения примера
данными из discovery.json. Допускается terraform.tfvars.json вместо HCL;
используется только один формат локальных параметров.

| Параметр | Значение стенда |
| --- | --- |
| region / availability_zone | ru-9 / ru-9a |
| Фронты и БД | PRC20.1-1024, flavor 9022 |
| Backend | SL1.1-2048, flavor 1012 |
| Образ | Ubuntu 24.04 LTS |
| Тип дисков | basic.ru-9a, HDD |
| Загрузочный диск / диск данных backend | 10 ГБ / 1 ГБ |
| Балансировщик | Octavia HA |
| admin_ssh_port | 22 |

ID образа и балансировщика выбираются из каталога проекта.
В admin_cidrs указывается внешний IPv4 оператора с /32.
До создания ресурсов сценарий проверяет внешний IP, DNS, авторизацию
и доступность образа. Устаревший одиночный /32 обновляется только на пустом
state; сложные списки доступа автоматически не перезаписываются.

Для фронтов и backend настроены отдельные группы anti-affinity.
Внешний SSH ограничен admin_cidrs, внутренний SSH использует TCP/22.
Параметр admin_ssh_port также допускает 443 как альтернативный порт SSH;
при добавлении HTTPS использование этого порта необходимо согласовать отдельно.

## Секреты и проверка Terraform

```powershell
.\scripts\selectel-fence-config.ps1
.\scripts\tf-selectel.ps1 init
.\scripts\tf-selectel.ps1 fmt -check
.\scripts\tf-selectel.ps1 validate
```

Скрипт запрашивает пароль отдельного пользователя fencing и проверяет доступ.
Пароли приложения, БД и кластера сохраняются в .local/selectel/secrets.yml.
Credentials оператора на серверы не передаются. Секреты и state не публикуются.

## Создание и настройка стенда

Команды выполняются последовательно. После завершения приложение остаётся
доступным; удаление инфраструктуры выполняется отдельно.

```powershell
.\scripts\selectel-deploy.ps1 -CreateResources
.\.tools\venv\Scripts\python.exe scripts/verify_selectel_fencing.py --empty-storage
.\.tools\venv\Scripts\python.exe scripts/controller.py --cloud selectel run initialize.yml -e allow_experimental_storage=true -e initialize_storage=true -e fencing_verified=true
.\.tools\venv\Scripts\python.exe scripts/controller.py --cloud selectel run activate.yml
.\.tools\venv\Scripts\python.exe scripts/controller.py --cloud selectel run verify.yml
.\scripts\tf-selectel.ps1 output -json lab
```

initialize.yml выполняется только один раз на новых пустых дисках,
после успешной проверки fencing. Флаги разрешают учебный эксперимент
DRBD dual-primary + GFS2; они не меняют ограничения поддержки этой схемы.

Адрес приложения содержится в lab.site_url. Для редактирования статей
администратор Django создаётся интерактивной командой createsuperuser;
общего пароля администратора нет. Доступ к admin на учебном HTTP-стенде
осуществляется через SSH-туннель.

## Проверка работающего стенда

```powershell
.\.tools\venv\Scripts\python.exe scripts/controller.py --cloud selectel run verify.yml
```

Проверяются общий том, репликация DRBD, динамические страницы, readiness
и статика через оба фронта. Инфраструктура остаётся развёрнутой.
Команды проверки отказоустойчивости приведены в [testing.md](testing.md).

## Удаление

```powershell
.\scripts\selectel-cleanup.ps1
```

Скрипт проверяет проект, регион и destroy-план собственного state,
удаляет ВМ, диски, IP, балансировщик и сеть, затем проверяет пустой state.
Проект, сервисные пользователи, исходники и локальные результаты сохраняются.

## Источники

- [Terraform в Selectel](https://docs.selectel.ru/terraform/providers/).
- [Облачный балансировщик](https://docs.selectel.ru/terraform/examples/cloud-load-balancers/create-load-balancer-and-server/).
- [Аутентификация](https://docs.selectel.ru/access-control/authentication-methods/).
