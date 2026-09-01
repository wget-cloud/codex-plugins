# GitOps и deployment

DevOps меняет только Git source в `k8s`; direct `kubectl apply/edit/patch/delete/scale`, ручной Helm upgrade и bypass Argo CD запрещены.

Перед approval должны существовать immutable image/package identities, migration order, rendered diff, ExternalSecret references, NetworkPolicy/ingress, probes/resources, telemetry, rollback target и health criteria.

Human approval связывается с exact repository, commit, environment, image digest/tag и rendered diff. Любое изменение identity инвалидирует approval.

Deployment Agent не пишет код/manifests. Он выполняет только разрешённые publish/sync/observe действия, smoke и bounded observation. Финансовая/доменная история не удаляется rollback-ом; после committed fact применяется forward recovery.
