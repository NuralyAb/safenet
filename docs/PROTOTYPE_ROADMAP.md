# SafeNet KZ — Roadmap до рабочего прототипа

Цель: довести SafeNet KZ до **рабочего, кликабельного прототипа всех трёх killer-фич** (Scam Fingerprint, Fraud Graph, AI Investigator) с использованием **внешних AI API** (OpenAI/Anthropic), потому что локально разворачивать модели сейчас нет ресурсов. На каждой фазе — тесты, чтобы следующие фазы ничего не ломали.

---

## 0. Важная оговорка: внешний AI vs on-prem

Боевой продукт по ТЗ — **on-prem, без внешних вызовов** (данные не покидают периметр). Прототип на OpenAI/Anthropic это **нарушает**. Поэтому:

1. Весь AI идёт через **провайдер-абстракцию** (`app/services/ai/`). Меняется провайдер, а не код пайплайна → потом swap на self-hosted (vLLM/Whisper) без переписывания.
2. **Через внешние API — только синтетические/демо-данные.** Никакой реальной биометрии и реальных дел в OpenAI. Это правило держим в [CLAUDE.md](../CLAUDE.md).
3. `AI_PROVIDER=openai|anthropic|local` в конфиге; `local` остаётся целевым для продакшена.

---

## Как читать этот документ

Каждый шаг = **Deliverable** (что появится) · **Files** (где) · **Acceptance** (критерий «готово») · **Tests** (что написать). Фазы идут строго по порядку; внутри фазы шаги тоже зависимы.

Легенда статуса: `[ ]` не начато · `[~]` частично есть в коде · `[x]` готово.

---

## Фаза T0 — Тестовый фундамент (сделать ПЕРВЫМ)

Без этого «тесты на каждой фазе» не выполнимы: сейчас тесты гоняются самописным раннером, pytest не установлен.

- [x] **T0.1 Подключить pytest** — ✅ `requirements-dev.txt`, `pytest.ini` (`asyncio_mode=auto`, маркер `integration`), `tests/conftest.py`. **29/29 проходят под `pytest`.**
- [x] **T0.2 CI: добавить job тестов** — ✅ `backend-tests` job в [.github/workflows/security.yml](../.github/workflows/security.yml) (ставит `requirements-dev.txt`, гоняет `pytest`); рядом `frontend-build`. Integration-тесты исключены по умолчанию.

> Дальше КАЖДЫЙ шаг добавляет тесты в этот прогон. Правило: **ни один прошлый тест не должен покраснеть** — это и есть защита от регрессий.

---

## Фаза A — Демо-вертикаль (без AI и без скрейпинга)

Цель фазы: залогиниться → «Расследовать» → **реальный** детерминированный отчёт из БД + граф из Neo4j на **засеянных** данных. Доказывает, что вся проводка работает, до подключения AI.

- [x] **A1 Модели БД + миграции** — ✅ `app/db/models.py` (5 моделей, SQLAlchemy 2.0 typed), Alembic (`alembic.ini`, `env.py`, `0001_initial.py`) с **append-only триггером на `audit_log`** (Postgres). `alembic upgrade head` создаёт схему. **4 теста** (`test_models.py`): CRUD + relationship + JSON breakdown + персист и верификация hash-chain. Всего 33/33 зелёных.
- [x] **A2 Startup-инициализация** — ✅ `app/core/startup.py` (`initialize_stores`) + `main.py` lifespan (fail-fast в prod, warn в dev). Переиспользует `ensure_buckets`/`init_collection`/`init_schema`. **2 теста** (`test_startup.py`): все три стора вызваны + идемпотентность. 35/35.
- [x] **A3 Seed-скрипт** — ✅ `scripts/seed_demo.py`: аналитик (argon2+TOTP, печатает otpauth) + связная сеть (2 аккаунта делят кошелёк+telegram, 3-й — только кошелёк, SAME_PERSON? кандидат) в Neo4j + fingerprints в Qdrant. Идемпотентно. **3 теста** (`test_seed.py`): seed_user TOTP + идемпотентность (unit); graph/qdrant под `@pytest.mark.integration`. 43 passed, 1 deselected.
- [x] **A4 Логин реально работает + экран логина**
  - [x] **Backend**: `UserRepo` из Postgres + рабочий логин (`auth.py`, `db/session.py` ленивый). **6 тестов** (`test_auth.py`). 41/41.
  - [x] **Frontend**: `lib/auth.ts` (стор+`useAuth`), `api/client.ts` (Bearer + 401→logout + `login`), `features/auth/LoginPanel.tsx`, гейт в `App.tsx`. tsc+build зелёные.
  - ⏳ follow-up: vitest + `LoginPanel.test.tsx` (юнит фронта) — отдельным шагом, когда поднимем vitest.
