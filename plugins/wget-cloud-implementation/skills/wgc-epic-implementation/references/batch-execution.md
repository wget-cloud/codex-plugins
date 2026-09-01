# Волны и массовая реализация

## Построение DAG

Dependency edge задаётся contract/schema, data migration, package publication, service availability, test fixture или explicit issue dependency. Priority не создаёт dependency автоматически.

## Ready wave

Item ready, если его product acceptance однозначна, обязательные predecessors доставлены/доступны в текущей рабочей среде, repository/path scope свободен и нужные secrets/authority не требуются прямо сейчас.

## Concurrency conflict graph

Запрещай параллельные write slices, если они затрагивают один repository, один proto/schema/public export, один migration chain, один generated output или один GitOps values/application boundary. Read-only Explorer/Reviewer могут идти параллельно на независимых областях.

Начинай с минимальной волны. Увеличивай concurrency только после успешной первой интеграции и при наличии свободных agent slots. Project size не является основанием запускать все items сразу.

## Checkpoint

Для каждого item фиксируй objective progress: diff, tests, artifact, blocker. Сообщение «работаю» не прогресс. Первый stall → correction/rescope; повторный stall/scope drift → interrupt, inspect partial work, split/restart.

## Failure isolation

Failure одного item блокирует только его descendants и shared boundary. Независимые branches DAG могут продолжать работу, если integration baseline остаётся зелёным.
