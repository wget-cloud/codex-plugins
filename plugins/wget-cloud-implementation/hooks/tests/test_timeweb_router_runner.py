import hashlib
import importlib.util
import io
import json
import os
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


PLUGIN_ROOT = Path(__file__).resolve().parents[2]
RUNNER_SOURCE = PLUGIN_ROOT / "scripts" / "timeweb_router_runner.py"
MANIFEST_SOURCE = PLUGIN_ROOT / "scripts" / "timeweb_router_manifest.json"
HOOK_SOURCE = PLUGIN_ROOT / "hooks" / "wgc_hooks.py"

RUNNER = "/usr/local/libexec/wget-cloud-ingress-recovery/router_runner.py"
MANIFEST = "/usr/local/libexec/wget-cloud-ingress-recovery/router-manifest.json"
TOKEN_FILE = "/usr/local/etc/wget-cloud-ingress-recovery/timeweb-cloud-token"
API_BASE = "https://api.timeweb.cloud"
PUBLIC_IP = "72.56.0.250"
LOCAL_IP = "192.168.0.16"
APPROVAL_ID = "twc-wise-finch-argocd-recovery-2026-08-20.2"
APPROVAL_OBSERVED = "2026-08-17T06:00:00Z"
APPROVAL_NOW = datetime(2026, 8, 17, 6, 2, tzinfo=timezone.utc)
APPROVAL_EXPIRY = "2026-08-17T06:05:00Z"
TARGET_TAG_OBJECT = "37c2ee42cb542d30ca200c06e1430d151428a70c"
TARGET_COMMIT = "6247abd4aec30e6a75aeba70123676019762f1a6"
TOKEN = "SYNTHETIC-TIMEWEB-TOKEN-MUST-BE-REDACTED"
ESTEV_DARWIN_UUID = "FFFFEEEE-DDDD-CCCC-BBBB-AAAA000001F5"
INFRA_API_VERSION = "infrastructure.wget-cloud/v1alpha1"
WORKER_HOSTNAME = "worker-192.168.0.16"

DESIRED_RULES = (
    {
        "protocol": "tcp",
        "local": {"ip": LOCAL_IP, "port": "30080"},
        "public": {"ip": PUBLIC_IP, "port": "80"},
    },
    {
        "protocol": "tcp",
        "local": {"ip": LOCAL_IP, "port": "30443"},
        "public": {"ip": PUBLIC_IP, "port": "443"},
    },
)


def canonical_rule(rule):
    if "local" in rule:
        return {
            "id": rule.get("id"),
            "localIp": rule["local"]["ip"],
            "localPort": rule["local"].get("port", "1-65535"),
            "protocol": rule.get("protocol", "tcp_udp"),
            "publicIp": rule["public"]["ip"],
            "publicPort": rule["public"].get("port", "1-65535"),
        }
    return {
        key: rule.get(key)
        for key in ("id", "localIp", "localPort", "protocol", "publicIp", "publicPort")
    }


