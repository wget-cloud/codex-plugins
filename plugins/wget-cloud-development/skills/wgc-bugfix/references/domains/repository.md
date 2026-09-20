# Backend-services repository

Target root: `/Users/estev/wc/wgetcloud/backend-services`. Перед работой прочитай root `AGENTS.md`; для сервиса также `doc/services/<name>/README.md`, `BUSINESS_LOGIC.md` и `ARCHITECTURE.md`. `services.json` — source of truth для зарегистрированных сервисов, module path, architecture profile, status, contracts, image и delivery flags.

Repository содержит несколько независимо разворачиваемых Go modules в одной Git history: `services/<name>`, `platform` и `contracts`. Корневой `go.work` предназначен для локальной разработки и repository checks, но не создаёт runtime-связь. Прямые imports между `services/*` запрещены. Изменение одного сервиса не расширяет scope на соседние, если не затронуты contracts, platform или repository-wide tooling.

Go version и tool versions сверяй с актуальными `go.work`, workflows и module files. Не полагайся на сохранённые здесь номера версий, если repository изменился.