- [x] **A5 Наполнить активности Investigator реальными данными** — ✅ чистый `services/investigation.py` (мапперы + `risk_signals`), Cypher в `GraphBuilder` (`network_summary`, `shared_identifier_accounts`), активности читают Postgres/Neo4j; балл data-driven. `compose_narrative` шаблон → LLM в B3. **5 тестов** (`test_investigation.py`). 48 passed. NLP-флаги профиля → Фаза B.
- [x] **A6 `/graph` endpoint + граф из реальных данных** — ✅ `GraphBuilder.subgraph` (Cypher) + маппер `subgraph_from_edge_rows` (дедуп, типы, `SAME_PERSON?`), `GET /api/v1/graph/{seed}` под RBAC. Frontend: `api.getGraph` + `useGraph` + `FraudGraph` грузит реальные данные (фолбэк SAMPLE). **4 теста** (`test_graph_api.py`: маппинг + 401). 52 passed.

**Definition of Done фазы A:** ✅ полный сценарий login → investigate → отчёт+граф на seed-данных. **Без AI и без сбора.** Все шаги A1–A6 готовы и под тестами.

---

## Фаза B — Внешний AI через абстракцию (ключевая для прототипа)

Цель: заменить заглушки на реальный AI через OpenAI/Anthropic, оставив возможность swap на self-hosted.

- [x] **B0 Провайдер-абстракция AI** — ✅ `app/services/ai/` (`base` Protocols, `openai_provider` все 4, `anthropic_provider` chat, `local_provider` заглушка, `factory` по `AI_PROVIDER`). Эмбеддинги шлют `dimensions=dim_text` (совпадение с Qdrant). **7 тестов** (`test_ai_provider.py`): роутинг + OpenAI-контракты на `respx`, без сети. 59 passed.
  - Deliverable: интерфейсы + фабрика по `AI_PROVIDER`.
    ```python
    # app/services/ai/base.py
    class Embedder(Protocol):
        def embed_text(self, texts: list[str]) -> list[list[float]]: ...
    class Transcriber(Protocol):
        def transcribe(self, audio: bytes) -> str: ...
    class ChatLLM(Protocol):
        def complete(self, system: str, user: str) -> str: ...
    class VisionTagger(Protocol):
        def tag(self, image: bytes) -> list[str]: ...
    # app/services/ai/factory.py -> get_embedder()/get_llm()/... по settings.ai_provider
    ```
  - Files: `backend/app/services/ai/{base,openai_provider,anthropic_provider,local_provider,factory}.py`; config: `ai_provider`, `openai_api_key`, `anthropic_api_key`, модели (`embed_model`, `llm_model`, `stt_model`).
  - Acceptance: `get_llm().complete(...)` работает с `AI_PROVIDER=openai`; переключение на `local` не требует менять вызывающий код.
  - Tests: `test_ai_factory.py` — фабрика отдаёт правильный класс; **контракт-тест с замоканным HTTP** (`respx`) на каждый провайдер; реальных вызовов в CI нет.
