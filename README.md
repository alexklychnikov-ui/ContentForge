# ContentForge (NODEX)

**AI-платформа контент-маркетинга:** Brand Kit → план на месяц → черновики → очередь → автопост → аналитика — в одном рабочем месте.

Демо: **[kitchen.alexklyvibe.ru](https://kitchen.alexklyvibe.ru)**  
Полное ТЗ: [`TZTech.md`](TZTech.md) · краткое summary: [`readmeSummary.md`](readmeSummary.md)

---

## Зачем

ContentForge закрывает цикл, описанный в ТЗ (§1.2): собрать голос бренда, спланировать месяц с учётом праздников и трендов, сгенерировать посты/статьи/письма, согласовать, поставить в расписание и опубликовать в каналы — без зоопарка из таблиц, ботов и отдельных ESP.

**Для кого:** SMM и контент-маркетологи МСБ, владельцы бизнеса без штатного SMM, агентства с несколькими брендами в одном workspace.

---

## Что реализовано из ТЗ

Ниже — соответствие ключевым блокам [`TZTech.md`](TZTech.md). Статусы: **готово** · **частично** · **не в MVP**.

### Аутентификация и workspace (UC-01, FR-AUTH)

| Требование | Статус | Реализация |
| --- | --- | --- |
| Регистрация / логин, JWT refresh | **готово** | `SCR-AUTH`, без user enumeration (AC-02) |
| Workspace при регистрации | **готово** | Owner по умолчанию |
| Роли Editor / Analyst / Viewer | **частично** | Модель в БД; invite в UI — фаза 2 (SCR-SET) |
| Изоляция чужих брендов | **готово** | 404 на чужой `brand_id` (AC-03) |

### Brand Kit и онбординг (UC-02, SCR-ONB)

| Требование | Статус | Реализация |
| --- | --- | --- |
| Ниша, ЦА, голос, стоп-слова, офферы, эталоны | **готово** | 5 шагов онбординга |
| Несколько брендов | **готово** | Переключатель в шапке, «Новый бренд» в настройках |
| Таймзона и locale контента | **готово** | RU/CIS select в настройках |
| Без Brand Kit — нет generate plan | **готово** | AC-04 |

### AI-план на месяц (UC-03, FR-PLN, SCR-PLAN)

| Требование | Статус | Реализация |
| --- | --- | --- |
| Генерация плана по targets (post / article / email) | **готово** | Celery job, 202 + poll |
| Праздники РФ из справочника | **готово** | Seed + подмешивание в промпт (FR-PLN-03) |
| Тренды `active` | **частично** | Чтение в плане; UI добавления — нет (API есть) |
| Валидация JSON, без «полуплана» | **готово** | AC-06 |
| Статусы `generating` → `draft` → `approved` | **готово** | FR-PLN-07 |
| Ручной CRUD слотов | **готово** | FR-PLN-06 |
| Предупреждение о коллизиях слотов | **частично** | Базовая логика; ±30 мин — не везде в UI |

### Контент и редактор (UC-04, FR-CNT, SCR-EDT)

| Требование | Статус | Реализация |
| --- | --- | --- |
| Типы `social_post`, `article`, `email` | **готово** | FR-CNT-01 |
| Генерация с учётом Brand Kit и канала | **готово** | FR-CNT-02 |
| Редактирование до публикации | **готово** | FR-CNT-06 |
| Варианты A/B | **готово** | Variant A/B в редакторе |
| Стоп-слова → блок schedule/publish | **готово** | Owner override + AuditLog (AC-09) |
| Rewrite выделенного фрагмента | **готово** | AC-10 |
| Медиа к постам | **частично** | Upload API; UI в редакторе — фаза 2 |
| Архивация контента | **готово** | Soft-delete (`archived`) |

### Календарь и расписание (UC-05, SCR-CAL)

| Требование | Статус | Реализация |
| --- | --- | --- |
| Месячная сетка слотов | **готово** | Фильтр по каналу |
| Переход в редактор слота | **готово** | Deep link: `channel`, `date`, `autogen` |
| Schedule по умолчанию | **готово** | Дата слота + 12:00 (таймзона бренда) |

### Публикация и очередь (UC-06, UC-07, FR-PUB, SCR-QUE)

| Требование | Статус | Реализация |
| --- | --- | --- |
| Статусы Publication (scheduled → published / failed / …) | **готово** | FR-PUB-02 |
| Воркер due-публикаций | **готово** | Beat каждую минуту, атомарный захват |
| Retry с backoff, idempotency | **готово** | AC-12, AC-13 |
| Cancel / retry / published_manual | **готово** | SCR-QUE |
| Deep link «Контент» → редактор | **готово** | `piece_id` в очереди |

### Каналы (FR-CHN, SCR-CHN)

| Канал | По ТЗ (фаза 1) | Факт |
| --- | --- | --- |
| **Telegram** | автопост | **готово** — текст + фото, AC-11 |
| **VK** | manual в MVP | **готово** — `wall.post`, текст (опережает ТЗ) |
| **Gmail** | SMTP + recipients | **готово** — App Password, cap, приветствие по имени |
| **Instagram** | manual + «нужен review» | **частично** — OAuth UI; publish = copy в буфер |
| **WordPress** | автопост в MVP | **не в MVP** — адаптер в коде, autopost вырезан |

Секреты каналов — Fernet в БД, не в GET (AC-18). Revoke отменяет будущие публикации (AC-19).

### Аналитика (UC-08, FR-ANL, SCR-ANL)

| Требование | Статус | Реализация |
| --- | --- | --- |
| Периодический sync метрик | **готово** | Celery каждые 6 ч |
| Сводка по каналам за период | **готово** | FR-ANL-04 |
| Честный `unavailable` вместо нулей | **готово** | FR-ANL-05, AC-16 |
| Экспорт CSV | **не в MVP** | Фаза 2 |

### A/B эксперименты (UC-09, FR-AB, SCR-AB)

| Требование | Статус | Реализация |
| --- | --- | --- |
| Два варианта, окно, primary metric | **готово** | FR-AB-01/02 |
| Sequential на Telegram | **готово** | FR-AB-03, AC-17 |
| Split-audience / Gmail / WP title | **не в MVP** | 409 unsupported |

### Автопилот (расширение сверх базового MVP)

В ТЗ auto-schedule всех слотов после approve — **фаза 3, opt-in** (§14.5, §17.3). Реализовано как **автоподготовка слотов**:

- Настройки бренда: toggle, lead hours, час слота
- Hourly Celery: approved-план → generate → schedule Publication
- По умолчанию **выключено** — канал не заливается сырыми черновиками

### Инфраструктура (§10, §17.1)

| Компонент | Статус |
| --- | --- |
| FastAPI + React + PostgreSQL + Celery + Redis | **готово** |
| Alembic миграции | **готово** | В т.ч. автоматом в `deploy-vps.sh` |
| docker-compose local + prod | **готово** |
| nginx TLS на VPS | **готово** |
| AuditLog (базовый) | **готово** |

### Экраны React (§7)

| Экран | Статус |
| --- | --- |
| SCR-AUTH, SCR-ONB, SCR-DASH | **готово** |
| SCR-PLAN, SCR-CAL, SCR-EDT | **готово** |
| SCR-CHN, SCR-QUE, SCR-ANL, SCR-AB, SCR-SET | **готово** |

---

## Пользовательский поток (как в проде)

```
Онбординг Brand Kit → Подключить каналы (TG/VK/Gmail)
        ↓
Сгенерировать план → Approve → Календарь
        ↓
Открыть слот → Редактор (generate / правки / A/B) → Поставить в очередь
        ↓
Очередь → автопост в срок → Аналитика

Опционально: Автоподготовка в настройках — слоты готовятся и ставятся в очередь без ручного клика.
```

---

## Перспективы расширения

Ориентир — фазы 2–3 из [`TZTech.md`](TZTech.md) §17 и открытые вопросы §19.

### Фаза 2 — команда и каналы

- **Invite и роли** — Analyst / Viewer, совместная работа в workspace (SCR-SET, FR ролей)
- **Instagram Graph publish** — после App Review; сейчас только OAuth + manual copy
- **Gmail OAuth / Gmail API** — вместо хранения App Password; `gmail_split_list` для A/B
- **VK** — фото к посту, углублённые метрики
- **Кастомные праздники бренда** — UI поверх существующего API
- **Media в редакторе** — UI к уже готовому upload API
- **CSV** — экспорт аналитики, импорт получателей email (с hard cap)
- **Health-check токенов** — cron + refresh где платформа позволяет

### Фаза 3 — автоматизация и глубина

- **Провайдер трендов** — внешний API вместо только ручного ввода (FR-PLN-04, Q-RES-01)
- **Расширенный Instagram** — карусели, осторожный Reels (если API и бюджет)
- **WordPress autopost** — вернуть в scope: publish/future, views через Jetpack/плагин
- **Opens/clicks email** — UTM/пиксель opt-in, без выдачи за «как Mailchimp»
- **Мультиязычный UI** — EN поверх текущего RU
- **Drag-and-drop календаря**, drill-down аналитики до публикации
- **Soft quota токенов** — учёт usage в Job, лимиты workspace (§14.4)

### Осознанно вне scope

- **Mailchimp** — гео/KYC из РФ (заменён на Gmail в ТЗ v1.1)
- **Публикация на чужие аккаунты**, скрытый сбор баз — запрещено политикой продукта (§4.4, R10)
- **Юркомплаенс erid** — напоминание в UI, не автоматическая маркировка (§15.4)

---

## Стек

| Слой | Технологии |
| --- | --- |
| Frontend | React 18, Vite 6, TypeScript, TanStack Query, React Router |
| Backend | Python, FastAPI, SQLAlchemy 2, Alembic, Pydantic |
| Data / queue | PostgreSQL 16, Redis 7, Celery (worker + beat) |
| AI | OpenAI Chat Completions (`OPENAI_MODEL`; пример: `gpt-5.4-mini-2026-03-17`, fallback в коде: `gpt-4o-mini`) |

---

## Быстрый старт

```bash
cp .env.example .env
# Минимум: OPENAI_API_KEY, TOKEN_ENCRYPTION_KEY, JWT_SECRET
# Fernet: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

docker compose up -d --build
```

| URL | Сервис |
| --- | --- |
| http://localhost:5173 | Frontend |
| http://localhost:8000 | API |
| http://localhost:8000/docs | OpenAPI |
| localhost:**15432** | Postgres (хост-порт, чтобы не конфликтовать с локальным 5432) |

Frontend с hot reload:

```bash
docker compose up -d postgres redis api worker beat
cd frontend && npm i && npm run dev
```

## Тесты

```bash
docker compose exec api pytest
cd frontend && npm test
```

## Переменные окружения

См. [`.env.example`](.env.example):

- `OPENAI_API_KEY`, `TOKEN_ENCRYPTION_KEY`, `JWT_SECRET` — обязательны
- `OPENAI_MODEL` — модель для API/worker. В корневом `.env` часто `OPENAI_MODEL_TEXT=…` — **бэкенд читает только `OPENAI_MODEL`**; для docker compose продублируй ключ (на VPS маппит `scripts/patch-vps-secrets.py`)
- `TELEGRAM_HTTPS_PROXY`, `META_APP_ID` / `META_APP_SECRET` — опционально

Prod: [`deploy/env.production.example`](deploy/env.production.example).

## Production

`docker-compose.prod.yml` + nginx (`deploy/nginx/`).

```bash
# на VPS
bash scripts/update-vps.sh   # git pull → build → alembic upgrade head → up -d
```

## Структура репозитория

```
backend/          FastAPI, Celery, Alembic, адаптеры каналов
frontend/         React SPA (экраны из §7 ТЗ)
deploy/           nginx, prod env
scripts/          деплой VPS, merge secrets
ai/workflow/      research → design → planning
TZTech.md         полное ТЗ v1.1
readmeSummary.md  краткое продуктовое summary
```

## Лицензия

Учебно-практический проект. Лицензия не задана — уточняй у автора перед коммерческим использованием.
