# Scoring API

HTTP-сервис скоринга. Принимает POST-запросы на `/method/` и возвращает результат вызова одного из двух методов: `online_score` или `clients_interests`.

## Требования

- Python 3.12+
- [uv](https://github.com/astral-sh/uv)
- Redis 7+ (для боевого запуска)
- Docker / Docker Compose (опционально)

## Установка

```bash
make install
```

## Make-команды

### Локальная разработка

| Команда | Описание |
|---|---|
| `make install` | Установить зависимости (`uv sync`) |
| `make lint` | Запустить линтер (`ruff`) |
| `make test` | Запустить тесты локально (Redis не нужен) |
| `make run` | Запустить сервер на порту 8080 (нужен Redis на localhost) |
| `make run PORT=9090` | Запустить сервер на произвольном порту |

### Docker (одиночный контейнер)

| Команда | Описание |
|---|---|
| `make docker-build` | Собрать образ `scoring-api-run` (stage `run`) |
| `make docker-build MODE=test` | Собрать образ `scoring-api-test` (stage `test`) |
| `make docker-run` | Запустить API в фоне на порту 8080 (без Redis) |
| `make docker-test` | Запустить тесты внутри Docker |

### Docker Compose (API + Redis)

| Команда | Описание |
|---|---|
| `make compose-up` | Поднять API + Redis, собрать образы |
| `make compose-down` | Остановить все сервисы |

## Запуск

### Локально (нужен Redis)

```bash
make run
# или явно:
uv run python api.py --port 8080 --log app.log
# с внешним Redis:
uv run python api.py --port 8080 --redis-host 10.0.0.1 --redis-port 6379
```

### Docker Compose (рекомендуется)

```bash
make compose-up    # поднять API + Redis
make compose-down  # остановить
```

### Только тесты в Docker

```bash
make docker-build MODE=test
make docker-test
```

## Примеры запросов (PowerShell)

### online_score

```powershell
Invoke-WebRequest -UseBasicParsing -Method POST -Uri "http://127.0.0.1:8080/method/" `
  -ContentType "application/json" `
  -Body '{"account": "horns&hoofs", "login": "h&f", "method": "online_score", "token": "55cc9ce545bcd144300fe9efc28e65d415b923ebb6be1e19d2750a2c03e80dd209a27954dca045e5bb12418e7d89b6d718a9e35af34e14e1d5bcd5a08f21fc95", "arguments": {"phone": "79175002040", "email": "stupnikov@otus.ru", "first_name": "Стансилав", "last_name": "Ступников", "birthday": "01.01.1990", "gender": 1}}' |
  Select-Object -ExpandProperty Content
```

Ответ: `{"response": {"score": 5.0}, "code": 200}`

### clients_interests

```powershell
Invoke-WebRequest -UseBasicParsing -Method POST -Uri "http://127.0.0.1:8080/method/" `
  -ContentType "application/json" `
  -Body '{"account": "horns&hoofs", "login": "h&f", "method": "clients_interests", "token": "55cc9ce545bcd144300fe9efc28e65d415b923ebb6be1e19d2750a2c03e80dd209a27954dca045e5bb12418e7d89b6d718a9e35af34e14e1d5bcd5a08f21fc95", "arguments": {"client_ids": [1, 2, 3], "date": "20.07.2017"}}' |
  Select-Object -ExpandProperty Content
```

Ответ: `{"response": {"1": [...], "2": [...], "3": [...]}, "code": 200}`

### admin (score всегда 42)

```powershell
$adminToken = -join ([System.Security.Cryptography.SHA512]::Create().ComputeHash(
  [System.Text.Encoding]::UTF8.GetBytes(([DateTime]::UtcNow.ToString("yyyyMMddHH")) + "42")
) | ForEach-Object { $_.ToString("x2") })

Invoke-WebRequest -UseBasicParsing -Method POST -Uri "http://127.0.0.1:8080/method/" `
  -ContentType "application/json" `
  -Body "{`"account`": `"horns&hoofs`", `"login`": `"admin`", `"method`": `"online_score`", `"token`": `"$adminToken`", `"arguments`": {`"phone`": `"79175002040`", `"email`": `"stupnikov@otus.ru`"}}" |
  Select-Object -ExpandProperty Content
```

Ответ: `{"response": {"score": 42}, "code": 200}`

> **Примечание:** токен admin зависит от текущего часа. При запуске через Docker (`make compose-up`) используйте `[DateTime]::UtcNow` (UTC). При локальном запуске (`make run`) — `Get-Date -Format "yyyyMMddHH"` (локальное время).

## Архитектура

| Файл | Назначение |
|---|---|
| `api.py` | HTTP-сервер, дескрипторы полей, валидация, роутинг методов |
| `scoring.py` | Логика подсчёта скора и получения интересов |
| `store.py` | `RedisStore` — Redis-клиент с retry и timeout |
| `test.py` | Unit и функциональные тесты с `FakeStore` |
| `Dockerfile` | Многостадийная сборка: `base` → `run` / `test` |
| `docker-compose.yml` | Оркестрация API + Redis |
