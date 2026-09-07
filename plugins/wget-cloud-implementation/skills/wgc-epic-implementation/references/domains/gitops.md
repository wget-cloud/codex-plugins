# GitOps

Найди Helm/Argo owner и environment overlay. Immutable images, Vault/External Secrets и rollout/rollback проверяются по exact environment/revision. Desired state меняется только через approved GitOps; direct cluster mutations запрещены существующей policy.

Профиль добавляет предметные знания, но не меняет полномочия роли. Загружай только выбранные профили. Выполняй существующие repository requirements; добавляй проверки только по изменяемым invariants.