def canonical_digest(rules):
    normalized = sorted(
        (canonical_rule(rule) for rule in rules),
        key=lambda item: (
            item["publicIp"],
            item["publicPort"],
            item["protocol"],
            item["localIp"],
            item["localPort"],
            item.get("id") or "",
        ),
    )
    encoded = json.dumps(normalized, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def object_digest(value):
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def published_digest(value):
    return f"sha256:{object_digest(value)}"


def discovered_router_id(suffix="7fa2b9c1"):
    return f"router-{suffix}"


def plan_digest():
    encoded = json.dumps(list(DESIRED_RULES), separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def foundation_evidence():
    k8s_router_plan = {
        "path": "infrastructure/k8s/components/clusters/twc-wise-finch/dns/router-recovery.yaml",
        "tagObjectSha": TARGET_TAG_OBJECT,
        "commitSha": TARGET_COMMIT,
        "offlinePlanOnly": True,
    }
    dns_plan = {
        "path": "infrastructure/k8s/components/clusters/twc-wise-finch/dns/cutover.yaml",
        "host": "argocd.wget-cloud.ru",
        "type": "A",
        "value": PUBLIC_IP,
        "offlinePlanOnly": True,
    }
    return {
        "observedAt": APPROVAL_OBSERVED,
        "expiresAt": APPROVAL_EXPIRY,
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
            "addresses": [LOCAL_IP],
            "ready": True,
        },
        "nodePortProbes": [
            {"address": f"{LOCAL_IP}:30080", "protocol": "tcp", "reachable": True},
            {"address": f"{LOCAL_IP}:30443", "protocol": "tcp", "reachable": True},
        ],
        "dns": {
            "host": "argocd.wget-cloud.ru",
            "type": "A",
            "expected": PUBLIC_IP,
            "observed": PUBLIC_IP,
        },
        "offlinePlans": {
            "k8sRouterPlanSha256": object_digest(k8s_router_plan),
            "dnsPlanSha256": object_digest(dns_plan),
            "k8sRouterPlan": k8s_router_plan,
            "dnsPlan": dns_plan,
        },
    }


def published_router_contract():
    return {
        "apiVersion": INFRA_API_VERSION,
        "kind": "TimewebRouterRecovery",
        "metadata": {"name": "twc-wise-finch"},
        "spec": {
            "api": {
                "baseUrl": API_BASE,
                "bearerTokenSource": "protectedRunnerFd",
                "dnatResponseFields": [
                    "id", "localIp", "localPort", "publicIp", "publicPort", "protocol"
                ],
                "endpoints": {
                    "listRouters": "/api/v1/routers",
                    "getRouter": "/api/v1/routers/{router_id}",
                    "listDnatRules": "/api/v1/routers/{router_id}/dnat-rules",
                    "getDnatRule": "/api/v1/routers/{router_id}/dnat-rules/{dnat_id}",
                    "createDnatRule": "/api/v1/routers/{router_id}/dnat-rules",
                    "deleteDnatRule": "/api/v1/routers/{router_id}/dnat-rules/{dnat_id}",
                },
            },
            "desiredRules": list(deepcopy(DESIRED_RULES)),
            "evidenceFreshness": {"maxAgeSeconds": 300, "maxFutureSkewSeconds": 30},
            "offlinePlanOnly": True,
            "requiredDns": {
                "host": "argocd.wget-cloud.ru",
                "provider": "timeweb",
                "type": "A",
                "value": PUBLIC_IP,
                "zone": "wget-cloud.ru",
            },
            "routerSelector": {"uniquePublicIPv4": PUBLIC_IP},
            "target": {"privateIPv4": LOCAL_IP, "workerHostname": WORKER_HOSTNAME},
        },
    }


def published_router_snapshot(router_id, existing_rules):
    return {
        "apiVersion": INFRA_API_VERSION,
        "kind": "TimewebRouterSnapshot",
        "spec": {
            "observedAt": APPROVAL_OBSERVED,
            "readOnly": True,
            "routers": [
                {"id": router_id, "name": "twc-wise-finch", "publicIps": [PUBLIC_IP]}
            ],
            "selectedRouter": {
                "id": router_id,
                "publicIPv4": PUBLIC_IP,
                "dnatRules": list(deepcopy(existing_rules)),
            },
        },
    }


def published_ingress_service(
    *, endpoint_slice_name="traefik-7f84c", endpoint_address="10.244.16.27"
):
    return {
        "apiVersion": INFRA_API_VERSION,
        "kind": "TimewebIngressServiceEvidence",
        "spec": {
            "observedAt": APPROVAL_OBSERVED,
            "readOnly": True,
            "service": {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {"name": "traefik", "namespace": "traefik"},
                "spec": {
                    "type": "NodePort",
                    "externalTrafficPolicy": "Local",
                    "ports": [
                        {"name": "http", "protocol": "TCP", "nodePort": 30080},
                        {"name": "https", "protocol": "TCP", "nodePort": 30443},
                    ],
                },
            },
            "endpointSlice": {
                "apiVersion": "discovery.k8s.io/v1",
                "kind": "EndpointSlice",
                "metadata": {
                    "name": endpoint_slice_name,
                    "namespace": "traefik",
                    "labels": {"kubernetes.io/service-name": "traefik"},
                },
                "readyEndpoints": [
                    {
                        "workerHostname": WORKER_HOSTNAME,
                        "addresses": [endpoint_address],
                        "ready": True,
                    }
                ],
            },
        },
    }


def published_dns_snapshot(*, record_id="record-actual-517"):
    return {
        "apiVersion": INFRA_API_VERSION,
        "kind": "TimewebDnsSnapshot",
        "spec": {
            "observedAt": APPROVAL_OBSERVED,
            "readOnly": True,
            "provider": "timeweb",
            "zone": "wget-cloud.ru",
            "records": [
                {
                    "recordId": record_id,
                    "name": "argocd.wget-cloud.ru",
                    "type": "A",
                    "values": [PUBLIC_IP],
                    "ttlSeconds": 300,
                }
            ],
        },
    }


def published_readiness_evidence():
    return {
        "apiVersion": INFRA_API_VERSION,
        "kind": "TimewebRouterRecoveryReadiness",
        "spec": {
            "observedAt": APPROVAL_OBSERVED,
            "readOnly": True,
            "ingressIPv4": PUBLIC_IP,
            "directNodePortProbes": [
                {"protocol": "HTTP", "targetIPv4": LOCAL_IP, "targetPort": 30080, "ready": True},
                {"protocol": "HTTPS", "targetIPv4": LOCAL_IP, "targetPort": 30443, "ready": True},
            ],
        },
    }


def published_foundation(
    router_id,
    existing_rules,
    *,
    resource_version="184467",
    endpoint_slice_name="traefik-7f84c",
    endpoint_address="10.244.16.27",
    dns_record_id="record-actual-517",
):
    return {
        "gitOpsStage5": {
            "name": "ingress-canary",
            "targetRevision": APPROVAL_ID,
            "syncStatus": "Synced",
            "healthStatus": "Healthy",
            "resourceVersion": resource_version,
            "reportedRevision": TARGET_TAG_OBJECT,
            "commitSha": TARGET_COMMIT,
            "operationPhase": "Succeeded",
        },
        "routerSnapshot": published_router_snapshot(router_id, existing_rules),
        "ingressService": published_ingress_service(
            endpoint_slice_name=endpoint_slice_name,
            endpoint_address=endpoint_address,
        ),
        "dnsSnapshot": published_dns_snapshot(record_id=dns_record_id),
        "readinessEvidence": published_readiness_evidence(),
    }


def published_router_plan(router_id, existing_rules, *, foundation=None):
    foundation = foundation or published_foundation(router_id, existing_rules)
    actions = []
    for desired in DESIRED_RULES:
        exact = [item for item in existing_rules if canonical_rule(item) | {"id": None} == canonical_rule(desired)]
        if exact:
            actions.append(
                {
                    "disposition": "adopt",
                    "existingRuleId": exact[0]["id"],
                    "desiredRule": deepcopy(desired),
                    "rollback": {"action": "preserve", "delete": False},
                }
            )
        else:
            actions.append(
                {
                    "disposition": "create",
                    "request": {
                        "method": "POST",
                        "path": f"/api/v1/routers/{router_id}/dnat-rules",
                        "body": deepcopy(desired),
                    },
                    "response": {"ruleIdSemantics": "captureCreatedRuleId"},
                    "rollback": {
                        "method": "DELETE",
                        "path": f"/api/v1/routers/{router_id}/dnat-rules/{{created_dnat_id}}",
                        "createdByThisRunOnly": True,
                    },
                }
            )
    digests = {
        "contractDigest": published_digest(published_router_contract()),
        "routerSnapshotDigest": published_digest(foundation["routerSnapshot"]),
        "ingressServiceDigest": published_digest(foundation["ingressService"]),
        "dnsSnapshotDigest": published_digest(foundation["dnsSnapshot"]),
        "readinessEvidenceDigest": published_digest(foundation["readinessEvidence"]),
        "actionDigest": published_digest(actions),
    }
    return {
        "apiVersion": INFRA_API_VERSION,
        "kind": "TimewebRouterRecoveryPlan",
        "metadata": {"name": "twc-wise-finch"},
        "spec": {
            "dryRun": True,
            "approvedForApply": False,
            "routerId": router_id,
            "actions": actions,
            **digests,
            "finalDigest": published_digest(digests),
        },
    }


def published_poststate(plan, rules, observed_at="2026-08-17T06:02:00Z"):
    return {
        "apiVersion": INFRA_API_VERSION,
        "kind": "TimewebRouterRecoveryPoststate",
        "spec": {
            "observedAt": observed_at,
            "readOnly": True,
            "routerId": plan["spec"]["routerId"],
            "actionDigest": plan["spec"]["actionDigest"],
            "planFinalDigest": plan["spec"]["finalDigest"],
            "rules": list(deepcopy(rules)),
        },
    }


def action_payload(router_id, prestate_sha, adopted_ids, created_ids):
    return {
        "approvalId": APPROVAL_ID,
        "routerId": router_id,
        "preStateSha256": prestate_sha,
        "planSha256": plan_digest(),
        "foundationSha256": object_digest(foundation_evidence()),
        "adoptedIds": list(adopted_ids),
        "createdIds": list(created_ids),
    }


def final_plan_payload(action_sha, poststate_sha, rules):
    return {
        "actionDigest": action_sha,
        "postStateSha256": poststate_sha,
        "rules": sorted((canonical_rule(rule) for rule in rules), key=lambda rule: rule["id"]),
    }


def rule_out(rule, rule_id):
    normalized = canonical_rule(rule)
    normalized["id"] = rule_id
    return normalized


def router_object(router_id=None):
    router_id = router_id or discovered_router_id()
    return {
        "id": router_id,
        "name": "twc-wise-finch",
        "status": "on",
        "ips": [{"ip": PUBLIC_IP, "nat": {"isEnabled": True}}],
    }


def policy(prestate=(), router_id=None):
    router_id = router_id or discovered_router_id()
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
            "manifest": MANIFEST,
            "credential": TOKEN_FILE,
        },
        "artifacts": {
            "runner": artifact("1" * 64, "0555"),
            "manifest": {
                "owner": "root",
                "group": "wheel",
                "mode": "0444",
                "acl": [],
                "linkCount": 1,
            },
            "credential": {
                "owner": "root",
                "group": "wheel",
                "mode": "0600",
                "acl": [
                    {
                        "inherited": False,
                        "principal": f"user:{ESTEV_DARWIN_UUID}",
                        "type": "allow",
                        "permissions": ["read", "readattr", "readextattr", "readsecurity"],
                    }
                ],
                "linkCount": 1,
            },
        },
        "api": {
            "baseUrl": API_BASE,
            "routersPath": "/api/v1/routers",
            "dnatPath": "/api/v1/routers/{router_id}/dnat-rules",
        },
        "router": {"publicIp": PUBLIC_IP, "localIp": LOCAL_IP},
        "desiredRules": list(deepcopy(DESIRED_RULES)),
        "approval": {
            "id": APPROVAL_ID,
            "observedAt": APPROVAL_OBSERVED,
            "expiresAt": APPROVAL_EXPIRY,
            "routerId": router_id,
            "preStateSha256": canonical_digest(prestate),
        },
    }


