# Platform module

`platform` содержит только стабильные технические primitives с одинаковой семантикой и минимум двумя реальными consumers либо заранее утверждённый repository-wide baseline: config, logging, telemetry, middleware, health, graceful shutdown и test helpers.

Domain types, service DTO, business errors/use cases, service-specific repositories и speculative base abstractions запрещены. `platform` не импортирует `services/*`. Изменение публичного API требует проверки всех consumers и affected-service matrix; новый abstraction создаётся вместе с реальным consumer и тестами.
