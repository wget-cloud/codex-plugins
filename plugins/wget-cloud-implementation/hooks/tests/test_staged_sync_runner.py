import base64
import hashlib
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


PLUGIN_ROOT = Path(__file__).resolve().parents[2]
RUNNER_SOURCE = PLUGIN_ROOT / "scripts" / "staged_sync_runner.py"
MANIFEST_SOURCE = PLUGIN_ROOT / "scripts" / "staged_sync_manifest.json"
REVISION = "6c2c3e9dadde2eec3d13fde830bc6db0392b13b8"
CONTEXT = "twc-wise-finch"
SERVER = "https://200.165.236.215:6443"
SOURCE_CA_SHA256 = "00296a1aa9437b97017dcc22e04e6fd8ea482663634f35926b374a09a3d5b4a9"
RUNNER = "/usr/local/libexec/wget-cloud-staged-sync/runner.py"
CLI = "/usr/local/libexec/wget-cloud-staged-sync/argocd-v3.0.0-darwin-arm64"
INSTALLED_MANIFEST = "/usr/local/libexec/wget-cloud-staged-sync/manifest.json"
KUBECONFIG = "/usr/local/etc/wget-cloud-staged-sync/twc-wise-finch.kubeconfig"
REPO_URL = "ssh://git@github.com/wget-cloud/k8s"
TAG = "twc-wise-finch-ingress-2026-08-15.1"
DESTINATION_SERVER = "https://kubernetes.default.svc"
ESTEV_DARWIN_UUID = "FFFFEEEE-DDDD-CCCC-BBBB-AAAA000001F5"
APPS = (
    (1, "twc-wise-finch-cluster", "Healthy"),
    (2, "twc-wise-finch-core", "Healthy"),
    (3, "twc-wise-finch-local-path-storage", "Missing"),
    (4, "twc-wise-finch-local-path-smoke", "Healthy"),
    (5, "local-path-storage-smoke", "Missing"),
)
CHILD_ENV = {
    "HOME": "/var/empty",
    "PATH": "/usr/bin:/bin",
    "LANG": "C",
    "LC_ALL": "C",
    "KUBECONFIG": KUBECONFIG,
}

