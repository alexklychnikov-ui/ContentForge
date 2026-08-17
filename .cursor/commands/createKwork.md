# /createKwork [ключевая фраза]

Сгенерируй обложку кворка (Kwork) по ключевой фразе пользователя.

## Вход

После команды идёт **ключевая фраза**, например:
`/createKwork разработка бота под ключ`

Если фразы нет — спроси одну строку и не генерируй.

## Бренд и стиль (LOCKED — не меняй без явного запроса)

Читай канон: `ai/workflow/research/kwork-cover-decisions.json`, `ai/workflow/research/kwork-cover-strategy.json`, правило `.cursor/rules/nodex-kwork-covers.mdc`.

- **Бренд:** `NODEX`
- **Wordmark на обложке:** маленький `NODEX` CAPS в углу (top-left); **заливка = градиент `#2F6BFF` → `#00E5A8`**, лёгкий glow; не белый solid
- **Tagline (не обязательно на картинке):** «NODEX — связки и автоматизация под задачу»
- **Scope:** один style kit на **все** ниши (меняются только claim / chips / hero-сцена)

### Style kit

| Token | Value |
|--------|--------|
| BG | `#0B1220` → `#152238` + лёгкая tech-текстура (grid/particles), не пустой «чёрный лист» |
| Accent | `#2F6BFF` |
| Highlight | `#00E5A8` |
| Text | white bold geometric sans, CAPS на claim |
| Wordmark | `NODEX` CAPS: gradient fill `#2F6BFF`→`#00E5A8` + soft glow (не solid white) |
| Layout | **плотная** сцена: claim слева/сверху, справа multi-layer hero (устройство + поток + иконки), заполнение кадра ≥80% |
| Density | HIGH — мало пустоты; слои, глубина, glow-trails, стрелки потока |
| Hero | 1 главный фокус + 2–4 поддерживающих элемента (экран/чат/таблица + иконки результата) |
| Chips | 2–4 коротких преимущества (или icon-bullets) |
| Drive | динамика: перспектива, motion glow, overlapping layers — не плоский «текст слева / шар справа» |
| Avoid | огромный negative space; один одинокий orb/молекула на пустом фоне; лицо продавца; хаос мелкого UI; нечитаемый текст |

### Референс «нравится» (энергия/плотность)

Ориентир по плотности: обложки с laptop+phone+flow icons+feature list+HUD accents (много слоёв, мало воздуха).  
Сохраняем NODEX-палитру; **не** копируем чужой маскот/лого маркетплейсов 1:1.

### Размер

- **Только одно** изображение: `1320x880` (3:2) — сразу финальный upload-size
- Не сохранять master `1536x1024` и не делать второй файл
- Если API не принимает `1320x880` — запросить ближайший 3:2, ресайзнуть один раз в `1320x880`, сохранить только его
- Min платформы: `660x440`, jpg/png ≤4MB

## Алгоритм

1. **Ключ** = фраза после `/createKwork` (trim).
2. Опционально: открой `https://kwork.ru/search?query=<encoded>` (Browser MCP), сними TOP 6–12 обложек — паттерны ниши + gaps. Не копируй топ-1 1:1.
3. При необходимости сверь нюансы упаковки кворка через LightRAG (`user-lightrag`).
4. Собери **финальный image prompt**:
   - **Первая строка ОБЯЗАТЕЛЬНО:** `[ключевая фраза]`
   - NODEX palette + **dense energetic composition** (см. style kit)
   - claim CAPS RU, chips, multi-layer hero под нишу
5. Выведи промпт в чат **отдельным fenced-блоком** ` ```text `.
6. Сохрани промпт в `Docs/prompt-<slug>.txt`.
7. Сгенерируй через ProxyAPI (`.env`: `PROXY_API_KEY`, `PROXY_BASE_URL`, `IMAGE_MODEL`), `/images/generations`, `quality=high`, `size=1320x880` (если API отклонит — ближайший 3:2 + один ресайз), `n=1`.
8. Сохрани в `Docs/` **один** файл: `nodex-<slug>-<timestamp>-1320x880.png` (без отдельного master).
9. Кратко: путь + чем плотнее/живее vs пустой минимализм.

## Шаблон промпта (структура)

```text
[ключевая фраза]
KWORK COVER marketplace thumbnail, aspect 3:2, size 1320x880, readable at 414x276.
Brand locked NODEX: dark navy #0B1220→#152238 with subtle tech grid/particles, accent #2F6BFF, mint #00E5A8, white bold geometric sans.
Small wordmark top-left: NODEX in CAPS with brand gradient fill #2F6BFF→#00E5A8 and soft glow — NOT solid white.
DENSE energetic composition — fill >=80% of frame, minimal empty void. Layered depth: foreground devices + mid glow trails + background HUD/grid.
Left: bold CAPS RU claim + 2-4 mint chips or icon bullets.
Right/center-right: multi-element hero scene for the offer (e.g. screen/table + chat/phone + flow arrows + 2-3 result icons). One clear focal point, supporting props around it.
Motion/drive: soft light streaks, overlapping layers, slight 3D perspective — NOT flat text-left / lonely orb-right.
Main on-image CAPS RU (sharp glyphs): «<CLAIM>».
Benefit chips: <chips>.
Hero scene: <конкретная плотная сцена под нишу>.
Avoid: large empty navy fields, single floating molecule alone, stock face, marketplace logo spam, tiny unreadable UI walls.
Constraints: readable in 2-3s at thumbnail size, high contrast, max 2 type roles.
Single polished dynamic Kwork cover.
```

## Запреты

- Не возвращайся к «пустому минимализму» (много воздуха + один объект).
- Не меняй бренд/палитру без запроса.
- Не пиши секреты из `.env` в чат.
- Не пропускай первую строку `[ключевая фраза]`.
- Не клади результат вне `Docs/`.
