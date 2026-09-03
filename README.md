# Wget Cloud Codex Plugins

Командный marketplace Codex для инженерных workflows Wget Cloud. Репозиторий хранит каталог marketplace и самодостаточные plugin bundles; application-код платформы сюда не входит.

## Структура

```text
.agents/plugins/marketplace.json          # упорядоченный каталог плагинов
plugins/
  wget-cloud-implementation/
    .codex-plugin/plugin.json             # manifest bundle
    README.md                              # карта компонентов плагина
    hooks/                                 # lifecycle guardrails и tests
    skills/
      wgc-implementation/                 # planned delivery workflow
      wgc-bugfix/                         # evidence-driven defect workflow
      wgc-task-creation/                  # product backlog and GitHub Project workflow
      wgc-epic-implementation/            # ordered Project task-pool delivery workflow
  wget-cloud-plugin-maintainer/
    .codex-plugin/plugin.json             # approval-gated maintenance bundle
    hooks/                                 # lifecycle approval and scope contracts
    skills/wgc-plugin-maintenance/         # explicit-only plugin-maintenance workflow
scripts/validate_marketplace.py           # structural validation всего каталога
```

## Границы компонентов

- `marketplace.json` отвечает только за discovery, порядок, policy и путь к plugin bundle.
- `.codex-plugin/plugin.json` описывает plugin UX и доступные component roots.
- `skills/<name>/SKILL.md` содержит короткий основной workflow; детали загружаются из `references/` по необходимости.
- `skills/<name>/agents/openai.yaml` — UI metadata скилла, не определения рабочих ролей.
- `skills/<name>/references/agents/` — отдельные role contracts. Один агент — один Markdown-файл; `index.md` содержит registry и общий envelope.
- `hooks/` содержит механические guardrails. Hooks не заменяют role verdicts и human approvals.

## Выбор скилла

- `$wgc-task-creation` — аудит требований/реализации, декомпозиция и публикация product-quality backlog в выбранный GitHub Project.
- `$wgc-epic-implementation` — массовая реализация выбранного эпика или пула Project items с dependency waves и синхронизацией статусов.
- `$wgc-implementation` — новая функциональность, refactor, contract или плановое cross-repo/GitOps изменение.
- `$wgc-bugfix` — пользовательский дефект, regression, crash, incident или неверное observable behavior, которое нужно воспроизвести и исправить.
- `$wgc-plugin-maintenance` — explicit-only аудит, repair и capability evolution самого `wget-cloud/codex-plugins` с item-level approvals.

## Проверка

Из корня репозитория:

```bash
make validate
```

`make validate` obtains only checksum-pinned official validators when they are
not already cached. For a network-free check, pass
`OFFICIAL_VALIDATOR_ARGS=--offline`; that mode never downloads a validator.

Дополнительно перед публикацией запусти официальные `quick_validate.py` для каждого скилла и `validate_plugin.py` для bundle. При изменении plugin bundle повысь `version` в manifest как обычный SemVer (`0.4.0` → `0.4.1` или prerelease вроде `0.5.0-rc.1`) без `+` build metadata. Cachebuster helper для этого marketplace не используется, а entry в `marketplace.json` ради переустановки не меняется.

После публикации переустанови plugin из marketplace:

```bash
codex plugin add wget-cloud-implementation@wget-cloud
```

Проверяй новую версию в новой задаче: активная задача продолжает использовать загруженный при старте plugin cache. В smoke-проверке убедись, что версия manifest ожидаемая, hooks запускаются без warning об unsupported `async`, а `SessionStart`, `PostToolUse` и `Stop` завершаются без ошибок. Не удаляй cache-каталог, пока на него ссылается активная задача.

GitHub Actions выполняет тот же `make validate` для pull request и push в `main`.

`wget-cloud-plugin-maintainer` не получает implicit routing. Его workflow разделяет Auditor, Architect, Test-maker, Implementor, Reviewer и QA; запись начинается только после Gate 1, а commit/push/install/release требуют отдельный Gate 2.

## Правила развития

1. Plugin folder, manifest `name` и marketplace entry `name` должны совпадать.
2. Новый skill создаётся штатным `skill-creator/scripts/init_skill.py` и остаётся самодостаточным.
3. Role verdict, phase и write scope меняются одновременно в role file, hook contract и tests.
4. Не копируй полную карту Wget Cloud в каждый role file: role получает task-local context через assignment envelope.
5. Не добавляй secrets, raw production logs, cookies, tokens или customer data.
6. Один commit должен представлять одну логическую причину изменения marketplace/plugin behavior.