def materialized_policy(prestate=(), router_id=None, *, foundation_kwargs=None):
    router_id = router_id or "router-wise-finch"
    result = policy(prestate, router_id=router_id)
    foundation = published_foundation(
        router_id, prestate, **(foundation_kwargs or {})
    )
    plan = published_router_plan(router_id, prestate, foundation=foundation)
    result["foundationEvidence"] = foundation
    result["foundationEvidenceSha256"] = published_digest(foundation)
    result["routerPlan"] = plan
    result["routerPlanSha256"] = published_digest(plan)
    return result


def refresh_materialized_lineage(contract):
    foundation = contract["foundationEvidence"]
    contract["foundationEvidenceSha256"] = published_digest(foundation)
    plan = contract["routerPlan"]
    plan["spec"].update(
        contractDigest=published_digest(published_router_contract()),
        routerSnapshotDigest=published_digest(foundation["routerSnapshot"]),
        ingressServiceDigest=published_digest(foundation["ingressService"]),
        dnsSnapshotDigest=published_digest(foundation["dnsSnapshot"]),
        readinessEvidenceDigest=published_digest(foundation["readinessEvidence"]),
        actionDigest=published_digest(plan["spec"]["actions"]),
    )
    lineage = {
        key: plan["spec"][key]
        for key in (
            "contractDigest",
            "routerSnapshotDigest",
            "ingressServiceDigest",
            "dnsSnapshotDigest",
            "readinessEvidenceDigest",
            "actionDigest",
        )
    }
    plan["spec"]["finalDigest"] = published_digest(lineage)
    contract["routerPlanSha256"] = published_digest(plan)
    return contract


def template_policy():
    contract = policy()
    contract.pop("approval")
    contract["approvalTemplate"] = {
        "id": APPROVAL_ID,
        "maxAgeSeconds": 300,
        "requiredRouterSnapshot": True,
    }
    return contract


def path_evidence(contract):
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
            "pathIdentity": {"device": 1, "inode": len(result) + 10},
            "descriptorIdentity": {"device": 1, "inode": len(result) + 10},
            "postDescriptorIdentity": {"device": 1, "inode": len(result) + 10},
        }
    for name, path in contract["installedPaths"].items():
        item = contract["artifacts"][name]
        sha = item.get("sha256")
        entry = {
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
            "pathIdentity": {"device": 1, "inode": len(result) + 10},
            "descriptorIdentity": {"device": 1, "inode": len(result) + 10},
            "postDescriptorIdentity": {"device": 1, "inode": len(result) + 10},
        }
        if sha:
            entry.update(
                sha256=sha,
                descriptorSha256=sha,
                postDescriptorSha256=sha,
            )
        result[path] = entry
    return result


class Response(SimpleNamespace):
    @classmethod
    def json(cls, status, payload):
        return cls(status=status, headers={"content-type": "application/json"}, body=json.dumps(payload).encode())


