# Scoring API

HTTP-сервис скоринга. Принимает POST-запросы на `/method/` и возвращает результат вызова одного из двух методов: `online_score` или `clients_interests`.

## Требования

- Python 3.12+
- [uv](https://github.com/astral-sh/uv)
- Docker (опционально)

## Установка

```bash
make install
```

## Make-команды

| Команда | Описание |
|---|---|
| `make install` | Установить зависимости (`uv sync`) |
| `make lint` | Запустить линтер (`ruff`) |
| `make test` | Запустить тесты (`pytest`) |
| `make run` | Запустить сервер локально на порту 8080 |
| `make run PORT=9090` | Запустить сервер на произвольном порту |
| `make docker-build` | Собрать Docker-образ `scoring-api-run` (stage `run`) |
| `make docker-build MODE=test` | Собрать Docker-образ `scoring-api-test` (stage `test`) |
| `make docker-run` | Запустить сервер в Docker (фоновый режим, порт 8080) |
| `make docker-test` | Запустить тесты внутри Docker |

## Запуск

### Локально

```bash
make run
# или с указанием порта и лог-файла:
uv run python api.py --port 8080 --log app.log
```

### Docker

```bash
make docker-build          # собрать образ
make docker-run            # запустить в фоне
make docker-build MODE=test && make docker-test  # запустить тесты
```

## Примеры запросов

### online_score

```bash
curl -X POST http://127.0.0.1:8080/method/ \
  -H "Content-Type: application/json" \
  -d '{
    "account": "horns&hoofs",
    "login": "h&f",
    "method": "online_score",
    "token": "55cc9ce545bcd144300fe9efc28e65d415b923ebb6be1e19d2750a2c03e80dd209a27954dca045e5bb12418e7d89b6d718a9e35af34e14e1d5bcd5a08f21fc95",
    "arguments": {
      "phone": "79175002040",
      "email": "stupnikov@otus.ru",
      "first_name": "Стансилав",
      "last_name": "Ступников",
      "birthday": "01.01.1990",
      "gender": 1
    }
  }'
```

Ответ: `{"response": {"score": 5.0}, "code": 200}`

### clients_interests

```bash
curl -X POST http://127.0.0.1:8080/method/ \
  -H "Content-Type: application/json" \
  -d '{
    "account": "horns&hoofs",
    "login": "h&f",
    "method": "clients_interests",
    "token": "55cc9ce545bcd144300fe9efc28e65d415b923ebb6be1e19d2750a2c03e80dd209a27954dca045e5bb12418e7d89b6d718a9e35af34e14e1d5bcd5a08f21fc95",
    "arguments": {
      "client_ids": [1, 2, 3, 4],
      "date": "20.07.2017"
    }
  }'
```

Ответ: `{"response": {"1": [...], "2": [...], ...}, "code": 200}`

### PowerShell (admin-запрос)

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

> **Примечание:** при запросе от `admin` всегда возвращается `score: 42`.
> Токен для admin зависит от текущего часа (UTC). При локальном запуске (`make run`) используйте `Get-Date -Format "yyyyMMddHH"` вместо `[DateTime]::UtcNow`.
