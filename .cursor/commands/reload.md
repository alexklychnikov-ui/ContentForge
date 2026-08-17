# /reload

Перезапуск локального ContentForge API. **cwd пользователя игнорировать.** Всегда корень: `C:\Python\Projects\AIPlatform4ContentMarketing`.

## Не делать

- Не опираться на cwd и не вызывать `.\scripts\restart-api.ps1`
- Не убивать чужой python (только uvicorn этого репо — через скрипт)
- Не поднимать второй uvicorn, если API уже актуальный

## До рестарта

1. GET `http://127.0.0.1:8000/health`
2. GET `http://127.0.0.1:8000/openapi.json` — `info.title` и paths

**Пропуск рестарта:** health **200** И title **ContentForge 0.7+** (не stale CF-1).
**Рестарт обязателен:** health не 200 **или** stale CF-1 (в OpenAPI по сути только `/health`, title не ContentForge 0.7+).

## Рестарт

Только абсолютный `-File`. Не реализуй uvicorn вручную.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Python\Projects\AIPlatform4ContentMarketing\scripts\restart-api.ps1
```

## После

Снова GET `http://127.0.0.1:8000/health`. Короткий отчёт **на русском**: 200 или текст ошибки. Не коммить.
