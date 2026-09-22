# Wget Cloud Engineering Plugin

Версия 9.2.1 содержит четыре самостоятельных skill, адаптивные команды и общие lifecycle hooks.

| Skill | Назначение |
|---|---|
| `wgc-task-creation` | интервью → исследование → альтернативы → SP → ревью → YouTrack |
| `wgc-epic-implementation` | полный состав и план каждой задачи → dev/epic branches → waves → implementation/review/QA → reconciliation |
| `wgc-implementation` | planned change → TestAssessment → implementation → review/QA → optional delivery |
| `wgc-bugfix` | reproduction/RCA → TestAssessment → minimal fix → review/QA → optional rollout |

В каждом skill `references/agents/index.md` хранит assignment envelope, model routing и ссылки на отдельные role contracts. Role file загружается только перед назначением. `agents/openai.yaml` содержит UI metadata, не role prompts.

## Runtime policy

Service tier не является quality gate. Стандартная разработка использует компактного Task Assessor и одного Implementor на Terra/medium. Третий assignment — Reviewer либо один specialist только для конкретного риска. Sol/medium допустим лишь при записанном blocker/critical escalation, а Full/large scope сам по себе его не разрешает; уровни Sol выше `medium` запрещены.

## Команды и профили

TaskAssessment выполняется один раз и переиспользуется между slices. На implementation/bugfix/item slice действует default budget: максимум 3 assignments, 10 coordination decisions, один unchanged wait без анализа и один correction/recheck. Implementor пишет код и минимальные tests; correction возвращается тому же агенту. Reviewer получает единый ReviewBundle, specialist при необходимости заменяет его. Test-maker остаётся только при явном `test_ownership=protected_test_maker`. Полный pipeline после finding не перезапускается.

Backend, Frontend, Site, Front-lib и GitOps — профили знаний внутри процессов, не новые skills. Data & Migration Reviewer и Reliability Reviewer дополняют существующие Browser QA, Security Reviewer и Contract QA. Domain profile не расширяет permissions роли. Новые тесты защищают конкретный invariant; existing evidence переиспользуется до релевантного изменения.

## Исходники и сборка

Редактируй `../../plugin-src/wget-cloud-implementation`, затем запускай `make -C ../.. skills-build`. Общие roles/policies/domains и workflow-specific части собираются по explicit `composition.json`. Каждый published skill автономен. `build_wgc_skills.py --check` ничего не пишет, отклоняет drift, неожиданные файлы, коллизии и выход за разрешённые пути. CI проверяет сборку и standalone links.

## Hooks

`hooks/wgc_hooks.py` выбирает профиль, фиксирует privacy-safe state, добавляет границы субагентам, блокирует destructive Git/direct cluster mutations и проверяет completion gates. Hook не заменяет role verdict, human approval, read-after-write и проверку diff оркестратором.

State version 4 хранит bounded TaskAssessment, structured gates, SHA-256 protected tests и metadata проверок, но не raw prompt, command output, logs или credentials. V2/v3 baseline сохраняется, старые approvals/verification сбрасываются; нужна новая оценка. Повреждённый state требует нового repository audit. Scope expansion, changed acceptance/plan и новые риски требуют переоценки. Kubernetes меняется только через GitOps; deployment authority всегда привязана к exact revision/environment/image.

`hooks/runtime/` разделяет verdict contracts, task/team policy, migration state и evidence metadata; `wgc_hooks.py` остаётся lifecycle adapter и владельцем существующих destructive-command checks. Проверка фактической семантики, неизвестных зависимостей и внешнего окружения остаётся обязанностью Orchestrator/Reviewer: hooks не являются полноценным sandbox для агентов и не доказывают качество по одному marker.

Lifecycle hooks сохраняют метаданные начала и завершения workflow/агентов в локальной очереди вне repository: в `PLUGIN_DATA/telemetry`, либо в пользовательском каталоге данных системы. При наличии `WGC_CODEX_LOGS_TOKEN` в окружении процесса Codex они отправляют очередь на `https://codex-logs.wget-cloud.ru/v1/events` по HTTPS с персональным Bearer token; ошибка доставки не блокирует задачу, повторная попытка происходит при следующем событии. Очередь ограничена 5000 событиями; при переполнении удаляется самое старое. События содержат opaque session/agent IDs, тип агента, роль из структурированного результата, модель из hook payload, проект и время. На `SubagentStop` hook дополнительно читает только числовые поля `token_count.info.total_token_usage` из transcript этого агента и отправляет input/output/cache/reasoning/total с `source=codex_transcript`. Промпты, ответы, команды, пути, credentials и customer data не отправляются. Формат transcript не является стабильным контрактом Codex; если файл недоступен или формат изменится, usage остаётся `null`, без оценки по тексту.

## Проверка и установка

```bash
make -C ../.. validate
codex plugin add wget-cloud-implementation@wget-cloud
```

После публикации smoke выполняется в новой задаче: активная задача продолжает использовать загруженную cache-версию. Проверяются manifest version и lifecycle hooks без warning/error; cache активной задачи не удаляется.

## YouTrack и работа с задачами