APP_CONTRACTS = {
    "twc-wise-finch-cluster": {
        "metadata": {
            "name": "twc-wise-finch-cluster",
            "namespace": "argocd",
            "labels": {"wget-cloud.io/profile": "twc-wise-finch"},
            "annotations": {},
        },
        "project": "default",
        "path": "infrastructure/k8s/gitops/clusters/twc-wise-finch/root",
        "directory": {"recurse": True},
        "destination": {"namespace": "argocd", "server": DESTINATION_SERVER},
        "syncOptions": ["CreateNamespace=true"],
    },
    "twc-wise-finch-core": {
        "metadata": {
            "name": "twc-wise-finch-core",
            "namespace": "argocd",
            "labels": {
                "app.kubernetes.io/instance": "twc-wise-finch-cluster",
                "wget-cloud.io/profile": "twc-wise-finch",
                "wget-cloud.io/bundle": "core",
            },
            "annotations": {"argocd.argoproj.io/sync-wave": "-50"},
        },
        "project": "wget-cloud",
        "path": "infrastructure/k8s/gitops/clusters/twc-wise-finch/bundles/core",
        "directory": {"recurse": True},
        "destination": {"namespace": "argocd", "server": DESTINATION_SERVER},
        "syncOptions": ["CreateNamespace=true"],
    },
    "twc-wise-finch-local-path-storage": {
        "metadata": {
            "name": "twc-wise-finch-local-path-storage",
            "namespace": "argocd",
            "labels": {
                "app.kubernetes.io/component": "storage",
                "app.kubernetes.io/instance": "twc-wise-finch-core",
            },
            "annotations": {"argocd.argoproj.io/sync-wave": "-20"},
        },
        "project": "wget-cloud",
        "path": "infrastructure/k8s/components/clusters/twc-wise-finch/core/storage",
        "directory": {"recurse": True},
        "destination": {"namespace": "local-path-storage", "server": DESTINATION_SERVER},
        "syncOptions": ["CreateNamespace=true", "ServerSideApply=true"],
    },
    "twc-wise-finch-local-path-smoke": {
        "metadata": {
            "name": "twc-wise-finch-local-path-smoke",
            "namespace": "argocd",
            "labels": {
                "app.kubernetes.io/instance": "twc-wise-finch-cluster",
                "wget-cloud.io/profile": "twc-wise-finch",
                "wget-cloud.io/bundle": "local-path-smoke",
            },
            "annotations": {"argocd.argoproj.io/sync-wave": "-45"},
        },
        "project": "wget-cloud",
        "path": "infrastructure/k8s/gitops/clusters/twc-wise-finch/bundles/local-path-smoke",
        "directory": {"recurse": True},
        "destination": {"namespace": "argocd", "server": DESTINATION_SERVER},
        "syncOptions": ["CreateNamespace=true"],
    },
    "local-path-storage-smoke": {
        "metadata": {
            "name": "local-path-storage-smoke",
            "namespace": "argocd",
            "labels": {
                "app.kubernetes.io/component": "storage-validation",
                "app.kubernetes.io/instance": "twc-wise-finch-local-path-smoke",
                "wget-cloud.io/profile": "twc-wise-finch",
            },
            "annotations": {"argocd.argoproj.io/sync-wave": "-19"},
        },
        "project": "wget-cloud",
        "path": "infrastructure/k8s/components/clusters/twc-wise-finch/validation/local-path",
        "directory": {},
        "destination": {"namespace": "local-path-storage", "server": DESTINATION_SERVER},
        "syncOptions": ["CreateNamespace=true", "ServerSideApply=true"],
    },
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def canonical_kubeconfig():
    ca = base64.b64encode(b"synthetic-ca").decode("ascii")
    cert = base64.b64encode(b"synthetic-cert").decode("ascii")
    key = base64.b64encode(b"synthetic-key").decode("ascii")
    return json.dumps(
        {
            "apiVersion": "v1",
            "kind": "Config",
            "current-context": CONTEXT,
            "contexts": [
                {"name": CONTEXT, "context": {"cluster": CONTEXT, "user": "staged-sync"}}
            ],
            "clusters": [
                {
                    "name": CONTEXT,
                    "cluster": {"server": SERVER, "certificate-authority-data": ca},
                }
            ],
            "users": [
                {
                    "name": "staged-sync",
                    "user": {
                        "client-certificate-data": cert,
                        "client-key-data": key,
                    },
                }
            ],
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def manifest(kubeconfig_text=None):
    kubeconfig_text = kubeconfig_text or canonical_kubeconfig()
    artifact = lambda digest, mode: {
        "sha256": digest,
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
            "manifest": INSTALLED_MANIFEST,
            "kubeconfig": KUBECONFIG,
        },
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
            "kubeconfig": {
                **artifact(sha256(kubeconfig_text.encode()), "0400"),
                "acl": [
                    {
                        "inherited": False,
                        "principal": "user:estev",
                        "type": "allow",
                        "permissions": ["read", "readattr", "readextattr", "readsecurity"],
                    }
                ],
            },
        },
        "managedDirectories": {
            "/usr/local/libexec/wget-cloud-staged-sync": {
                "owner": "root",
                "group": "wheel",
                "mode": "0755",
                "acl": [],
            },
            "/usr/local/etc/wget-cloud-staged-sync": {
                "owner": "root",
                "group": "wheel",
                "mode": "0755",
                "acl": [],
            },
        },
        "systemBinaries": {
            "/usr/bin/env": artifact(
                "540f3b55630775d9b2a3aa08cbbe87928ea62c615cd4d13c11f68e2b4571aebc",
                "0755",
            ),
            "/usr/bin/python3": {
                **artifact(
                    "506cb2ddd061e2992c8ee7c53853340688b53d9fcec94c3aa936524cea5b40cb",
                    "0755",
                ),
                "linkCount": 78,
            },
            "/bin/ls": artifact(
                "0056d8fd617b4af3e6f8ec08a08530747962b7392ccd767b275677e8387dac51",
                "0755",
            ),
        },
        "cluster": {
            "context": CONTEXT,
            "server": SERVER,
            "caSha256": sha256(b"synthetic-ca"),
            "revision": REVISION,
        },
        "applications": [
            {
                "stage": stage,
                "name": app,
                "preState": {"sync": "OutOfSync", "health": health},
            }
            for stage, app, health in APPS
        ],
    }


def runtime_manifest(module, kubeconfig_text=None):
    """Use the implementation's current base contract to isolate focused RED cases."""
    policy = json.loads(MANIFEST_SOURCE.read_text(encoding="utf-8"))
    kubeconfig_text = kubeconfig_text or canonical_kubeconfig()
    policy["artifacts"]["kubeconfig"]["sha256"] = sha256(kubeconfig_text.encode())
    policy["cluster"]["caSha256"] = sha256(b"synthetic-ca")
    module.validate_manifest(policy)
    return policy


def path_evidence(policy):
    evidence = {}

    def directory(path):
        evidence[path] = {
            "path": path,
            "canonicalPath": path,
            "kind": "directory",
            "symlink": False,
            "owner": "root",
            "group": "wheel",
            "mode": "0755",
            "acl": [],
            "linkCount": 2,
            "pathIdentity": {"device": 1, "inode": len(evidence) + 100},
            "descriptorIdentity": {"device": 1, "inode": len(evidence) + 100},
            "postDescriptorIdentity": {"device": 1, "inode": len(evidence) + 100},
            "descriptorVerified": True,
            "effectiveWritable": False,
        }

    for path in (
        "/",
        "/usr",
        "/usr/bin",
        "/usr/local",
        "/usr/local/libexec",
        "/usr/local/libexec/wget-cloud-staged-sync",
        "/usr/local/etc",
        "/usr/local/etc/wget-cloud-staged-sync",
        "/var",
        "/var/empty",
    ):
        directory(path)

    for name, path in policy["installedPaths"].items():
        contract = policy["artifacts"][name]
        item = {
            "path": path,
            "canonicalPath": path,
            "kind": "file",
            "symlink": False,
            "owner": contract["owner"],
            "group": contract["group"],
            "mode": contract["mode"],
            "acl": deepcopy(contract["acl"]),
            "linkCount": contract["linkCount"],
            "pathIdentity": {"device": 1, "inode": len(evidence) + 100},
            "descriptorIdentity": {"device": 1, "inode": len(evidence) + 100},
            "postDescriptorIdentity": {"device": 1, "inode": len(evidence) + 100},
            "descriptorVerified": True,
            "effectiveWritable": False,
        }
        if "sha256" in contract:
            item["sha256"] = contract["sha256"]
        descriptor_hash = item.get("sha256", "a" * 64)
        item["descriptorSha256"] = descriptor_hash
        item["postDescriptorSha256"] = descriptor_hash
        evidence[path] = item
    for path, contract in policy["systemBinaries"].items():
        evidence[path] = {
            "path": path,
            "canonicalPath": path,
            "kind": "file",
            "symlink": False,
            "owner": contract["owner"],
            "group": contract["group"],
            "mode": contract["mode"],
            "acl": [],
            "linkCount": contract["linkCount"],
            "sha256": contract["sha256"],
            "descriptorSha256": contract["sha256"],
            "postDescriptorSha256": contract["sha256"],
            "pathIdentity": {"device": 1, "inode": len(evidence) + 100},
            "descriptorIdentity": {"device": 1, "inode": len(evidence) + 100},
            "postDescriptorIdentity": {"device": 1, "inode": len(evidence) + 100},
            "descriptorVerified": True,
            "effectiveWritable": False,
        }
    return evidence


def application_object(
    name,
    *,
    sync,
    health,
    revision=REVISION,
    conditions=None,
    operation=None,
    contracts=APP_CONTRACTS,
):
    contract = contracts[name]
    return {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Application",
        "metadata": deepcopy(contract["metadata"]),
        "spec": {
            "project": contract["project"],
            "source": {
                "repoURL": REPO_URL,
                "targetRevision": TAG,
                "path": contract["path"],
                "directory": deepcopy(contract["directory"]),
            },
            "destination": deepcopy(contract["destination"]),
            "syncPolicy": {"syncOptions": list(contract["syncOptions"])},
        },
        "status": {
            "sync": {"status": sync, "revision": revision},
            "health": {"status": health},
            "conditions": [] if conditions is None else conditions,
            "operationState": operation,
        },
    }


def application_state(
    name,
    *,
    sync,
    health,
    revision=REVISION,
    conditions=None,
    operation=None,
    contracts=APP_CONTRACTS,
):
    return json.dumps(
        application_object(
            name,
            sync=sync,
            health=health,
            revision=revision,
            conditions=conditions,
            operation=operation,
            contracts=contracts,
        ),
        separators=(",", ":"),
    )


class StagedSyncRunnerTest(unittest.TestCase):
    def module(self):
        self.assertTrue(RUNNER_SOURCE.is_file(), "staged_sync_runner.py contract is not implemented")
        spec = importlib.util.spec_from_file_location("staged_sync_runner_under_test", RUNNER_SOURCE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def assert_policy_error(self, module, callback):
        error = getattr(module, "PolicyError", None)
        self.assertIsNotNone(error, "runner must expose PolicyError")
        with self.assertRaises(error):
            callback()

    def test_source_manifest_has_exact_v1_stage_mapping_and_install_contract(self):
        module = self.module()
        self.assertTrue(MANIFEST_SOURCE.is_file(), "staged_sync_manifest.json is missing")
        source = json.loads(MANIFEST_SOURCE.read_text(encoding="utf-8"))
        module.validate_manifest(source)
        self.assertEqual(source["schemaVersion"], 1)
        self.assertEqual(source["installedPaths"], manifest()["installedPaths"])
        self.assertEqual(
            source["cluster"],
            {
                "context": CONTEXT,
                "server": SERVER,
                "caSha256": SOURCE_CA_SHA256,
                "revision": REVISION,
            },
        )
        self.assertEqual(source["applications"], manifest()["applications"])
        self.assertEqual(source["artifacts"]["runner"]["mode"], "0555")
        self.assertEqual(source["artifacts"]["cli"]["mode"], "0555")
        self.assertEqual(source["artifacts"]["manifest"]["mode"], "0444")
        self.assertEqual(source["artifacts"]["kubeconfig"]["mode"], "0400")
        self.assertNotIn("sha256", source["artifacts"]["manifest"])
        self.assertEqual(
            source["systemBinaries"],
            manifest()["systemBinaries"],
            "macOS system binaries must use their observed 0755 modes and pinned identities",
        )
        self.assertIn("/bin/ls", source["systemBinaries"])

    def test_manifest_rejects_unknown_keys_bad_hashes_duplicate_stages_and_ingress(self):
        module = self.module()
        mutations = {}
        wrong_schema = runtime_manifest(module)
        wrong_schema["schemaVersion"] = 2
        mutations["schema"] = wrong_schema
        unknown = runtime_manifest(module)
        unknown["unexpected"] = True
        mutations["unknown-key"] = unknown
        bad_hash = runtime_manifest(module)
        bad_hash["artifacts"]["runner"]["sha256"] = "not-a-hash"
        mutations["hash"] = bad_hash
        duplicate_stage = runtime_manifest(module)
        duplicate_stage["applications"][1]["stage"] = 1
        mutations["duplicate-stage"] = duplicate_stage
        ingress = runtime_manifest(module)
        ingress["applications"].append(
            {"stage": 6, "name": "traefik", "preState": {"sync": "OutOfSync", "health": "Healthy"}}
        )
        mutations["ingress"] = ingress
        for case, candidate in mutations.items():
            with self.subTest(case=case):
                self.assert_policy_error(module, lambda candidate=candidate: module.validate_manifest(candidate))

    def test_installation_accepts_only_root_wheel_files_modes_hashes_acl_and_ancestors(self):
        module = self.module()
        policy = runtime_manifest(module)
        evidence = path_evidence(policy)
        module.validate_installation(policy, evidence.__getitem__)

        mutations = {
            "runner-hash": (RUNNER, "sha256", "0" * 64),
            "runner-owner": (RUNNER, "owner", "estev"),
            "runner-group": (RUNNER, "group", "staff"),
            "runner-mode": (RUNNER, "mode", "0755"),
            "runner-symlink": (RUNNER, "symlink", True),
            "runner-hardlink": (RUNNER, "linkCount", 2),
            "kubeconfig-mode": (KUBECONFIG, "mode", "0444"),
            "kubeconfig-acl": (KUBECONFIG, "acl", []),
            "managed-dir-mode": (
                "/usr/local/libexec/wget-cloud-staged-sync",
                "mode",
                "0775",
            ),
            "ancestor-owner": ("/usr/local", "owner", "estev"),
            "ancestor-writable": ("/usr/local", "mode", "0775"),
            "ancestor-acl": (
                "/usr/local",
                "acl",
                [{"principal": "group:staff", "type": "allow", "permissions": ["write"]}],
            ),
            "system-binary-hash": ("/usr/bin/python3", "sha256", "0" * 64),
            "descriptor-not-verified": (RUNNER, "descriptorVerified", False),
            "effective-user-can-write": (RUNNER, "effectiveWritable", True),
            "descriptor-identity-mismatch": (
                RUNNER,
                "postDescriptorIdentity",
                {"device": 1, "inode": 999999},
            ),
            "descriptor-hash-mismatch": (RUNNER, "postDescriptorSha256", "0" * 64),
            "wrong-kubeconfig-acl-uuid": (
                KUBECONFIG,
                "acl",
                [
                    {
                        "inherited": False,
                        "principal": "user:FFFFEEEE-DDDD-CCCC-BBBB-AAAA000001F4",
                        "type": "allow",
                        "permissions": ["read", "readattr", "readextattr", "readsecurity"],
                    }
                ],
            ),
            "wrong-kubeconfig-acl-user": (
                KUBECONFIG,
                "acl",
                [
                    {
                        "inherited": False,
                        "principal": "user:mallory",
                        "type": "allow",
                        "permissions": ["read", "readattr", "readextattr", "readsecurity"],
                    }
                ],
            ),
        }
        for case, (path, field, value) in mutations.items():
            broken = deepcopy(evidence)
            broken[path][field] = value
            with self.subTest(case=case):
                self.assert_policy_error(
                    module,
                    lambda broken=broken: module.validate_installation(policy, broken.__getitem__),
                )

    def test_installation_rejects_missing_ancestor_and_canonical_path_alias(self):
        module = self.module()
        policy = runtime_manifest(module)
        for case, mutate in {
            "missing-ancestor": lambda evidence: evidence.pop("/usr/local"),
            "canonical-alias": lambda evidence: evidence[RUNNER].__setitem__(
                "canonicalPath", "/tmp/runner.py"
            ),
        }.items():
            evidence = path_evidence(policy)
            mutate(evidence)
            with self.subTest(case=case):
                self.assert_policy_error(
                    module,
                    lambda evidence=evidence: module.validate_installation(policy, evidence.__getitem__),
                )

    def test_acl_normalizes_only_the_pinned_darwin_uuid_to_estev(self):
        module = self.module()
        ls_output = (
            "-r--------+ 1 root wheel 1 Aug 17 00:00 synthetic\n"
            f" 0: {ESTEV_DARWIN_UUID} allow read,readattr,readextattr,readsecurity\n"
        )
        result = SimpleNamespace(returncode=0, stdout=ls_output, stderr="")
        with mock.patch.object(module.subprocess, "run", return_value=result) as run:
            acl = module._acl_for_path(Path(KUBECONFIG))
        self.assertEqual(
            acl,
            [
                {
                    "inherited": False,
                    "principal": "user:estev",
                    "type": "allow",
                    "permissions": ["read", "readattr", "readextattr", "readsecurity"],
                }
            ],
        )
        self.assertEqual(run.call_args.args[0], ["/bin/ls", "-lde", KUBECONFIG])

    def test_inspection_exposes_descriptor_and_path_identity_for_toctou_checks(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "artifact"
            path.write_bytes(b"descriptor-backed-test-artifact")
            evidence = module.inspect_path(str(path))
        self.assertTrue(evidence.get("descriptorVerified"))
        self.assertEqual(evidence.get("descriptorIdentity"), evidence.get("pathIdentity"))
        self.assertEqual(evidence.get("postDescriptorIdentity"), evidence.get("descriptorIdentity"))
        self.assertEqual(evidence.get("postDescriptorSha256"), evidence.get("descriptorSha256"))
        self.assertEqual(
            evidence.get("descriptorSha256"),
            sha256(b"descriptor-backed-test-artifact"),
        )
        self.assertIs(evidence.get("effectiveWritable"), True)

    def test_kubeconfig_accepts_exact_sha_and_rejects_unsafe_or_ambiguous_schema(self):
        module = self.module()
        text = canonical_kubeconfig()
        policy = runtime_manifest(module, text)
        module.validate_kubeconfig(text, policy)

        candidates = {}
        parsed = json.loads(text)
        for case, container, key, value in (
            ("exec", parsed["users"][0]["user"], "exec", {"command": "/tmp/helper"}),
            ("auth-provider", parsed["users"][0]["user"], "auth-provider", {"name": "oidc"}),
            ("proxy", parsed["clusters"][0]["cluster"], "proxy-url", "http://127.0.0.1:1"),
            ("tls-name", parsed["clusters"][0]["cluster"], "tls-server-name", "attacker"),
            ("insecure", parsed["clusters"][0]["cluster"], "insecure-skip-tls-verify", True),
            ("external-ca", parsed["clusters"][0]["cluster"], "certificate-authority", "/tmp/ca"),
        ):
            candidate = deepcopy(parsed)
            target = candidate["users"][0]["user"] if container is parsed["users"][0]["user"] else candidate["clusters"][0]["cluster"]
            target[key] = value
            candidates[case] = json.dumps(candidate, separators=(",", ":"), sort_keys=True)
        duplicate_entry = deepcopy(parsed)
        duplicate_entry["contexts"].append(deepcopy(duplicate_entry["contexts"][0]))
        candidates["duplicate-context-entry"] = json.dumps(duplicate_entry, separators=(",", ":"))
        candidates["duplicate-json-key"] = text.replace(
            '"current-context":"twc-wise-finch"',
            '"current-context":"twc-wise-finch","current-context":"twc-wise-finch"',
        )
        candidates["wrong-server"] = text.replace(SERVER, "https://127.0.0.1:6443")
        candidates["wrong-sha"] = text + "\n"
        for case, candidate in candidates.items():
            with self.subTest(case=case):
                self.assert_policy_error(
                    module,
                    lambda candidate=candidate: module.validate_kubeconfig(candidate, policy),
                )

    def test_read_application_enforces_complete_normalized_gitops_contract(self):
        module = self.module()
        target = APPS[-1][1]
        valid = application_object(
            target,
            sync="OutOfSync",
            health="Missing",
            contracts=module.APPLICATION_CONTRACTS,
        )

        def read(candidate):
            return module._read_application(
                target,
                lambda argv, **kwargs: SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps(candidate, separators=(",", ":")),
                    stderr="",
                ),
            )

        self.assertEqual(read(valid), valid["status"])
        mutations = {}
        for case in (
            "api-version",
            "kind",
            "metadata-labels",
            "metadata-annotations",
            "project",
            "repo-url",
            "tag",
            "path",
            "directory",
            "source-tool",
            "destination-server",
            "destination-namespace",
            "automated-sync",
            "multiple-sources",
        ):
            candidate = deepcopy(valid)
            if case == "api-version":
                candidate["apiVersion"] = "v1"
            elif case == "kind":
                candidate["kind"] = "ConfigMap"
            elif case == "metadata-labels":
                candidate["metadata"]["labels"] = {"wget-cloud.io/profile": "attacker"}
            elif case == "metadata-annotations":
                candidate["metadata"]["annotations"] = {
                    "argocd.argoproj.io/sync-wave": "999"
                }
            elif case == "project":
                candidate["spec"]["project"] = "default"
            elif case == "repo-url":
                candidate["spec"]["source"]["repoURL"] = "https://example.invalid/k8s"
            elif case == "tag":
                candidate["spec"]["source"]["targetRevision"] = REVISION
            elif case == "path":
                candidate["spec"]["source"]["path"] = "infrastructure/k8s/gitops/clusters/dev/root"
            elif case == "directory":
                candidate["spec"]["source"]["directory"] = {"recurse": False}
            elif case == "source-tool":
                candidate["spec"]["source"]["plugin"] = {"name": "unapproved"}
            elif case == "destination-server":
                candidate["spec"]["destination"]["server"] = "https://attacker.invalid"
            elif case == "destination-namespace":
                candidate["spec"]["destination"]["namespace"] = "default"
            elif case == "automated-sync":
                candidate["spec"]["syncPolicy"]["automated"] = {"prune": True}
            elif case == "multiple-sources":
                candidate["spec"]["sources"] = [deepcopy(candidate["spec"]["source"])]
            mutations[case] = candidate

        for case, candidate in mutations.items():
            with self.subTest(case=case):
                self.assert_policy_error(module, lambda candidate=candidate: read(candidate))

    def test_application_tracking_label_matches_the_exact_app_of_apps_owner(self):
        module = self.module()
        expected_owners = {
            "twc-wise-finch-core": "twc-wise-finch-cluster",
            "twc-wise-finch-local-path-storage": "twc-wise-finch-core",
            "twc-wise-finch-local-path-smoke": "twc-wise-finch-cluster",
            "local-path-storage-smoke": "twc-wise-finch-local-path-smoke",
        }

        def read(name, candidate):
            return module._read_application(
                name,
                lambda argv, **kwargs: SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps(candidate, separators=(",", ":")),
                    stderr="",
                ),
            )

        def assert_accepted(name, candidate):
            try:
                observed = read(name, candidate)
            except module.PolicyError:
                self.fail(f"exact tracking-label contract was rejected for {name}")
            self.assertEqual(observed, candidate["status"])

        root = application_object(
            "twc-wise-finch-cluster",
            sync="OutOfSync",
            health="Healthy",
        )
        assert_accepted("twc-wise-finch-cluster", root)
        root_with_tracking = deepcopy(root)
        root_with_tracking["metadata"]["labels"]["app.kubernetes.io/instance"] = "unexpected"
        self.assert_policy_error(
            module,
            lambda: read("twc-wise-finch-cluster", root_with_tracking),
        )

        for name, owner in expected_owners.items():
            health = next(health for _, app, health in APPS if app == name)
            valid = application_object(name, sync="OutOfSync", health=health)
            with self.subTest(app=name, case="exact-owner"):
                self.assertEqual(valid["metadata"]["labels"]["app.kubernetes.io/instance"], owner)
                assert_accepted(name, valid)

            missing = deepcopy(valid)
            missing["metadata"]["labels"].pop("app.kubernetes.io/instance")
            wrong = deepcopy(valid)
            wrong["metadata"]["labels"]["app.kubernetes.io/instance"] = "wrong-owner"
            extra = deepcopy(valid)
            extra["metadata"]["labels"]["unapproved.example/label"] = "present"
            for case, candidate in (
                ("missing-owner", missing),
                ("wrong-owner", wrong),
                ("arbitrary-label", extra),
            ):
                with self.subTest(app=name, case=case):
                    self.assert_policy_error(
                        module,
                        lambda candidate=candidate, name=name: read(name, candidate),
                    )

    def test_execute_stage_checks_every_predecessor_and_target_application_contract(self):
        module = self.module()
        kubeconfig = canonical_kubeconfig()
        policy = runtime_manifest(module, kubeconfig)
        evidence = path_evidence(policy)
        target_stage = 5
        target = APPS[-1][1]

        for broken_app in (name for _, name, _ in APPS):
            calls = []
            read_counts = {}

            def fake_run(argv, **kwargs):
                calls.append(list(argv))
                if argv[4:6] != ["app", "get"]:
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                app = argv[6]
                read_counts[app] = read_counts.get(app, 0) + 1
                index = [name for _, name, _ in APPS].index(app)
                value = application_object(
                    app,
                    sync=(
                        "Synced"
                        if index < target_stage - 1 or read_counts[app] > 1
                        else "OutOfSync"
                    ),
                    health=(
                        "Healthy"
                        if index < target_stage - 1 or read_counts[app] > 1
                        else APPS[index][2]
                    ),
                    contracts=module.APPLICATION_CONTRACTS,
                )
                if app == broken_app:
                    value["spec"]["source"]["path"] = "infrastructure/k8s/unauthorized"
                return SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps(value, separators=(",", ":")),
                    stderr="",
                )

            with self.subTest(broken_app=broken_app):
                self.assert_policy_error(
                    module,
                    lambda: module.execute_stage(
                        target_stage,
                        target,
                        REVISION,
                        policy,
                        inspect_path=evidence.__getitem__,
                        read_text=lambda path: kubeconfig,
                        run_process=fake_run,
                        environ={},
                        stdout=io.StringIO(),
                        stderr=io.StringIO(),
                    ),
                )
                self.assertFalse(any("sync" in argv for argv in calls))

    def test_execute_stage_uses_exact_shell_false_argv_clean_env_and_live_gates(self):
        module = self.module()
        kubeconfig = canonical_kubeconfig()
        policy = runtime_manifest(module, kubeconfig)
        evidence = path_evidence(policy)
        calls = []
        target_stage = 3
        target = APPS[target_stage - 1][1]

        def fake_run(argv, **kwargs):
            calls.append((list(argv), dict(kwargs)))
            if argv[4:6] == ["app", "get"]:
                app = argv[6]
                index = [name for _, name, _ in APPS].index(app)
                if app == target and sum(
                    1
                    for call, _ in calls
                    if call[4:6] == ["app", "get"] and call[6] == target
                ) > 1:
                    stdout = application_state(
                        app,
                        sync="Synced",
                        health="Healthy",
                        contracts=module.APPLICATION_CONTRACTS,
                    )
                elif index < target_stage - 1:
                    stdout = application_state(
                        app,
                        sync="Synced",
                        health="Healthy",
                        contracts=module.APPLICATION_CONTRACTS,
                    )
                else:
                    stdout = application_state(
                        app,
                        sync="OutOfSync",
                        health=APPS[index][2],
                        contracts=module.APPLICATION_CONTRACTS,
                    )
                return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        stdout = io.StringIO()
        stderr = io.StringIO()
        result = module.execute_stage(
            target_stage,
            target,
            REVISION,
            policy,
            inspect_path=evidence.__getitem__,
            read_text=lambda path: kubeconfig if path == KUBECONFIG else "",
            run_process=fake_run,
            environ={"HOME": "/tmp", "HTTP_PROXY": "http://attacker.invalid", "TOKEN": "secret"},
            stdout=stdout,
            stderr=stderr,
        )
        self.assertEqual(result, 0)
        expected_sync = [
            CLI,
            "--core",
            "--kube-context",
            CONTEXT,
            "app",
            "sync",
            target,
            "--app-namespace",
            "argocd",
            "--revision",
            REVISION,
            "--timeout",
            "600",
        ]
        expected_wait = [
            CLI,
            "--core",
            "--kube-context",
            CONTEXT,
            "app",
            "wait",
            target,
            "--app-namespace",
            "argocd",
            "--sync",
            "--health",
            "--operation",
            "--timeout",
            "600",
        ]
        argv_calls = [argv for argv, _ in calls]
        self.assertIn(expected_sync, argv_calls)
        self.assertIn(expected_wait, argv_calls)
        self.assertLess(argv_calls.index(expected_sync), argv_calls.index(expected_wait))
        self.assertEqual(
            sum(1 for argv in argv_calls if argv[4:6] == ["app", "get"] and argv[6] == target),
            2,
            "the target Application contract must be re-read after sync and wait",
        )
        for _, kwargs in calls:
            self.assertIs(kwargs.get("shell"), False)
            self.assertEqual(kwargs.get("env"), CHILD_ENV)
            self.assertTrue(kwargs.get("text"))
            self.assertFalse(kwargs.get("check"))
            self.assertIn("timeout", kwargs)
        combined = stdout.getvalue() + stderr.getvalue()
        self.assertNotIn("secret", combined.lower())
        self.assertNotIn("client-key-data", combined)

    def test_execute_stage_rechecks_the_full_target_contract_after_sync(self):
        module = self.module()
        kubeconfig = canonical_kubeconfig()
        policy = runtime_manifest(module, kubeconfig)
        evidence = path_evidence(policy)
        target = APPS[0][1]
        target_reads = 0
        calls = []

        def fake_run(argv, **kwargs):
            nonlocal target_reads
            calls.append(list(argv))
            if argv[4:6] != ["app", "get"]:
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            target_reads += 1
            value = application_object(
                target,
                sync="OutOfSync" if target_reads == 1 else "Synced",
                health="Healthy",
                contracts=module.APPLICATION_CONTRACTS,
            )
            if target_reads == 2:
                value["spec"]["source"]["repoURL"] = "https://example.invalid/replaced"
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(value, separators=(",", ":")),
                stderr="",
            )

        self.assert_policy_error(
            module,
            lambda: module.execute_stage(
                1,
                target,
                REVISION,
                policy,
                inspect_path=evidence.__getitem__,
                read_text=lambda path: kubeconfig,
                run_process=fake_run,
                environ={},
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            ),
        )
        self.assertEqual(target_reads, 2)
        self.assertTrue(any("sync" in argv for argv in calls))

    def test_execute_stage_rechecks_descriptor_identity_after_kubeconfig_read(self):
        module = self.module()
        kubeconfig = canonical_kubeconfig()
        policy = runtime_manifest(module, kubeconfig)
        evidence = path_evidence(policy)
        swapped = False
        calls = []
        target_reads = 0

        def inspect(path):
            item = deepcopy(evidence[path])
            if swapped and path == policy["installedPaths"]["cli"]:
                item["postDescriptorIdentity"] = {"device": 1, "inode": 999999}
                item["sha256"] = "0" * 64
            return item

        def read_text(path):
            nonlocal swapped
            swapped = True
            return kubeconfig

        def fake_run(argv, **kwargs):
            nonlocal target_reads
            calls.append(list(argv))
            if argv[4:6] == ["app", "get"]:
                app = argv[6]
                target_reads += 1
                return SimpleNamespace(
                    returncode=0,
                    stdout=application_state(
                        app,
                        sync="OutOfSync" if target_reads == 1 else "Synced",
                        health="Healthy",
                        contracts=module.APPLICATION_CONTRACTS,
                    ),
                    stderr="",
                )
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        self.assert_policy_error(
            module,
            lambda: module.execute_stage(
                1,
                APPS[0][1],
                REVISION,
                policy,
                inspect_path=inspect,
                read_text=read_text,
                run_process=fake_run,
                environ={},
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            ),
        )
        self.assertFalse(any("sync" in argv for argv in calls))

    def test_execute_stage_fails_closed_on_query_error_timeout_or_invalid_live_state(self):
        module = self.module()
        kubeconfig = canonical_kubeconfig()
        policy = runtime_manifest(module, kubeconfig)
        evidence = path_evidence(policy)

        def run_case(behavior):
            calls = []

            def fake_run(argv, **kwargs):
                calls.append(list(argv))
                return behavior(argv, kwargs)

            stdout = io.StringIO()
            stderr = io.StringIO()
            self.assert_policy_error(
                module,
                lambda: module.execute_stage(
                    1,
                    APPS[0][1],
                    REVISION,
                    policy,
                    inspect_path=evidence.__getitem__,
                    read_text=lambda path: kubeconfig,
                    run_process=fake_run,
                    environ={},
                    stdout=stdout,
                    stderr=stderr,
                ),
            )
            self.assertFalse(any("sync" in argv for argv in calls))
            self.assertNotIn("SECRET-MATERIAL", stdout.getvalue() + stderr.getvalue())

        cases = {
            "query-error": lambda argv, kwargs: SimpleNamespace(
                returncode=7, stdout="", stderr="SECRET-MATERIAL"
            ),
            "timeout": lambda argv, kwargs: (_ for _ in ()).throw(
                subprocess.TimeoutExpired(argv, kwargs["timeout"], stderr="SECRET-MATERIAL")
            ),
            "condition": lambda argv, kwargs: SimpleNamespace(
                returncode=0,
                stdout=application_state(
                    APPS[0][1],
                    sync="OutOfSync",
                    health="Healthy",
                    conditions=[{"type": "ComparisonError"}],
                    contracts=module.APPLICATION_CONTRACTS,
                ),
                stderr="",
            ),
            "active-operation": lambda argv, kwargs: SimpleNamespace(
                returncode=0,
                stdout=application_state(
                    APPS[0][1],
                    sync="OutOfSync",
                    health="Healthy",
                    operation={"phase": "Running"},
                    contracts=module.APPLICATION_CONTRACTS,
                ),
                stderr="",
            ),
        }
        for case, behavior in cases.items():
            with self.subTest(case=case):
                run_case(behavior)


if __name__ == "__main__":
    unittest.main()
