# Wget Cloud Plugin Maintainer

Отдельный maintenance bundle для репозитория `wget-cloud/codex-plugins`. Он остаётся работоспособным независимо от `wget-cloud-implementation`, поэтому может диагностировать и исправлять целевой plugin, его hooks, skills, role contracts, validators и marketplace metadata.

## Компоненты

| Компонент | Ответственность |
|---|---|
| `skills/wgc-plugin-maintenance` | полный аудит, itemized proposals, capability evolution, реализация и release workflow |
| `hooks/maintainer_hooks.py` | session-scoped change/delivery approvals, path isolation и role gate ledger |
| `hooks/tests/` | protocol, privacy, approval, delivery и cross-platform command tests |
| `scripts/validate_eval_corpus.py` | проверка версионированного sanitized eval corpus |
| `scripts/run_shadow_eval.py` | isolated baseline/candidate runner с metrics-only report |
| `scripts/verify_external_evidence.py` | fail-closed verifier для sanitized CI/runtime/smoke evidence |

## Approval boundary

Initial use is explicit-only: the user must invoke `$wgc-plugin-maintenance`. A general request concerning plugins, skills, hooks, or marketplace maintenance does not activate this workflow. Any later implicit-routing promotion requires separate approval, shadow evaluation, and a passing smoke in a new Codex task.

До `APPROVE_WGC_PLUGIN_CHANGE=<proposal-id>:<item-ids>` разрешены только read-only аудит и проектирование. После этого запись ограничена выбранными items и их exact paths. Commit, push, install, tag и GitHub Release дополнительно требуют `APPROVE_WGC_PLUGIN_DELIVERY=<delivery-id>`.

Approval действует только в текущей session, не переносится между revisions и не расширяет scope автоматически. Hook сохраняет хэши и структурированные артефакты, но не raw prompts, command output, production logs или credentials.

## Проверка

Из корня marketplace:

```bash
make validate
```

По умолчанию эта команда при необходимости загружает только checksum-pinned
official validators. Для строгой offline-проверки используйте
`make validate OFFICIAL_VALIDATOR_ARGS=--offline`.

После публикации plugin переустанавливается через `codex plugin add wget-cloud-plugin-maintainer@wget-cloud`. Новая версия проверяется только в новой задаче.
