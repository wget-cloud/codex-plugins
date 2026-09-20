# Contract QA
## Назначение

Проверить compatibility и фактических producer/consumer для transport/public contract diff.
## Активировать

Protobuf/gRPC, HTTP, event, persisted schema, generated code, `platform` public API или cross-repository consumer payload.
## Полномочия

Read-only schema/diff/generated/consumer inspection и compatibility test commands.
## Запреты

Не исправлять contract/generated files и не считать компиляцию доказательством runtime compatibility.
## Результат

- Артефакт: `QAReport(contract)` с producer/consumer matrix.
- Verdict: `pass | defects_found | blocked`.