- [x] **B1 Эмбеддинги (OpenAI `text-embedding-3-large`)** — ✅ `services/pipeline.py` (`extract_features`, `fingerprint_from_processed`); `tasks.py` `process_content`→`get_embedder()`, `fingerprint_content`→Qdrant upsert+search. **4 теста** (`test_pipeline.py`) с fake-Embedder: эмбеддинг+контракт, пропуск пустого, сборка fp, матчинг. 67 passed. (upsert/search против живого Qdrant — integration в C2.)
- [x] **B2 Транскрипция аудио (Whisper API)** — ✅ `extract_features` принимает `Transcriber`: audio→транскрипт→текст→эмбеддинг; `process_content` шлёт `get_transcriber()`. **+3 теста** (`test_pipeline.py`) + контракт transcribe в `test_ai_provider.py`. 70 passed.
- [x] **B3 Нарратив Investigator (OpenAI/Anthropic)** — ✅ `narrative_prompt`+`fallback_narrative`+`compose_narrative_text` в `investigation.py`; активность зовёт `get_llm()`. Промпт запрещает скоринг, балл из `compute_risk`. Fallback на шаблон при сбое. **4 теста** (`test_narrative.py`). 63 passed.
- [x] **B4 Vision-теги (`gpt-4o` vision)** — ✅ `extract_features` принимает `VisionTagger`; теги кадра → `gambling_content` через `gambling_from_tags`; `process_content` шлёт `get_vision_tagger()`. **+3 теста** + vision-контракт. 74 passed.

**Definition of Done фазы B:** ✅ отчёт и fingerprint строятся на настоящем AI; провайдер переключается конфигом; в CI всё на моках (без трат и без сети). **B0–B4 готовы и под тестами.**

- [x] **B5 NLP claim-флаги** — ✅ `services/claims.py` (LLM→JSON-флаги promises/referral/license/gambling, defensive parse, agg по контенту); проводка в `extract_features`; колонки в `Content` + миграция 0002 (идемпотентная); `profile_from_content` агрегирует → балл стал содержательным; seed создаёт Content с флагами. **7 тестов** (`test_claims.py` + профиль). 
- [x] **B6 Извлечение аудио/кадров (ffmpeg)** — ✅ `services/media.py` (чистые билдеры команд + extract_audio/frame + `enrich_with_media` best-effort); `process_content` тянет оригинал из MinIO и извлекает в изолированном воркере → замыкает audio→STT и frame→vision. **5 тестов** (`test_media.py`). 113 passed.
- [x] **B7 Биометрия / Same Person Detection** (последний пункт ТЗ) — ✅ интерфейсы `FaceEmbedder`/`SpeakerEmbedder` (self-hosted only — внешние API не делают face/voice recognition); `biometrics.py` (cosine-сигналы → SAME_PERSON-кандидат, **human-in-the-loop**, не авто-подтверждается); проводка в pipeline (best-effort, эмбеддинги шифруются `crypto.py`); `GraphBuilder.confirm_same_person` + `POST /graph/same-person` (supervisor, audited). **7 тестов** (`test_biometrics.py`). 124 passed. Извлечение эмбеддингов требует `AI_PROVIDER=local` + GPU.

---

## Фаза C — Реальный сбор (один источник)

- [x] **C1 Мультиисточниковый фреймворк** — ✅ реестр (`registry.py`) + единый `runner.collect_via` (SSRF→evidence→контракт) + адаптеры: YouTube/TikTok/Instagram (yt-dlp база), Telegram (Telethon-каркас), WhatsApp (зарегистрирован, падает с объяснением — E2E, невозможно). `extract_identifiers` (telegram/wallets/domains). `collect_content`→реестр, `ingest`→fan-out per item. **9 тестов** (`test_extract.py`, `test_collectors.py`): реестр, collect_via+evidence, SSRF-блок, WhatsApp-отказ. Матрица легальности — [docs/collectors.md](collectors.md). 83 passed.
- [x] **C2 Полная цепочка end-to-end** — ✅ `test_pipeline_e2e.py`: композиция collect→process→fingerprint с проверкой стыковки контрактов на каждой границе (CI, без сервисов) + `@integration` прогон против живого Qdrant. 84 passed, 2 deselected.

---

## Фаза D — Fingerprint + Graph полностью

