import ast
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from urllib.parse import quote


PLUGIN_ROOT = Path(__file__).resolve().parents[2]
RUNNER_SOURCE = PLUGIN_ROOT / "scripts" / "ingress_recovery_runner.py"
MANIFEST_SOURCE = PLUGIN_ROOT / "scripts" / "ingress_recovery_manifest.json"
HOOK_SOURCE = PLUGIN_ROOT / "hooks" / "wgc_hooks.py"

CONTEXT = "twc-wise-finch"
TARGET_TAG = "twc-wise-finch-argocd-recovery-2026-08-20.2"
TARGET_TAG_OBJECT = "37c2ee42cb542d30ca200c06e1430d151428a70c"
TARGET_COMMIT = "6247abd4aec30e6a75aeba70123676019762f1a6"
PREVIOUS_TAG = "twc-wise-finch-argocd-recovery-2026-08-17.1"
PREVIOUS_TAG_OBJECT = "344a7e5f87e6c9212dd1ac22256336faad0eb002"
PREVIOUS_COMMIT = "925f7a2949c6ff50b76e55ccec80abdfff59178b"
RUNNER = "/usr/local/libexec/wget-cloud-ingress-recovery/promotion_runner.py"
MANIFEST = "/usr/local/libexec/wget-cloud-ingress-recovery/promotion-manifest.json"
CLI = "/usr/local/libexec/wget-cloud-ingress-recovery/argocd-v3.0.0-darwin-arm64"
KUBECONFIG = "/usr/local/etc/wget-cloud-ingress-recovery/twc-wise-finch.kubeconfig"
GIT_CREDENTIAL = "/usr/local/etc/wget-cloud-ingress-recovery/github-k8s-token"
GITHUB_API_BASE = "https://api.github.com"
GITHUB_REPOSITORY = "wget-cloud/k8s"
GITHUB_TOKEN = "github_pat_SYNTHETIC_SECRET_MUST_NEVER_LEAK"
ROOT_APP = "twc-wise-finch-cluster"
APPS = (
    ROOT_APP,
    "twc-wise-finch-ingress",
    "cert-manager",
    "traefik",
    "ingress-canary",
    "twc-wise-finch-ingress-issuer",
    "argocd-public",
)
PREVIOUS_STORAGE_OWNERS = (
    "twc-wise-finch-local-path-storage",
    "twc-wise-finch-local-path-smoke",
    "local-path-storage-smoke",
)
GITHUB_COMMIT_URL = (
    f"{GITHUB_API_BASE}/repos/{GITHUB_REPOSITORY}/git/commits/{TARGET_COMMIT}"
)
ENCODED_TARGET_TAG = quote(TARGET_TAG, safe="")
GITHUB_REF_REQUEST_URL = (
    f"{GITHUB_API_BASE}/repos/{GITHUB_REPOSITORY}/git/ref/tags/{ENCODED_TARGET_TAG}"
)
GITHUB_REF_CANONICAL_URL = (
    f"{GITHUB_API_BASE}/repos/{GITHUB_REPOSITORY}/git/refs/tags/{ENCODED_TARGET_TAG}"
)
MAX_GITHUB_RESPONSE_BYTES = 64 * 1024


def github_ref_payload():
    tag_url = (
        f"{GITHUB_API_BASE}/repos/{GITHUB_REPOSITORY}/git/tags/{TARGET_TAG_OBJECT}"
    )
    return {
        "ref": f"refs/tags/{TARGET_TAG}",
        "node_id": "REF_kwDOK8sYN7ByZWZzL3RhZ3MvcmVjb3Zlcnk",
        "url": GITHUB_REF_CANONICAL_URL,
        "object": {
            "sha": TARGET_TAG_OBJECT,
            "type": "tag",
            "url": tag_url,
        },
    }


def github_tag_payload():
    tag_url = (
        f"{GITHUB_API_BASE}/repos/{GITHUB_REPOSITORY}/git/tags/{TARGET_TAG_OBJECT}"
    )
    return {
        "node_id": "TA_kwDOK8sYN9oAKDM3YzJlZTQyY2I1NDJkMzA",
        "tag": TARGET_TAG,
        "sha": TARGET_TAG_OBJECT,
        "url": tag_url,
        "message": "Reviewed twc-wise-finch ingress recovery promotion",
        "tagger": {
            "name": "Wget Cloud Release",
            "email": "release@wget-cloud.invalid",
            "date": "2026-08-20T12:00:00Z",
        },
        "object": {
            "sha": TARGET_COMMIT,
            "type": "commit",
            "url": GITHUB_COMMIT_URL,
        },
        "verification": {
            "verified": False,
            "reason": "unsigned",
            "signature": None,
            "payload": None,
            "verified_at": None,
        },
    }
ESTEV_DARWIN_UUID = "FFFFEEEE-DDDD-CCCC-BBBB-AAAA000001F5"
SAFE_READ_ACL = [
    {
        "inherited": False,
        "principal": f"user:{ESTEV_DARWIN_UUID}",
        "type": "allow",
        "permissions": ["read", "readattr", "readextattr", "readsecurity"],
    }
]
ROUTER_APPROVAL_ID = TARGET_TAG
ROUTER_NOW = datetime(2026, 8, 17, 6, 2, tzinfo=timezone.utc)
ARGO_PREFIX = [CLI, "--core", "--kube-context", CONTEXT]
SOURCE_PATHS = {
    ROOT_APP: ["infrastructure/k8s/gitops/clusters/twc-wise-finch/root"],
    "twc-wise-finch-ingress": ["infrastructure/k8s/gitops/clusters/twc-wise-finch/bundles/ingress"],
    "cert-manager": ["infrastructure/k8s/charts/cert-manager"],
    "traefik": [
        "infrastructure/k8s/charts/traefik",
        ".",
        "infrastructure/k8s/components/clusters/twc-wise-finch/core/ingress-controller",
    ],
    "ingress-canary": ["infrastructure/k8s/components/clusters/twc-wise-finch/validation/ingress"],
    "twc-wise-finch-ingress-issuer": ["infrastructure/k8s/components/clusters/twc-wise-finch/core/cert-manager"],
    "argocd-public": ["infrastructure/k8s/components/clusters/twc-wise-finch/core/argocd-public"],
}
PROFILE_BUNDLES = {
    "core": "enabled",
    "local-path-smoke": "enabled",
    "controllers": "planned",
    "ingress": "enabled",
    "vault-restore": "planned",
    "eso-ready": "planned",
    "data": "planned",
    "apps": "planned",
    "full": "planned",
}
FORBIDDEN_BUNDLES = ["controllers", "vault-restore", "eso-ready", "data", "apps", "full"]


