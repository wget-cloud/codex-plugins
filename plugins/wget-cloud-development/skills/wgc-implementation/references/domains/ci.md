# CI and service registry

`services.json` управляет affected-service matrix: path, module, Dockerfile, contracts, image, build/publish/deploy capability. Service-only change запускает только его row; contracts, platform и repository tooling запускают всех доказанных consumers. Nightly/`force_all` проверяют весь registry; `fail-fast: false` сохраняет независимые результаты.

При изменении registry или planner проверь JSON, `scripts/ci/plan.py`, affected/unaffected fixtures и manual/scheduled paths. Каждый row создаёт отдельный candidate image, SBOM, provenance и security report. Не включай publish/deploy для migrating service до выполнения migration gates и явного разрешения.
