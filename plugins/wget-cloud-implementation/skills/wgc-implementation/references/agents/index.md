# Реестр агентов implementation-конвейера

Открывай файл роли непосредственно перед её назначением и не загружай downstream-роли заранее. Оркестратор читает этот index полностью, а затем передаёт субагенту конкретный role contract вместе с task scope.

## Общий assignment envelope

```text
WORK_ITEM: <id и цель>
ROLE: <role>
TASK_SLICE: <одна ограниченная подзадача>
REPOSITORIES: <разрешённые repo>
ALLOW_PATHS: <разрешённые пути>
DENY_PATHS: <запрещённые пути, включая protected tests>
INPUT_ARTIFACTS: <план, findings, acceptance criteria>
LOCAL_INSTRUCTIONS: <AGENTS.md и обязательные docs>
EXPECTED_COMMANDS: <проверки>
OUTPUT_CONTRACT: <артефакт и verdict enum>
```

Каждому субагенту добавляй: «Работай только в выданном scope. Сохраняй существующие изменения. Не выполняй commit, push, PR, merge, release или deployment без приложенного разрешения. Не объявляй всю задачу завершённой. Если scope недостаточен, верни `needs_input`».

## Роли

| Роль | Когда применять | Write scope | Контракт |
|---|---|---|---|
| Orchestrator | всегда | координационные действия | [orchestrator.md](orchestrator.md) |
| Explorer | reconnaissance | нет | [explorer.md](explorer.md) |
| Architect | design и DAG | нет | [architect.md](architect.md) |
| Architecture guardian | plan/diff architecture gate | нет | [architecture-guardian.md](architecture-guardian.md) |
| Test-maker | executable acceptance baseline | только tests allowlist | [test-maker.md](test-maker.md) |
| Implementor | один DAG slice | production/docs allowlist | [implementor.md](implementor.md) |
| Reviewer | code review | нет | [reviewer.md](reviewer.md) |
| QA | adversarial behavior verification | нет в repository | [qa.md](qa.md) |
| DevOps | GitOps desired state | `k8s` allowlist | [devops.md](devops.md) |
| Infrastructure reviewer | GitOps review | нет | [infrastructure-reviewer.md](infrastructure-reviewer.md) |
| Deployment agent | approved publication/rollout observation | только exact publish action | [deployment-agent.md](deployment-agent.md) |

## Машинный результат

Каждый субагент завершает ответ одной последней строкой, используя exact revision из `SubagentStart`:

```text
WGC_AGENT_RESULT: {"role":"<role>","verdict":"<role verdict>","phase":"<plan|diff только для architecture-guardian, иначе пусто>","input_revision":"<exact-input-revision>"}
```

Строка не заменяет артефакт и evidence. Оркестратор перепроверяет diff, команды и revision. Допустимые verdicts определены в role files и проверяются hooks с учётом профиля `implementation`.

## Независимость

- Implementor не совмещается с Test-maker, Reviewer или Architecture guardian.
- Architect не утверждает свой план.
- DevOps не является Infrastructure reviewer.
- Deployment agent не пишет application-код или manifests.
- Два write-агента не работают одновременно в одном repository или contract boundary.
