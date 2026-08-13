# Инструкции для codex-plugins

Перед изменением прочитай корневой `README.md`, manifest/README затронутого plugin и `SKILL.md` затронутых skills.

## Архитектура repository

- `.agents/plugins/marketplace.json` — каталог, а не место для skill/hook конфигурации.
- Каждый каталог `plugins/<name>` — самостоятельный plugin bundle с `.codex-plugin/plugin.json`.
- Каждый `skills/<name>` самодостаточен: не ссылайся на references соседнего skill.
- `agents/openai.yaml` содержит только UI metadata. Исполняемые role contracts хранятся по одному файлу в `references/agents/`, с registry в `references/agents/index.md`.
- Подробности workflow/artifacts/projects держи в `references/`, а `SKILL.md` оставляй маршрутизатором и набором обязательных invariants.
- Hooks должны оставаться stdlib-only, privacy-safe и fail-closed только для high-confidence destructive policy checks.

## Изменения

- Используй `plugin-creator` для manifest/marketplace и `skill-creator` для skills.
- При изменении plugin bundle повышай manifest `version` как plain SemVer без `+` build metadata; cachebuster helper не используй и marketplace entry ради версии не редактируй.
- При добавлении plugin/skill применяй штатные scaffold scripts; не оставляй TODO placeholders.
- Изменение role verdict/phase обязано синхронно обновить role file, hook profile contract и tests.
- Не объединяй роли с конфликтом независимости и не создавай общий shared role file за пределами skill: skill должен оставаться переносимым.
- Не добавляй README/CHANGELOG/installation guides внутрь skill folder.

## Обязательные проверки

```bash
make validate
```

Также запусти official quick validator каждого изменённого skill, plugin validator и `git diff --check`.

После публикации переустанови plugin через `codex plugin add <plugin>@<marketplace>` и выполняй smoke только в новой задаче: уже активные задачи продолжают ссылаться на загруженную при старте cache-версию. Smoke обязан проверить manifest version и отсутствие warning/error на lifecycle hooks. Не удаляй cache, используемый активной задачей.

Commit/push выполняй только по явному разрешению пользователя. Marketplace publication и deployment внешних Wget Cloud приложений — разные операции.
