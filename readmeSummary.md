# ContentForge — продуктовое summary

Кратко: для кого, что сделано, что в плане.  
Обычный GitHub README (установка, стек, структура): [`README.md`](README.md).

---

## Для кого

| Аудитория | Зачем |
| --- | --- |
| **Контент-маркетолог / SMM МСБ** | 1–3 бренда, мало бюджета: план → черновики → очередь без зоопарка таблиц и ботов |
| **Владелец бизнеса без штатного SMM** | Brand Kit + автоподготовка слотов: меньше ручной рутины до публикации |
| **Digital-агентство** | Несколько клиентских брендов в одном workspace, изоляция по бренду |

Язык UI — русский. Контекст: учебно-практический fullstack-проект (см. `TZTech.md`).

**Prod:** https://kitchen.alexklyvibe.ru

---

## Что сделано (MVP)

### Рабочее место
- Регистрация / логин (JWT), workspace
- **Несколько брендов:** онбординг Brand Kit, переключатель в шапке, «Новый бренд» в настройках
- Дашборд: KPI, ближайшие публикации, статусы AI-джобов

### Контент-цикл
1. **План** — AI-генерация месячного плана (каналы, цели, праздники РФ, тренды), approve, CRUD слотов
2. **Календарь** — сетка месяца → глубокая ссылка в редактор (канал, дата, autogen)
3. **Редактор** — social / article / email; варианты A/B; generate / rewrite; архивация; постановка в очередь (дата слота + 12:00 по умолчанию)
4. **Очередь** — scheduled / published / failed; cancel, retry, mark manual; ссылка обратно в контент

### Каналы (автопост)
| Канал | Статус |
| --- | --- |
| **Telegram** | Bot + channel, текст и фото |
| **VK** | `wall.post`, текст |
| **Gmail** | SMTP App Password, список получателей, приветствие по имени |
| **Instagram** | OAuth в UI; публикация = ручной copy (не autopost) |
| **WordPress** | Адаптер в бэкенде; UI-подключения нет, autopost вырезан |

### Автопилот
- В настройках бренда: **автоподготовка слотов** (lead hours, час слота)
- Hourly Celery: approved-план → generate → schedule Publication
- Отдельный beat: публикация due-записей каждую минуту; analytics sync раз в 6 ч

### Прочее
- A/B: sequential на Telegram
- Аналитика: сводка по каналам
- Таймзона (RU/CIS select), locale контента
- Health, docker-compose prod, nginx TLS на VPS

---

## Что в плане

### Ближайшее / фаза 2
- Инвайты в workspace (роли editor / analyst / viewer)
- Instagram App Review + реальный Graph publish (сейчас manual)
- Gmail OAuth / API вместо чистого SMTP
- VK: фото к посту
- UI для media upload в редакторе (API уже есть)
- UI добавления holidays / trends (API есть)
- Alembic в `update-vps.sh` (сейчас миграции вручную на VPS)

### Дальше / фаза 3
- CSV export аналитики, CSV import получателей
- Расширение A/B (gmail split-list и др.)
- Reels / расширенный Instagram
- WordPress autopost (если вернём в scope)

### Вне scope (сейчас)
- Mailchimp (гео/KYC из РФ)
- Полноценный team-CRM / биллинг

Детали требований — в `TZTech.md`; артефакты дизайн/план — в `ai/workflow/`.