def object_digest(value):
    return hashlib.sha256(json.dumps(value, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def infrastructure_digest(value):
    return f"sha256:{object_digest(value)}"


def published_router_gate(dispositions=("create", "create"), router_id="router-wise-finch"):
    desired = [
        {
            "protocol": "tcp",
            "local": {"ip": "192.168.0.16", "port": "30080"},
            "public": {"ip": "72.56.0.250", "port": "80"},
        },
        {
            "protocol": "tcp",
            "local": {"ip": "192.168.0.16", "port": "30443"},
            "public": {"ip": "72.56.0.250", "port": "443"},
        },
    ]
    stable_ids = ["z-http-stable", "a-https-stable"]
    actions = []
    for disposition, item, stable_id in zip(dispositions, desired, stable_ids):
        if disposition == "create":
            actions.append(
                {
                    "disposition": "create",
                    "request": {
                        "method": "POST",
                        "path": f"/api/v1/routers/{router_id}/dnat-rules",
                        "body": item,
                    },
                    "response": {"ruleIdSemantics": "captureCreatedRuleId"},
                    "rollback": {
                        "method": "DELETE",
                        "path": f"/api/v1/routers/{router_id}/dnat-rules/{{created_dnat_id}}",
                        "createdByThisRunOnly": True,
                    },
                }
            )
        elif disposition == "adopt":
            actions.append(
                {
                    "disposition": "adopt",
                    "existingRuleId": stable_id,
                    "desiredRule": item,
                    "rollback": {"action": "preserve", "delete": False},
                }
            )
        else:
            raise AssertionError(f"unsupported fixture disposition: {disposition}")
    lineage = {
        "contractDigest": "sha256:" + "1" * 64,
        "routerSnapshotDigest": "sha256:" + "2" * 64,
        "ingressServiceDigest": "sha256:" + "3" * 64,
        "dnsSnapshotDigest": "sha256:" + "4" * 64,
        "readinessEvidenceDigest": "sha256:" + "5" * 64,
        "actionDigest": infrastructure_digest(actions),
    }
    router_plan = {
        "apiVersion": "infrastructure.wget-cloud/v1alpha1",
        "kind": "TimewebRouterRecoveryPlan",
        "metadata": {"name": CONTEXT},
        "spec": {
            "dryRun": True,
            "approvedForApply": False,
            "routerId": router_id,
            "actions": actions,
            **lineage,
            "finalDigest": infrastructure_digest(lineage),
        },
    }
    rules = [
        {
            "id": stable_ids[0],
            "localIp": "192.168.0.16",
            "localPort": "30080",
            "publicIp": "72.56.0.250",
            "publicPort": "80",
            "protocol": "tcp",
        },
        {
            "id": stable_ids[1],
            "localIp": "192.168.0.16",
            "localPort": "30443",
            "publicIp": "72.56.0.250",
            "publicPort": "443",
            "protocol": "tcp",
        },
    ]
    router_poststate = {
        "apiVersion": "infrastructure.wget-cloud/v1alpha1",
        "kind": "TimewebRouterRecoveryPoststate",
        "spec": {
            "observedAt": "2026-08-17T06:01:00Z",
            "readOnly": True,
            "routerId": router_id,
            "actionDigest": router_plan["spec"]["actionDigest"],
            "planFinalDigest": router_plan["spec"]["finalDigest"],
            "rules": rules,
        },
    }
    promotion_actions = [
        {
            "action": "sync",
            "application": "argocd-public",
            "sourcePaths": SOURCE_PATHS["argocd-public"],
            "targetRevision": TARGET_TAG,
            "tagObjectSha": TARGET_TAG_OBJECT,
            "commitSha": TARGET_COMMIT,
            "prune": False,
        }
    ]
    promotion_lineage = {
        "contractDigest": "sha256:" + "a" * 64,
        "liveSnapshotDigest": "sha256:" + "b" * 64,
        "revisionSnapshotDigest": "sha256:" + "c" * 64,
        "actionDigest": infrastructure_digest(promotion_actions),
        "routerPlanDigest": infrastructure_digest(router_plan),
        "routerPoststateDigest": infrastructure_digest(router_poststate),
    }
    promotion_plan = {
        "apiVersion": "infrastructure.wget-cloud/v1alpha1",
        "kind": "TimewebGitOpsPromotionPlan",
        "metadata": {"name": "twc-wise-finch-argocd-recovery"},
        "spec": {
            "stage": 7,
            "dryRun": True,
            "approvedForApply": False,
            "revision": {
                "tag": TARGET_TAG,
                "tagObjectSha": TARGET_TAG_OBJECT,
                "commitSha": TARGET_COMMIT,
            },
            "actions": promotion_actions,
            **promotion_lineage,
            "finalDigest": infrastructure_digest(promotion_lineage),
        },
    }
    return {
        "approvalId": ROUTER_APPROVAL_ID,
        "observedAt": "2026-08-17T06:00:00Z",
        "expiresAt": "2026-08-17T06:05:00Z",
        "routerPlan": router_plan,
        "routerPoststate": router_poststate,
        "promotionPlan": promotion_plan,
    }


def refresh_published_gate_lineage(gate):
    plan = gate["routerPlan"]
    plan["spec"]["actionDigest"] = infrastructure_digest(plan["spec"]["actions"])
    plan_fields = (
        "contractDigest",
        "routerSnapshotDigest",
        "ingressServiceDigest",
        "dnsSnapshotDigest",
        "readinessEvidenceDigest",
        "actionDigest",
    )
    plan["spec"]["finalDigest"] = infrastructure_digest(
        {key: plan["spec"][key] for key in plan_fields}
    )
    poststate = gate["routerPoststate"]
    poststate["spec"]["actionDigest"] = plan["spec"]["actionDigest"]
    poststate["spec"]["planFinalDigest"] = plan["spec"]["finalDigest"]
    promotion = gate["promotionPlan"]
    promotion["spec"]["actionDigest"] = infrastructure_digest(
        promotion["spec"]["actions"]
    )
    promotion["spec"]["routerPlanDigest"] = infrastructure_digest(plan)
    promotion["spec"]["routerPoststateDigest"] = infrastructure_digest(poststate)
    promotion_fields = (
        "contractDigest",
        "liveSnapshotDigest",
        "revisionSnapshotDigest",
        "actionDigest",
        "routerPlanDigest",
        "routerPoststateDigest",
    )
    promotion["spec"]["finalDigest"] = infrastructure_digest(
        {key: promotion["spec"][key] for key in promotion_fields}
    )
    return gate


def rules_digest(rules):
    normalized = sorted(
        rules,
        key=lambda item: (
            item["publicIp"],
            item["publicPort"],
            item["protocol"],
            item["localIp"],
            item["localPort"],
            item["id"],
        ),
    )
    return object_digest(normalized)


def router_foundation():
    k8s_plan = {
        "path": "infrastructure/k8s/components/clusters/twc-wise-finch/dns/router-recovery.yaml",
        "tagObjectSha": TARGET_TAG_OBJECT,
        "commitSha": TARGET_COMMIT,
        "offlinePlanOnly": True,
    }
    dns_plan = {
        "path": "infrastructure/k8s/components/clusters/twc-wise-finch/dns/cutover.yaml",
        "host": "argocd.wget-cloud.ru",
        "type": "A",
        "value": "72.56.0.250",
        "offlinePlanOnly": True,
    }
    return {
        "observedAt": "2026-08-17T06:00:00Z",
        "expiresAt": "2026-08-17T06:05:00Z",
        "stage5": {
            "application": "ingress-canary",
            "reportedRevision": TARGET_TAG_OBJECT,
            "commitSha": TARGET_COMMIT,
            "sync": "Synced",
            "health": "Healthy",
            "operation": "Succeeded",
        },
        "service": {
            "apiVersion": "v1",
            "kind": "Service",
            "namespace": "traefik",
            "name": "traefik",
            "type": "NodePort",
            "ports": [
                {"name": "web", "protocol": "TCP", "port": 80, "nodePort": 30080},
                {"name": "websecure", "protocol": "TCP", "port": 443, "nodePort": 30443},
            ],
        },
        "endpointSlice": {
            "apiVersion": "discovery.k8s.io/v1",
            "kind": "EndpointSlice",
            "namespace": "traefik",
            "serviceName": "traefik",
            "addresses": ["192.168.0.16"],
            "ready": True,
        },
        "nodePortProbes": [
            {"address": "192.168.0.16:30080", "protocol": "tcp", "reachable": True},
            {"address": "192.168.0.16:30443", "protocol": "tcp", "reachable": True},
        ],
        "dns": {
            "host": "argocd.wget-cloud.ru",
            "type": "A",
            "expected": "72.56.0.250",
            "observed": "72.56.0.250",
        },
        "offlinePlans": {
            "k8sRouterPlanSha256": object_digest(k8s_plan),
            "dnsPlanSha256": object_digest(dns_plan),
            "k8sRouterPlan": k8s_plan,
            "dnsPlan": dns_plan,
        },
    }


def router_gate():
    foundation = router_foundation()
    desired = [
        {
            "protocol": "tcp",
            "local": {"ip": "192.168.0.16", "port": "30080"},
            "public": {"ip": "72.56.0.250", "port": "80"},
        },
        {
            "protocol": "tcp",
            "local": {"ip": "192.168.0.16", "port": "30443"},
            "public": {"ip": "72.56.0.250", "port": "443"},
        },
    ]
    rules = [
        {
            "id": "dnat-http",
            "localIp": "192.168.0.16",
            "localPort": "30080",
            "protocol": "tcp",
            "publicIp": "72.56.0.250",
            "publicPort": "80",
        },
        {
            "id": "dnat-https",
            "localIp": "192.168.0.16",
            "localPort": "30443",
            "protocol": "tcp",
            "publicIp": "72.56.0.250",
            "publicPort": "443",
        },
    ]
    base = {
        "approvalId": ROUTER_APPROVAL_ID,
        "routerId": "router-7fa2b9c1",
        "observedAt": "2026-08-17T06:00:00Z",
        "expiresAt": "2026-08-17T06:05:00Z",
        "preStateSha256": "4" * 64,
        "planSha256": object_digest(desired),
        "foundationEvidence": foundation,
        "foundationSha256": object_digest(foundation),
        "adoptedIds": ["dnat-http"],
        "createdIds": ["dnat-https"],
        "rules": rules,
    }
    action = {
        key: base[key]
        for key in (
            "approvalId",
            "routerId",
            "preStateSha256",
            "planSha256",
            "foundationSha256",
            "adoptedIds",
            "createdIds",
        )
    }
    base["actionDigest"] = object_digest(action)
    base["postStateSha256"] = rules_digest(rules)
    base["planFinalDigest"] = object_digest(
        {
            "actionDigest": base["actionDigest"],
            "postStateSha256": base["postStateSha256"],
            "rules": rules,
        }
    )
    return base


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def policy():
    artifact = lambda sha, mode: {
        "sha256": sha,
        "owner": "root",
        "group": "wheel",
        "mode": mode,
        "acl": [],
        "linkCount": 1,
    }
    return {
        "schemaVersion": 1,
        "installedPaths": {
            "runner": RUNNER,
            "cli": CLI,
            "manifest": MANIFEST,
            "kubeconfig": KUBECONFIG,
        },
        "paths": {"gitCredential": GIT_CREDENTIAL},
        "artifacts": {
            "runner": artifact("1" * 64, "0555"),
            "cli": artifact("2" * 64, "0555"),
            "manifest": {
                "owner": "root",
                "group": "wheel",
                "mode": "0444",
                "acl": [],
                "linkCount": 1,
            },
            "kubeconfig": {**artifact("3" * 64, "0400"), "acl": deepcopy(SAFE_READ_ACL)},
            "gitCredential": {
                "owner": "root",
                "group": "wheel",
                "mode": "0600",
                "acl": deepcopy(SAFE_READ_ACL),
                "linkCount": 1,
            },
        },
        "cluster": {
            "context": CONTEXT,
            "rootApplication": ROOT_APP,
            "previousTagObject": PREVIOUS_TAG_OBJECT,
            "previousCommit": PREVIOUS_COMMIT,
            "targetTag": TARGET_TAG,
            "targetTagObject": TARGET_TAG_OBJECT,
            "targetCommit": TARGET_COMMIT,
        },
        "stages": [
            {"stage": index, "name": name, "operation": operation, "sourcePaths": deepcopy(SOURCE_PATHS[name])}
            for index, (name, operation) in enumerate(
                (
                    (ROOT_APP, "root-promote"),
                    ("twc-wise-finch-ingress", "ingress-owner"),
                    ("cert-manager", "sync"),
                    ("traefik", "sync"),
                    ("ingress-canary", "sync"),
                    ("twc-wise-finch-ingress-issuer", "sync"),
                    ("argocd-public", "router-gated-sync"),
                ),
                start=1,
            )
        ],
        "profileBundles": deepcopy(PROFILE_BUNDLES),
        "forbiddenBundles": list(FORBIDDEN_BUNDLES),
    }


def application_contracts():
    repo = "ssh://git@github.com/wget-cloud/k8s"
    destination = lambda namespace: {
        "server": "https://kubernetes.default.svc",
        "namespace": namespace,
    }
    source = lambda path, **extra: {
        "repoURL": repo,
        "targetRevision": TARGET_TAG,
        "path": path,
        **extra,
    }
    return {
        ROOT_APP: {
            "metadata": {"labels": {"wget-cloud.io/profile": CONTEXT}, "annotations": {}},
            "project": "default",
            "destination": destination("argocd"),
            "source": source(SOURCE_PATHS[ROOT_APP][0], directory={"recurse": True}),
            "syncPolicy": {"syncOptions": ["CreateNamespace=true"]},
            "trackingOwner": None,
        },
        "twc-wise-finch-ingress": {
            "metadata": {
                "labels": {"wget-cloud.io/profile": CONTEXT, "wget-cloud.io/bundle": "ingress"},
                "annotations": {"argocd.argoproj.io/sync-wave": "-40"},
            },
            "project": "wget-cloud",
            "destination": destination("argocd"),
            "source": source(SOURCE_PATHS["twc-wise-finch-ingress"][0], directory={"recurse": True}),
            "syncPolicy": {"syncOptions": ["CreateNamespace=true"]},
            "trackingOwner": ROOT_APP,
        },
        "cert-manager": {
            "metadata": {
                "labels": {"app.kubernetes.io/component": "cert-manager", "wget-cloud.io/profile": CONTEXT},
                "annotations": {"argocd.argoproj.io/sync-wave": "-12"},
            },
            "project": "wget-cloud",
            "destination": destination("cert-manager"),
            "source": source(
                SOURCE_PATHS["cert-manager"][0],
                helm={
                    "releaseName": "cert-manager",
                    "valueFiles": ["../../components/clusters/twc-wise-finch/core/cert-manager/values.yaml"],
                },
            ),
            "syncPolicy": {"syncOptions": ["CreateNamespace=true", "ServerSideApply=true"]},
            "trackingOwner": "twc-wise-finch-ingress",
        },
        "traefik": {
            "metadata": {"labels": {}, "annotations": {"argocd.argoproj.io/sync-wave": "-10"}},
            "project": "wget-cloud",
            "destination": destination("traefik"),
            "sources": [
                source(
                    SOURCE_PATHS["traefik"][0],
                    helm={
                        "releaseName": "traefik",
                        "skipCrds": True,
                        "valueFiles": ["$values/infrastructure/k8s/components/clusters/twc-wise-finch/core/ingress-controller/values.yaml"],
                    },
                ),
                source(".", ref="values"),
                source(SOURCE_PATHS["traefik"][2], directory={"include": "ingress-class.yaml"}),
            ],
            "syncPolicy": {"syncOptions": ["CreateNamespace=true", "ServerSideApply=true"]},
            "trackingOwner": "twc-wise-finch-ingress",
        },
        "ingress-canary": {
            "metadata": {"labels": {}, "annotations": {"argocd.argoproj.io/sync-wave": "-9"}},
            "project": "wget-cloud",
            "destination": destination("traefik"),
            "source": source(SOURCE_PATHS["ingress-canary"][0]),
            "syncPolicy": {"syncOptions": ["CreateNamespace=true", "ServerSideApply=true"]},
            "trackingOwner": "twc-wise-finch-ingress",
        },
        "twc-wise-finch-ingress-issuer": {
            "metadata": {
                "labels": {"wget-cloud.io/profile": CONTEXT},
                "annotations": {"argocd.argoproj.io/sync-wave": "-8"},
            },
            "project": "wget-cloud",
            "destination": destination("cert-manager"),
            "source": source(SOURCE_PATHS["twc-wise-finch-ingress-issuer"][0], directory={"include": "issuer.yaml"}),
            "syncPolicy": {"syncOptions": ["CreateNamespace=true", "ServerSideApply=true"]},
            "trackingOwner": "twc-wise-finch-ingress",
        },
        "argocd-public": {
            "metadata": {
                "labels": {"wget-cloud.io/profile": CONTEXT},
                "annotations": {"argocd.argoproj.io/sync-wave": "-7"},
            },
            "project": "wget-cloud",
            "destination": destination("argocd"),
            "source": source(SOURCE_PATHS["argocd-public"][0]),
            "syncPolicy": {"syncOptions": ["ServerSideApply=true"]},
            "trackingOwner": "twc-wise-finch-ingress",
        },
    }
def evidence(contract):
    result = {}
    for path in (
        "/",
        "/usr",
        "/usr/local",
        "/usr/local/libexec",
        "/usr/local/libexec/wget-cloud-ingress-recovery",
        "/usr/local/etc",
        "/usr/local/etc/wget-cloud-ingress-recovery",
    ):
        result[path] = {
            "path": path,
            "canonicalPath": path,
            "kind": "directory",
            "owner": "root",
            "group": "wheel",
            "mode": "0755",
            "acl": [],
            "linkCount": 2,
            "symlink": False,
            "effectiveWritable": False,
            "descriptorVerified": True,
            "pathIdentity": {"device": 1, "inode": len(result) + 1},
            "descriptorIdentity": {"device": 1, "inode": len(result) + 1},
            "postDescriptorIdentity": {"device": 1, "inode": len(result) + 1},
        }
    installed = {
        **contract["installedPaths"],
        "gitCredential": contract["paths"]["gitCredential"],
    }
    for name, path in installed.items():
        item = contract["artifacts"][name]
        result[path] = {
            "path": path,
            "canonicalPath": path,
            "kind": "file",
            "owner": item["owner"],
            "group": item["group"],
            "mode": item["mode"],
            "acl": deepcopy(item["acl"]),
            "linkCount": item["linkCount"],
            "symlink": False,
            "effectiveWritable": False,
            "descriptorVerified": True,
            "pathIdentity": {"device": 1, "inode": len(result) + 1},
            "descriptorIdentity": {"device": 1, "inode": len(result) + 1},
            "postDescriptorIdentity": {"device": 1, "inode": len(result) + 1},
        }
        if "sha256" in item:
            result[path].update(
                sha256=item["sha256"],
                descriptorSha256=item["sha256"],
                postDescriptorSha256=item["sha256"],
            )
    return result


def application(
    name,
    source_revision,
    status_revision,
    sync="OutOfSync",
    health="Healthy",
    operation_phase="Succeeded",
    commit_revision=None,
):
    del commit_revision
    contract = deepcopy(application_contracts()[name])
    metadata_contract = contract.pop("metadata")
    tracking_owner = contract.pop("trackingOwner")
    if tracking_owner is not None:
        metadata_contract["annotations"] = {
            **metadata_contract["annotations"],
            "argocd.argoproj.io/tracking-id": (
                f"{tracking_owner}:argoproj.io/Application:argocd/{name}"
            ),
        }
    sources = contract.get("sources") or [contract.get("source")]
    for source_item in sources:
        source_item["targetRevision"] = source_revision
    sync_state = {"status": sync}
    sync_result = {}
    if status_revision is not None:
        if name == "traefik":
            sync_state["revisions"] = [status_revision] * 3
            sync_result = {"revisions": [status_revision] * 3}
        else:
            sync_state["revision"] = status_revision
            sync_result = {"revision": status_revision}
    status = {
        "sync": sync_state,
        "health": {"status": health},
        "conditions": [],
    }
    if operation_phase is not None:
        status["operationState"] = {
            "phase": operation_phase,
            "syncResult": sync_result,
        }
    return {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Application",
        "metadata": {"name": name, "namespace": "argocd", **metadata_contract},
        "spec": contract,
        "status": status,
    }


def published_live_scope(stage, pending_resolved=None, historical_terminal=False):
    if stage == 1:
        return [
            application(
                ROOT_APP,
                PREVIOUS_TAG,
                PREVIOUS_TAG_OBJECT,
                sync="OutOfSync",
                health="Healthy",
                operation_phase=None,
                commit_revision=PREVIOUS_COMMIT,
            )
        ]
    scope = APPS[:2] if stage == 2 else APPS
    result = []
    for index, name in enumerate(scope):
        completed = index < stage - 1
        resolved_pending = (
            index % 2 == 1
            if pending_resolved is None
            else bool(pending_resolved.get(name, False))
        )
        operation_phase = "Succeeded" if completed else None
        result.append(
            application(
                name,
                TARGET_TAG,
                TARGET_TAG_OBJECT if completed or resolved_pending else None,
                sync="Synced" if completed else "OutOfSync",
                health="Healthy" if completed else "Missing",
                operation_phase=operation_phase,
                commit_revision=TARGET_COMMIT if completed or resolved_pending else None,
            )
        )
        if not completed and historical_terminal:
            item = result[-1]
            sources = item["spec"].get("sources") or [item["spec"]["source"]]
            historical = PREVIOUS_TAG_OBJECT
            item["status"]["operationState"] = {
                "phase": "Succeeded",
                "finishedAt": "2026-08-17T05:59:30Z",
                "syncResult": (
                    {"revisions": [historical] * len(sources)}
                    if len(sources) > 1
                    else {"revision": historical}
                ),
            }
    return result


class IngressRecoveryRunnerTest(unittest.TestCase):
    def module(self):
        self.assertTrue(
            RUNNER_SOURCE.is_file(),
            "separate ingress_recovery_runner.py contract is not implemented",
        )
        spec = importlib.util.spec_from_file_location("ingress_recovery_runner", RUNNER_SOURCE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(hasattr(module, "PolicyError"))
        if hasattr(module, "_attest_tag"):
            module._production_attest_tag = module._attest_tag
            module._attest_tag = mock.Mock()
        if hasattr(module, "read_git_credential_fd"):
            module._production_read_git_credential_fd = module.read_git_credential_fd
            module.read_git_credential_fd = mock.Mock(return_value=GITHUB_TOKEN)
        return module

    def assert_policy_error(self, module, callback):
        with self.assertRaises(module.PolicyError):
            callback()

    def test_source_manifest_is_a_separate_exact_promotion_contract(self):
        module = self.module()
        self.assertTrue(MANIFEST_SOURCE.is_file(), "ingress recovery manifest is missing")
        source = json.loads(MANIFEST_SOURCE.read_text(encoding="utf-8"))
        self.assertEqual(
            {item["name"]: item.get("sourcePaths") for item in source.get("stages", [])},
            SOURCE_PATHS,
        )
        self.assertEqual(source.get("profileBundles"), PROFILE_BUNDLES)
        self.assertEqual(source.get("forbiddenBundles"), FORBIDDEN_BUNDLES)
        module.validate_manifest(source)
        self.assertEqual(source["schemaVersion"], 1)
        self.assertEqual(source["installedPaths"], policy()["installedPaths"])
        self.assertEqual(source["paths"], {"gitCredential": GIT_CREDENTIAL})
        self.assertEqual(
            [(item["stage"], item["name"], item["operation"]) for item in source["stages"]],
            [
                (1, ROOT_APP, "root-promote"),
                (2, "twc-wise-finch-ingress", "ingress-owner"),
                (3, "cert-manager", "sync"),
                (4, "traefik", "sync"),
                (5, "ingress-canary", "sync"),
                (6, "twc-wise-finch-ingress-issuer", "sync"),
                (7, "argocd-public", "router-gated-sync"),
            ],
        )
        self.assertEqual(
            source["cluster"],
            {
                "context": CONTEXT,
                "rootApplication": ROOT_APP,
                "previousTagObject": PREVIOUS_TAG_OBJECT,
                "previousCommit": PREVIOUS_COMMIT,
                "targetTag": TARGET_TAG,
                "targetTagObject": TARGET_TAG_OBJECT,
                "targetCommit": TARGET_COMMIT,
            },
        )
        self.assertEqual(source["artifacts"]["kubeconfig"]["acl"], SAFE_READ_ACL)
        self.assertEqual(
            source["artifacts"]["gitCredential"],
            {
                "owner": "root",
                "group": "wheel",
                "mode": "0600",
                "acl": SAFE_READ_ACL,
                "linkCount": 1,
            },
        )
        self.assertNotIn("sha256", source["artifacts"]["gitCredential"])

    def test_all_seven_live_applications_match_the_exact_normalized_tag_contract(self):
        module = self.module()
        validator = getattr(module, "validate_application_contract", None)
        self.assertIsNotNone(validator, "exact normalized Application contract validator is missing")
        contracts = application_contracts()
        self.assertEqual(tuple(contracts), APPS)
        for name in APPS:
            live = application(name, TARGET_TAG, TARGET_TAG_OBJECT, sync="Synced", commit_revision=TARGET_COMMIT)
            with self.subTest(app=name):
                normalized = validator(live, name, contracts[name])
                self.assertEqual(
                    normalized,
                    {
                        "name": name,
                        "reportedRevision": TARGET_TAG_OBJECT,
                        "commitSha": TARGET_COMMIT,
                        "sourceRevisions": [TARGET_TAG] * (3 if name == "traefik" else 1),
                        "reportedRevisions": [TARGET_TAG_OBJECT] * (3 if name == "traefik" else 1),
                        "sync": "Synced",
                        "health": "Healthy",
                        "operation": "Succeeded",
                        "trackingOwner": contracts[name]["trackingOwner"],
                    },
                )

                raw = deepcopy(live)
                raw["metadata"].update(
                    {
                        "uid": f"00000000-0000-4000-8000-{APPS.index(name):012d}",
                        "resourceVersion": "184467",
                        "generation": 7,
                        "creationTimestamp": "2026-08-15T10:00:00Z",
                        "managedFields": [
                            {
                                "manager": "argocd-application-controller",
                                "operation": "Update",
                                "apiVersion": "argoproj.io/v1alpha1",
                                "time": "2026-08-17T06:00:00Z",
                                "fieldsType": "FieldsV1",
                                "fieldsV1": {"f:status": {}},
                            }
                        ],
                    }
                )
                raw["metadata"].setdefault("annotations", {})[
                    "kubectl.kubernetes.io/last-applied-configuration"
                ] = json.dumps(
                    {
                        "apiVersion": "argoproj.io/v1alpha1",
                        "kind": "Application",
                        "metadata": {"name": name, "namespace": "argocd"},
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                )
                tracking_owner = contracts[name]["trackingOwner"]
                if tracking_owner is not None:
                    raw["metadata"]["annotations"].pop(
                        "argocd.argoproj.io/tracking-id", None
                    )
                    raw["metadata"].setdefault("labels", {})[
                        "argocd.argoproj.io/instance"
                    ] = tracking_owner
                self.assertEqual(
                    validator(raw, name, contracts[name]),
                    normalized,
                    "server-owned Kubernetes metadata must be normalized away",
                )

            for case, mutate in (
                ("path", lambda value: (value["spec"].get("source") or value["spec"]["sources"][0]).update(path="attacker")),
                (
                    "project",
                    lambda value: value["spec"].update(
                        project="wget-cloud" if value["spec"]["project"] == "default" else "default"
                    ),
                ),
                ("destination", lambda value: value["spec"]["destination"].update(namespace="default")),
                ("label", lambda value: value["metadata"].setdefault("labels", {}).update({"unexpected": "owner"})),
                ("annotation", lambda value: value["metadata"].setdefault("annotations", {}).update({"unexpected": "true"})),
                ("automated", lambda value: value["spec"]["syncPolicy"].update(automated={"prune": True})),
                ("prune-option", lambda value: value["spec"]["syncPolicy"]["syncOptions"].append("Prune=true")),
            ):
                drifted = deepcopy(live)
                mutate(drifted)
                with self.subTest(app=name, drift=case):
                    self.assert_policy_error(module, lambda drifted=drifted, name=name: validator(drifted, name, contracts[name]))

        traefik = application("traefik", TARGET_TAG, TARGET_TAG_OBJECT, sync="Synced", commit_revision=TARGET_COMMIT)
        traefik["spec"]["sources"].reverse()
        self.assert_policy_error(module, lambda: validator(traefik, "traefik", contracts["traefik"]))

    def test_stage1_accepts_realistic_full_last_applied_and_absent_conditions_but_rejects_drift(self):
        module = self.module()
        validator = module.validate_application_contract
        contract = deepcopy(application_contracts()[ROOT_APP])
        contract["source"]["targetRevision"] = PREVIOUS_TAG
        live = application(
            ROOT_APP,
            PREVIOUS_TAG,
            PREVIOUS_TAG_OBJECT,
            sync="OutOfSync",
            health="Healthy",
            operation_phase=None,
            commit_revision=PREVIOUS_COMMIT,
        )
        full_last_applied = {
            "apiVersion": live["apiVersion"],
            "kind": live["kind"],
            "metadata": {
                "name": ROOT_APP,
                "namespace": "argocd",
                "labels": deepcopy(contract["metadata"]["labels"]),
            },
            "spec": deepcopy(live["spec"]),
        }
        live["metadata"].setdefault("annotations", {})[
            "kubectl.kubernetes.io/last-applied-configuration"
        ] = json.dumps(full_last_applied, separators=(",", ":"), sort_keys=True)
        expected = {
            "name": ROOT_APP,
            "reportedRevision": PREVIOUS_TAG_OBJECT,
            "reportedRevisions": [PREVIOUS_TAG_OBJECT],
            "commitSha": PREVIOUS_COMMIT,
            "sourceRevisions": [PREVIOUS_TAG],
            "sync": "OutOfSync",
            "health": "Healthy",
            "operation": None,
            "trackingOwner": None,
        }
        self.assertEqual(validator(live, ROOT_APP, contract), expected)

        no_conditions = deepcopy(live)
        no_conditions["status"].pop("conditions")
        self.assertEqual(
            validator(no_conditions, ROOT_APP, contract),
            expected,
            "an absent Argo status.conditions field is equivalent to an empty list",
        )

        malformed = deepcopy(live)
        malformed["metadata"]["annotations"][
            "kubectl.kubernetes.io/last-applied-configuration"
        ] = "{not-json"
        self.assert_policy_error(
            module,
            lambda: validator(malformed, ROOT_APP, contract),
        )
        user_drift = deepcopy(live)
        user_drift["metadata"]["annotations"]["attacker.example/owner"] = "true"
        self.assert_policy_error(
            module,
            lambda: validator(user_drift, ROOT_APP, contract),
        )

    def test_stage_live_scope_matches_published_promotion_validator_semantics(self):
        module = self.module()
        validator = getattr(module, "validate_stage_live_scope", None)
        self.assertIsNotNone(
            validator,
            "published seven-Application live-scope validator is missing",
        )
        for stage in range(1, 8):
            live = published_live_scope(stage)
            with self.subTest(stage=stage):
                normalized = validator(stage, live, policy())
                expected_names = list(APPS[:1] if stage == 1 else APPS[:2] if stage == 2 else APPS)
                self.assertEqual([item["name"] for item in normalized], expected_names)
                if stage == 1:
                    root = normalized[0]
                    self.assertEqual(root["reportedRevision"], PREVIOUS_TAG_OBJECT)
                    self.assertEqual(root["commitSha"], PREVIOUS_COMMIT)
                    self.assertEqual((root["sync"], root["health"]), ("OutOfSync", "Healthy"))
                    self.assertIsNone(root["operation"])
                    continue
                for index, item in enumerate(normalized):
                    if index < stage - 1:
                        self.assertEqual(
                            (item["sync"], item["health"], item["operation"]),
                            ("Synced", "Healthy", "Succeeded"),
                        )
                        self.assertEqual(
                            (item["reportedRevision"], item["commitSha"]),
                            (TARGET_TAG_OBJECT, TARGET_COMMIT),
                        )
                    else:
                        self.assertEqual(
                            (item["sync"], item["health"], item["operation"]),
                            ("OutOfSync", "Missing", None),
                        )
                        self.assertIn(
                            (item.get("reportedRevision"), item.get("commitSha")),
                            ((None, None), (TARGET_TAG_OBJECT, TARGET_COMMIT)),
                        )

        for stage in range(2, 8):
            names = APPS[:2] if stage == 2 else APPS
            pending = names[stage - 1 :]
            variants = [{name: False for name in pending}, {name: True for name in pending}]
            variants.extend(
                {
                    candidate: candidate == selected
                    for candidate in pending
                }
                for selected in pending
            )
            for resolved in variants:
                values = published_live_scope(stage, pending_resolved=resolved)
                with self.subTest(stage=stage, resolved=resolved):
                    normalized = validator(stage, values, policy())
                    for item in normalized[stage - 1 :]:
                        expected = (
                            (TARGET_TAG_OBJECT, TARGET_COMMIT)
                            if resolved[item["name"]]
                            else (None, None)
                        )
                        self.assertEqual(
                            (item.get("reportedRevision"), item.get("commitSha")),
                            expected,
                        )

            historical = published_live_scope(
                stage,
                pending_resolved={name: True for name in pending},
                historical_terminal=True,
            )
            normalized = validator(stage, historical, policy())
            self.assertTrue(
                all(item["operation"] is None for item in normalized[stage - 1 :]),
                "terminal historical Argo operationState is not an active operation",
            )

        current_completed = published_live_scope(
            4,
            pending_resolved={name: True for name in APPS[3:]},
        )
        current_completed[3] = application(
            "traefik",
            TARGET_TAG,
            TARGET_TAG_OBJECT,
            sync="Synced",
            health="Healthy",
            operation_phase="Succeeded",
            commit_revision=TARGET_COMMIT,
        )
        self.assertEqual(
            validator(4, current_completed, policy())[3]["operation"],
            "Succeeded",
            "only the current stage may already be completed for an idempotent rerun",
        )
        future_completed = deepcopy(current_completed)
        future_completed[4] = application(
            "ingress-canary",
            TARGET_TAG,
            TARGET_TAG_OBJECT,
            sync="Synced",
            health="Healthy",
            operation_phase="Succeeded",
            commit_revision=TARGET_COMMIT,
        )
        self.assert_policy_error(
            module,
            lambda: validator(4, future_completed, policy()),
        )

        for case, stage, mutate in (
            ("future-app-missing", 3, lambda values: values.pop()),
            (
                "completed-not-succeeded",
                4,
                lambda values: values[1]["status"]["operationState"].update(phase="Running"),
            ),
            (
                "pending-operation-present",
                5,
                lambda values: values[5]["status"].update(
                    operationState={"phase": "Running", "syncResult": {}}
                ),
            ),
            (
                "pending-terminal-misclassified-active",
                4,
                lambda values: (
                    values[3]["status"]["health"].update(status="Healthy"),
                    values[3]["status"].update(
                        operationState={
                            "phase": "Succeeded",
                            "syncResult": {"revisions": [TARGET_TAG_OBJECT] * 3},
                        }
                    ),
                ),
            ),
        ):
            values = published_live_scope(stage)
            mutate(values)
            with self.subTest(case=case):
                self.assert_policy_error(
                    module,
                    lambda values=values, stage=stage: validator(stage, values, policy()),
                )

        normalized_pending = {
            "name": "cert-manager",
            "reportedRevision": None,
            "reportedRevisions": [None],
            "commitSha": None,
            "sourceRevisions": [TARGET_TAG],
            "sync": "OutOfSync",
            "health": "Missing",
            "operation": None,
            "trackingOwner": "twc-wise-finch-ingress",
        }
        for present_field, absent_field, present_value in (
            ("reportedRevision", "commitSha", TARGET_TAG_OBJECT),
            ("commitSha", "reportedRevision", TARGET_COMMIT),
        ):
            one_sided = deepcopy(normalized_pending)
            one_sided[present_field] = present_value
            one_sided[absent_field] = None
            with self.subTest(
                case="pending-one-sided-revision",
                present_field=present_field,
            ):
                self.assert_policy_error(
                    module,
                    lambda one_sided=one_sided: module.classify_stage_state(
                        3, one_sided, policy()
                    ),
                )

    def test_revision_normalization_distinguishes_reported_tag_object_from_peeled_commit(self):
        module = self.module()
        normalizer = getattr(module, "normalize_application_state", None)
        classifier = getattr(module, "classify_stage_state", None)
        self.assertIsNotNone(normalizer)
        self.assertIsNotNone(classifier)
        complete = application(ROOT_APP, TARGET_TAG, TARGET_TAG_OBJECT, sync="Synced", commit_revision=TARGET_COMMIT)
        revision_map = {
            TARGET_TAG_OBJECT: TARGET_COMMIT,
            PREVIOUS_TAG_OBJECT: PREVIOUS_COMMIT,
        }
        normalized = normalizer(complete, policy(), revision_map)
        self.assertEqual(normalized["reportedRevision"], TARGET_TAG_OBJECT)
        self.assertEqual(normalized["commitSha"], TARGET_COMMIT)
        self.assertEqual(classifier(1, normalized, policy()), "completed")

        completed_terminal = deepcopy(complete)
        completed_terminal["status"]["operationState"][
            "finishedAt"
        ] = "2026-08-17T06:00:30Z"
        completed_normalized = normalizer(
            completed_terminal, policy(), revision_map
        )
        self.assertEqual(
            completed_normalized["operation"],
            "Succeeded",
            "a finished current-target Argo operation remains the completed operation",
        )
        self.assertEqual(
            classifier(1, completed_normalized, policy()),
            "completed",
        )

        same_target_historical_pending = application(
            "cert-manager",
            TARGET_TAG,
            TARGET_TAG_OBJECT,
            sync="OutOfSync",
            health="Missing",
            operation_phase=None,
            commit_revision=TARGET_COMMIT,
        )
        same_target_historical_pending["status"]["operationState"] = {
            "phase": "Succeeded",
            "finishedAt": "2026-08-17T05:59:30Z",
            "syncResult": {"revision": TARGET_TAG_OBJECT},
        }
        same_target_pending_normalized = normalizer(
            same_target_historical_pending, policy(), revision_map
        )
        self.assertIsNone(
            same_target_pending_normalized["operation"],
            "a terminal result is historical while the live app is OutOfSync/Missing",
        )
        self.assertEqual(
            classifier(3, same_target_pending_normalized, policy()),
            "pending",
        )

        same_target_completed = deepcopy(same_target_historical_pending)
        same_target_completed["status"]["sync"]["status"] = "Synced"
        same_target_completed["status"]["health"]["status"] = "Healthy"
        same_target_completed_normalized = normalizer(
            same_target_completed, policy(), revision_map
        )
        self.assertEqual(
            same_target_completed_normalized["operation"],
            "Succeeded",
            "the same terminal result is current for a Synced/Healthy app",
        )
        self.assertEqual(
            classifier(3, same_target_completed_normalized, policy()),
            "completed",
        )

        historical_pending = application(
            "cert-manager",
            TARGET_TAG,
            TARGET_TAG_OBJECT,
            sync="OutOfSync",
            health="Missing",
            operation_phase=None,
            commit_revision=TARGET_COMMIT,
        )
        historical_pending["status"]["operationState"] = {
            "phase": "Succeeded",
            "finishedAt": "2026-08-17T05:59:30Z",
            "syncResult": {"revision": PREVIOUS_TAG_OBJECT},
        }
        historical_normalized = normalizer(
            historical_pending, policy(), revision_map
        )
        self.assertIsNone(historical_normalized["operation"])
        self.assertEqual(
            classifier(3, historical_normalized, policy()),
            "pending",
        )
        historical_not_pending = deepcopy(historical_pending)
        historical_not_pending["status"]["sync"]["status"] = "Synced"
        historical_not_pending["status"]["health"]["status"] = "Healthy"
        invalid_historical = normalizer(
            historical_not_pending, policy(), revision_map
        )
        self.assert_policy_error(
            module,
            lambda: classifier(3, invalid_historical, policy()),
        )

        old = application(
            ROOT_APP,
            PREVIOUS_TAG,
            PREVIOUS_TAG_OBJECT,
            sync="OutOfSync",
            health="Healthy",
            operation_phase=None,
            commit_revision=PREVIOUS_COMMIT,
        )
        self.assertEqual(classifier(1, normalizer(old, policy(), revision_map), policy()), "pending")
        self.assert_policy_error(module, lambda: classifier(2, normalizer(old, policy(), revision_map), policy()))

        mixed_lineage = application(
            ROOT_APP,
            PREVIOUS_TAG,
            TARGET_TAG_OBJECT,
            sync="OutOfSync",
            health="Healthy",
            operation_phase=None,
            commit_revision=TARGET_COMMIT,
        )
        self.assert_policy_error(
            module,
            lambda: classifier(
                1,
                normalizer(mixed_lineage, policy(), revision_map),
                policy(),
            ),
        )

        for case, mutate in (
            (
                "unresolved",
                lambda value: (
                    value["status"]["sync"].pop("revision"),
                    value["status"]["operationState"]["syncResult"].pop("revision"),
                ),
            ),
            ("unknown-reported", lambda value: value["status"]["sync"].update(revision="a" * 40)),
            ("running", lambda value: value["status"]["operationState"].update(phase="Running")),
            ("failed", lambda value: value["status"]["operationState"].update(phase="Failed")),
        ):
            candidate = deepcopy(complete)
            mutate(candidate)
            with self.subTest(case=case):
                self.assert_policy_error(module, lambda candidate=candidate: normalizer(candidate, policy(), revision_map))

    def test_manifest_rejects_unknown_apps_mutable_revisions_prune_and_selectors(self):
        module = self.module()
        candidates = {}
        mutable = policy()
        mutable["cluster"]["targetTag"] = "main"
        candidates["mutable-revision"] = mutable
        lightweight = policy()
        lightweight["cluster"]["targetTagObject"] = TARGET_COMMIT
        candidates["lightweight-tag"] = lightweight
        wrong_peel = policy()
        wrong_peel["cluster"]["targetCommit"] = PREVIOUS_COMMIT
        candidates["wrong-peel"] = wrong_peel
        duplicate = policy()
        duplicate["stages"][2]["stage"] = 2
        candidates["duplicate-stage"] = duplicate
        unknown = policy()
        unknown["stages"].append({"stage": 8, "name": "all-apps", "operation": "sync"})
        candidates["unknown-app"] = unknown
        for key, value in (("prune", True), ("selector", "wget-cloud.io/profile=x")):
            candidate = policy()
            candidate["stages"][2][key] = value
            candidates[key] = candidate
        extra = policy()
        extra["unexpected"] = True
        candidates["unknown-key"] = extra
        path_drift = policy()
        path_drift["stages"][3]["sourcePaths"][2] = "infrastructure/k8s/components/clusters/dev"
        candidates["source-path-drift"] = path_drift
        enabled_later = policy()
        enabled_later["profileBundles"]["apps"] = "enabled"
        candidates["later-bundle-enabled"] = enabled_later
        missing_forbidden = policy()
        missing_forbidden["forbiddenBundles"].remove("full")
        candidates["forbidden-bundle-removed"] = missing_forbidden

        for case, candidate in candidates.items():
            with self.subTest(case=case):
                self.assert_policy_error(module, lambda candidate=candidate: module.validate_manifest(candidate))

    def test_non_root_stage_never_sets_revision_and_uses_exact_core_sync_wait_argv(self):
        module = self.module()
        contract = policy()
        observed = evidence(contract)
        inspect = observed.__getitem__
        calls = []
        before = published_live_scope(
            4,
            pending_resolved={name: True for name in APPS[3:]},
        )
        after = deepcopy(before)
        after[3] = application(
            "traefik",
            TARGET_TAG,
            TARGET_TAG_OBJECT,
            sync="Synced",
            health="Healthy",
            operation_phase="Succeeded",
            commit_revision=TARGET_COMMIT,
        )
        after_wait = False

        def fake_run(argv, **kwargs):
            nonlocal after_wait
            argv = list(argv)
            calls.append(argv)
            if "git" in Path(argv[0]).name and "ls-remote" in argv:
                return SimpleNamespace(
                    returncode=0,
                    stdout=f"{TARGET_TAG_OBJECT}\trefs/tags/{TARGET_TAG}\n{TARGET_COMMIT}\trefs/tags/{TARGET_TAG}^{{}}\n",
                    stderr="",
                )
            if "app" in argv and argv[argv.index("app") + 1] == "get":
                name = argv[argv.index("app") + 2]
                return SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps(
                        (after if after_wait else before)[APPS.index(name)]
                    ),
                    stderr="",
                )
            if "app" in argv and argv[argv.index("app") + 1] == "wait":
                after_wait = True
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        self.assertEqual(
            module.execute_stage(
                4,
                "traefik",
                TARGET_COMMIT,
                contract,
                inspect_path=observed.__getitem__,
                read_text=lambda path: "synthetic-kubeconfig",
                run_process=fake_run,
                environ={},
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            ),
            0,
        )
        self.assertFalse(any("set" in argv for argv in calls))
        self.assertIn(
            ARGO_PREFIX + ["app", "sync", "traefik", "--app-namespace", "argocd", "--timeout", "600"],
            calls,
        )
        self.assertIn(
            ARGO_PREFIX
            + [
                "app",
                "wait",
                "traefik",
                "--app-namespace",
                "argocd",
                "--sync",
                "--health",
                "--operation",
                "--timeout",
                "600",
            ],
            calls,
        )
        self.assertEqual(module._attest_tag.call_count, 2)

    def test_execute_stage_collects_and_validates_full_published_scope_before_and_after_mutation(self):
        module = self.module()
        contract = policy()
        observed = evidence(contract)
        pre = published_live_scope(
            4,
            pending_resolved={name: True for name in APPS[3:]},
        )
        post = deepcopy(pre)
        post[3] = application(
            "traefik",
            TARGET_TAG,
            TARGET_TAG_OBJECT,
            sync="Synced",
            health="Healthy",
            operation_phase="Succeeded",
            commit_revision=TARGET_COMMIT,
        )
        calls = []
        after_wait = False

        def fake_run(argv, **kwargs):
            nonlocal after_wait
            argv = list(argv)
            calls.append(argv)
            if "git" in Path(argv[0]).name and "ls-remote" in argv:
                return SimpleNamespace(
                    returncode=0,
                    stdout=(
                        f"{TARGET_TAG_OBJECT}\trefs/tags/{TARGET_TAG}\n"
                        f"{TARGET_COMMIT}\trefs/tags/{TARGET_TAG}^{{}}\n"
                    ),
                    stderr="",
                )
            if "app" in argv:
                action = argv[argv.index("app") + 1]
                if action == "get":
                    name = argv[argv.index("app") + 2]
                    values = post if after_wait else pre
                    return SimpleNamespace(
                        returncode=0,
                        stdout=json.dumps(values[APPS.index(name)]),
                        stderr="",
                    )
                if action == "wait":
                    after_wait = True
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with mock.patch.object(
            module,
            "validate_stage_live_scope",
            wraps=module.validate_stage_live_scope,
        ) as scope_validator:
            self.assertEqual(
                module.execute_stage(
                    4,
                    "traefik",
                    TARGET_COMMIT,
                    contract,
                    inspect_path=observed.__getitem__,
                    read_text=lambda path: "synthetic-kubeconfig",
                    run_process=fake_run,
                    environ={},
                    stdout=io.StringIO(),
                    stderr=io.StringIO(),
                ),
                0,
            )
        self.assertGreaterEqual(
            scope_validator.call_count,
            2,
            "execute_stage must invoke the published live-scope validator before mutation and after wait",
        )
        for call in scope_validator.call_args_list:
            stage_arg = call.args[0] if call.args else call.kwargs["stage"]
            scope_arg = call.args[1] if len(call.args) > 1 else call.kwargs["applications"]
            self.assertEqual(stage_arg, 4)
            self.assertEqual(
                [item["metadata"]["name"] for item in scope_arg],
                list(APPS),
            )
        gets = [
            argv[argv.index("app") + 2]
            for argv in calls
            if "app" in argv and argv[argv.index("app") + 1] == "get"
        ]
        self.assertEqual(set(gets), set(APPS))
        self.assertTrue(all(gets.count(name) >= 2 for name in APPS))

        drifted = deepcopy(pre)
        drifted[6]["metadata"].setdefault("labels", {})["attacker"] = "owner"
        mutation_calls = []

        def invalid_future(argv, **kwargs):
            argv = list(argv)
            mutation_calls.append(argv)
            if "git" in Path(argv[0]).name and "ls-remote" in argv:
                return SimpleNamespace(
                    returncode=0,
                    stdout=(
                        f"{TARGET_TAG_OBJECT}\trefs/tags/{TARGET_TAG}\n"
                        f"{TARGET_COMMIT}\trefs/tags/{TARGET_TAG}^{{}}\n"
                    ),
                    stderr="",
                )
            if "app" in argv and argv[argv.index("app") + 1] == "get":
                name = argv[argv.index("app") + 2]
                return SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps(drifted[APPS.index(name)]),
                    stderr="",
                )
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        self.assert_policy_error(
            module,
            lambda: module.execute_stage(
                4,
                "traefik",
                TARGET_COMMIT,
                contract,
                inspect_path=observed.__getitem__,
                read_text=lambda path: "synthetic-kubeconfig",
                run_process=invalid_future,
                environ={},
                stdout=io.StringIO(),
                stderr=io.StringIO(),
                monotonic=iter(range(1000)).__next__,
                sleep=lambda delay: None,
                convergence_timeout=3.0,
            ),
        )
        self.assertFalse(any("sync" in argv for argv in mutation_calls))

    def test_installation_is_root_owned_hash_pinned_and_toctou_attested(self):
        module = self.module()
        contract = policy()
        observed = evidence(contract)
        module.validate_installation(contract, observed.__getitem__)

        for case, path, field, value in (
            ("runner-owner", RUNNER, "owner", "estev"),
            ("runner-mode", RUNNER, "mode", "0755"),
            ("runner-hash", RUNNER, "postDescriptorSha256", "0" * 64),
            ("runner-symlink", RUNNER, "symlink", True),
            ("runner-hardlink", RUNNER, "linkCount", 2),
            ("kubeconfig-writable", KUBECONFIG, "effectiveWritable", True),
            ("kubeconfig-acl", KUBECONFIG, "acl", []),
            ("kubeconfig-swap", KUBECONFIG, "postDescriptorIdentity", {"device": 9, "inode": 9}),
            ("git-credential-owner", GIT_CREDENTIAL, "owner", "estev"),
            ("git-credential-mode", GIT_CREDENTIAL, "mode", "0644"),
            ("git-credential-acl", GIT_CREDENTIAL, "acl", []),
            ("git-credential-hardlink", GIT_CREDENTIAL, "linkCount", 2),
            ("git-credential-swap", GIT_CREDENTIAL, "postDescriptorIdentity", {"device": 9, "inode": 9}),
            ("libexec-recovery-writable", "/usr/local/libexec/wget-cloud-ingress-recovery", "effectiveWritable", True),
            ("etc-recovery-symlink", "/usr/local/etc/wget-cloud-ingress-recovery", "symlink", True),
        ):
            broken = deepcopy(observed)
            broken[path][field] = value
            with self.subTest(case=case):
                self.assert_policy_error(
                    module,
                    lambda broken=broken: module.validate_installation(contract, broken.__getitem__),
                )

    def test_git_credential_is_read_once_from_one_nofollow_stable_descriptor(self):
        module = self.module()
        reader = getattr(module, "_production_read_git_credential_fd", None)
        self.assertIsNotNone(reader, "dedicated GitHub credential FD reader is missing")
        contract = policy()
        observed = evidence(contract)
        identity = observed[GIT_CREDENTIAL]["pathIdentity"]
        opens, reads, closes = [], [], []
        raw = GITHUB_TOKEN.encode()
        stats = [
            SimpleNamespace(
                st_dev=identity["device"],
                st_ino=identity["inode"],
                st_size=len(raw),
            ),
            SimpleNamespace(
                st_dev=identity["device"],
                st_ino=identity["inode"],
                st_size=len(raw),
            ),
        ]

        value = reader(
            contract,
            inspect_path=observed.__getitem__,
            open_fd=lambda path, flags: opens.append((path, flags)) or 73,
            read_fd=lambda fd, size: reads.append((fd, size)) or raw,
            fstat_fd=lambda fd: stats.pop(0),
            close_fd=closes.append,
        )
        self.assertEqual(value, GITHUB_TOKEN)
        self.assertEqual([path for path, _ in opens], [GIT_CREDENTIAL])
        self.assertEqual(len(reads), 1, "credential content must be read exactly once")
        self.assertEqual(reads[0][0], 73)
        self.assertGreaterEqual(reads[0][1], len(raw) + 1)
        self.assertEqual(closes, [73])
        self.assertEqual(stats, [], "credential requires exact pre/post fstat proof")
        if hasattr(os, "O_NOFOLLOW"):
            self.assertTrue(opens[0][1] & os.O_NOFOLLOW)
        self.assertNotIn("sha256", contract["artifacts"]["gitCredential"])

        for case, raw_value, before_size, after_size, after_inode in (
            ("short-read", raw[:-1], len(raw), len(raw), identity["inode"]),
            ("growth", raw + b"x", len(raw), len(raw) + 1, identity["inode"]),
            ("truncation", raw[:-1], len(raw), len(raw) - 1, identity["inode"]),
            ("identity-swap", raw, len(raw), len(raw), identity["inode"] + 1),
        ):
            case_stats = [
                SimpleNamespace(
                    st_dev=identity["device"],
                    st_ino=identity["inode"],
                    st_size=before_size,
                ),
                SimpleNamespace(
                    st_dev=identity["device"],
                    st_ino=after_inode,
                    st_size=after_size,
                ),
            ]
            with self.subTest(case=case):
                self.assert_policy_error(
                    module,
                    lambda case_stats=case_stats, raw_value=raw_value: reader(
                        contract,
                        inspect_path=observed.__getitem__,
                        open_fd=lambda path, flags: 74,
                        read_fd=lambda fd, size: raw_value,
                        fstat_fd=lambda fd: case_stats.pop(0),
                        close_fd=lambda fd: None,
                    ),
                )

    def test_private_github_tag_attestation_uses_exact_api_lineage_and_header_only_secret(self):
        module = self.module()
        attestor = getattr(module, "_production_attest_tag", None)
        self.assertIsNotNone(attestor, "in-process GitHub tag attestor is missing")
        ref_url = GITHUB_REF_REQUEST_URL
        tag_url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPOSITORY}/git/tags/{TARGET_TAG_OBJECT}"
        calls = []
        payloads = {ref_url: github_ref_payload(), tag_url: github_tag_payload()}

        def request_json(url, *, headers, allow_redirects):
            calls.append((url, deepcopy(headers), allow_redirects))
            return {"status": 200, "url": url, "body": deepcopy(payloads[url])}

        attestor(policy(), token=GITHUB_TOKEN, request_json=request_json)
        self.assertEqual([url for url, _, _ in calls], [ref_url, tag_url])
        expected_headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self.assertTrue(all(headers == expected_headers for _, headers, _ in calls))
        self.assertTrue(all(allow_redirects is False for _, _, allow_redirects in calls))
        self.assertTrue(all(GITHUB_TOKEN not in url for url, _, _ in calls))
        self.assertTrue(
            all(
                [key for key, value in headers.items() if GITHUB_TOKEN in value]
                == ["Authorization"]
                for _, headers, _ in calls
            )
        )

    def test_private_github_tag_attestation_fails_closed_and_redacts_secret(self):
        module = self.module()
        attestor = getattr(module, "_production_attest_tag", None)
        self.assertIsNotNone(attestor, "in-process GitHub tag attestor is missing")
        ref_url = GITHUB_REF_REQUEST_URL
        tag_url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPOSITORY}/git/tags/{TARGET_TAG_OBJECT}"
        valid_ref = github_ref_payload()
        valid_tag = github_tag_payload()
        cases = {
            "redirect": (ref_url, {"status": 200, "url": "https://evil.example/ref", "body": valid_ref}),
            "lightweight": (ref_url, {"status": 200, "url": ref_url, "body": {**valid_ref, "object": {"type": "commit", "sha": TARGET_COMMIT}}}),
            "wrong-tag-object": (ref_url, {"status": 200, "url": ref_url, "body": {**valid_ref, "object": {"type": "tag", "sha": "a" * 40}}}),
            "wrong-ref-canonical-url": (ref_url, {"status": 200, "url": ref_url, "body": {**valid_ref, "url": ref_url}}),
            "wrong-object-type": (tag_url, {"status": 200, "url": tag_url, "body": {**valid_tag, "object": {"type": "tree", "sha": TARGET_COMMIT}}}),
            "wrong-peeled-commit": (tag_url, {"status": 200, "url": tag_url, "body": {**valid_tag, "object": {"type": "commit", "sha": "b" * 40}}}),
            "wrong-ref-object-url": (ref_url, {"status": 200, "url": ref_url, "body": {**valid_ref, "object": {**valid_ref["object"], "url": "https://api.github.com/repos/attacker/repo/git/tags/" + TARGET_TAG_OBJECT}}}),
            "wrong-commit-object-url": (tag_url, {"status": 200, "url": tag_url, "body": {**valid_tag, "object": {**valid_tag["object"], "url": "https://api.github.com/repos/attacker/repo/git/commits/" + TARGET_COMMIT}}}),
            "extra-identity": (tag_url, {"status": 200, "url": tag_url, "body": {**valid_tag, "peeled": {"type": "commit", "sha": "c" * 40, "url": GITHUB_COMMIT_URL}}}),
            "verification-type-confusion": (tag_url, {"status": 200, "url": tag_url, "body": {**valid_tag, "verification": {**valid_tag["verification"], "verified": "false"}}}),
            "verification-reason-conflict": (tag_url, {"status": 200, "url": tag_url, "body": {**valid_tag, "verification": {**valid_tag["verification"], "reason": "valid"}}}),
            "verification-signature-conflict": (tag_url, {"status": 200, "url": tag_url, "body": {**valid_tag, "verification": {**valid_tag["verification"], "signature": "unexpected"}}}),
            "verification-payload-conflict": (tag_url, {"status": 200, "url": tag_url, "body": {**valid_tag, "verification": {**valid_tag["verification"], "payload": "unexpected"}}}),
            "verification-time-conflict": (tag_url, {"status": 200, "url": tag_url, "body": {**valid_tag, "verification": {**valid_tag["verification"], "verified_at": "2026-08-20T12:00:01Z"}}}),
        }
        for case, (failed_url, failed_response) in cases.items():
            def request_json(url, *, headers, allow_redirects):
                self.assertFalse(allow_redirects)
                if url == failed_url:
                    return deepcopy(failed_response)
                return {"status": 200, "url": url, "body": deepcopy(valid_ref if url == ref_url else valid_tag)}

            out, err = io.StringIO(), io.StringIO()
            with self.subTest(case=case), mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
                try:
                    attestor(policy(), token=GITHUB_TOKEN, request_json=request_json)
                except module.PolicyError as exc:
                    exposed = f"{exc}\n{out.getvalue()}\n{err.getvalue()}"
                    self.assertNotIn(GITHUB_TOKEN, exposed)
                else:
                    self.fail("unexpected GitHub identity must fail closed")

        def secret_error(url, *, headers, allow_redirects):
            return {
                "status": 401,
                "url": url,
                "body": {"message": f"credential rejected: {GITHUB_TOKEN}"},
            }

        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
            try:
                attestor(policy(), token=GITHUB_TOKEN, request_json=secret_error)
            except module.PolicyError as exc:
                self.assertNotIn(GITHUB_TOKEN, f"{exc}\n{out.getvalue()}\n{err.getvalue()}")
            else:
                self.fail("HTTP authentication failure must fail closed")

    def test_github_http_adapter_enforces_media_type_bounds_json_redirects_and_redaction(self):
        module = self.module()
        adapter = getattr(module, "_github_api_get_json", None)
        self.assertIsNotNone(adapter, "bounded GitHub JSON HTTP adapter is missing")
        url = GITHUB_REF_REQUEST_URL
        payload = github_ref_payload()
        encoded = json.dumps(payload, separators=(",", ":")).encode()

        class Response:
            def __init__(self, body, content_type, *, status=200, final_url=url):
                self.body = body
                self.headers = {} if content_type is None else {"Content-Type": content_type}
                self.status = status
                self.final_url = final_url
                self.read_sizes = []

            def geturl(self):
                return self.final_url

            def read(self, size):
                self.read_sizes.append(size)
                return self.body[:size]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        for media_type in (
            "application/json",
            "application/json; charset=utf-8",
            "application/vnd.github+json",
            "application/vnd.github+json; charset=utf-8",
        ):
            response = Response(encoded, media_type)
            requests = []

            def open_url(request, *args, **kwargs):
                requests.append(request)
                return response

            with self.subTest(media_type=media_type):
                value = adapter(
                    url,
                    token=GITHUB_TOKEN,
                    open_url=open_url,
                    max_response_bytes=MAX_GITHUB_RESPONSE_BYTES,
                )
                self.assertEqual(value, {"status": 200, "url": url, "body": payload})
                self.assertEqual(response.read_sizes, [MAX_GITHUB_RESPONSE_BYTES + 1])
                self.assertEqual(len(requests), 1)
                self.assertEqual(requests[0].full_url, url)
                self.assertEqual(requests[0].get_header("Authorization"), f"Bearer {GITHUB_TOKEN}")
                self.assertNotIn(GITHUB_TOKEN, requests[0].full_url)

        invalid = {
            "missing-content-type": Response(encoded, None),
            "wrong-content-type": Response(encoded, "text/html"),
            "redirect": Response(encoded, "application/json", final_url="https://evil.example/ref"),
            "oversized": Response(b"{" + b"x" * MAX_GITHUB_RESPONSE_BYTES + b"}", "application/json"),
            "malformed-json": Response(b"{not-json", "application/json"),
            "http-error-with-secret": Response(
                json.dumps({"message": GITHUB_TOKEN}).encode(),
                "application/json",
                status=401,
            ),
        }
        for case, response in invalid.items():
            out, err = io.StringIO(), io.StringIO()
            with self.subTest(case=case), mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
                try:
                    adapter(
                        url,
                        token=GITHUB_TOKEN,
                        open_url=lambda request, *args, response=response, **kwargs: response,
                        max_response_bytes=MAX_GITHUB_RESPONSE_BYTES,
                    )
                except module.PolicyError as exc:
                    self.assertNotIn(GITHUB_TOKEN, f"{exc}\n{out.getvalue()}\n{err.getvalue()}")
                else:
                    self.fail("invalid GitHub HTTP response must fail closed")

    def test_kubeconfig_is_read_once_from_the_same_attested_descriptor(self):
        module = self.module()
        reader = getattr(module, "read_attested_text_fd", None)
        self.assertIsNotNone(reader, "TOCTOU-stable descriptor reader is missing")
        contract = policy()
        observed = evidence(contract)
        inspect = observed.__getitem__
        opens, reads, closes = [], [], []
        identity = observed[KUBECONFIG]["pathIdentity"]

        def open_fd(path, flags):
            opens.append((path, flags))
            return 51

        def read_fd(fd, size):
            reads.append((fd, size))
            return b"apiVersion: v1\n" if len(reads) == 1 else b""

        value = reader(
            contract,
            "kubeconfig",
            inspect_path=inspect,
            open_fd=open_fd,
            read_fd=read_fd,
            fstat_fd=lambda fd: SimpleNamespace(st_dev=identity["device"], st_ino=identity["inode"]),
            close_fd=closes.append,
        )
        self.assertEqual(value, "apiVersion: v1\n")
        self.assertEqual(opens[0][0], KUBECONFIG)
        self.assertEqual(closes, [51])

        swapped = deepcopy(observed)
        swapped[KUBECONFIG]["descriptorIdentity"] = {"device": 9, "inode": 9}
        self.assert_policy_error(
            module,
            lambda: reader(
                contract,
                "kubeconfig",
                inspect_path=swapped.__getitem__,
                open_fd=open_fd,
                read_fd=read_fd,
                fstat_fd=lambda fd: SimpleNamespace(st_dev=1, st_ino=1),
                close_fd=closes.append,
            ),
        )

    def test_ingress_main_reads_promotion_manifest_from_one_stable_nofollow_fd(self):
        module = self.module()
        reader = getattr(module, "read_promotion_manifest_fd", None)
        self.assertIsNotNone(
            reader,
            "promotion main requires a TOCTOU-stable manifest descriptor reader",
        )
        contract = policy()
        observed = evidence(contract)
        inspect = observed.__getitem__
        manifest_identity = observed[MANIFEST]["pathIdentity"]
        encoded = json.dumps(contract, separators=(",", ":"), sort_keys=True).encode()
        chunks = [encoded, b""]
        opens, closes = [], []

        def open_fd(path, flags):
            opens.append((path, flags))
            return 61

        loaded = reader(
            inspect_path=inspect,
            open_fd=open_fd,
            read_fd=lambda fd, size: chunks.pop(0),
            fstat_fd=lambda fd: SimpleNamespace(
                st_dev=manifest_identity["device"],
                st_ino=manifest_identity["inode"],
            ),
            close_fd=closes.append,
        )
        self.assertEqual(loaded, contract)
        self.assertEqual(opens[0][0], MANIFEST)
        if hasattr(os, "O_NOFOLLOW"):
            self.assertTrue(opens[0][1] & os.O_NOFOLLOW)
        self.assertEqual(closes, [61])

        chunks[:] = [encoded, b""]
        opens.clear()
        closes.clear()
        with mock.patch.object(
            module, "execute_stage", return_value=0
        ) as execute, mock.patch.dict(
            os.environ, {"WGC_GITOPS_INGRESS_RECOVERY_APPROVED": "1"}, clear=True
        ):
            result = module.main(
                ["--stage", "4", "--app", "traefik", "--revision", TARGET_COMMIT],
                inspect_path=inspect,
                open_fd=open_fd,
                read_fd=lambda fd, size: chunks.pop(0),
                fstat_fd=lambda fd: SimpleNamespace(
                    st_dev=manifest_identity["device"],
                    st_ino=manifest_identity["inode"],
                ),
                close_fd=closes.append,
                run_process=lambda argv, **kwargs: None,
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            )
        self.assertEqual(result, 0)
        self.assertEqual(opens[0][0], MANIFEST)
        if hasattr(os, "O_NOFOLLOW"):
            self.assertTrue(opens[0][1] & os.O_NOFOLLOW)
        self.assertEqual(closes, [61])
        execute.assert_called_once()
        args, kwargs = execute.call_args
        self.assertEqual(args[:4], (4, "traefik", TARGET_COMMIT, contract))
        self.assertIs(kwargs["inspect_path"], inspect)

    def test_execute_stage_promotes_only_root_and_syncs_one_exact_app_without_prune(self):
        module = self.module()
        contract = policy()
        observed = evidence(contract)
        storage_prestate = {
            name: (PREVIOUS_TAG, PREVIOUS_TAG_OBJECT, PREVIOUS_COMMIT)
            for name in PREVIOUS_STORAGE_OWNERS
        }
        reads = {name: 0 for name in APPS}
        calls = []

        def fake_run(argv, **kwargs):
            argv = list(argv)
            calls.append((argv, dict(kwargs)))
            app_index = argv.index("app") if "app" in argv else -1
            action = argv[app_index + 1] if app_index >= 0 else ""
            if action == "get":
                name = argv[app_index + 2]
                reads[name] += 1
                if reads[name] == 1:
                    source_revision = PREVIOUS_TAG
                    reported_revision = PREVIOUS_TAG_OBJECT
                    commit_revision = PREVIOUS_COMMIT
                    sync, health, operation = "OutOfSync", "Healthy", None
                elif 2 <= reads[name] <= 5:
                    source_revision = TARGET_TAG
                    reported_revision = None
                    commit_revision = None
                    sync, health, operation = "OutOfSync", "Missing", None
                elif reads[name] == 6:
                    source_revision = TARGET_TAG
                    reported_revision = TARGET_TAG_OBJECT
                    commit_revision = TARGET_COMMIT
                    sync, health, operation = "OutOfSync", "Missing", None
                else:
                    source_revision = TARGET_TAG
                    reported_revision = TARGET_TAG_OBJECT
                    commit_revision = TARGET_COMMIT
                    sync, health, operation = "Synced", "Healthy", "Succeeded"
                return SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps(
                        application(
                            name,
                            source_revision,
                            reported_revision,
                            sync=sync,
                            health=health,
                            operation_phase=operation,
                            commit_revision=commit_revision,
                        )
                    ),
                    stderr="",
                )
            if "git" in Path(argv[0]).name and "ls-remote" in argv:
                return SimpleNamespace(
                    returncode=0,
                    stdout=(
                        f"{TARGET_TAG_OBJECT}\trefs/tags/{TARGET_TAG}\n"
                        f"{TARGET_COMMIT}\trefs/tags/{TARGET_TAG}^{{}}\n"
                    ),
                    stderr="",
                )
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        clock = iter(index * 0.5 for index in range(100))
        sleeps = []
        result = module.execute_stage(
            1,
            ROOT_APP,
            TARGET_COMMIT,
            contract,
            inspect_path=observed.__getitem__,
            read_text=lambda path: "synthetic-kubeconfig",
            run_process=fake_run,
            environ={"TOKEN": "MUST-NOT-PROPAGATE", "HTTP_PROXY": "http://attacker"},
            stdout=io.StringIO(),
            stderr=io.StringIO(),
            monotonic=lambda: next(clock),
            sleep=sleeps.append,
            convergence_timeout=30.0,
        )
        self.assertEqual(result, 0)
        module.read_git_credential_fd.assert_called_once()
        argv_calls = [argv for argv, _ in calls]
        self.assertEqual(tuple(item["name"] for item in contract["stages"]), APPS)
        self.assertTrue(set(storage_prestate).isdisjoint(APPS))
        self.assertTrue(
            all(
                lineage == (PREVIOUS_TAG, PREVIOUS_TAG_OBJECT, PREVIOUS_COMMIT)
                for lineage in storage_prestate.values()
            )
        )
        self.assertEqual(module._attest_tag.call_count, 2, "every stage must attest the protected tag pair before and after")
        mutations = [argv for argv in argv_calls if "app" in argv and argv[argv.index("app") + 1] in {"set", "sync", "wait"}]
        mutation_apps = {argv[argv.index("app") + 2] for argv in mutations}
        self.assertEqual(mutation_apps, {ROOT_APP})
        self.assertTrue(mutation_apps.isdisjoint(storage_prestate))
        set_calls = [argv for argv in mutations if argv[argv.index("app") + 1] == "set"]
        self.assertEqual(
            set_calls,
            [ARGO_PREFIX + ["app", "set", ROOT_APP, "--app-namespace", "argocd", "--revision", TARGET_TAG]],
        )
        set_index = argv_calls.index(set_calls[0])
        sync_index = next(index for index, argv in enumerate(argv_calls) if "app" in argv and argv[argv.index("app") + 1] == "sync")
        convergence_gets = [
            argv
            for argv in argv_calls[set_index + 1 : sync_index]
            if "app" in argv and argv[argv.index("app") + 1] == "get"
        ]
        self.assertGreaterEqual(
            len(convergence_gets),
            5,
            "stage1 must poll read-only until spec tag and raw tag-object converge before sync",
        )
        self.assertTrue(sleeps)
        self.assertTrue(all(0 < delay <= 2 for delay in sleeps))
        self.assertEqual(
            [argv for argv in mutations if argv[argv.index("app") + 1] == "sync"],
            [ARGO_PREFIX + ["app", "sync", ROOT_APP, "--app-namespace", "argocd", "--timeout", "600"]],
        )
        self.assertEqual(
            [argv for argv in mutations if argv[argv.index("app") + 1] == "wait"],
            [
                ARGO_PREFIX
                + [
                    "app",
                    "wait",
                    ROOT_APP,
                    "--app-namespace",
                    "argocd",
                    "--sync",
                    "--health",
                    "--operation",
                    "--timeout",
                    "600",
                ]
            ],
        )
        wait_index = next(index for index, argv in enumerate(argv_calls) if "app" in argv and argv[argv.index("app") + 1] == "wait")
        self.assertLess(sync_index, wait_index)
        for argv in mutations:
            self.assertNotIn("--prune", argv)
            self.assertNotIn("--selector", argv)
            self.assertNotIn("-l", argv)
            self.assertNotIn(TARGET_COMMIT, argv)
            self.assertNotIn("--kubeconfig", argv)
        for argv, kwargs in calls:
            self.assertIs(kwargs.get("shell"), False)
            self.assertNotIn("TOKEN", kwargs.get("env", {}))
            self.assertNotIn("HTTP_PROXY", kwargs.get("env", {}))
            if "app" in argv and argv[argv.index("app") + 1] in {"sync", "wait"}:
                self.assertGreater(
                    kwargs.get("timeout", 0),
                    600,
                    "outer process timeout must leave a safe margin beyond Argo's 600s timeout",
                )

    def test_stage_one_never_syncs_while_post_set_tag_resolution_is_unresolved(self):
        module = self.module()
        contract = policy()
        observed = evidence(contract)
        calls = []
        reads = 0

        def fake_run(argv, **kwargs):
            nonlocal reads
            argv = list(argv)
            calls.append(argv)
            if "git" in Path(argv[0]).name and "ls-remote" in argv:
                return SimpleNamespace(
                    returncode=0,
                    stdout=(
                        f"{TARGET_TAG_OBJECT}\trefs/tags/{TARGET_TAG}\n"
                        f"{TARGET_COMMIT}\trefs/tags/{TARGET_TAG}^{{}}\n"
                    ),
                    stderr="",
                )
            if "app" in argv and argv[argv.index("app") + 1] == "get":
                reads += 1
                value = application(
                    ROOT_APP,
                    "twc-wise-finch-argocd-recovery-2026-08-17.1" if reads == 1 else TARGET_TAG,
                    PREVIOUS_TAG_OBJECT if reads == 1 else None,
                    sync="OutOfSync",
                    health="Healthy" if reads == 1 else "Missing",
                    operation_phase=None,
                    commit_revision=PREVIOUS_COMMIT if reads == 1 else None,
                )
                return SimpleNamespace(returncode=0, stdout=json.dumps(value), stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        self.assert_policy_error(
            module,
            lambda: module.execute_stage(
                1,
                ROOT_APP,
                TARGET_COMMIT,
                contract,
                inspect_path=observed.__getitem__,
                read_text=lambda path: "synthetic-kubeconfig",
                run_process=fake_run,
                environ={},
                stdout=io.StringIO(),
                stderr=io.StringIO(),
                monotonic=iter(range(1000)).__next__,
                sleep=lambda delay: None,
                convergence_timeout=3.0,
            ),
        )
        self.assertTrue(any("set" in argv for argv in calls))
        self.assertFalse(any("sync" in argv for argv in calls))

    def test_execute_stage_is_idempotent_and_never_mutates_on_invalid_live_state_or_cli_error(self):
        module = self.module()
        contract = policy()
        observed = evidence(contract)

        calls = []
        ready_scope = []

        def already_ready(argv, **kwargs):
            argv = list(argv)
            calls.append(argv)
            if "get" in argv:
                name = argv[argv.index("get") + 1]
                return SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps(ready_scope[APPS.index(name)]),
                    stderr="",
                )
            if "git" in Path(argv[0]).name and "ls-remote" in argv:
                return SimpleNamespace(
                    returncode=0,
                    stdout=f"{TARGET_TAG_OBJECT}\trefs/tags/{TARGET_TAG}\n{TARGET_COMMIT}\trefs/tags/{TARGET_TAG}^{{}}\n",
                    stderr="",
                )
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        for stage, app in enumerate(APPS, start=1):
            calls.clear()
            ready_scope = published_live_scope(
                stage,
                pending_resolved={name: False for name in APPS},
            )
            ready_scope[stage - 1] = application(
                app,
                TARGET_TAG,
                TARGET_TAG_OBJECT,
                sync="Synced",
                health="Healthy",
                operation_phase="Succeeded",
                commit_revision=TARGET_COMMIT,
            )
            extra = (
                {"router_gate": published_router_gate(), "now": ROUTER_NOW}
                if stage == 7
                else {}
            )
            with self.subTest(stage=stage, app=app):
                self.assertEqual(
                    module.execute_stage(
                        stage,
                        app,
                        TARGET_COMMIT,
                        contract,
                        inspect_path=observed.__getitem__,
                        read_text=lambda path: "synthetic-kubeconfig",
                        run_process=already_ready,
                        environ={},
                        stdout=io.StringIO(),
                        stderr=io.StringIO(),
                        **extra,
                    ),
                    0,
                )
                self.assertEqual(module._attest_tag.call_count, 2)
                module._attest_tag.reset_mock()
                module.read_git_credential_fd.reset_mock()
                self.assertFalse(
                    any(token in {"set", "sync", "wait"} for argv in calls for token in argv)
                )

        for case, response in (
            ("invalid-json", SimpleNamespace(returncode=0, stdout="not-json", stderr="SECRET")),
            ("cli-error", SimpleNamespace(returncode=7, stdout="", stderr="SECRET")),
        ):
            failed_calls = []

            def fail(argv, **kwargs):
                failed_calls.append(list(argv))
                return response

            out, err = io.StringIO(), io.StringIO()
            with self.subTest(case=case):
                self.assert_policy_error(
                    module,
                    lambda: module.execute_stage(
                        3,
                        "cert-manager",
                        TARGET_COMMIT,
                        contract,
                        inspect_path=observed.__getitem__,
                        read_text=lambda path: "synthetic-kubeconfig",
                        run_process=fail,
                        environ={},
                        stdout=out,
                        stderr=err,
                    ),
                )
                self.assertFalse(any(token in {"set", "sync"} for argv in failed_calls for token in argv))
                self.assertNotIn("SECRET", out.getvalue() + err.getvalue())

    def test_stage_fails_before_argocd_when_private_github_attestation_rejects(self):
        module = self.module()
        contract = policy()
        observed = evidence(contract)
        for case in ("retagged-object", "changed-peel", "lightweight"):
            calls = []
            def fake_run(argv, **kwargs):
                calls.append(list(argv))
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            with self.subTest(case=case):
                module._attest_tag.side_effect = module.PolicyError("ingress recovery policy rejected")
                self.assert_policy_error(
                    module,
                    lambda: module.execute_stage(
                        4,
                        "traefik",
                        TARGET_COMMIT,
                        contract,
                        inspect_path=observed.__getitem__,
                        read_text=lambda path: "synthetic-kubeconfig",
                        run_process=fake_run,
                        environ={},
                        stdout=io.StringIO(),
                        stderr=io.StringIO(),
                    ),
                )
                self.assertFalse(any("app" in argv for argv in calls))
                module._attest_tag.reset_mock(side_effect=True)

    def test_public_argocd_stage_fails_before_cli_without_attested_router_gate(self):
        module = self.module()
        contract = policy()
        calls = []
        self.assert_policy_error(
            module,
            lambda: module.execute_stage(
                7,
                "argocd-public",
                TARGET_COMMIT,
                contract,
                router_gate=None,
                inspect_path=evidence(contract).__getitem__,
                read_text=lambda path: "synthetic-kubeconfig",
                run_process=lambda argv, **kwargs: calls.append(list(argv)),
                environ={},
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            ),
        )
        self.assertEqual(calls, [])

        for case, mutate in (
            ("missing-plan", lambda value: value.pop("planSha256")),
            ("bad-poststate", lambda value: value.update(postStateSha256="not-a-digest")),
            ("expired", lambda value: value.update(expiresAt="2026-08-17T06:01:59Z")),
            ("wrong-approval", lambda value: value.update(approvalId="another-operation")),
            ("missing-router", lambda value: value.update(routerId="")),
            (
                "created-adopted-overlap",
                lambda value: value.update(createdIds=["dnat-http"]),
            ),
            ("foundation-drift", lambda value: value["foundationEvidence"]["stage5"].update(health="Degraded")),
            ("foundation-digest", lambda value: value.update(foundationSha256="0" * 64)),
            ("action-digest", lambda value: value.update(actionDigest="1" * 64)),
            ("final-digest", lambda value: value.update(planFinalDigest="2" * 64)),
            ("final-rule-drift", lambda value: value["rules"][0].update(localIp="192.168.0.99")),
            (
                "router-plan-path-drift",
                lambda value: value["foundationEvidence"]["offlinePlans"]["k8sRouterPlan"].update(path="attacker.yaml"),
            ),
        ):
            gate = router_gate()
            mutate(gate)
            with self.subTest(case=case):
                self.assert_policy_error(
                    module,
                    lambda gate=gate: module.execute_stage(
                        7,
                        "argocd-public",
                        TARGET_COMMIT,
                        contract,
                        router_gate=gate,
                        now=ROUTER_NOW,
                        inspect_path=evidence(contract).__getitem__,
                        read_text=lambda path: "synthetic-kubeconfig",
                        run_process=lambda argv, **kwargs: calls.append(list(argv)),
                        environ={},
                        stdout=io.StringIO(),
                        stderr=io.StringIO(),
                    ),
                )
        self.assertEqual(calls, [])

    def test_router_gate_is_read_from_one_attested_fd_and_recomputed_before_stage7(self):
        module = self.module()
        reader = getattr(module, "read_router_gate_fd", None)
        validator = getattr(module, "validate_router_gate", None)
        self.assertIsNotNone(reader, "router gate descriptor reader is missing")
        self.assertIsNotNone(validator, "stage7 gate recomputation validator is missing")
        gate = published_router_gate()
        encoded = json.dumps(gate, separators=(",", ":"), sort_keys=True).encode()
        item = {
            "path": getattr(module, "ROUTER_GATE", "/usr/local/etc/wget-cloud-ingress-recovery/router-gate.json"),
            "canonicalPath": getattr(module, "ROUTER_GATE", "/usr/local/etc/wget-cloud-ingress-recovery/router-gate.json"),
            "kind": "file",
            "owner": "root",
            "group": "wheel",
            "mode": "0400",
            "acl": deepcopy(SAFE_READ_ACL),
            "linkCount": 1,
            "symlink": False,
            "effectiveWritable": False,
            "descriptorVerified": True,
            "pathIdentity": {"device": 3, "inode": 71},
            "descriptorIdentity": {"device": 3, "inode": 71},
            "postDescriptorIdentity": {"device": 3, "inode": 71},
        }
        chunks = [encoded, b""]
        value = reader(
            inspect_path=lambda path: item,
            open_fd=lambda path, flags: 71,
            read_fd=lambda fd, size: chunks.pop(0),
            fstat_fd=lambda fd: SimpleNamespace(st_dev=3, st_ino=71),
            close_fd=lambda fd: None,
        )
        self.assertEqual(value, gate)
        self.assertTrue(validator(value, ROUTER_NOW))
        self.assertFalse(
            validator(router_gate(), ROUTER_NOW),
            "legacy custom router gate must never authorize stage7",
        )
        for field, mutate in (
            (
                "router-action",
                lambda item: item["routerPlan"]["spec"].update(
                    actionDigest="sha256:" + "0" * 64
                ),
            ),
            (
                "poststate-final",
                lambda item: item["routerPoststate"]["spec"].update(
                    planFinalDigest="sha256:" + "0" * 64
                ),
            ),
            (
                "promotion-final",
                lambda item: item["promotionPlan"]["spec"].update(
                    finalDigest="sha256:" + "0" * 64
                ),
            ),
        ):
            drifted = deepcopy(value)
            mutate(drifted)
            with self.subTest(field=field):
                self.assertFalse(validator(drifted, ROUTER_NOW))

    def test_stage7_recomputes_published_router_plan_poststate_and_promotion_final_lineage(self):
        module = self.module()
        validator = getattr(module, "validate_router_gate", None)
        self.assertIsNotNone(validator)
        for router_id in (
            "router-a",
            "router-ab",
            "router-abc",
            "router-1234567",
            "router-a-",
            "router-a1-b",
        ):
            with self.subTest(valid_router_id=router_id):
                self.assertTrue(
                    validator(
                        published_router_gate(router_id=router_id), ROUTER_NOW
                    ),
                    "stage7 must use the exact published ^router-[a-z0-9][a-z0-9-]*$ contract",
                )
        for router_id in (
            "router-",
            "router-A",
            "router-a_b",
            "router-a.b",
            "router-a/b",
        ):
            with self.subTest(invalid_router_id=router_id):
                self.assertFalse(
                    validator(
                        published_router_gate(router_id=router_id), ROUTER_NOW
                    )
                )
        for dispositions in (
            ("create", "create"),
            ("adopt", "create"),
            ("create", "adopt"),
            ("adopt", "adopt"),
        ):
            gate = published_router_gate(
                dispositions=dispositions,
                router_id="router-a" if dispositions == ("adopt", "adopt") else "router-wise-finch",
            )
            with self.subTest(dispositions=dispositions):
                self.assertTrue(
                    validator(gate, ROUTER_NOW),
                    "stage7 must accept every ordered create/adopt published lineage",
                )

        gate = published_router_gate()
        for case, mutate in (
            (
                "router-plan-content",
                lambda value: value["routerPlan"]["spec"]["actions"][0]["request"]["body"]["local"].update(port="30081"),
            ),
            (
                "router-poststate-content",
                lambda value: value["routerPoststate"]["spec"]["rules"][0].update(localPort="30081"),
            ),
            (
                "router-plan-digest",
                lambda value: value["promotionPlan"]["spec"].update(routerPlanDigest="sha256:" + "0" * 64),
            ),
            (
                "router-poststate-digest",
                lambda value: value["promotionPlan"]["spec"].update(routerPoststateDigest="sha256:" + "0" * 64),
            ),
            (
                "promotion-final-lineage",
                lambda value: value["promotionPlan"]["spec"].update(finalDigest="sha256:" + "0" * 64),
            ),
            (
                "poststate-plan-final",
                lambda value: value["routerPoststate"]["spec"].update(planFinalDigest="sha256:" + "0" * 64),
            ),
        ):
            candidate = deepcopy(gate)
            mutate(candidate)
            with self.subTest(case=case):
                self.assertFalse(validator(candidate, ROUTER_NOW))

        reordered_poststate = deepcopy(gate)
        reordered_poststate["routerPoststate"]["spec"]["rules"].reverse()
        refresh_published_gate_lineage(reordered_poststate)
        self.assertFalse(
            validator(reordered_poststate, ROUTER_NOW),
            "poststate must retain desired HTTP/80 then HTTPS/443 order regardless of rule IDs",
        )

        wrong_promotion_action = deepcopy(gate)
        promotion_spec = wrong_promotion_action["promotionPlan"]["spec"]
        promotion_spec["actionDigest"] = infrastructure_digest([])
        promotion_lineage = {
            key: promotion_spec[key]
            for key in (
                "contractDigest",
                "liveSnapshotDigest",
                "revisionSnapshotDigest",
                "actionDigest",
                "routerPlanDigest",
                "routerPoststateDigest",
            )
        }
        promotion_spec["finalDigest"] = infrastructure_digest(promotion_lineage)
        self.assertFalse(
            validator(wrong_promotion_action, ROUTER_NOW),
            "promotion actionDigest must be recomputed from the exact stage7 action",
        )

    def test_published_only_router_gate_has_no_unreachable_legacy_fallback(self):
        tree = ast.parse(RUNNER_SOURCE.read_text(encoding="utf-8"))
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "validate_router_gate"
        )
        try_node = next(
            (node for node in function.body if isinstance(node, ast.Try)),
            None,
        )
        if try_node is None:
            return
        published_return = next(
            (
                index
                for index, statement in enumerate(try_node.body)
                if isinstance(statement, ast.Return)
            ),
            None,
        )
        if published_return is not None:
            self.assertEqual(
                try_node.body[published_return + 1 :],
                [],
                "legacy router-gate statements after the published-only return are unreachable and must be removed",
            )

    def test_hook_allows_only_exact_attested_recovery_runner_command(self):
        spec = importlib.util.spec_from_file_location("wgc_hooks_ingress_contract", HOOK_SOURCE)
        hooks = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hooks)
        command_builder = getattr(hooks, "ingress_recovery_runner_command", None)
        parser = getattr(hooks, "parse_ingress_recovery_runner_command", None)
        approver = getattr(hooks, "approved_gitops_ingress_recovery", None)
        self.assertIsNotNone(command_builder, "exact ingress recovery hook exception is missing")
        self.assertIsNotNone(parser)
        self.assertIsNotNone(approver)
        self.assertEqual(
            getattr(hooks, "INGRESS_RECOVERY_MANIFEST", None),
            MANIFEST,
            "hook must pin the distinct promotion manifest",
        )
        exact = command_builder(4, "traefik", TARGET_COMMIT)
        self.assertEqual(parser(exact), (4, "traefik", TARGET_COMMIT))
        for near_miss in (
            exact + " --prune",
            exact + " --selector wget-cloud.io/profile=twc-wise-finch",
            exact.replace(RUNNER, "/tmp/runner.py"),
            exact.replace(TARGET_COMMIT, "main"),
            exact.replace(TARGET_COMMIT, "a" * 40),
            exact.replace("--stage 4 --app traefik", "--stage 4 --app cert-manager"),
            "argocd app sync twc-wise-finch-ingress",
        ):
            with self.subTest(command=near_miss):
                self.assertIsNone(parser(near_miss))

        with mock.patch.object(hooks, "pinned_ls_before_acl", return_value=True), mock.patch.object(
            hooks, "pinned_system_ancestor_chain", return_value=True
        ), mock.patch.object(hooks, "pinned_system_binary", return_value=True), mock.patch.object(
            hooks, "pinned_root_file", return_value=True
        ):
            self.assertTrue(approver(exact))
        with mock.patch.object(hooks, "pinned_ls_before_acl", return_value=False), mock.patch.object(
            hooks, "pinned_system_ancestor_chain", return_value=True
        ), mock.patch.object(hooks, "pinned_system_binary", return_value=True), mock.patch.object(
            hooks, "pinned_root_file", return_value=True
        ):
            self.assertFalse(approver(exact))


if __name__ == "__main__":
    unittest.main()
