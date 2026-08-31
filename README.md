# ContentForge (NODEX)


<!-- MOCKUPS:START -->
![Mockup](Docs/mockups/mockup-20260831-190921.png)
<!-- MOCKUPS:END -->

**AI-платформа контент-маркетинга:** Brand Kit → план на месяц → черновики → очередь → автопост → аналитика — в одном рабочем месте.

Демо: **[kitchen.alexklyvibe.ru](https://kitchen.alexklyvibe.ru)**  
Краткое summary: [`readmeSummary.md`](readmeSummary.md)

## Демонстрация

Обзор интерфейса и основных сценариев — в [`Docs/demo/`](Docs/demo/).

**Видео:** [demo-overview.mp4](Docs/demo/videos/demo-overview.mp4) — переходы по экранам сервиса (вход → дашборд → календарь → план → каналы → очередь → аналитика → A/B → настройки → редактор).

**Скриншоты** ([`Docs/demo/screenshots/`](Docs/demo/screenshots/)):

| Файл | Экран |
| --- | --- |
| [01-login.png](Docs/demo/screenshots/01-login.png) | Вход и регистрация |
| [02-dashboard.png](Docs/demo/screenshots/02-dashboard.png) | Дашборд |
| [03-calendar-slot.png](Docs/demo/screenshots/03-calendar-slot.png) | Календарь, слот дня |
| [04-plan-existing.png](Docs/demo/screenshots/04-plan-existing.png) | Мастер плана |
| [05-channels.png](Docs/demo/screenshots/05-channels.png) | Каналы |
| [06-queue.png](Docs/demo/screenshots/06-queue.png) | Очередь |
| [07-analytics.png](Docs/demo/screenshots/07-analytics.png) | Аналитика |
| [08-ab.png](Docs/demo/screenshots/08-ab.png) | A/B |
| [09-settings.png](Docs/demo/screenshots/09-settings.png) | Настройки |
| [10-editor.png](Docs/demo/screenshots/10-editor.png) | Редактор |

---

## Зачем

ContentForge закрывает полный цикл контент-маркетинга: собрать голос бренда, спланировать месяц с учётом праздников и трендов, сгенерировать посты/статьи/письма, согласовать, поставить в расписание и опубликовать в каналы — без зоопарка из таблиц, ботов и отдельных ESP.

**Для кого:** SMM и контент-маркетологи МСБ, владельцы бизнеса без штатного SMM, агентства с несколькими брендами в одном workspace.

---

## Что реализовано

Статусы: **готово** · **частично** · **не в MVP**.

### Аутентификация и workspace

| Возможность | Статус | Как работает |
| --- | --- | --- |
| Регистрация / логин, JWT refresh | **готово** | Единое сообщение об ошибке, без user enumeration |
| Workspace при регистрации | **готово** | Owner по умолчанию |
| Роли Editor / Analyst / Viewer | **частично** | Модель в БД; invite в UI — в планах |
| Изоляция чужих брендов | **готово** | 404 на чужой `brand_id` |

### Brand Kit и онбординг

| Возможность | Статус | Как работает |
| --- | --- | --- |
| Ниша, ЦА, голос, стоп-слова, офферы, эталоны | **готово** | 5 шагов онбординга |
| Несколько брендов | **готово** | Переключатель в шапке, «Новый бренд» в настройках |
| Таймзона и locale контента | **готово** | RU/CIS select в настройках |
| Без Brand Kit — нет генерации плана | **готово** | Блокировка до заполнения kit |

### AI-план на месяц

| Возможность | Статус | Как работает |
| --- | --- | --- |
| Генерация плана по targets (post / article / email) | **готово** | Celery job, 202 + poll |
| Праздники РФ из справочника | **готово** | Seed + подмешивание в промпт |
| Тренды `active` | **частично** | Чтение в плане; UI добавления — нет (API есть) |
| Валидация JSON, без «полуплана» | **готово** | Невалидный ответ модели → failed |
| Статусы `generating` → `draft` → `approved` | **готово** | Мастер плана |
| Ручной CRUD слотов | **готово** | Добавление, правка, удаление |
| Предупреждение о коллизиях слотов | **частично** | Базовая логика; ±30 мин — не везде в UI |

### Контент и редактор

| Возможность | Статус | Как работает |
| --- | --- | --- |
| Типы `social_post`, `article`, `email` | **готово** | Три формата контента |
| Генерация с учётом Brand Kit и канала | **готово** | OpenAI + ограничения адаптера |
| Редактирование до публикации | **готово** | Сохранение черновиков |
| Варианты A/B | **готово** | Variant A/B в редакторе |
| Стоп-слова → блок schedule/publish | **готово** | Owner override + AuditLog |
| Rewrite выделенного фрагмента | **готово** | Не затирает остальной текст |
| Медиа к постам | **частично** | Upload API; UI в редакторе — в планах |
| Архивация контента | **готово** | Soft-delete (`archived`) |

### Календарь и расписание

| Возможность | Статус | Как работает |
| --- | --- | --- |
| Месячная сетка слотов | **готово** | Фильтр по каналу |
| Переход в редактор слота | **готово** | Deep link: `channel`, `date`, `autogen` |
| Schedule по умолчанию | **готово** | Дата слота + 12:00 (таймзона бренда) |

### Публикация и очередь

| Возможность | Статус | Как работает |
| --- | --- | --- |
| Статусы Publication (scheduled → published / failed / …) | **готово** | Полный lifecycle |
| Воркер due-публикаций | **готово** | Beat каждую минуту, атомарный захват |
| Retry с backoff, idempotency | **готово** | Без дублей на площадке |
| Cancel / retry / published_manual | **готово** | Страница очереди |
| Deep link «Контент» → редактор | **готово** | `piece_id` в очереди |

### Каналы

| Канал | Статус | Как работает |
| --- | --- | --- |
| **Telegram** | **готово** | Bot + channel, текст + фото |
| **VK** | **готово** | `wall.post`, текст |
| **Gmail** | **готово** | SMTP App Password, список получателей, приветствие по имени |
| **Instagram** | **частично** | OAuth UI; publish = copy в буфер |
| **WordPress** | **не в MVP** | Адаптер в коде, autopost вырезан |

Секреты каналов — Fernet в БД, не отдаются в GET. Revoke отменяет будущие публикации.

### Аналитика

| Возможность | Статус | Как работает |
| --- | --- | --- |
| Периодический sync метрик | **готово** | Celery каждые 6 ч |
| Сводка по каналам за период | **готово** | Дашборд аналитики |
| Честный `unavailable` вместо нулей | **готово** | Нет фейковых метрик |
| Экспорт CSV | **не в MVP** | В планах |

### A/B эксперименты

| Возможность | Статус | Как работает |
| --- | --- | --- |
| Два варианта, окно, primary metric | **готово** | Страница A/B |
| Sequential на Telegram | **готово** | Две публикации по очереди |
| Split-audience / Gmail / WP title | **не в MVP** | 409 unsupported |

### Автопилот

Опциональная **автоподготовка слотов** (по умолчанию выключена):

- Настройки бренда: toggle, lead hours, час слота
- Hourly Celery: approved-план → generate → schedule Publication
- Канал не заливается сырыми черновиками без явного включения

### Инфраструктура

| Компонент | Статус |
| --- | --- |
| FastAPI + React + PostgreSQL + Celery + Redis | **готово** |
| Alembic миграции | **готово** | В т.ч. автоматом в `deploy-vps.sh` |
| docker-compose local + prod | **готово** |
| nginx TLS на VPS | **готово** |
| AuditLog (базовый) | **готово** |

### Экраны

| Экран | Статус |
| --- | --- |
| Вход / регистрация, онбординг, дашборд | **готово** |
| План, календарь, редактор | **готово** |
| Каналы, очередь, аналитика, A/B, настройки | **готово** |

---

## Пользовательский поток

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

### Ближайшее — команда и каналы

- **Invite и роли** — Analyst / Viewer, совместная работа в workspace
- **Instagram Graph publish** — после App Review; сейчас только OAuth + manual copy
- **Gmail OAuth / Gmail API** — вместо хранения App Password; split-list для A/B
- **VK** — фото к посту, углублённые метрики
- **Кастомные праздники бренда** — UI поверх существующего API
- **Media в редакторе** — UI к уже готовому upload API
- **CSV** — экспорт аналитики, импорт получателей email (с hard cap)
- **Health-check токенов** — cron + refresh где платформа позволяет

### Дальше — автоматизация и глубина

- **Провайдер трендов** — внешний API вместо только ручного ввода
- **Расширенный Instagram** — карусели, осторожный Reels (если API и бюджет)
- **WordPress autopost** — publish/future, views через Jetpack/плагин
- **Opens/clicks email** — UTM/пиксель opt-in, без выдачи за «как Mailchimp»
- **Мультиязычный UI** — EN поверх текущего RU
- **Drag-and-drop календаря**, drill-down аналитики до публикации
- **Soft quota токенов** — учёт usage в Job, лимиты workspace

### Осознанно вне scope

- **Mailchimp** — гео/KYC из РФ (заменён на Gmail)
- **Публикация на чужие аккаунты**, скрытый сбор баз — запрещено политикой продукта
- **Юркомплаенс erid** — напоминание в UI, не автоматическая маркировка

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
frontend/         React SPA
deploy/           nginx, prod env
scripts/          деплой VPS, merge secrets, demo capture
Docs/demo/        скриншоты и видео
ai/workflow/      research → design → planning артефакты
readmeSummary.md  краткое продуктовое summary
```

## Лицензия

Учебно-практический проект. Лицензия не задана — уточняй у автора перед коммерческим использованием.
