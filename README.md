# ContentForge (NODEX)

AI-платформа для планирования, генерации и мультиканальной публикации контента.

Демо: [kitchen.alexklyvibe.ru](https://kitchen.alexklyvibe.ru)

Продуктовое summary (ЦА, MVP, roadmap): [`readmeSummary.md`](readmeSummary.md) · полное ТЗ: [`TZTech.md`](TZTech.md)

## Возможности

- Brand Kit и несколько брендов в одном workspace
- AI-контент-план на месяц (праздники РФ, тренды)
- Календарь, редактор (посты / статьи / email), варианты A/B
- Очередь публикаций с автопостом
- Каналы: **Telegram**, **VK**, **Gmail** (SMTP); Instagram — OAuth + ручная публикация
- Автоподготовка слотов (опционально в настройках бренда)
- Аналитика по каналам

## Стек

| Слой | Технологии |
| --- | --- |
| Frontend | React 18, Vite 6, TypeScript, TanStack Query, React Router |
| Backend | Python, FastAPI, SQLAlchemy 2, Alembic, Pydantic |
| Data / queue | PostgreSQL 16, Redis 7, Celery (worker + beat) |
| AI | OpenAI Chat Completions (`gpt-4o-mini` по умолчанию) |

## Требования

- Docker + Docker Compose
- Node.js 20+ (для локального frontend вне контейнера)
- Ключ OpenAI (`OPENAI_API_KEY`)

## Быстрый старт

```bash
cp .env.example .env
# Заполни минимум: OPENAI_API_KEY, TOKEN_ENCRYPTION_KEY, JWT_SECRET
# Fernet: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

docker compose up -d --build
```

Сервисы:

| URL | Что |
| --- | --- |
| http://localhost:5173 | Frontend |
| http://localhost:8000 | API |
| http://localhost:8000/health | Healthcheck |
| http://localhost:8000/docs | OpenAPI (Swagger) |

Postgres в compose слушает хост **15432** (чтобы не конфликтовать с локальным Postgres на 5432).

### Frontend отдельно (hot reload)

```bash
docker compose up -d postgres redis api worker beat
cd frontend && npm i && npm run dev
```

Vite проксирует `/api` на `http://localhost:8000` (или `VITE_API_PROXY_TARGET`).

## Тесты

```bash
# Backend
docker compose exec api pytest

# Frontend
cd frontend && npm test
```

## Структура репозитория

```
backend/          FastAPI, Celery, миграции, адаптеры каналов
frontend/         React SPA
deploy/           nginx, prod env example
scripts/          деплой / утилиты VPS
ai/workflow/      research → design → planning артефакты
TZTech.md         техническое задание
readmeSummary.md  ЦА / сделано / план
```

## Переменные окружения

См. [`.env.example`](.env.example). Обязательные для локалки:

- `OPENAI_API_KEY`
- `TOKEN_ENCRYPTION_KEY` — Fernet для токенов каналов
- `JWT_SECRET`

Опционально: `OPENAI_MODEL`, `TELEGRAM_HTTPS_PROXY` (если `api.telegram.org` недоступен), Meta OAuth (`META_APP_ID` / `META_APP_SECRET`) для Instagram.

Prod-шаблон: [`deploy/env.production.example`](deploy/env.production.example).

## Production

Прод собирается через `docker-compose.prod.yml` + nginx (`deploy/nginx/`).  
Обновление на VPS: `scripts/update-vps.sh` (после `git pull`). Миграции Alembic при необходимости — вручную в api-контейнере (`alembic upgrade head`).

## Лицензия

Учебно-практический проект. Лицензия не задана — уточняй у автора репозитория перед коммерческим использованием.
