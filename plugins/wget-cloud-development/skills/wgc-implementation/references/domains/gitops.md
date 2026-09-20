# GitOps

Сначала проверь `services.json`: image, status, `publish` и `deploy` должны разрешать предполагаемый delivery. Найди Helm/Argo owner и environment overlay для exact service. Immutable image digest/tag, Vault/External Secrets, probes, resources, telemetry, rollout, smoke и rollback проверяются по exact environment/revision. Desired state меняется только через approved GitOps; direct cluster mutations запрещены.

Миграция из legacy TypeScript runtime не удаляет старый source. Отключение старого build/publish/deploy допускается только после успешного Go rollout и soak, отдельного CI guard и подтверждённого ownership transfer.

Профиль добавляет предметные знания, но не меняет полномочия роли. Загружай только выбранные профили. Выполняй существующие repository requirements; добавляй проверки только по изменяемым invariants.