Единственный tracker задач — [YouTrack Wget Cloud](https://youtrack.wget-cloud.ru). GitHub используется для repositories/PR/CI. Все операции с карточками идут через MCP; REST/curl/browser fallback отсутствует. Скилы перечитывают актуальные правила PRD-A-1 и предметные статьи, schemas, карточки, связи и комментарии.

Все процессы исследуют код, задают вопросы и предлагают содержательные альтернативы. Противоречие текущей логике или выявленная существенная проблема требуют явного решения пользователя до зависимой реализации. Создание эпика требует полной продуктовой проработки и плана каждой задачи, включая межпроектные зависимости. Уже данное разрешение того же scope не запрашивается повторно.

Effort Estimator независимо оценивает SP по шкале 1/2/3/5/8/13, с confidence и основаниями. Это отдельная роль от Task Assessor, выбирающего risk/team/test gates. SP не переводятся в часы и не записываются в period fields. Поле Story Points типа integer подтверждено через MCP во всех семи проектах; оценка записывается в поле, обоснование — в описание. Если в будущем поле отсутствует в актуальной schema, оценка сохраняется в описании; административное создание поля не входит в обычную публикацию задач. В task-creation даже Light требует Product Manager, Project Manager, Implementation Auditor, Effort Estimator и независимого Backlog Reviewer.

Самостоятельная задача: `dev → <prefix>/<ID> → dev`. Эпик в каждом затронутом repo: `dev → epic/<ID> → dev`. Задача эпика: `epic/<ID> → <prefix>/<ID> → epic/<ID>`. Prefix определяется типом/категорией. Сообщения коммитов: `[BE-4]: Название задачи`. Перед task→epic task-ветка содержит ровно один squash-коммит; epic→dev сохраняет коммиты отдельных задач. Git actions и deployment остаются в явно разрешённом scope.

Stage движется по фактическому выполнению, ревью, доставке и приёмке; «Причина блокировки» не заменяет Stage. Merge не доказывает выкладку. Полный EpicInventory сохраняется между партиями ≤100 задач; финальный report покрывает всех членов и внешние зависимости. Уже доставленные, заблокированные, отложенные и отменённые работы учитываются отдельно. Hooks проверяют coverage/revision markers, а Orchestrator независимо проверяет реальные артефакты и YouTrack.

Визуальный план, роли и схемы ветвления: [YouTrack workflow](YOUTRACK-WORKFLOW.md).

## Стадии эпика

Project Manager ведёт Исследование → Груминг → К реализации → Декомпозиция → Готово к разработке → В разработке → Готово к выпуску → Приёмка → Реализован. Выход из Исследования и Декомпозиции требует точного approval пользователя; груминг завершается его решением о готовности, а Реализован — его приёмкой всех задач на production. Допускаются возвраты Груминг → Исследование и Декомпозиция → Груминг. Ранняя карточка не требует заранее готового backlog. Все переходы выполняет YouTrack Operator по актуальному плану PM, также после изменения дочерней задачи через implementation/bugfix. Hooks проверяют структурированные условия и сохраняют возможность паузы на вопросах без ложного завершения backlog.

## MCP и персональная авторизация

`.mcp.json` запускает `scripts/youtrack_mcp.py` через Python 3. Launcher использует `npx --yes mcp-remote@0.1.38` как stdio-мост к официальному endpoint `https://youtrack.wget-cloud.ru/mcp`. Требуются Python 3, Node.js/npm с npx в PATH процесса MCP и доступ к npm при первом запуске. Bridge version зафиксирована; npm registry явно ограничен registry.npmjs.org, пользовательский/global npm config отключён, запуск идёт из пустого временного каталога без repository .npmrc и install scripts. Первый запуск может потребовать время на загрузку. Транзитивные зависимости не vendored/lockfile-pinned; npm проверяет integrity из доверенного registry. MCP transport реализует библиотека, launcher получает credential и запускает процесс.

По умолчанию используется постоянный токен YouTrack с scope YouTrack и правами конкретного пользователя:

1. Создай токен в личных настройках YouTrack. Не отправляй его в чат и не помещай в repository/config плагина.
2. На macOS в Keychain Access создай password item: service/name `wget-cloud-youtrack`, account `mcp`, password — токен. При необходимости разреши системный запрос чтения Keychain. Launcher читает только эту запись. Не вводи токен через аргументы shell-команд или историю терминала.
3. Альтернатива: секрет `WGC_YOUTRACK_TOKEN` в окружении самого процесса MCP. Переменная терминала не гарантированно доступна приложению из Dock; для desktop предпочтителен Keychain. Launcher сначала использует environment, затем Keychain на macOS. Пустое/некорректное значение не заменяется молча другим credential.
4. После установки проверь подключение в новой задаче через read-only `find_projects` и `get_issue_fields_schema`. Не создавай тестовые карточки для smoke без отдельного разрешения.

Токен передаётся только в environment дочернего bridge, не в argv; endpoint фиксирован. Launcher не печатает/не сохраняет его, передаёт только разрешённые системные переменные окружения и auth header, исключает посторонние credentials/npm/debug flags и не передаёт диагностический stderr bridge. При неуспехе выводит краткую причину без raw output. OAuth — опционально через `WGC_YOUTRACK_AUTH=oauth` в окружении MCP: мост открывает браузер, если версия/настройки YouTrack это поддерживают; OAuth credentials хранит сам mcp-remote вне bundle. Эта совместимость не предполагается без smoke. Автоматического переключения token→OAuth нет.

Если YouTrack MCP уже подключён глобально, не включай одновременно две одинаковые конфигурации. При установке выбери один connection; действующее персональное подключение этот repository не изменяет. Официальные источники: [YouTrack MCP](https://www.jetbrains.com/help/youtrack/server/model-context-protocol-server.html), [mcp-remote](https://github.com/geelen/mcp-remote). При сборке/тестах нет автоматического создания полей, настройки OAuth-сервера или доступа к credentials.