class TimewebRouterRunnerTest(unittest.TestCase):
    def module(self):
        self.assertTrue(
            RUNNER_SOURCE.is_file(),
            "separate timeweb_router_runner.py contract is not implemented",
        )
        spec = importlib.util.spec_from_file_location("timeweb_router_runner", RUNNER_SOURCE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(hasattr(module, "PolicyError"))
        return module

    def assert_policy_error(self, module, callback):
        with self.assertRaises(module.PolicyError):
            callback()

    def test_source_manifest_is_non_executable_template_with_exact_official_contract(self):
        module = self.module()
        self.assertTrue(MANIFEST_SOURCE.is_file(), "Timeweb router manifest is missing")
        source = json.loads(MANIFEST_SOURCE.read_text(encoding="utf-8"))
        template_validator = getattr(module, "validate_manifest_template", None)
        self.assertIsNotNone(template_validator, "source approvalTemplate validator is missing")
        template_validator(source)
        self.assertEqual(source["installedPaths"], template_policy()["installedPaths"])
        self.assertEqual(source["api"]["baseUrl"], API_BASE)
        self.assertEqual(source["api"]["routersPath"], "/api/v1/routers")
        self.assertEqual(
            source["api"]["dnatPath"], "/api/v1/routers/{router_id}/dnat-rules"
        )
        self.assertEqual(source["router"], {"publicIp": PUBLIC_IP, "localIp": LOCAL_IP})
        self.assertEqual(source["desiredRules"], list(DESIRED_RULES))
        self.assertEqual(
            source["approvalTemplate"],
            {
                "id": APPROVAL_ID,
                "maxAgeSeconds": 300,
                "requiredRouterSnapshot": True,
            },
        )
        self.assertNotIn("approval", source)
        self.assert_policy_error(
            module,
            lambda: module.validate_manifest(source, now=APPROVAL_NOW),
        )

    def test_manifest_rejects_expiry_bad_digest_unknown_fields_and_unsafe_targets(self):
        module = self.module()
        cases = {}
        expired = policy()
        expired["approval"]["expiresAt"] = "2026-08-17T05:59:59Z"
        cases["expired"] = expired
        future = policy()
        future["approval"]["observedAt"] = "2026-08-17T06:02:01Z"
        cases["future-observation"] = future
        stale_window = policy()
        stale_window["approval"]["expiresAt"] = "2026-08-17T06:05:01Z"
        cases["over-300-seconds"] = stale_window
        wrong_router = policy()
        wrong_router["approval"]["routerId"] = "router_COPY"
        cases["router-lineage"] = wrong_router
        bad_digest = policy()
        bad_digest["approval"]["preStateSha256"] = "not-a-digest"
        cases["digest"] = bad_digest
        wrong_api = policy()
        wrong_api["api"]["baseUrl"] = "https://attacker.invalid"
        cases["api"] = wrong_api
        wrong_ip = policy()
        wrong_ip["router"]["localIp"] = "192.168.0.17"
        cases["local-ip"] = wrong_ip
        udp = policy()
        udp["desiredRules"][0]["protocol"] = "tcp_udp"
        cases["protocol"] = udp
        extra = policy()
        extra["token"] = TOKEN
        cases["inline-token"] = extra
        for case, candidate in cases.items():
            with self.subTest(case=case):
                self.assert_policy_error(
                    module,
                    lambda candidate=candidate: module.validate_manifest(candidate, now=APPROVAL_NOW),
                )

    def test_inspect_path_classifies_directories_and_materialized_manifest_attests_published_artifacts(self):
        module = self.module()
        self.assertEqual(
            module.inspect_path("/")["kind"],
            "directory",
            "the production entrypoint must be able to attest its root-owned directory chain",
        )
        adopted = rule_out(DESIRED_RULES[0], "dnat-http-existing")
        contract = materialized_policy([adopted], router_id="router-wise-finch")
        validator = getattr(module, "validate_materialized_manifest", None)
        self.assertIsNotNone(
            validator,
            "runtime manifest validator for embedded foundation evidence and generated plan is missing",
        )
        validator(contract, now=APPROVAL_NOW)
        dynamic_contract = materialized_policy(
            [adopted],
            router_id="router-a",
            foundation_kwargs={
                "resource_version": "991273",
                "endpoint_slice_name": "traefik-94f66",
                "endpoint_address": "10.244.23.91",
                "dns_record_id": "dns-908172",
            },
        )
        validator(dynamic_contract, now=APPROVAL_NOW)
        self.assertNotEqual(
            contract["foundationEvidence"]["gitOpsStage5"]["resourceVersion"],
            dynamic_contract["foundationEvidence"]["gitOpsStage5"]["resourceVersion"],
        )
        self.assertNotEqual(
            contract["foundationEvidence"]["ingressService"]["spec"]["endpointSlice"]["metadata"]["name"],
            dynamic_contract["foundationEvidence"]["ingressService"]["spec"]["endpointSlice"]["metadata"]["name"],
        )
        foundation = contract["foundationEvidence"]
        self.assertEqual(
            set(foundation),
            {
                "gitOpsStage5",
                "routerSnapshot",
                "ingressService",
                "dnsSnapshot",
                "readinessEvidence",
            },
        )
        self.assertEqual(
            foundation["ingressService"]["spec"]["service"]["spec"]["ports"],
            [
                {"name": "http", "protocol": "TCP", "nodePort": 30080},
                {"name": "https", "protocol": "TCP", "nodePort": 30443},
            ],
        )
        self.assertEqual(
            foundation["ingressService"]["spec"]["endpointSlice"]["metadata"]["labels"],
            {"kubernetes.io/service-name": "traefik"},
        )
        self.assertEqual(
            foundation["readinessEvidence"]["spec"]["directNodePortProbes"],
            [
                {"protocol": "HTTP", "targetIPv4": LOCAL_IP, "targetPort": 30080, "ready": True},
                {"protocol": "HTTPS", "targetIPv4": LOCAL_IP, "targetPort": 30443, "ready": True},
            ],
        )
        plan = contract["routerPlan"]
        self.assertEqual(plan["kind"], "TimewebRouterRecoveryPlan")
        self.assertEqual(
            [item["disposition"] for item in plan["spec"]["actions"]],
            ["adopt", "create"],
        )
        self.assertEqual(plan["spec"]["actionDigest"], published_digest(plan["spec"]["actions"]))
        lineage = {
            key: plan["spec"][key]
            for key in (
                "contractDigest",
                "routerSnapshotDigest",
                "ingressServiceDigest",
                "dnsSnapshotDigest",
                "readinessEvidenceDigest",
                "actionDigest",
            )
        }
        self.assertEqual(plan["spec"]["finalDigest"], published_digest(lineage))

        reordered = deepcopy(contract)
        reordered_plan = reordered["routerPlan"]
        reordered_plan["spec"]["actions"].reverse()
        reordered_plan["spec"]["actionDigest"] = published_digest(
            reordered_plan["spec"]["actions"]
        )
        reordered_lineage = {
            key: reordered_plan["spec"][key]
            for key in (
                "contractDigest",
                "routerSnapshotDigest",
                "ingressServiceDigest",
                "dnsSnapshotDigest",
                "readinessEvidenceDigest",
                "actionDigest",
            )
        }
        reordered_plan["spec"]["finalDigest"] = published_digest(reordered_lineage)
        reordered["routerPlanSha256"] = published_digest(reordered_plan)
        self.assert_policy_error(
            module,
            lambda: validator(reordered, now=APPROVAL_NOW),
        )

        for case, mutate in (
            (
                "foundation-content-with-stale-digest",
                lambda value: value["foundationEvidence"]["ingressService"]["spec"]["service"]["spec"]["ports"][0].update(nodePort=30081),
            ),
            (
                "plan-action-with-stale-digest",
                lambda value: value["routerPlan"]["spec"]["actions"].reverse(),
            ),
            (
                "foundation-top-level-digest",
                lambda value: value.update(foundationEvidenceSha256="sha256:" + "0" * 64),
            ),
            (
                "plan-top-level-digest",
                lambda value: value.update(routerPlanSha256="sha256:" + "0" * 64),
            ),
        ):
            candidate = deepcopy(contract)
            mutate(candidate)
            with self.subTest(case=case):
                self.assert_policy_error(
                    module,
                    lambda candidate=candidate: validator(candidate, now=APPROVAL_NOW),
                )

        for case, foundation_kwargs in (
            ("empty-resource-version", {"resource_version": ""}),
            ("empty-endpointslice-name", {"endpoint_slice_name": ""}),
            ("empty-endpoint-address", {"endpoint_address": ""}),
            ("empty-dns-record-id", {"dns_record_id": ""}),
        ):
            candidate = materialized_policy(
                [adopted],
                router_id="router-a",
                foundation_kwargs=foundation_kwargs,
            )
            with self.subTest(case=case):
                self.assert_policy_error(
                    module,
                    lambda candidate=candidate: validator(candidate, now=APPROVAL_NOW),
                )

        stale = deepcopy(dynamic_contract)
        for item in (
            stale["foundationEvidence"]["routerSnapshot"],
            stale["foundationEvidence"]["ingressService"],
            stale["foundationEvidence"]["dnsSnapshot"],
            stale["foundationEvidence"]["readinessEvidence"],
        ):
            item["spec"]["observedAt"] = "2026-08-17T05:56:59Z"
        refresh_materialized_lineage(stale)
        self.assert_policy_error(
            module,
            lambda: validator(stale, now=APPROVAL_NOW),
        )

    def test_credential_is_root_0600_acl_pinned_and_read_once_through_attested_fd(self):
        module = self.module()
        contract = policy()
        observed = path_evidence(contract)
        opens, reads, closes = [], [], []
        fd_stat = SimpleNamespace(st_dev=1, st_ino=observed[TOKEN_FILE]["pathIdentity"]["inode"])

        def open_fd(path, flags):
            opens.append((path, flags))
            return 41

        def read_fd(fd, size):
            reads.append((fd, size))
            return (TOKEN + "\n").encode() if len(reads) == 1 else b""

        token = module.read_credential_fd(
            contract,
            inspect_path=observed.__getitem__,
            open_fd=open_fd,
            read_fd=read_fd,
            fstat_fd=lambda fd: fd_stat,
            close_fd=closes.append,
        )
        self.assertEqual(token, TOKEN)
        self.assertEqual(opens[0][0], TOKEN_FILE)
        self.assertTrue(opens[0][1] & os.O_RDONLY == os.O_RDONLY)
        if hasattr(os, "O_NOFOLLOW"):
            self.assertTrue(opens[0][1] & os.O_NOFOLLOW)
        self.assertEqual(closes, [41])

        for case, field, value in (
            ("owner", "owner", "estev"),
            ("mode", "mode", "0640"),
            ("hardlink", "linkCount", 2),
            ("symlink", "symlink", True),
            ("acl", "acl", []),
            ("writable", "effectiveWritable", True),
        ):
            broken = deepcopy(observed)
            broken[TOKEN_FILE][field] = value
            with self.subTest(case=case):
                self.assert_policy_error(
                    module,
                    lambda broken=broken: module.read_credential_fd(
                        contract,
                        inspect_path=broken.__getitem__,
                        open_fd=open_fd,
                        read_fd=read_fd,
                        fstat_fd=lambda fd: fd_stat,
                        close_fd=closes.append,
                    ),
                )

    def test_apply_uses_only_official_get_post_paths_and_reports_adopted_vs_created_ids(self):
        module = self.module()
        adopted = rule_out(DESIRED_RULES[0], "dnat-http-adopted")
        created = rule_out(DESIRED_RULES[1], "dnat-https-created")
        contract = policy([adopted])
        observed = path_evidence(contract)
        calls = []
        list_reads = 0

        def request(method, url, headers, body, timeout):
            nonlocal list_reads
            calls.append((method, url, deepcopy(headers), body, timeout))
            self.assertEqual(headers["Authorization"], f"Bearer {TOKEN}")
            if (method, url) == ("GET", f"{API_BASE}/api/v1/routers"):
                return Response.json(200, {"routers": [router_object()]})
            if (method, url) == ("GET", f"{API_BASE}/api/v1/routers/{discovered_router_id()}"):
                return Response.json(200, {"router": router_object()})
            if (method, url) == ("GET", f"{API_BASE}/api/v1/routers/{discovered_router_id()}/dnat-rules"):
                list_reads += 1
                return Response.json(200, {"dnatRules": [adopted] if list_reads == 1 else [adopted, created]})
            if (method, url) == ("POST", f"{API_BASE}/api/v1/routers/{discovered_router_id()}/dnat-rules"):
                self.assertEqual(json.loads(body), DESIRED_RULES[1])
                return Response.json(201, {"dnatRule": created})
            if (method, url) == ("GET", f"{API_BASE}/api/v1/routers/{discovered_router_id()}/dnat-rules/dnat-https-created"):
                return Response.json(200, {"dnatRule": created})
            self.fail(f"unexpected request: {method} {url}")

        out, err = io.StringIO(), io.StringIO()
        result = module.execute_recovery(
            contract,
            foundation_evidence=foundation_evidence(),
            inspect_path=observed.__getitem__,
            read_token=lambda: TOKEN,
            http_request=request,
            now=APPROVAL_NOW,
            environ={"TIMEWEB_CLOUD_TOKEN": "ENV-SECRET", "HTTP_PROXY": "http://attacker"},
            stdout=out,
            stderr=err,
        )
        action_sha = object_digest(
            action_payload(
                discovered_router_id(),
                canonical_digest([adopted]),
                ["dnat-http-adopted"],
                ["dnat-https-created"],
            )
        )
        post_sha = canonical_digest([adopted, created])
        self.assertEqual(result["approvalId"], APPROVAL_ID)
        self.assertEqual(result["routerId"], discovered_router_id())
        self.assertEqual(result["observedAt"], APPROVAL_OBSERVED)
        self.assertEqual(result["expiresAt"], APPROVAL_EXPIRY)
        self.assertEqual(result["preStateSha256"], canonical_digest([adopted]))
        self.assertEqual(result["planSha256"], plan_digest())
        self.assertEqual(result["foundationEvidence"], foundation_evidence())
        self.assertEqual(result["foundationSha256"], object_digest(foundation_evidence()))
        self.assertEqual(result["postStateSha256"], post_sha)
        self.assertEqual(result["adoptedIds"], ["dnat-http-adopted"])
        self.assertEqual(result["createdIds"], ["dnat-https-created"])
        self.assertEqual(
            result["rules"],
            sorted([adopted, created], key=lambda rule: rule["id"]),
        )
        self.assertEqual(result["actionDigest"], action_sha)
        self.assertEqual(
            result["planFinalDigest"],
            object_digest(final_plan_payload(action_sha, post_sha, [adopted, created])),
        )
        self.assertEqual(
            [(method, url) for method, url, _, _, _ in calls],
            [
                ("GET", f"{API_BASE}/api/v1/routers"),
                ("GET", f"{API_BASE}/api/v1/routers/{discovered_router_id()}"),
                ("GET", f"{API_BASE}/api/v1/routers/{discovered_router_id()}/dnat-rules"),
                ("POST", f"{API_BASE}/api/v1/routers/{discovered_router_id()}/dnat-rules"),
                ("GET", f"{API_BASE}/api/v1/routers/{discovered_router_id()}/dnat-rules/dnat-https-created"),
                ("GET", f"{API_BASE}/api/v1/routers/{discovered_router_id()}/dnat-rules"),
            ],
        )
        combined = out.getvalue() + err.getvalue()
        self.assertNotIn(TOKEN, combined)
        self.assertNotIn("ENV-SECRET", combined)

    def test_main_reads_one_attested_materialized_manifest_and_executes_its_exact_plan_to_published_poststate(self):
        module = self.module()
        reader = getattr(module, "read_materialized_manifest_fd", None)
        self.assertIsNotNone(
            reader,
            "main needs a TOCTOU-stable materialized-manifest descriptor reader",
        )
        router_id = "router-wise-finch"
        adopted = rule_out(DESIRED_RULES[0], "z-http-existing")
        created = rule_out(DESIRED_RULES[1], "a-https-created")
        contract = materialized_policy([adopted], router_id=router_id)
        observed = path_evidence(contract)
        encoded = json.dumps(contract, separators=(",", ":"), sort_keys=True).encode()
        chunks = [encoded, b""]
        manifest_identity = observed[MANIFEST]["pathIdentity"]
        closes = []
        loaded = reader(
            now=APPROVAL_NOW,
            inspect_path=observed.__getitem__,
            open_fd=lambda path, flags: 52,
            read_fd=lambda fd, size: chunks.pop(0),
            fstat_fd=lambda fd: SimpleNamespace(
                st_dev=manifest_identity["device"], st_ino=manifest_identity["inode"]
            ),
            close_fd=closes.append,
        )
        self.assertEqual(loaded, contract)
        self.assertEqual(closes, [52])

        calls = []
        events = []
        list_reads = 0

        def request(method, url, headers, body, timeout):
            nonlocal list_reads
            calls.append((method, url, body))
            if (method, url) == ("GET", f"{API_BASE}/api/v1/routers"):
                return Response.json(200, {"routers": [router_object(router_id)]})
            if (method, url) == ("GET", f"{API_BASE}/api/v1/routers/{router_id}"):
                return Response.json(200, {"router": router_object(router_id)})
            if (method, url) == (
                "GET",
                f"{API_BASE}/api/v1/routers/{router_id}/dnat-rules",
            ):
                list_reads += 1
                if list_reads == 2:
                    events.append("final-get")
                return Response.json(
                    200,
                    {"dnatRules": [adopted] if list_reads == 1 else [adopted, created]},
                )
            if (method, url) == (
                "POST",
                f"{API_BASE}/api/v1/routers/{router_id}/dnat-rules",
            ):
                self.assertEqual(json.loads(body), DESIRED_RULES[1])
                return Response.json(201, {"dnatRule": created})
            if (method, url) == (
                "GET",
                f"{API_BASE}/api/v1/routers/{router_id}/dnat-rules/a-https-created",
            ):
                return Response.json(200, {"dnatRule": created})
            self.fail(f"unexpected request: {method} {url}")

        def poststate_now():
            events.append("poststate-observed-at")
            return datetime(2026, 8, 17, 6, 3, tzinfo=timezone.utc)

        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(
            module, "read_materialized_manifest_fd", return_value=contract
        ) as manifest_read, mock.patch.object(
            module, "read_credential_fd", return_value=TOKEN
        ) as token_read, mock.patch.dict(
            os.environ, {"WGC_TIMEWEB_ROUTER_RECOVERY_APPROVED": "1"}, clear=True
        ):
            exit_code = module.main(
                [],
                inspect_path=observed.__getitem__,
                http_request=request,
                now=APPROVAL_NOW,
                poststate_now=poststate_now,
                stdout=out,
                stderr=err,
            )
        self.assertEqual(exit_code, 0)
        manifest_read.assert_called_once()
        token_read.assert_called_once()
        poststate = json.loads(out.getvalue())
        self.assertEqual(
            poststate,
            published_poststate(
                contract["routerPlan"],
                [adopted, created],
                observed_at="2026-08-17T06:03:00Z",
            ),
        )
        self.assertEqual(events, ["final-get", "poststate-observed-at"])
        self.assertEqual(
            [(method, url) for method, url, _ in calls],
            [
                ("GET", f"{API_BASE}/api/v1/routers"),
                ("GET", f"{API_BASE}/api/v1/routers/{router_id}"),
                ("GET", f"{API_BASE}/api/v1/routers/{router_id}/dnat-rules"),
                ("POST", f"{API_BASE}/api/v1/routers/{router_id}/dnat-rules"),
                ("GET", f"{API_BASE}/api/v1/routers/{router_id}/dnat-rules/a-https-created"),
                ("GET", f"{API_BASE}/api/v1/routers/{router_id}/dnat-rules"),
            ],
        )
        self.assertNotIn(TOKEN, out.getvalue() + err.getvalue())

    def test_foundation_evidence_is_exact_and_validated_before_any_timeweb_post(self):
        module = self.module()
        validator = getattr(module, "validate_foundation_evidence", None)
        self.assertIsNotNone(validator, "foundation lineage validator is missing")
        good = foundation_evidence()
        self.assertEqual(validator(good, now=APPROVAL_NOW), object_digest(good))
        for case, mutate in (
            ("stage5-unhealthy", lambda value: value["stage5"].update(health="Degraded")),
            ("service-nodeport", lambda value: value["service"]["ports"][0].update(nodePort=30081)),
            ("endpoint-not-ready", lambda value: value["endpointSlice"].update(ready=False)),
            ("endpoint-wrong-worker", lambda value: value["endpointSlice"].update(addresses=["192.168.0.17"])),
            ("probe-failed", lambda value: value["nodePortProbes"][1].update(reachable=False)),
            ("dns-drift", lambda value: value["dns"].update(observed="109.195.38.30")),
            ("online-plan", lambda value: value["offlinePlans"]["k8sRouterPlan"].update(offlinePlanOnly=False)),
            ("plan-digest", lambda value: value["offlinePlans"].update(k8sRouterPlanSha256="0" * 64)),
            ("source-path", lambda value: value["offlinePlans"]["dnsPlan"].update(path="attacker.yaml")),
            ("expired", lambda value: value.update(expiresAt="2026-08-17T06:01:59Z")),
            ("future", lambda value: value.update(observedAt="2026-08-17T06:02:01Z")),
        ):
            candidate = deepcopy(good)
            mutate(candidate)
            with self.subTest(case=case):
                self.assert_policy_error(module, lambda candidate=candidate: validator(candidate, now=APPROVAL_NOW))

    def test_materialized_router_id_is_freshly_discovered_and_not_a_runner_constant(self):
        module = self.module()
        self.assertFalse(hasattr(module, "ROUTER_ID"), "runner must not pin a synthetic router ID")
        for suffix in (
            "a",
            "ab",
            "abc",
            "1234567",
            "a-",
            "a1-b",
            "7fa2b9c1",
            "wise-finch",
            "edge-01",
        ):
            router_id = discovered_router_id(suffix)
            existing = [
                rule_out(DESIRED_RULES[0], f"{suffix}-http"),
                rule_out(DESIRED_RULES[1], f"{suffix}-https"),
            ]
            contract = policy(existing, router_id=router_id)
            calls = []

            def request(method, url, headers, body, timeout):
                calls.append((method, url))
                if url == f"{API_BASE}/api/v1/routers":
                    return Response.json(200, {"routers": [router_object(router_id)]})
                if url == f"{API_BASE}/api/v1/routers/{router_id}":
                    return Response.json(200, {"router": router_object(router_id)})
                if url == f"{API_BASE}/api/v1/routers/{router_id}/dnat-rules":
                    return Response.json(200, {"dnatRules": existing})
                self.fail(f"unexpected request: {method} {url}")

            with self.subTest(surface="execute_recovery", router_id=router_id):
                result = module.execute_recovery(
                    contract,
                    foundation_evidence=foundation_evidence(),
                    inspect_path=path_evidence(contract).__getitem__,
                    read_token=lambda: TOKEN,
                    http_request=request,
                    now=APPROVAL_NOW,
                    environ={},
                    stdout=io.StringIO(),
                    stderr=io.StringIO(),
                )
                self.assertEqual(result["routerId"], router_id)
                self.assertGreaterEqual(sum(url.endswith("/dnat-rules") for _, url in calls), 2)

            runtime = materialized_policy(existing, router_id=router_id)
            runtime_evidence = path_evidence(runtime)
            calls.clear()
            with self.subTest(surface="main", router_id=router_id):
                with mock.patch.object(
                    module, "read_materialized_manifest_fd", return_value=runtime
                ), mock.patch.object(
                    module, "read_credential_fd", return_value=TOKEN
                ), mock.patch.dict(
                    os.environ,
                    {"WGC_TIMEWEB_ROUTER_RECOVERY_APPROVED": "1"},
                    clear=True,
                ):
                    self.assertEqual(
                        module.main(
                            [],
                            inspect_path=runtime_evidence.__getitem__,
                            http_request=request,
                            now=APPROVAL_NOW,
                            poststate_now=lambda: datetime(
                                2026, 8, 17, 6, 3, tzinfo=timezone.utc
                            ),
                            stdout=io.StringIO(),
                            stderr=io.StringIO(),
                        ),
                        0,
                        "main must use the exact published ^router-[a-z0-9][a-z0-9-]*$ contract",
                    )

        for router_id in (
            "router-",
            "router--a",
            "router-A",
            "router-a_b",
            "router-a.b",
            "router-a/b",
            "route-a",
        ):
            candidate = materialized_policy([], router_id=router_id)
            candidate_evidence = path_evidence(candidate)
            calls = []

            def invoke_invalid():
                with mock.patch.object(
                    module,
                    "read_materialized_manifest_fd",
                    return_value=candidate,
                ), mock.patch.object(
                    module, "read_credential_fd", return_value=TOKEN
                ), mock.patch.dict(
                    os.environ,
                    {"WGC_TIMEWEB_ROUTER_RECOVERY_APPROVED": "1"},
                    clear=True,
                ):
                    return module.main(
                        [],
                        inspect_path=candidate_evidence.__getitem__,
                        http_request=lambda *args, **kwargs: calls.append(args),
                        now=APPROVAL_NOW,
                        stdout=io.StringIO(),
                        stderr=io.StringIO(),
                    )

            with self.subTest(invalid_router_id=router_id):
                self.assert_policy_error(module, invoke_invalid)
                self.assertEqual(calls, [])

    def test_router_discovery_digest_and_port_overlap_are_fail_closed_before_post(self):
        module = self.module()
        overlap = {
            "id": "existing-overlap",
            "localIp": "192.168.0.99",
            "localPort": "8080-8082",
            "publicIp": PUBLIC_IP,
            "publicPort": "79-81",
            "protocol": "tcp",
        }
        scenarios = {
            "ambiguous-router": ([router_object(), router_object("router-copy")], [], policy()),
            "prestate-digest-mismatch": ([router_object()], [], policy([overlap])),
            "overlapping-range": ([router_object()], [overlap], policy([overlap])),
        }
        for case, (routers, rules, contract) in scenarios.items():
            calls = []

            def request(method, url, headers, body, timeout):
                calls.append((method, url))
                if url.endswith("/api/v1/routers"):
                    return Response.json(200, {"routers": routers})
                if url.endswith(f"/routers/{discovered_router_id()}"):
                    return Response.json(200, {"router": router_object()})
                if url.endswith("/dnat-rules"):
                    return Response.json(200, {"dnatRules": rules})
                self.fail(f"mutation attempted in fail-closed case: {method} {url}")

            with self.subTest(case=case):
                self.assert_policy_error(
                    module,
                    lambda: module.execute_recovery(
                        contract,
                        foundation_evidence=foundation_evidence(),
                        inspect_path=path_evidence(contract).__getitem__,
                        read_token=lambda: TOKEN,
                        http_request=request,
                        now=APPROVAL_NOW,
                        environ={},
                        stdout=io.StringIO(),
                        stderr=io.StringIO(),
                    ),
                )
                self.assertFalse(any(method in {"POST", "DELETE"} for method, _ in calls))

    def test_discovered_router_must_match_fresh_detail_id_and_public_ip(self):
        module = self.module()
        router_id = discovered_router_id()
        contract = policy([], router_id=router_id)
        for case, detail in (
            ("detail-id", router_object(discovered_router_id("different"))),
            (
                "detail-public-ip",
                {
                    **router_object(router_id),
                    "ips": [{"ip": "109.195.38.30", "nat": {"isEnabled": True}}],
                },
            ),
        ):
            calls = []

            def request(method, url, headers, body, timeout):
                calls.append((method, url))
                if url == f"{API_BASE}/api/v1/routers":
                    return Response.json(200, {"routers": [router_object(router_id)]})
                if url == f"{API_BASE}/api/v1/routers/{router_id}":
                    return Response.json(200, {"router": detail})
                self.fail(f"router detail mismatch must fail before rules: {method} {url}")

            with self.subTest(case=case):
                self.assert_policy_error(
                    module,
                    lambda: module.execute_recovery(
                        contract,
                        foundation_evidence=foundation_evidence(),
                        inspect_path=path_evidence(contract).__getitem__,
                        read_token=lambda: TOKEN,
                        http_request=request,
                        now=APPROVAL_NOW,
                        environ={},
                        stdout=io.StringIO(),
                        stderr=io.StringIO(),
                    ),
                )
                self.assertFalse(any(method in {"POST", "DELETE"} for method, _ in calls))

    def test_partial_failure_compensates_only_a_runner_created_unchanged_rule(self):
        module = self.module()
        contract = policy([])
        observed = path_evidence(contract)
        first = rule_out(DESIRED_RULES[0], "created-http")
        calls = []

        def request(method, url, headers, body, timeout):
            calls.append((method, url, body))
            if url.endswith("/api/v1/routers"):
                return Response.json(200, {"routers": [router_object()]})
            if url.endswith(f"/routers/{discovered_router_id()}"):
                return Response.json(200, {"router": router_object()})
            if method == "GET" and url.endswith("/dnat-rules"):
                return Response.json(200, {"dnatRules": []})
            if method == "POST" and json.loads(body) == DESIRED_RULES[0]:
                return Response.json(201, {"dnatRule": first})
            if method == "GET" and url.endswith("/dnat-rules/created-http"):
                return Response.json(200, {"dnatRule": first})
            if method == "POST" and json.loads(body) == DESIRED_RULES[1]:
                return Response.json(500, {"message": TOKEN, "requestId": "sensitive-body"})
            if method == "DELETE" and url.endswith("/dnat-rules/created-http"):
                return Response(status=204, headers={}, body=b"")
            self.fail(f"unexpected request: {method} {url}")

        out, err = io.StringIO(), io.StringIO()
        self.assert_policy_error(
            module,
            lambda: module.execute_recovery(
                contract,
                foundation_evidence=foundation_evidence(),
                inspect_path=observed.__getitem__,
                read_token=lambda: TOKEN,
                http_request=request,
                now=APPROVAL_NOW,
                environ={},
                stdout=out,
                stderr=err,
            ),
        )
        deletes = [(method, url) for method, url, _ in calls if method == "DELETE"]
        self.assertEqual(
            deletes,
            [("DELETE", f"{API_BASE}/api/v1/routers/{discovered_router_id()}/dnat-rules/created-http")],
        )
        self.assertGreaterEqual(
            sum(1 for method, url, _ in calls if method == "GET" and url.endswith("/dnat-rules/created-http")),
            2,
            "compensation must freshly re-read the runner-created rule before exact DELETE",
        )
        self.assertNotIn(TOKEN, out.getvalue() + err.getvalue())
        self.assertNotIn("sensitive-body", out.getvalue() + err.getvalue())

    def test_idempotent_exact_rules_make_no_post_or_delete(self):
        module = self.module()
        existing = [
            rule_out(DESIRED_RULES[0], "stable-http"),
            rule_out(DESIRED_RULES[1], "stable-https"),
        ]
        contract = policy(existing)
        calls = []

        def request(method, url, headers, body, timeout):
            calls.append((method, url))
            if url.endswith("/api/v1/routers"):
                return Response.json(200, {"routers": [router_object()]})
            if url.endswith(f"/routers/{discovered_router_id()}"):
                return Response.json(200, {"router": router_object()})
            if url.endswith("/dnat-rules"):
                return Response.json(200, {"dnatRules": existing})
            self.fail(f"idempotent recovery attempted mutation: {method} {url}")

        result = module.execute_recovery(
            contract,
            foundation_evidence=foundation_evidence(),
            inspect_path=path_evidence(contract).__getitem__,
            read_token=lambda: TOKEN,
            http_request=request,
            now=APPROVAL_NOW,
            environ={},
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        self.assertEqual(result["createdIds"], [])
        self.assertEqual(result["adoptedIds"], ["stable-http", "stable-https"])
        self.assertEqual(result["preStateSha256"], canonical_digest(existing))
        self.assertEqual(result["postStateSha256"], canonical_digest(existing))
        self.assertEqual(result["planSha256"], plan_digest())
        self.assertFalse(any(method in {"POST", "DELETE"} for method, _ in calls))

    def test_compensation_refuses_delete_if_created_rule_changed_after_post(self):
        module = self.module()
        contract = policy([])
        original = rule_out(DESIRED_RULES[0], "created-http")
        changed = deepcopy(original)
        changed["localIp"] = "192.168.0.99"
        created_reads = 0
        calls = []

        def request(method, url, headers, body, timeout):
            nonlocal created_reads
            calls.append((method, url, body))
            if url.endswith("/api/v1/routers"):
                return Response.json(200, {"routers": [router_object()]})
            if url.endswith(f"/routers/{discovered_router_id()}"):
                return Response.json(200, {"router": router_object()})
            if method == "GET" and url.endswith("/dnat-rules"):
                return Response.json(200, {"dnatRules": []})
            if method == "POST" and json.loads(body) == DESIRED_RULES[0]:
                return Response.json(201, {"dnatRule": original})
            if method == "GET" and url.endswith("/dnat-rules/created-http"):
                created_reads += 1
                return Response.json(200, {"dnatRule": original if created_reads == 1 else changed})
            if method == "POST" and json.loads(body) == DESIRED_RULES[1]:
                return Response.json(500, {"message": "failure"})
            self.fail(f"unsafe compensation request: {method} {url}")

        self.assert_policy_error(
            module,
            lambda: module.execute_recovery(
                contract,
                foundation_evidence=foundation_evidence(),
                inspect_path=path_evidence(contract).__getitem__,
                read_token=lambda: TOKEN,
                http_request=request,
                now=APPROVAL_NOW,
                environ={},
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            ),
        )
        self.assertEqual(created_reads, 2)
        self.assertFalse(any(method == "DELETE" for method, _, _ in calls))

    def test_concurrent_final_drift_fails_closed_and_compensates_only_created_unchanged_ids(self):
        module = self.module()
        contract = policy([])
        first = rule_out(DESIRED_RULES[0], "created-http")
        second = rule_out(DESIRED_RULES[1], "created-https")
        drift = {
            "id": "concurrent-drift",
            "localIp": "192.168.0.99",
            "localPort": "8080",
            "publicIp": PUBLIC_IP,
            "publicPort": "80-81",
            "protocol": "tcp",
        }
        list_reads = 0
        calls = []

        def request(method, url, headers, body, timeout):
            nonlocal list_reads
            calls.append((method, url, body))
            if url.endswith("/api/v1/routers"):
                return Response.json(200, {"routers": [router_object()]})
            if url.endswith(f"/routers/{discovered_router_id()}"):
                return Response.json(200, {"router": router_object()})
            if method == "GET" and url.endswith("/dnat-rules"):
                list_reads += 1
                return Response.json(200, {"dnatRules": [] if list_reads == 1 else [first, second, drift]})
            if method == "POST" and json.loads(body) == DESIRED_RULES[0]:
                return Response.json(201, {"dnatRule": first})
            if method == "POST" and json.loads(body) == DESIRED_RULES[1]:
                return Response.json(201, {"dnatRule": second})
            if method == "GET" and url.endswith("/dnat-rules/created-http"):
                return Response.json(200, {"dnatRule": first})
            if method == "GET" and url.endswith("/dnat-rules/created-https"):
                return Response.json(200, {"dnatRule": second})
            if method == "DELETE" and url.endswith(("/dnat-rules/created-http", "/dnat-rules/created-https")):
                return Response(status=204, headers={}, body=b"")
            self.fail(f"unexpected request: {method} {url}")

        self.assert_policy_error(
            module,
            lambda: module.execute_recovery(
                contract,
                foundation_evidence=foundation_evidence(),
                inspect_path=path_evidence(contract).__getitem__,
                read_token=lambda: TOKEN,
                http_request=request,
                now=APPROVAL_NOW,
                environ={},
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            ),
        )
        self.assertEqual(list_reads, 2, "poststate must come from a fresh final collection GET")
        deleted = {
            url.rsplit("/", 1)[-1]
            for method, url, _ in calls
            if method == "DELETE"
        }
        self.assertEqual(deleted, {"created-http", "created-https"})
        self.assertNotIn("concurrent-drift", deleted)

    def test_hook_allows_only_exact_attested_router_runner_command(self):
        spec = importlib.util.spec_from_file_location("wgc_hooks_router_contract", HOOK_SOURCE)
        hooks = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hooks)
        builder = getattr(hooks, "timeweb_router_runner_command", None)
        parser = getattr(hooks, "parse_timeweb_router_runner_command", None)
        approver = getattr(hooks, "approved_timeweb_router_recovery", None)
        self.assertIsNotNone(builder, "exact Timeweb router hook exception is missing")
        self.assertIsNotNone(parser)
        self.assertIsNotNone(approver)
        self.assertEqual(
            getattr(hooks, "TIMEWEB_ROUTER_MANIFEST", None),
            MANIFEST,
            "hook must pin the distinct materialized router manifest",
        )
        exact = builder()
        self.assertTrue(parser(exact))
        self.assertNotIn(TOKEN, exact)
        self.assertNotIn("TOKEN", exact.upper())
        for near_miss in (
            exact + " --router-id attacker",
            exact + " --token secret",
            exact.replace(RUNNER, "/tmp/router_runner.py"),
            "curl -X POST https://api.timeweb.cloud/api/v1/routers/x/dnat-rules",
        ):
            with self.subTest(command=near_miss):
                self.assertFalse(parser(near_miss))
        materialized_digest = "f" * 64
        template_digest = hashlib.sha256(MANIFEST_SOURCE.read_bytes()).hexdigest()
        self.assertEqual(getattr(hooks, "TIMEWEB_ROUTER_TEMPLATE_SHA256", None), template_digest)
        with mock.patch.object(hooks, "current_root_file_digest", return_value=materialized_digest), mock.patch.object(
            hooks, "pinned_ls_before_acl", return_value=True
        ), mock.patch.object(
            hooks, "pinned_system_ancestor_chain", return_value=True
        ), mock.patch.object(hooks, "pinned_system_binary", return_value=True), mock.patch.object(
            hooks, "pinned_root_file", return_value=True
        ):
            self.assertTrue(approver(exact))
        with mock.patch.object(hooks, "current_root_file_digest", return_value=template_digest), mock.patch.object(
            hooks, "pinned_ls_before_acl", return_value=True
        ), mock.patch.object(
            hooks, "pinned_system_ancestor_chain", return_value=True
        ), mock.patch.object(hooks, "pinned_system_binary", return_value=True), mock.patch.object(
            hooks, "pinned_root_file", return_value=True
        ):
            self.assertFalse(approver(exact), "source approvalTemplate digest must never authorize runtime execution")


if __name__ == "__main__":
    unittest.main()