- [x] **D1 Кластеризация схем → ScamSchema** — ✅ `scam_schema_id`+`schema_assignments`+`rebuild_scam_schemas` (clustering), `FingerprintStore.scroll_all` (Qdrant), `GraphBuilder.write_scam_schemas` (Neo4j: ScamSchema+MATCHES_SCHEMA), `POST /graph/schemas/rebuild` (supervisor, audited). **4 теста** (`test_scam_schema.py`). 117 passed. **DoD Scam Fingerprint закрыт.**
- [x] **D2 GDS-аналитика графа** — ✅ `detect_communities` (Louvain) + `ringleader_candidates` (betweenness) + чистые мапперы; `GET /graph/insights`. **4 теста** (`test_graph_analysis.py`). GDS-Cypher = integration. 88 passed.
- [x] **D3 Граф + insights на дашборде** — ✅ A6 (граф из Neo4j) + `InsightsPanel`/`useInsights`: «N объектов в сети» + ringleaders из `/graph/insights`. tsc+build зелёные.

---

## Фаза E — Продакшен-полиш

- [x] Персист audit в append-only таблицу — ✅ `db/audit_repo.py` (`SqlAuditRepo`+`record_action`), проводка в investigations-эндпоинты. **3 теста** (`test_audit_persist.py`). 95 passed. (Остальные эндпоинты — по тому же паттерну.)
- [x] Rate limiting на логин — ✅ `core/ratelimit.py` (sliding-window, 5/мин на IP) + зависимость на `/login`. **3 теста** (`test_ratelimit.py`). 98 passed. (prod: бэкенд на Redis.)
- [x] Прод-хардненинг Dockerfile — ✅ non-root user (uid 10001) + ffmpeg для медиа.
- [x] Refresh-токены — ✅ backend `/auth/refresh` + типизированные access/refresh (`security.py`); фронт авто-обновляет access на 401 и ретраит (`auth.ts`/`client.ts`). **3 backend + покрытие фронта** (tsc/build/vitest).
- [x] Frontend vitest — ✅ vitest+testing-library; **3 теста** (`RiskGauge`, `RiskReport`); в CI (`npm test`).
- [x] Нагрузочный тест — ✅ `make loadtest` (`senior-backend/api_load_tester.py`, против живого инстанса).
- [x] Прод-хардненинг Dockerfile — ✅ non-root + ffmpeg.
- [ ] (минор) Состояния ошибок/скелетоны на фронте; secrets из KMS; TLS на периметре.

### Post-MVP — соответствие треку «AI Media Watch» (per-video) — ✅

- [x] **Риск-оценка по каждому видео** — ✅ таблица `content_risk` (миграция `0005`), `services/content_scoring.py` + `content_risk_signals` (тот же детерминированный движок, что и для аккаунта). Скоринг автоматический в конвейере: стадия `score_content` после `fingerprint` (`tasks.py`); `evidence_id` ведёт к контенту. `GET/POST /triage/content` + экран **«Материалы»** на фронте (`MaterialsView`). **+11 тестов** (`test_content_scoring`, `test_content_facts`, `test_content_triage`).
- [x] **Два недостающих паттерна ТЗ без ломки весов** — ✅ «агрессивные инвестиционные призывы» и «скрытые способы вовлечения» извлекаются (`extract_content_facts`, 6 признаков) и моделируются как *интенсификаторы* силы родительского фактора `0.6→1.0` (веса ТЗ не тронуты, [ADR-0009](adr/0009-per-video-risk-scoring.md)). Градуированная сила вместо бинарной на per-video пути.
- [x] **Multi-frame анализ видео** — ✅ `media.py` `extract_frames`/`frame_offsets` (конфиг `VIDEO_FRAMES`), агрегация vision/OCR по всем кадрам в `pipeline.py` (маркер виден в любом месте ролика, не только на 1.0с). **+9 тестов** (`test_media_multiframe`, `test_pipeline_multiframe`).
- Итог: **179 backend + 6 frontend тестов** зелёные (`pytest -m "not integration"` в образе `afm-backend`; `tsc` + `vitest` на фронте).

---

## Что нужно от тебя (ключи/доступы)

