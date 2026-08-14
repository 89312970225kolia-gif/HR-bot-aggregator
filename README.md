# HR Screening Bot

Самостоятельный Telegram-бот для первичного сбора и структурирования откликов.
Python-приложение заменяет прежние Make/n8n workflow и не зависит от них во время
работы. AI анализирует только профессиональные материалы; решение всегда принимает HR.

## Возможности

- `/start` и `/restart` с восстановлением состояния после перезапуска;
- приём PDF и DOCX до настраиваемого лимита;
- извлечение PDF через `pypdf`, DOCX через `python-docx`, включая таблицы;
- строгий JSON-анализ YandexGPT с Pydantic-валидацией;
- mock AI без расхода токенов;
- карточка кандидата HR с кнопками «Одобрить» и «Отклонить»;
- авторизация callback по `HR_USER_ID` и защита от повторного решения;
- Google Sheets upsert по названиям колонок, без зависимости от их порядка;
- SQLite для локального polling и YDB для облачного webhook-режима;
- постоянная работа через Yandex Cloud Functions без включённого компьютера.

## Архитектура

```text
Telegram -> aiogram handlers -> SQLite / YDB
                              -> PDF/DOCX parser
                              -> YandexGPT -> validated AIResult
                              -> Google Sheets
                              -> HR card -> human approve/reject
                              -> candidate notification
```

Основные каталоги:

- `app/bot/handlers` — Telegram-команды, документы, текст и HR callback;
- `app/db` — SQLite/YDB schema, модели и атомарные repositories;
- `app/services` — resume parser, YandexGPT, Sheets и HR-уведомления;
- `app/schemas` — Pydantic-контракты;
- `app/vacancies` — конфигурация вакансии вне handlers;
- `scripts` — инициализация и повторная синхронизация;
- `tests` — unit/integration tests без реальных секретов.

## Поток кандидата и state machine

```text
/start -> waiting_resume
resume -> waiting_cover_letter
cover letter -> analysis_in_progress
AI success -> waiting_hr_decision
HR approve -> approved
HR reject -> rejected
AI/parse failure -> analysis_failed
```

Критичные переходы выполняются атомарно в выбранном хранилище. Поэтому два одинаковых
сообщения или два callback не запускают повторный AI-анализ и не меняют уже принятое
решение.

`/start` продолжает существующую заявку. `/restart` создаёт новую заявку только после
завершённой или технически неуспешной предыдущей заявки.

## HR flow

После валидного AI-анализа бот отправляет карточку в числовой `HR_CHAT_ID`. Callback:

```text
approve:<application_id>
reject:<application_id>
```

Нажать кнопки может только пользователь с числовым `HR_USER_ID`. После решения:

1. выбранное хранилище атомарно фиксирует `approved` или `rejected`;
2. обновляется существующая строка Google Sheets;
3. сообщение отправляется по сохранённому `telegram_user_id` кандидата;
4. inline-клавиатура удаляется;
5. повторный callback отвечает, что решение уже принято.

Публичный `@gentelman_nick` показывается кандидату только как контакт. Он не заменяет
числовые Telegram ID.

## AI flow

Нативный completion-запрос отправляется в конфигурируемый Yandex endpoint. Приложение
поддерживает официальный ответ `result.alternatives[0].message.text`, запасной
`alternatives[0].message.text` и OpenAI-compatible `choices[0].message.content`.

Перед `json.loads` снимается только внешняя пара Markdown fences. Затем `AIResult`
проверяет все обязательные поля, enum и восемь integer scores в диапазоне `0..10`.
Средний балл Python может вычислить для диагностики, но Yandex его не определяет и не
принимает решение о найме.

Retry: первоначальный запрос плюс максимум две попытки только для timeout/network,
HTTP 429 и 5xx. HTTP 400/401/403 не повторяются. Ключи и полный текст резюме не
пишутся в production log.

## Google Sheets

Таблица должна содержать строку заголовков. Сервис сначала читает заголовки и строит
`header -> column index`; перестановка колонок не ломает запись.

Поиск строки выполняется по `Application ID`, если такая колонка есть, иначе по
`Candidate ID`. Анализ добавляет строку, approve/reject обновляет ту же строку.
Ошибка Sheets не отменяет SQLite/Telegram flow. Повторная синхронизация:

```bash
python -m scripts.sync_sheets
```

Чтобы создать рекомендуемые заголовки в пустом листе:

```bash
python -m scripts.init_sheet
```

Google Spreadsheet нужно открыть для email сервисного аккаунта с правом редактора.

## Установка

Нужен Python 3.12 или новее.

```bash
git clone <repository-url>
cd hr-screening-bot

python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

cp .env.example .env
python -m scripts.init_db
python -m app.main
```

При успешном старте в логах появятся:

```text
Database initialized
Bot started
Telegram mode: polling
```

## Переменные окружения

Обязательно заполнить:

- `TELEGRAM_BOT_TOKEN` — BotFather token;
- `HR_CHAT_ID` — числовой чат, куда отправлять карточки;
- `HR_USER_ID` — числовой Telegram user ID человека, принимающего решение;
- `YANDEX_API_KEY` и `YANDEX_FOLDER_ID` при `AI_MODE=yandex`;
- `GOOGLE_SPREADSHEET_ID` и `GOOGLE_SERVICE_ACCOUNT_FILE` при включённых Sheets.

