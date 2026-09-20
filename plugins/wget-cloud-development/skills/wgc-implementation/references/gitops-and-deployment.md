# Delivery backend-services

## Границы

Каждый `services/<name>` имеет отдельные module, binary, Dockerfile, image, release identity, deployment и rollback. `services.json` задаёт status, image и `buildImage`/`publish`/`deploy`; не обходи disabled flags. Общий repository commit не означает общий release.

Изменение service запускает только его affected-service row. Contracts, `platform` и repository tooling запускают всех доказанных consumers. Candidate image сопровождается SBOM, provenance и security report. Production container: non-root, один service binary, без shell/package manager, с fail-fast config, health и graceful shutdown.

## GitOps

GitOps находится за пределами backend-services repository. Найди фактического owner, values/overlay, chart и service image reference; не предполагай имя chart или путь. Desired state меняется только через Git после отдельного разрешения. Direct mutating cluster commands запрещены.

Deployment authority привязана к exact service, environment, commit/image digest, desired-state revision, smoke и rollback plan. `Synced` не доказывает health, `Healthy` не заменяет consumer smoke. Failure ведёт к evidence и Git revert/forward-fix proposal, а не ручному patch кластера.

## Миграция из TypeScript

Старый runtime не удаляется автоматически. Сначала: contract/behavior compatibility, candidate image, shadow, load/soak, approved GitOps rollout и rollback evidence. Только затем отдельным изменением отключаются legacy build/publish/deploy paths с CI guard; source/tests/docs/contracts остаются. Status `migrating` меняется на `active`, а publish/deploy включаются только после фактического ownership transfer.

Commit, push, PR, registry publication, GitOps mutation, release и deployment требуют соответствующего явного разрешения.
