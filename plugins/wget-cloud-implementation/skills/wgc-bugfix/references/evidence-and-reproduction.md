# Evidence и воспроизведение

## Принцип минимально необходимого доступа

Сначала используй локальные исходники, тесты, сохранённые error messages и предоставленные пользователем identifiers. К runtime-системам переходи только если локальных данных недостаточно. Любой запрос должен иметь конкретную гипотезу, environment, узкий time range и ограниченный объём результата.

Предпочтительный порядок:

1. Точный пользовательский symptom и timestamp.
2. Release identity: commit, build, image digest/tag, frontend asset version.
3. Browser console/network или API response с удалёнными credentials.
4. Request/correlation/trace ID.
5. Scoped service logs и traces.
6. Aggregated metrics и rollout events.
7. Read-only data inspection с tenant-safe predicates, если это действительно нужно.

Не используй broad log tail, полные database dumps, cluster-wide secrets listing или запросы без time/namespace/service scope.

## EvidenceBundle

Для каждого evidence item фиксируй:

- стабильный handle или краткое redacted summary, но не секрет/полный payload;
- source, environment, service/component;
- временной интервал и timezone;
- release identity;
- связь с гипотезой: `supports | contradicts | neutral`;
- ограничения достоверности.

Храни в Git только синтетические/обезличенные fixtures. Сырые production-логи, HAR, screenshots с PII и токены остаются во внешнем одобренном хранилище; в отчёте указывай handle и redaction status.

## Redaction checklist

Перед включением вывода в артефакт удалить или замаскировать:

- Authorization/Cookie/Set-Cookie, JWT, API keys и session IDs;
- email, телефон, ФИО, адрес и пользовательский контент, если они не нужны для доказательства;
- database DSN, registry credentials, Vault/External Secret data;
- полные request/response bodies с business data;
- внутренние identifiers, если достаточно стабильного хеша или последних символов.

Если безопасно отредактировать вывод нельзя, не цитируй его. Опиши проверку и результат агрегированно.

## Воспроизведение

Хороший `ReproductionReport` содержит:

- точную исходную revision и environment;
- минимальные preconditions и test data ownership;
- детерминированные шаги или команду;
- observed result и expected invariant;
- частоту (`N/M`) и variance;
- negative control или соседний passing path;
- screenshots/log handles только после redaction;
- cleanup test data, если оно создавалось разрешённым способом.

Воспроизведение в production не должно изменять реальные данные без отдельного разрешения. Даже read-only запрос запрещён, если он может раскрыть реальные данные foreign tenant. Предпочитай локальную среду, synthetic canary tenants, dry-run или уже произошедший redacted request trace.

## Если не воспроизводится

Не патчить код по интуиции. Выполни последовательно:

1. Сверь release/config/feature flags/cache/service-worker и tenant/role.
2. Сверь часовой пояс, locale, clock, retry и concurrency условия.
3. Уменьши сценарий до ближайшего стабильного failing observable.
4. Запроси конкретный недостающий identifier или временной диапазон.
5. Если evidence однозначно указывает execution path, подготовь предложение characterization test и запроси формальный `reproduction_waiver`; сам тест создаёт только test-maker после approval.
6. Иначе заверши `not_reproduced`/`needs_input`, перечислив уже исключённые гипотезы.

## RootCauseAnalysis

RCA должна отвечать на пять вопросов:

1. Где именно впервые нарушается invariant?
2. Как вход достигает этой ветки исполнения?
3. Почему существующие guards/tests/observability не поймали дефект?
4. Какие две или более правдоподобные альтернативы проверены и отвергнуты?
5. Почему предлагаемый patch устраняет причину, а не маскирует symptom?

Корреляция с последним commit недостаточна без execution evidence. Одновременно не превращай bugfix в полное расследование системы: после доказанной причины останови расширение scope.
