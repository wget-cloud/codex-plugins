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

- `$wgc-implementation` — новая функциональность, refactor, contract или плановое cross-repo/GitOps изменение.
- `$wgc-bugfix` — пользовательский дефект, regression, crash, incident или неверное observable behavior, которое нужно воспроизвести и исправить.

## Проверка

Из корня репозитория:

```bash
make validate
```

Дополнительно перед публикацией запусти официальные `quick_validate.py` для каждого скилла и `validate_plugin.py` для bundle. При изменении plugin bundle обнови cachebuster через `plugin-creator/scripts/update_plugin_cachebuster.py`, не редактируя marketplace entry ради переустановки.

GitHub Actions выполняет тот же `make validate` для pull request и push в `main`.

## Правила развития

1. Plugin folder, manifest `name` и marketplace entry `name` должны совпадать.
2. Новый skill создаётся штатным `skill-creator/scripts/init_skill.py` и остаётся самодостаточным.
3. Role verdict, phase и write scope меняются одновременно в role file, hook contract и tests.
4. Не копируй полную карту Wget Cloud в каждый role file: role получает task-local context через assignment envelope.
5. Не добавляй secrets, raw production logs, cookies, tokens или customer data.
6. Один commit должен представлять одну логическую причину изменения marketplace/plugin behavior.
