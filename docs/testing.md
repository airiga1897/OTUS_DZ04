# Проверка работоспособности и отказоустойчивости

Стенд создаётся по [инструкции Selectel](selectel.md).
Следующие команды проверяют существующую инфраструктуру и не удаляют её.
Команды выполняются из корня репозитория с доступом к локальным SSH-ключам
и параметрам стенда.

## Работа общего хранилища и приложения

Проверка работоспособности:

```powershell
.\.tools\venv\Scripts\python.exe scripts/controller.py --cloud selectel run verify.yml
```

verify.yml проверяет:

- GFS2 смонтирована на обоих backend в /srv/otus.
- Каждый backend записывает файл с fsync; оба файла читаются с обоих узлов.
- Обе реплики DRBD находятся в состоянии UpToDate.
- Через каждый Nginx доступны динамическая страница, readiness и статика
  с новым ключом кеша.

Проверка повторного применения конфигурации:

```powershell
.\.tools\venv\Scripts\python.exe scripts/controller.py --cloud selectel run site.yml -e allow_experimental_storage=true
.\.tools\venv\Scripts\python.exe scripts/controller.py --cloud selectel run verify.yml
```

Повтор site.yml подтверждает идемпотентность настройки:
changed=0, failed=0, unreachable=0 на всех пяти ВМ.

## Fencing

Проверка выполняется только на новом стенде до инициализации DRBD/GFS2:

```powershell
.\.tools\venv\Scripts\python.exe scripts/verify_selectel_fencing.py --empty-storage
```

Этот сценарий не запускается повторно на работающем общем хранилище.
До инициализации GFS2 backend1 выключает backend2 через агент fencing,
затем проверка повторяется в обратную сторону. Nova API независимо
подтверждает SHUTOFF и power_state=4. После каждой проверки выключенный
узел запускается и проверяется его доступность по доверенному SSH.
При неуспешной проверке хранилище не инициализируется.

## Отказ обслуживающих ВМ

```powershell
.\.tools\venv\Scripts\python.exe scripts/verify_selectel_failures.py
```

backend1, backend2, nginx2 и nginx1 выключаются по очереди.
При выключенном узле проверяются динамика, readiness и статика
через публичный адрес балансировщика. Каждый узел возвращается в работу
до следующего сценария; после восстановления повторяется verify.yml.

## Разделение сети backend

```powershell
.\.tools\venv\Scripts\python.exe scripts/verify_selectel_partition.py
```

На backend2 временно блокируется входящий и исходящий трафик к backend1.
Доступ к qdevice, API облака и SSH через фронт сохраняется.
До блокировки устанавливается автоматический откат правил.

Проверяется, что кластер выключает один backend через fencing,
а оставшийся обслуживает динамику, readiness и статику.
После восстановления связи и возврата узла повторяется проверка
обоих mount, состояния реплик и взаимного чтения файлов.

Этот сценарий проверяет конкретное разделение сети. Отказы БД, зоны,
облачного роутера и все возможные аварии хранилища не входят
в подтверждённые результаты.

Результаты приведены в [deployment-status.md](deployment-status.md).