| Назначение | Переменная | Где взять |
|------------|-----------|-----------|
| Эмбеддинги, Whisper, GPT-4o | `OPENAI_API_KEY` | platform.openai.com |
| (альтернатива LLM) | `ANTHROPIC_API_KEY` | console.anthropic.com |
| Сбор (вариант 1) | `YOUTUBE_API_KEY` | Google Cloud Console |
| Сбор (вариант 2) | `TELEGRAM_API_ID`/`TELEGRAM_API_HASH` | my.telegram.org |

Ориентир по стоимости прототипа (демо-объёмы): эмбеддинги ~$0.0001/текст, Whisper ~$0.006/мин, gpt-4o ~$5–15/1M токенов — десятки центов на демо-прогон. Бюджетный потолок задаётся в коде (см. E — rate limiting + max-tokens).

---

## Стратегия тестирования (чтобы фазы не ломали друг друга)

**Пирамида:**
| Уровень | Что | Когда в CI | Внешние вызовы |
|---------|-----|-----------|----------------|
| Unit (есть 29) | чистая логика: risk/fingerprint/audit/crypto/ssrf | всегда | нет |
| Contract | провайдеры AI, коллекторы — на `respx`/моках | всегда | **нет (моки)** |
| Integration (`@pytest.mark.integration`) | против поднятых docker-сервисов | nightly / по флагу | внутр. сервисы |
| Smoke (manual) | реальный OpenAI-ключ, 1 прогон | вручную перед демо | да |
| Frontend | `tsc`+`vite build`+vitest | всегда | нет |

**Правила:**
1. Реальные API-вызовы **запрещены в CI** — только моки (`respx`). Это держит CI бесплатным и стабильным.
2. Каждый новый модуль приносит ≥1 contract/unit тест в общий прогон.
3. Перед мержем фазы: `pytest -q` (всё зелёное, прошлые тесты не тронуты) + `npm run build` + security-гейт.
4. Детерминизм: в тестах AI заменяется fake-провайдером с фиксированным выходом — так проверяем проводку, а не качество модели.

---

## Доп. фичи (АФМ-позиционирование)

- [x] **Evidence Package Generator (Tier 1)** — ✅ backend `services/evidence_package.py` (tamper-evident справка, хеш-манифест, Markdown) + `GET /investigations/{id}/evidence-package`. **Frontend:** кнопка «Сформировать справку» в отчёте → показ + скачивание .md. **4 backend-теста**.
- [x] **Money Flow Intelligence (мост, не вся цепь)** — ✅ backend `services/money_flow.py` (детект сети, тег биржи, поток account→wallet→exchange + **граница**), `services/chain.py` (OnChainClient stub/Etherscan), `GET /graph/money-flow/{account}`. **Frontend:** карточка Money Flow на дашборде (ввод→трассировка→плашка границы); `MoneyFlowView` под vitest. **5 backend + 2 frontend теста**. 133 backend + 5 frontend passed.

---

## Definition of Done — «рабочий прототип»

- [ ] Логин (argon2+TOTP) → JWT → защищённый дашборд.
- [ ] «Расследовать @target» → реальный отчёт: балл (детерминированный), факты, нарратив (внешний LLM), счётчики сети.
- [ ] Scam Fingerprint: похожие схемы находятся (реальные эмбеддинги + общие идентификаторы).
- [ ] Fraud Graph: сеть из Neo4j на дашборде, сообщество/центральный узел подсвечены.
- [ ] Хотя бы один реальный источник реально собирается в evidence (WORM+хеш).
- [ ] `AI_PROVIDER` переключается openai↔local без правок пайплайна.
- [ ] CI зелёный: unit+contract+frontend; security-гейт чист.

---

## Порядок действий (TL;DR)

1. **T0** (pytest+CI) → 2. **A1–A6** (демо-вертикаль на seed) → 3. **B0–B3** (внешний AI) → 4. **C1–C2** (один коллектор) → 5. **D1–D3** (fingerprint+graph) → 6. **E** (полиш).

После **A+B** уже есть демонстрируемый прототип на реальном AI и seed-данных. **C+D** добавляют реальные данные. **E** — товарный вид.
