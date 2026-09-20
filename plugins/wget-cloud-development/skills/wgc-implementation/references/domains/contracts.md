# Contracts

`contracts` — отдельный Go module и source of truth для Protobuf wire contracts и generation tooling. Generated files не редактируются вручную. Удаление или перенумерация field, изменение wire type или RPC — breaking; нужен новый versioned package и migration plan. Metadata, deadlines, status codes, idempotency и message-size limits тоже являются contract behavior.

Contract change всегда critical. Выполни `buf lint`, `buf breaking` относительно корректного base, воспроизводимую generation с чистым diff и consumer audit/tests. Пока существуют TypeScript consumers в legacy backend, совместимость и coordinated delivery проверяются в обоих repositories; это не разрешает менять второй repository без явного scope.