Один раз укажите только token, включите `DEBUG=true`, перезапустите бота и отправьте
`/debug_id` из HR-чата. В диагностическом режиме остальные credentials не обязательны.
Команда покажет `user_id` и `chat_id`. После заполнения `.env` верните `DEBUG=false` —
production-запуск снова потребует HR, Yandex и включённые Google credentials.

Полный безопасный шаблон находится в `.env.example`. Не коммитьте `.env` и JSON-ключ
Google.

## Telegram и отключение старых workflow

Перед первым Python-запуском обязательно:

1. выключить Make scenario;
2. сделать n8n workflow inactive/unpublished;
3. убедиться, что другой процесс не использует тот же bot token.

В локальном режиме Python удаляет прежний Telegram webhook и начинает long polling.
В облачном режиме Telegram вызывает публичную Cloud Function по webhook. Один token не
может одновременно обслуживаться несколькими polling/webhook реализациями.
`DROP_PENDING_UPDATES=true` удаляет старые необработанные updates при переключении.

## Yandex Cloud Functions

Облачный runtime использует `function_handler.handler`, Telegram webhook и serverless
YDB. Он сохраняет ту же бизнес-логику handlers, YandexGPT, Google Sheets и HR
approve/reject, но не требует постоянно включённого компьютера.

Архив для новой версии функции:

```bash
./scripts/package_cloud.sh
```

Основные настройки функции:

```env
TELEGRAM_MODE=webhook
STORAGE_BACKEND=ydb
YDB_ENDPOINT=grpcs://ydb.serverless.yandexcloud.net:2135
YDB_DATABASE=/region/cloud-id/database-id
YDB_USE_METADATA_CREDENTIALS=true
TELEGRAM_WEBHOOK_SECRET=<random-secret>
GOOGLE_SERVICE_ACCOUNT_JSON_B64=<base64-service-account-json>
```

Для версии функции нужен сервисный аккаунт с минимальной ролью на выбранную YDB.
Функция должна быть публичной для Telegram, но каждый POST дополнительно проверяется
по заголовку `X-Telegram-Bot-Api-Secret-Token`.

## Mock smoke без Yandex и Google

Для ручного Telegram-прохождения установите:

```env
AI_MODE=mock
GOOGLE_SHEETS_ENABLED=false
```

Затем `/start -> DOCX/PDF -> cover letter -> HR card -> approve/reject` работает без
AI-расходов и Sheets. Отдельная локальная проверка доменного контура:

```bash
python -m scripts.smoke_mock
```

Реальную демонстрацию AI выполняйте только с `AI_MODE=yandex`.

## Тесты

```bash
pytest -q
ruff check .
```

Тесты покрывают DOCX paragraphs/tables, PDF, повреждённый DOCX, AI JSON/fences/schema,
переходы и неправильные переходы, restart persistence, HR authorization/callback
format/idempotency и Sheets append/update/column reorder.

## Docker

```bash
cp .env.example .env
docker compose up -d --build
docker compose logs -f bot
```

SQLite хранится в volume `./data:/app/data`. `.env` не копируется в image. Для Docker
укажите:

```env
GOOGLE_SERVICE_ACCOUNT_FILE=/run/secrets/google-service-account.json
```

и положите credentials в `service-account.json` рядом с compose-файлом. Если Sheets
выключены, удалите соответствующий bind mount или создайте файл перед запуском.

## Graceful shutdown и эксплуатация

`Ctrl+C` останавливает polling, закрывает HTTP/Telegram sessions и оставляет SQLite в
согласованном состоянии. Для постоянной работы используйте Docker с
`restart: unless-stopped`, systemd/launchd либо облачный runtime, поддерживающий
долгоживущий polling-процесс.

## Известные ограничения

- OCR сканированных PDF в MVP не выполняется;
- реальные Telegram, YandexGPT и Google Sheets требуют credentials и отдельного E2E;
- SQLite подходит только для локального одиночного процесса; облачный режим использует
  общую serverless YDB;
- холодный старт Cloud Functions может дать небольшую задержку первого ответа.

## Безопасность

- AI не получает и не должен оценивать чувствительные характеристики;
- решение принимает только HR;
- callbacks проверяются по `HR_USER_ID`;
- секреты хранятся только в `.env` или переменных/secret store облачной функции;
- логи не содержат токены, ключи, Authorization header и полный текст резюме;
- SQLite и Google credentials должны иметь ограниченные filesystem permissions.

## История

Первый MVP был собран в Make, затем логика частично переносилась в n8n. Экспорты
сохранены только как reference. Финальный runtime — это Python-приложение.

## Реальный E2E checklist

После заполнения credentials проверить отдельно:

- `/start`, PDF и DOCX;
- реальный YandexGPT и валидный JSON;
- одна строка Google Sheets;
- карточка в `HR_CHAT_ID`;
- approve и отдельная новая заявка reject;
- сообщения кандидату;
- сохранность SQLite после restart;
- отсутствие активных Make/n8n обработчиков того же token.
