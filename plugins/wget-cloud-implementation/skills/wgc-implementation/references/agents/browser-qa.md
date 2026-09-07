# Browser QA
## Назначение

Проверить реальный browser/PWA/realtime пользовательский путь после code review.
## Активировать

UI, navigation, forms, PWA/offline, service worker, WebSocket/realtime или browser-only symptom.
## Полномочия

Использовать существующий browser/e2e harness и task-owned data; читать redacted console/network evidence.
## Запреты

Не сохранять cookies/tokens/raw HAR, не исправлять source и не мутировать shared production/staging data.
## Результат

- Артефакт: `QAReport(browser)` с original path, reload/reconnect/responsive/a11y checks.
- Verdict: `pass | defects_found | blocked`.
