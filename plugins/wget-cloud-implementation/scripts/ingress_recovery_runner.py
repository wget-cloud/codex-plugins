#!/usr/bin/env python3
"""Fail-closed, single-application Argo CD ingress recovery runner."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import grp
import hashlib
import json
import os
import pwd
import re
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence, TextIO


RUNNER = "/usr/local/libexec/wget-cloud-ingress-recovery/promotion_runner.py"
CLI = "/usr/local/libexec/wget-cloud-ingress-recovery/argocd-v3.0.0-darwin-arm64"
MANIFEST = "/usr/local/libexec/wget-cloud-ingress-recovery/promotion-manifest.json"
KUBECONFIG = "/usr/local/etc/wget-cloud-ingress-recovery/twc-wise-finch.kubeconfig"
GIT_CREDENTIAL = "/usr/local/etc/wget-cloud-ingress-recovery/github-k8s-token"
ROUTER_GATE = "/usr/local/etc/wget-cloud-ingress-recovery/router-gate.json"
CONTEXT = "twc-wise-finch"
ROOT_APPLICATION = "twc-wise-finch-cluster"
PREVIOUS_TAG_OBJECT = "344a7e5f87e6c9212dd1ac22256336faad0eb002"
PREVIOUS_COMMIT = "925f7a2949c6ff50b76e55ccec80abdfff59178b"
PREVIOUS_TAG = "twc-wise-finch-argocd-recovery-2026-08-17.1"
TARGET_TAG = "twc-wise-finch-argocd-recovery-2026-08-20.2"
TARGET_TAG_OBJECT = "37c2ee42cb542d30ca200c06e1430d151428a70c"
TARGET_COMMIT = "6247abd4aec30e6a75aeba70123676019762f1a6"
GITHUB_API_BASE = "https://api.github.com"
GITHUB_REPOSITORY = "wget-cloud/k8s"
GITHUB_API_TIMEOUT = 10.0
MAX_GITHUB_RESPONSE_BYTES = 64 * 1024
DARWIN_USER_UUID = "FFFFEEEE-DDDD-CCCC-BBBB-AAAA000001F5"
SAFE_READ_ACL = [{
    "inherited": False,
    "principal": f"user:{DARWIN_USER_UUID}",
    "type": "allow",
    "permissions": ["read", "readattr", "readextattr", "readsecurity"],
}]
STAGES = (
    (1, ROOT_APPLICATION, "root-promote"),
    (2, "twc-wise-finch-ingress", "ingress-owner"),
    (3, "cert-manager", "sync"),
    (4, "traefik", "sync"),
    (5, "ingress-canary", "sync"),
    (6, "twc-wise-finch-ingress-issuer", "sync"),
    (7, "argocd-public", "router-gated-sync"),
)
SOURCE_PATHS = {
    ROOT_APPLICATION: ["infrastructure/k8s/gitops/clusters/twc-wise-finch/root"],
    "twc-wise-finch-ingress": ["infrastructure/k8s/gitops/clusters/twc-wise-finch/bundles/ingress"],
    "cert-manager": ["infrastructure/k8s/charts/cert-manager"],
    "traefik": ["infrastructure/k8s/charts/traefik", ".", "infrastructure/k8s/components/clusters/twc-wise-finch/core/ingress-controller"],
    "ingress-canary": ["infrastructure/k8s/components/clusters/twc-wise-finch/validation/ingress"],
    "twc-wise-finch-ingress-issuer": ["infrastructure/k8s/components/clusters/twc-wise-finch/core/cert-manager"],
    "argocd-public": ["infrastructure/k8s/components/clusters/twc-wise-finch/core/argocd-public"],
}
PROFILE_BUNDLES = {"core": "enabled", "local-path-smoke": "enabled", "controllers": "planned", "ingress": "enabled", "vault-restore": "planned", "eso-ready": "planned", "data": "planned", "apps": "planned", "full": "planned"}
FORBIDDEN_BUNDLES = ["controllers", "vault-restore", "eso-ready", "data", "apps", "full"]
DESTINATION_SERVER = "https://kubernetes.default.svc"
REPO_SOURCE = "ssh://git@github.com/wget-cloud/k8s"
ARGO_PREFIX = (CLI, "--core", "--kube-context", CONTEXT)


def _source(path: str, **extra: Any) -> Mapping[str, Any]:
    return {"repoURL": REPO_SOURCE, "targetRevision": TARGET_TAG, "path": path, **extra}


APPLICATION_CONTRACTS = {
    ROOT_APPLICATION: {"metadata": {"labels": {"wget-cloud.io/profile": CONTEXT}, "annotations": {}}, "project": "default", "destination": {"server": DESTINATION_SERVER, "namespace": "argocd"}, "source": _source(SOURCE_PATHS[ROOT_APPLICATION][0], directory={"recurse": True}), "syncPolicy": {"syncOptions": ["CreateNamespace=true"]}, "trackingOwner": None},
    "twc-wise-finch-ingress": {"metadata": {"labels": {"wget-cloud.io/profile": CONTEXT, "wget-cloud.io/bundle": "ingress"}, "annotations": {"argocd.argoproj.io/sync-wave": "-40"}}, "project": "wget-cloud", "destination": {"server": DESTINATION_SERVER, "namespace": "argocd"}, "source": _source(SOURCE_PATHS["twc-wise-finch-ingress"][0], directory={"recurse": True}), "syncPolicy": {"syncOptions": ["CreateNamespace=true"]}, "trackingOwner": ROOT_APPLICATION},
    "cert-manager": {"metadata": {"labels": {"app.kubernetes.io/component": "cert-manager", "wget-cloud.io/profile": CONTEXT}, "annotations": {"argocd.argoproj.io/sync-wave": "-12"}}, "project": "wget-cloud", "destination": {"server": DESTINATION_SERVER, "namespace": "cert-manager"}, "source": _source(SOURCE_PATHS["cert-manager"][0], helm={"releaseName": "cert-manager", "valueFiles": ["../../components/clusters/twc-wise-finch/core/cert-manager/values.yaml"]}), "syncPolicy": {"syncOptions": ["CreateNamespace=true", "ServerSideApply=true"]}, "trackingOwner": "twc-wise-finch-ingress"},
    "traefik": {"metadata": {"labels": {}, "annotations": {"argocd.argoproj.io/sync-wave": "-10"}}, "project": "wget-cloud", "destination": {"server": DESTINATION_SERVER, "namespace": "traefik"}, "sources": [_source(SOURCE_PATHS["traefik"][0], helm={"releaseName": "traefik", "skipCrds": True, "valueFiles": ["$values/infrastructure/k8s/components/clusters/twc-wise-finch/core/ingress-controller/values.yaml"]}), _source(".", ref="values"), _source(SOURCE_PATHS["traefik"][2], directory={"include": "ingress-class.yaml"})], "syncPolicy": {"syncOptions": ["CreateNamespace=true", "ServerSideApply=true"]}, "trackingOwner": "twc-wise-finch-ingress"},
    "ingress-canary": {"metadata": {"labels": {}, "annotations": {"argocd.argoproj.io/sync-wave": "-9"}}, "project": "wget-cloud", "destination": {"server": DESTINATION_SERVER, "namespace": "traefik"}, "source": _source(SOURCE_PATHS["ingress-canary"][0]), "syncPolicy": {"syncOptions": ["CreateNamespace=true", "ServerSideApply=true"]}, "trackingOwner": "twc-wise-finch-ingress"},
    "twc-wise-finch-ingress-issuer": {"metadata": {"labels": {"wget-cloud.io/profile": CONTEXT}, "annotations": {"argocd.argoproj.io/sync-wave": "-8"}}, "project": "wget-cloud", "destination": {"server": DESTINATION_SERVER, "namespace": "cert-manager"}, "source": _source(SOURCE_PATHS["twc-wise-finch-ingress-issuer"][0], directory={"include": "issuer.yaml"}), "syncPolicy": {"syncOptions": ["CreateNamespace=true", "ServerSideApply=true"]}, "trackingOwner": "twc-wise-finch-ingress"},
    "argocd-public": {"metadata": {"labels": {"wget-cloud.io/profile": CONTEXT}, "annotations": {"argocd.argoproj.io/sync-wave": "-7"}}, "project": "wget-cloud", "destination": {"server": DESTINATION_SERVER, "namespace": "argocd"}, "source": _source(SOURCE_PATHS["argocd-public"][0]), "syncPolicy": {"syncOptions": ["ServerSideApply=true"]}, "trackingOwner": "twc-wise-finch-ingress"},
}
INSTALLED_PATHS = {
    "runner": RUNNER,
    "cli": CLI,
    "manifest": MANIFEST,
    "kubeconfig": KUBECONFIG,
}
POLICY_PATHS = {"gitCredential": GIT_CREDENTIAL}
SAFE_ENV = {
    "HOME": "/var/empty",
    "PATH": "/usr/bin:/bin",
    "LANG": "C",
    "LC_ALL": "C",
    "KUBECONFIG": KUBECONFIG,
}
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
REVISION_RE = re.compile(r"[0-9a-f]{40}\Z")


class PolicyError(RuntimeError):
    """A deliberately non-specific fail-closed policy rejection."""


def _reject() -> None:
    raise PolicyError("ingress recovery policy rejected")


def _dict(value: Any, keys: Sequence[str]) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != set(keys):
        _reject()
    return value


def _validate_acl(value: Any) -> None:
    if value != []:
        _reject()


def _validate_artifact(value: Any, mode: str, *, sha: bool = True, acl: Any = None) -> None:
    keys = ["owner", "group", "mode", "acl", "linkCount"]
    if sha:
        keys.append("sha256")
    item = _dict(value, keys)
    if item["owner"] != "root" or item["group"] != "wheel" or item["mode"] != mode:
        _reject()
    if item["acl"] != ([] if acl is None else acl):
        _reject()
    if item["linkCount"] != 1:
        _reject()
    if sha and (not isinstance(item["sha256"], str) or HASH_RE.fullmatch(item["sha256"]) is None):
        _reject()


def validate_manifest(policy: Any) -> None:
    root = _dict(policy, ("schemaVersion", "installedPaths", "paths", "artifacts", "cluster", "stages", "profileBundles", "forbiddenBundles"))
    if root["schemaVersion"] != 1 or isinstance(root["schemaVersion"], bool):
        _reject()
    paths = _dict(root["installedPaths"], tuple(INSTALLED_PATHS))
    if dict(paths) != INSTALLED_PATHS:
        _reject()
    policy_paths = _dict(root["paths"], tuple(POLICY_PATHS))
    if dict(policy_paths) != POLICY_PATHS:
        _reject()
    artifacts = _dict(root["artifacts"], (*INSTALLED_PATHS, *POLICY_PATHS))
    _validate_artifact(artifacts["runner"], "0555")
    _validate_artifact(artifacts["cli"], "0555")
    _validate_artifact(artifacts["manifest"], "0444", sha=False)
    _validate_artifact(artifacts["kubeconfig"], "0400", acl=SAFE_READ_ACL)
    _validate_artifact(artifacts["gitCredential"], "0600", sha=False, acl=SAFE_READ_ACL)
    cluster = _dict(root["cluster"], ("context", "rootApplication", "previousTagObject", "previousCommit", "targetTag", "targetTagObject", "targetCommit"))
    if cluster["context"] != CONTEXT or cluster["rootApplication"] != ROOT_APPLICATION:
        _reject()
    for key in ("previousTagObject", "previousCommit", "targetTagObject", "targetCommit"):
        if not isinstance(cluster[key], str) or REVISION_RE.fullmatch(cluster[key]) is None:
            _reject()
    if cluster["previousTagObject"] != PREVIOUS_TAG_OBJECT or cluster["previousCommit"] != PREVIOUS_COMMIT:
        _reject()
    if cluster["targetTag"] != TARGET_TAG or cluster["targetTagObject"] != TARGET_TAG_OBJECT or cluster["targetCommit"] != TARGET_COMMIT:
        _reject()
    if cluster["targetTagObject"] == cluster["targetCommit"] or cluster["targetCommit"] == cluster["previousCommit"]:
        _reject()
    stages = root["stages"]
    if not isinstance(stages, list) or len(stages) != len(STAGES):
        _reject()
    observed = []
    for item in stages:
        stage = _dict(item, ("stage", "name", "operation", "sourcePaths"))
        if isinstance(stage["stage"], bool) or not isinstance(stage["stage"], int):
            _reject()
        if not isinstance(stage["name"], str) or not isinstance(stage["operation"], str):
            _reject()
        if stage["sourcePaths"] != SOURCE_PATHS.get(stage["name"]):
            _reject()
        observed.append((stage["stage"], stage["name"], stage["operation"]))
    if tuple(observed) != STAGES:
        _reject()
    if root["profileBundles"] != PROFILE_BUNDLES or root["forbiddenBundles"] != FORBIDDEN_BUNDLES:
        _reject()


def _identity_ok(item: Mapping[str, Any]) -> bool:
    identities = (item.get("pathIdentity"), item.get("descriptorIdentity"), item.get("postDescriptorIdentity"))
    return all(isinstance(value, dict) and set(value) == {"device", "inode"} for value in identities) and identities[0] == identities[1] == identities[2]


def _evidence(inspect_path: Callable[[str], Mapping[str, Any]], path: str) -> Mapping[str, Any]:
    try:
        item = inspect_path(path)
    except (KeyError, OSError, RuntimeError, TypeError, ValueError):
        _reject()
    if not isinstance(item, Mapping):
        _reject()
    return item


def _fd_sha256(descriptor: int) -> str:
    digest = hashlib.sha256()
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)
    except OSError:
        _reject()


def _acl(path: Path) -> list[Mapping[str, Any]]:
    try:
        result = subprocess.run(
            ["/bin/ls", "-lde", str(path)], stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, timeout=5, check=False,
            shell=False, env={"HOME": "/var/empty", "PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
        )
    except (OSError, subprocess.TimeoutExpired):
        _reject()
    if result.returncode != 0:
        _reject()
    entries = []
    for line in result.stdout.splitlines()[1:]:
        match = re.fullmatch(r"\s*\d+:\s+(\S+)\s+(allow|deny)\s+(.+?)\s*", line)
        if match is None:
            _reject()
        permissions = [part.strip() for part in match.group(3).split(",") if part.strip()]
        entries.append({
            "inherited": "inherited" in permissions,
            "principal": f"user:{DARWIN_USER_UUID}" if match.group(1) in {DARWIN_USER_UUID, "estev"} else f"untrusted:{match.group(1)}",
            "type": match.group(2),
            "permissions": [part for part in permissions if part != "inherited"],
        })
    return entries


def inspect_path(path_value: str) -> Mapping[str, Any]:
    path = Path(path_value)
    descriptor = -1
    try:
        before = path.lstat()
        canonical = path.resolve(strict=True)
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(str(path), flags)
        opened = os.fstat(descriptor)
        kind = "file" if stat.S_ISREG(opened.st_mode) else "directory" if stat.S_ISDIR(opened.st_mode) else "other"
        digest = _fd_sha256(descriptor) if kind == "file" else None
        acl = _acl(path)
        after = os.fstat(descriptor)
        post_digest = _fd_sha256(descriptor) if kind == "file" else None
        post_path = path.lstat()
        identity = lambda value: {"device": value.st_dev, "inode": value.st_ino}
        stable = all(
            getattr(before, field) == getattr(opened, field) == getattr(after, field) == getattr(post_path, field)
            for field in ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode", "st_nlink")
        ) and digest == post_digest
        result = {
            "path": path_value, "canonicalPath": str(canonical), "kind": kind,
            "symlink": stat.S_ISLNK(before.st_mode), "owner": pwd.getpwuid(opened.st_uid).pw_name,
            "group": grp.getgrgid(opened.st_gid).gr_name, "mode": format(stat.S_IMODE(opened.st_mode), "04o"),
            "acl": acl, "linkCount": opened.st_nlink, "pathIdentity": identity(before),
            "descriptorIdentity": identity(opened), "postDescriptorIdentity": identity(after),
            "descriptorVerified": stable, "effectiveWritable": os.access(path, os.W_OK, effective_ids=True),
        }
        if kind == "file":
            result.update(sha256=digest, descriptorSha256=digest, postDescriptorSha256=post_digest)
        return result
    except (KeyError, OSError, RuntimeError, TypeError, ValueError):
        _reject()
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _validate_common(item: Mapping[str, Any], path: str, kind: str) -> None:
    if item.get("path") != path or item.get("canonicalPath") != path:
        _reject()
    if item.get("kind") != kind or item.get("symlink") is not False:
        _reject()
    if item.get("owner") != "root" or item.get("group") != "wheel":
        _reject()
    if item.get("descriptorVerified") is not True or item.get("effectiveWritable") is not False:
        _reject()
    if not _identity_ok(item):
        _reject()


def validate_installation(policy: Mapping[str, Any], inspect_path: Callable[[str], Mapping[str, Any]]) -> None:
    validate_manifest(policy)
    for path in ("/", "/usr", "/usr/local", "/usr/local/libexec", "/usr/local/libexec/wget-cloud-ingress-recovery", "/usr/local/etc", "/usr/local/etc/wget-cloud-ingress-recovery"):
        item = _evidence(inspect_path, path)
        _validate_common(item, path, "directory")
        if item.get("mode") != "0755" or item.get("acl") != []:
            _reject()
    artifact_paths = {**policy["installedPaths"], **policy["paths"]}
    for name, path in artifact_paths.items():
        contract = policy["artifacts"][name]
        item = _evidence(inspect_path, path)
        _validate_common(item, path, "file")
        if item.get("mode") != contract["mode"] or item.get("acl") != contract["acl"]:
            _reject()
        if item.get("linkCount") != 1:
            _reject()
        if "sha256" in contract:
            expected = contract["sha256"]
            if (item.get("sha256"), item.get("descriptorSha256"), item.get("postDescriptorSha256")) != (expected, expected, expected):
                _reject()


def read_git_credential_fd(
    policy: Mapping[str, Any], *, inspect_path: Callable[[str], Mapping[str, Any]],
    open_fd: Callable[[str, int], int] = os.open, read_fd: Callable[[int, int], bytes] = os.read,
    fstat_fd: Callable[[int], Any] = os.fstat, close_fd: Callable[[int], None] = os.close,
) -> str:
    validate_installation(policy, inspect_path)
    path = policy["paths"]["gitCredential"]
    item = _evidence(inspect_path, path)
    identity = item.get("descriptorIdentity")
    descriptor = -1
    try:
        descriptor = open_fd(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0))
        opened = fstat_fd(descriptor)
        if not isinstance(identity, Mapping) or (opened.st_dev, opened.st_ino) != (identity.get("device"), identity.get("inode")):
            _reject()
        size = getattr(opened, "st_size", None)
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0 or size >= 16384:
            _reject()
        raw = read_fd(descriptor, size + 1)
        after = fstat_fd(descriptor)
        if (
            (after.st_dev, after.st_ino) != (identity.get("device"), identity.get("inode"))
            or getattr(after, "st_size", None) != size
        ):
            _reject()
        if not isinstance(raw, bytes) or len(raw) != size:
            _reject()
        token = raw.decode("utf-8")
        if not token or token != token.strip() or any(character.isspace() for character in token):
            _reject()
        return token
    except (OSError, UnicodeDecodeError, TypeError, ValueError):
        _reject()
    finally:
        if descriptor >= 0:
            try:
                close_fd(descriptor)
            except OSError:
                pass


def read_attested_text_fd(
    policy: Mapping[str, Any], name: str, *, inspect_path: Callable[[str], Mapping[str, Any]],
    open_fd: Callable[[str, int], int] = os.open, read_fd: Callable[[int, int], bytes] = os.read,
    fstat_fd: Callable[[int], Any] = os.fstat, close_fd: Callable[[int], None] = os.close,
) -> str:
    validate_installation(policy, inspect_path)
    if name not in policy["installedPaths"]:
        _reject()
    path = policy["installedPaths"][name]
    item = _evidence(inspect_path, path)
    identity = item.get("descriptorIdentity")
    descriptor = -1
    try:
        descriptor = open_fd(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0))
        opened = fstat_fd(descriptor)
        if not isinstance(identity, Mapping) or (opened.st_dev, opened.st_ino) != (identity.get("device"), identity.get("inode")):
            _reject()
        chunks, total = [], 0
        while True:
            chunk = read_fd(descriptor, 4096)
            if not chunk:
                break
            total += len(chunk)
            if not isinstance(chunk, bytes) or total > 1024 * 1024:
                _reject()
            chunks.append(chunk)
        after = fstat_fd(descriptor)
        if (after.st_dev, after.st_ino) != (identity.get("device"), identity.get("inode")):
            _reject()
        return b"".join(chunks).decode("utf-8")
    except (OSError, UnicodeDecodeError, TypeError, ValueError):
        _reject()
    finally:
        if descriptor >= 0:
            try:
                close_fd(descriptor)
            except OSError:
                pass


def read_promotion_manifest_fd(
    *, inspect_path: Callable[[str], Mapping[str, Any]],
    open_fd: Callable[[str, int], int] = os.open,
    read_fd: Callable[[int, int], bytes] = os.read,
    fstat_fd: Callable[[int], Any] = os.fstat,
    close_fd: Callable[[int], None] = os.close,
) -> Mapping[str, Any]:
    item = _evidence(inspect_path, MANIFEST)
    if item.get("path") != MANIFEST or item.get("canonicalPath") != MANIFEST or item.get("kind") != "file":
        _reject()
    if item.get("owner") != "root" or item.get("group") != "wheel" or item.get("mode") != "0444" or item.get("acl") != [] or item.get("linkCount") != 1:
        _reject()
    if item.get("symlink") is not False or item.get("effectiveWritable") is not False or item.get("descriptorVerified") is not True or not _identity_ok(item):
        _reject()
    identity = item["descriptorIdentity"]
    descriptor = -1
    try:
        descriptor = open_fd(MANIFEST, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0))
        before = fstat_fd(descriptor)
        if (before.st_dev, before.st_ino) != (identity["device"], identity["inode"]):
            _reject()
        chunks, total = [], 0
        while True:
            chunk = read_fd(descriptor, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > 1024 * 1024:
                _reject()
            chunks.append(chunk)
        after = fstat_fd(descriptor)
        if (after.st_dev, after.st_ino) != (identity["device"], identity["inode"]):
            _reject()
        value = json.loads(b"".join(chunks).decode("utf-8"))
        validate_manifest(value)
        return value
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        _reject()
    finally:
        if descriptor >= 0:
            try:
                close_fd(descriptor)
            except OSError:
                pass


def _run(run_process: Callable[..., Any], argv: Sequence[str]) -> Any:
    try:
        return run_process(
            list(argv), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            timeout=660, check=False, shell=False, env=dict(SAFE_ENV),
        )
    except (OSError, subprocess.TimeoutExpired, TypeError, ValueError):
        _reject()


def normalize_application_state(value: Mapping[str, Any], policy: Mapping[str, Any], revision_map: Mapping[str, str]) -> Mapping[str, Any]:
    status = value.get("status")
    spec = value.get("spec")
    if not isinstance(status, Mapping) or not isinstance(spec, Mapping) or status.get("conditions", []) != []:
        _reject()
    sources = spec.get("sources") if "sources" in spec else [spec.get("source")]
    if not isinstance(sources, list) or not sources or not all(isinstance(item, Mapping) for item in sources):
        _reject()
    source_revisions = [item.get("targetRevision") for item in sources]
    if not all(isinstance(item, str) and item for item in source_revisions):
        _reject()
    sync_state = status.get("sync")
    operation = status.get("operationState")
    if not isinstance(sync_state, Mapping):
        _reject()
    multi = len(sources) > 1
    reported = sync_state.get("revisions") if multi else [sync_state.get("revision")]
    if reported is None:
        reported = [None] * len(sources)
    if not isinstance(reported, list) or len(reported) != len(sources):
        _reject()
    if operation is None:
        operation_phase = None
    elif isinstance(operation, Mapping) and operation.get("phase") == "Succeeded" and isinstance(operation.get("finishedAt"), str):
        historical_result = operation.get("syncResult")
        if not isinstance(historical_result, Mapping):
            _reject()
        historical_reported = historical_result.get("revisions") if multi else [historical_result.get("revision")]
        if historical_reported is None or not isinstance(historical_reported, list) or len(historical_reported) != len(sources):
            _reject()
        if not all(isinstance(item, str) and item in revision_map for item in historical_reported):
            _reject()
        operation_phase = (
            "Succeeded"
            if (
                historical_reported == reported
                and all(item is not None for item in reported)
                and sync_state.get("status") == "Synced"
                and status.get("health", {}).get("status") == "Healthy"
            )
            else None
        )
    elif isinstance(operation, Mapping) and operation.get("phase") == "Succeeded":
        result = operation.get("syncResult")
        if not isinstance(result, Mapping):
            _reject()
        result_reported = result.get("revisions") if multi else [result.get("revision")]
        if result_reported is None:
            result_reported = [None] * len(sources)
        if reported != result_reported or any(item is None for item in reported):
            _reject()
        operation_phase = "Succeeded"
    else:
        _reject()
    if any(item is None for item in reported):
        if not all(item is None for item in reported) or operation_phase is not None:
            _reject()
        commits = [None] * len(reported)
    elif not all(isinstance(item, str) and item in revision_map for item in reported):
        _reject()
    else:
        commits = [revision_map[item] for item in reported]
    if len(set(reported)) != 1 or len(set(commits)) != 1:
        _reject()
    return {
        "reportedRevision": reported[0], "reportedRevisions": list(reported), "commitSha": commits[0],
        "sourceRevisions": source_revisions, "sync": sync_state.get("status"),
        "health": status.get("health", {}).get("status"), "operation": operation_phase,
    }


def validate_application_contract(value: Mapping[str, Any], name: str, contract: Mapping[str, Any]) -> Mapping[str, Any]:
    if name not in APPLICATION_CONTRACTS:
        _reject()
    if contract != APPLICATION_CONTRACTS[name]:
        allowed = json.loads(json.dumps(APPLICATION_CONTRACTS[ROOT_APPLICATION])) if name == ROOT_APPLICATION else None
        if allowed is not None:
            allowed["source"]["targetRevision"] = PREVIOUS_TAG
        if contract != allowed:
            _reject()
    metadata = value.get("metadata")
    spec = value.get("spec")
    if not isinstance(metadata, Mapping) or not isinstance(spec, Mapping):
        _reject()
    expected_meta = contract["metadata"]
    expected_spec = {key: value for key, value in contract.items() if key not in {"metadata", "trackingOwner"}}
    annotations = dict(metadata.get("annotations") or {})
    labels = dict(metadata.get("labels") or {})
    owner = contract["trackingOwner"]
    last_applied = annotations.pop("kubectl.kubernetes.io/last-applied-configuration", None)
    if last_applied is not None:
        try:
            mechanical = json.loads(last_applied)
        except (TypeError, json.JSONDecodeError):
            _reject()
        minimal = {"apiVersion": "argoproj.io/v1alpha1", "kind": "Application", "metadata": {"name": name, "namespace": "argocd"}}
        if mechanical != minimal:
            if not isinstance(mechanical, Mapping) or set(mechanical) != {"apiVersion", "kind", "metadata", "spec"}:
                _reject()
            applied_metadata = mechanical.get("metadata")
            if not isinstance(applied_metadata, Mapping) or set(applied_metadata) - {"name", "namespace", "labels", "annotations"}:
                _reject()
            if {
                "name": applied_metadata.get("name"),
                "namespace": applied_metadata.get("namespace"),
                "labels": dict(applied_metadata.get("labels") or {}),
                "annotations": dict(applied_metadata.get("annotations") or {}),
            } != {
                "name": name,
                "namespace": "argocd",
                "labels": dict(expected_meta["labels"]),
                "annotations": dict(expected_meta["annotations"]),
            }:
                _reject()
            if mechanical["apiVersion"] != "argoproj.io/v1alpha1" or mechanical["kind"] != "Application" or mechanical["spec"] != expected_spec:
                _reject()
    expected_annotations = dict(expected_meta["annotations"])
    expected_labels = dict(expected_meta["labels"])
    if owner:
        tracking = annotations.pop("argocd.argoproj.io/tracking-id", None)
        instance = labels.pop("argocd.argoproj.io/instance", None)
        expected_tracking = f"{owner}:argoproj.io/Application:argocd/{name}"
        if (tracking is not None and tracking != expected_tracking) or (instance is not None and instance != owner):
            _reject()
        if tracking is None and instance is None:
            _reject()
    server_owned = {"uid", "resourceVersion", "generation", "creationTimestamp", "managedFields"}
    if set(metadata) - ({"name", "namespace", "labels", "annotations"} | server_owned):
        _reject()
    normalized_metadata = {"name": metadata.get("name"), "namespace": metadata.get("namespace"), "labels": labels, "annotations": annotations}
    if normalized_metadata != {"name": name, "namespace": "argocd", "labels": expected_labels, "annotations": expected_annotations}:
        _reject()
    if spec != expected_spec:
        _reject()
    normalized = normalize_application_state(value, {"cluster": {"targetTagObject": TARGET_TAG_OBJECT, "targetCommit": TARGET_COMMIT}}, {TARGET_TAG_OBJECT: TARGET_COMMIT, PREVIOUS_TAG_OBJECT: PREVIOUS_COMMIT})
    normalized.update(name=name, trackingOwner=owner)
    return normalized


def classify_stage_state(stage: int, normalized: Mapping[str, Any], policy: Mapping[str, Any]) -> str:
    target = policy["cluster"]
    if (
        normalized.get("reportedRevision") == target["targetTagObject"]
        and normalized.get("commitSha") == target["targetCommit"]
        and all(item == target["targetTag"] for item in normalized.get("sourceRevisions", []))
        and normalized.get("sync") == "Synced" and normalized.get("health") == "Healthy" and normalized.get("operation") == "Succeeded"
    ):
        return "completed"
    if stage == 1 and normalized.get("reportedRevision") == target["previousTagObject"] and normalized.get("commitSha") == target["previousCommit"] and normalized.get("sync") == "OutOfSync" and normalized.get("health") == "Healthy" and normalized.get("operation") is None:
        return "pending"
    if stage > 1 and (normalized.get("reportedRevision"), normalized.get("commitSha")) in {
        (None, None),
        (target["targetTagObject"], target["targetCommit"]),
    } and all(item == target["targetTag"] for item in normalized.get("sourceRevisions", [])) and normalized.get("sync") == "OutOfSync" and normalized.get("health") == "Missing" and normalized.get("operation") is None:
        return "pending"
    _reject()


def validate_stage_live_scope(stage: int, values: Any, policy: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if not isinstance(stage, int) or stage < 1 or stage > len(STAGES) or not isinstance(values, list):
        _reject()
    names = [item[1] for item in STAGES]
    expected_names = names[:1] if stage == 1 else names[:2] if stage == 2 else names
    if len(values) != len(expected_names):
        _reject()
    normalized_values: list[Mapping[str, Any]] = []
    for index, (name, value) in enumerate(zip(expected_names, values)):
        if not isinstance(value, Mapping) or value.get("metadata", {}).get("name") != name:
            _reject()
        contract = APPLICATION_CONTRACTS[name]
        if stage == 1 and value.get("spec", {}).get("source", {}).get("targetRevision") == PREVIOUS_TAG:
            contract = json.loads(json.dumps(contract))
            contract["source"]["targetRevision"] = PREVIOUS_TAG
        normalized = validate_application_contract(value, name, contract)
        if stage == 1:
            state = classify_stage_state(1, normalized, policy)
            if state not in {"pending", "completed"}:
                _reject()
        elif index < stage - 1:
            if classify_stage_state(index + 1, normalized, policy) != "completed":
                _reject()
        elif index == stage - 1:
            state = classify_stage_state(index + 1, normalized, policy)
            if state not in {"pending", "completed"}:
                _reject()
            if state == "pending" and (normalized.get("reportedRevision"), normalized.get("commitSha")) not in {
                (None, None), (policy["cluster"]["targetTagObject"], policy["cluster"]["targetCommit"]),
            }:
                _reject()
        elif classify_stage_state(index + 1, normalized, policy) != "pending":
            _reject()
        normalized_values.append(normalized)
    return normalized_values


def _read_application(run_process: Callable[..., Any], name: str) -> Mapping[str, Any]:
    result = _run(run_process, (*ARGO_PREFIX, "app", "get", name, "--app-namespace", "argocd", "-o", "json"))
    if getattr(result, "returncode", 1) != 0:
        _reject()
    try:
        value = json.loads(getattr(result, "stdout", ""))
    except (json.JSONDecodeError, TypeError):
        _reject()
    if not isinstance(value, dict):
        _reject()
    contract = APPLICATION_CONTRACTS[name]
    if name == ROOT_APPLICATION and value.get("spec", {}).get("source", {}).get("targetRevision") == PREVIOUS_TAG:
        contract = json.loads(json.dumps(contract))
        contract["source"]["targetRevision"] = PREVIOUS_TAG
    return validate_application_contract(value, name, contract)


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _reject()
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00").astimezone(timezone.utc)
    except ValueError:
        _reject()


def _object_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def _canonical_rule(rule: Mapping[str, Any]) -> Mapping[str, Any]:
    return {key: rule.get(key) for key in ("id", "localIp", "localPort", "protocol", "publicIp", "publicPort")}


def _rules_digest(rules: Sequence[Mapping[str, Any]]) -> str:
    normalized = sorted((_canonical_rule(rule) for rule in rules), key=lambda item: (item["publicIp"], item["publicPort"], item["protocol"], item["localIp"], item["localPort"], item["id"]))
    return _object_digest(normalized)


def _infrastructure_digest(value: Any) -> str:
    return "sha256:" + _object_digest(value)


def _published_digest(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def _validate_published_router_gate(value: Mapping[str, Any], now: datetime) -> bool:
    if set(value) != {"approvalId", "observedAt", "expiresAt", "routerPlan", "routerPoststate", "promotionPlan"}:
        return False
    if value["approvalId"] != TARGET_TAG:
        return False
    observed, expires = _parse_timestamp(value["observedAt"]), _parse_timestamp(value["expiresAt"])
    if not (observed <= now.astimezone(timezone.utc) < expires and 0 < (expires - observed).total_seconds() <= 300):
        return False
    plan = value["routerPlan"]
    if not isinstance(plan, Mapping) or set(plan) != {"apiVersion", "kind", "metadata", "spec"}:
        return False
    if plan["apiVersion"] != "infrastructure.wget-cloud/v1alpha1" or plan["kind"] != "TimewebRouterRecoveryPlan" or plan["metadata"] != {"name": CONTEXT}:
        return False
    plan_spec = plan["spec"]
    plan_keys = {"dryRun", "approvedForApply", "routerId", "actions", "contractDigest", "routerSnapshotDigest", "ingressServiceDigest", "dnsSnapshotDigest", "readinessEvidenceDigest", "actionDigest", "finalDigest"}
    if not isinstance(plan_spec, Mapping) or set(plan_spec) != plan_keys or plan_spec["dryRun"] is not True or plan_spec["approvedForApply"] is not False:
        return False
    router_id = plan_spec["routerId"]
    if not isinstance(router_id, str) or re.fullmatch(r"router-[a-z0-9][a-z0-9-]*", router_id) is None:
        return False
    desired = [
        {"protocol": "tcp", "local": {"ip": "192.168.0.16", "port": "30080"}, "public": {"ip": "72.56.0.250", "port": "80"}},
        {"protocol": "tcp", "local": {"ip": "192.168.0.16", "port": "30443"}, "public": {"ip": "72.56.0.250", "port": "443"}},
    ]
    actions = plan_spec["actions"]
    if not isinstance(actions, list) or len(actions) != 2:
        return False
    for action, rule in zip(actions, desired):
        create = {
            "disposition": "create",
            "request": {"method": "POST", "path": f"/api/v1/routers/{router_id}/dnat-rules", "body": rule},
            "response": {"ruleIdSemantics": "captureCreatedRuleId"},
            "rollback": {"method": "DELETE", "path": f"/api/v1/routers/{router_id}/dnat-rules/{{created_dnat_id}}", "createdByThisRunOnly": True},
        }
        if action != create:
            if not isinstance(action, Mapping) or set(action) != {"disposition", "existingRuleId", "desiredRule", "rollback"}:
                return False
            if action["disposition"] != "adopt" or action["desiredRule"] != rule or action["rollback"] != {"action": "preserve", "delete": False}:
                return False
            if not isinstance(action["existingRuleId"], str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", action["existingRuleId"]) is None:
                return False
    if plan_spec["actionDigest"] != _infrastructure_digest(actions):
        return False
    lineage_keys = ("contractDigest", "routerSnapshotDigest", "ingressServiceDigest", "dnsSnapshotDigest", "readinessEvidenceDigest", "actionDigest")
    lineage = {key: plan_spec[key] for key in lineage_keys}
    if not all(_published_digest(item) for item in lineage.values()) or plan_spec["finalDigest"] != _infrastructure_digest(lineage):
        return False
    poststate = value["routerPoststate"]
    if not isinstance(poststate, Mapping) or set(poststate) != {"apiVersion", "kind", "spec"} or poststate["apiVersion"] != "infrastructure.wget-cloud/v1alpha1" or poststate["kind"] != "TimewebRouterRecoveryPoststate":
        return False
    post = poststate["spec"]
    if not isinstance(post, Mapping) or set(post) != {"observedAt", "readOnly", "routerId", "actionDigest", "planFinalDigest", "rules"}:
        return False
    if post["readOnly"] is not True or post["routerId"] != router_id or post["actionDigest"] != plan_spec["actionDigest"] or post["planFinalDigest"] != plan_spec["finalDigest"]:
        return False
    post_observed = _parse_timestamp(post["observedAt"])
    if not (observed <= post_observed <= now.astimezone(timezone.utc)):
        return False
    rules = post["rules"]
    if not isinstance(rules, list) or len(rules) != 2 or len({rule.get("id") for rule in rules if isinstance(rule, Mapping)}) != 2:
        return False
    desired_order = [("192.168.0.16", "30080", "72.56.0.250", "80", "tcp"), ("192.168.0.16", "30443", "72.56.0.250", "443", "tcp")]
    if [(rule.get("localIp"), rule.get("localPort"), rule.get("publicIp"), rule.get("publicPort"), rule.get("protocol")) for rule in rules if isinstance(rule, Mapping)] != desired_order:
        return False
    for action, rule in zip(actions, rules):
        if action.get("disposition") == "adopt" and action.get("existingRuleId") != rule.get("id"):
            return False
    promotion = value["promotionPlan"]
    if not isinstance(promotion, Mapping) or set(promotion) != {"apiVersion", "kind", "metadata", "spec"} or promotion["apiVersion"] != "infrastructure.wget-cloud/v1alpha1" or promotion["kind"] != "TimewebGitOpsPromotionPlan" or promotion["metadata"] != {"name": "twc-wise-finch-argocd-recovery"}:
        return False
    spec = promotion["spec"]
    promotion_keys = {"stage", "dryRun", "approvedForApply", "revision", "actions", "contractDigest", "liveSnapshotDigest", "revisionSnapshotDigest", "actionDigest", "routerPlanDigest", "routerPoststateDigest", "finalDigest"}
    if not isinstance(spec, Mapping) or set(spec) != promotion_keys or spec["stage"] != 7 or spec["dryRun"] is not True or spec["approvedForApply"] is not False:
        return False
    if spec["revision"] != {"tag": TARGET_TAG, "tagObjectSha": TARGET_TAG_OBJECT, "commitSha": TARGET_COMMIT}:
        return False
    if spec["actions"] != [{"action": "sync", "application": "argocd-public", "sourcePaths": SOURCE_PATHS["argocd-public"], "targetRevision": TARGET_TAG, "tagObjectSha": TARGET_TAG_OBJECT, "commitSha": TARGET_COMMIT, "prune": False}]:
        return False
    if spec["actionDigest"] != _infrastructure_digest(spec["actions"]):
        return False
    if spec["routerPlanDigest"] != _infrastructure_digest(plan) or spec["routerPoststateDigest"] != _infrastructure_digest(poststate):
        return False
    promotion_lineage_keys = ("contractDigest", "liveSnapshotDigest", "revisionSnapshotDigest", "actionDigest", "routerPlanDigest", "routerPoststateDigest")
    promotion_lineage = {key: spec[key] for key in promotion_lineage_keys}
    return all(_published_digest(item) for item in promotion_lineage.values()) and spec["finalDigest"] == _infrastructure_digest(promotion_lineage)


def validate_foundation_evidence(value: Any, *, now: datetime) -> str:
    if not isinstance(value, Mapping):
        _reject()
    try:
        observed, expires = _parse_timestamp(value["observedAt"]), _parse_timestamp(value["expiresAt"])
    except (KeyError, PolicyError):
        _reject()
    current = now.astimezone(timezone.utc)
    if not (observed <= current < expires and 0 < (expires - observed).total_seconds() <= 300):
        _reject()
    stage = value.get("stage5")
    if stage != {"application": "ingress-canary", "reportedRevision": TARGET_TAG_OBJECT, "commitSha": TARGET_COMMIT, "sync": "Synced", "health": "Healthy", "operation": "Succeeded"}:
        _reject()
    if value.get("service") != {"apiVersion": "v1", "kind": "Service", "namespace": "traefik", "name": "traefik", "type": "NodePort", "ports": [{"name": "web", "protocol": "TCP", "port": 80, "nodePort": 30080}, {"name": "websecure", "protocol": "TCP", "port": 443, "nodePort": 30443}]}:
        _reject()
    if value.get("endpointSlice") != {"apiVersion": "discovery.k8s.io/v1", "kind": "EndpointSlice", "namespace": "traefik", "serviceName": "traefik", "addresses": ["192.168.0.16"], "ready": True}:
        _reject()
    if value.get("nodePortProbes") != [{"address": "192.168.0.16:30080", "protocol": "tcp", "reachable": True}, {"address": "192.168.0.16:30443", "protocol": "tcp", "reachable": True}]:
        _reject()
    if value.get("dns") != {"host": "argocd.wget-cloud.ru", "type": "A", "expected": "72.56.0.250", "observed": "72.56.0.250"}:
        _reject()
    k8s_plan = {"path": "infrastructure/k8s/components/clusters/twc-wise-finch/dns/router-recovery.yaml", "tagObjectSha": TARGET_TAG_OBJECT, "commitSha": TARGET_COMMIT, "offlinePlanOnly": True}
    dns_plan = {"path": "infrastructure/k8s/components/clusters/twc-wise-finch/dns/cutover.yaml", "host": "argocd.wget-cloud.ru", "type": "A", "value": "72.56.0.250", "offlinePlanOnly": True}
    if value.get("offlinePlans") != {"k8sRouterPlanSha256": _object_digest(k8s_plan), "dnsPlanSha256": _object_digest(dns_plan), "k8sRouterPlan": k8s_plan, "dnsPlan": dns_plan}:
        _reject()
    if set(value) != {"observedAt", "expiresAt", "stage5", "service", "endpointSlice", "nodePortProbes", "dns", "offlinePlans"}:
        _reject()
    return _object_digest(value)


def validate_router_gate(value: Any, now: datetime) -> bool:
    try:
        if not isinstance(value, Mapping) or "routerPlan" not in value:
            return False
        return _validate_published_router_gate(value, now)
    except (KeyError, TypeError, PolicyError, ValueError):
        return False


def read_router_gate_fd(*, inspect_path: Callable[[str], Mapping[str, Any]], open_fd: Callable[[str, int], int] = os.open, read_fd: Callable[[int, int], bytes] = os.read, fstat_fd: Callable[[int], Any] = os.fstat, close_fd: Callable[[int], None] = os.close) -> Mapping[str, Any]:
    item = _evidence(inspect_path, ROUTER_GATE)
    if item.get("path") != ROUTER_GATE or item.get("canonicalPath") != ROUTER_GATE or item.get("kind") != "file" or item.get("owner") != "root" or item.get("group") != "wheel" or item.get("mode") != "0400" or item.get("acl") != SAFE_READ_ACL or item.get("linkCount") != 1 or item.get("symlink") is not False or item.get("effectiveWritable") is not False or item.get("descriptorVerified") is not True or not _identity_ok(item):
        _reject()
    identity = item["descriptorIdentity"]
    descriptor = -1
    try:
        descriptor = open_fd(ROUTER_GATE, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0))
        before = fstat_fd(descriptor)
        if (before.st_dev, before.st_ino) != (identity["device"], identity["inode"]):
            _reject()
        chunks, total = [], 0
        while True:
            chunk = read_fd(descriptor, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > 1024 * 1024:
                _reject()
            chunks.append(chunk)
        after = fstat_fd(descriptor)
        if (after.st_dev, after.st_ino) != (identity["device"], identity["inode"]):
            _reject()
        value = json.loads(b"".join(chunks).decode())
        if not isinstance(value, Mapping):
            _reject()
        return value
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        _reject()
    finally:
        if descriptor >= 0:
            close_fd(descriptor)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def _open_github_url(request: urllib.request.Request, *, timeout: float) -> Any:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirectHandler())
    return opener.open(request, timeout=timeout)


def _github_api_get_json(
    url: str, *, token: str, open_url: Callable[..., Any] = _open_github_url,
    max_response_bytes: int = MAX_GITHUB_RESPONSE_BYTES,
) -> Mapping[str, Any]:
    if (
        not isinstance(url, str)
        or not url.startswith(f"{GITHUB_API_BASE}/repos/{GITHUB_REPOSITORY}/")
        or not isinstance(token, str)
        or not token
        or any(character.isspace() for character in token)
        or isinstance(max_response_bytes, bool)
        or not isinstance(max_response_bytes, int)
        or max_response_bytes <= 0
        or max_response_bytes > MAX_GITHUB_RESPONSE_BYTES
    ):
        _reject()
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        request = urllib.request.Request(url, headers=headers, method="GET")
        with open_url(request, timeout=GITHUB_API_TIMEOUT) as response:
            if getattr(response, "status", None) != 200 or response.geturl() != url:
                _reject()
            content_type = response.headers.get("Content-Type")
            if not isinstance(content_type, str) or content_type.split(";", 1)[0].strip().lower() not in {
                "application/json", "application/vnd.github+json",
            }:
                _reject()
            raw = response.read(max_response_bytes + 1)
            if not isinstance(raw, bytes) or len(raw) > max_response_bytes:
                _reject()
            body = json.loads(raw.decode("utf-8"))
            return {"status": response.status, "url": response.geturl(), "body": body}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, urllib.error.URLError):
        _reject()


def _request_github_json(url: str, *, headers: Mapping[str, str], allow_redirects: bool) -> Mapping[str, Any]:
    expected_keys = {"Accept", "Authorization", "X-GitHub-Api-Version"}
    if allow_redirects is not False or not isinstance(headers, Mapping) or set(headers) != expected_keys:
        _reject()
    authorization = headers.get("Authorization")
    if (
        headers.get("Accept") != "application/vnd.github+json"
        or headers.get("X-GitHub-Api-Version") != "2022-11-28"
        or not isinstance(authorization, str)
        or not authorization.startswith("Bearer ")
    ):
        _reject()
    return _github_api_get_json(url, token=authorization[7:])


def _attest_tag(
    policy: Mapping[str, Any], *, token: str,
    request_json: Callable[..., Mapping[str, Any]] = _request_github_json,
) -> None:
    if not isinstance(token, str) or not token or any(character.isspace() for character in token):
        _reject()
    cluster = policy["cluster"]
    ref_url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPOSITORY}/git/ref/tags/{cluster['targetTag']}"
    tag_url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPOSITORY}/git/tags/{cluster['targetTagObject']}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        ref_response = _dict(request_json(ref_url, headers=headers, allow_redirects=False), ("status", "url", "body"))
        if ref_response["status"] != 200 or ref_response["url"] != ref_url:
            _reject()
        ref_body = _dict(ref_response["body"], ("ref", "node_id", "url", "object"))
        ref_object = _dict(ref_body["object"], ("type", "sha", "url"))
        expected_tag_url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPOSITORY}/git/tags/{cluster['targetTagObject']}"
        canonical_ref_url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPOSITORY}/git/refs/tags/{cluster['targetTag']}"
        if (
            ref_body["ref"] != f"refs/tags/{cluster['targetTag']}"
            or not isinstance(ref_body["node_id"], str)
            or not ref_body["node_id"]
            or ref_body["url"] != canonical_ref_url
            or ref_object != {"type": "tag", "sha": cluster["targetTagObject"], "url": expected_tag_url}
        ):
            _reject()
        tag_response = _dict(request_json(tag_url, headers=headers, allow_redirects=False), ("status", "url", "body"))
        if tag_response["status"] != 200 or tag_response["url"] != tag_url:
            _reject()
        tag_body = _dict(tag_response["body"], ("node_id", "tag", "sha", "url", "message", "tagger", "object", "verification"))
        tagger = _dict(tag_body["tagger"], ("name", "email", "date"))
        verification = _dict(tag_body["verification"], ("verified", "reason", "signature", "payload", "verified_at"))
        tag_object = _dict(tag_body["object"], ("type", "sha", "url"))
        expected_commit_url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPOSITORY}/git/commits/{cluster['targetCommit']}"
        if (
            not isinstance(tag_body["node_id"], str)
            or not tag_body["node_id"]
            or tag_body["tag"] != cluster["targetTag"]
            or tag_body["sha"] != cluster["targetTagObject"]
            or tag_body["url"] != tag_url
            or not isinstance(tag_body["message"], str)
            or not all(isinstance(tagger[key], str) for key in tagger)
            or verification != {
                "verified": False,
                "reason": "unsigned",
                "signature": None,
                "payload": None,
                "verified_at": None,
            }
            or tag_object != {"type": "commit", "sha": cluster["targetCommit"], "url": expected_commit_url}
        ):
            _reject()
    except PolicyError:
        raise
    except Exception:
        _reject()


def execute_stage(
    stage: int,
    app: str,
    revision: str,
    policy: Mapping[str, Any],
    *,
    router_gate: Any = None,
    now: Optional[datetime] = None,
    inspect_path: Callable[[str], Mapping[str, Any]],
    read_text: Callable[[str], str],
    run_process: Callable[..., Any] = subprocess.run,
    environ: Optional[Mapping[str, str]] = None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    convergence_timeout: float = 30.0,
) -> int:
    del environ, stderr
    validate_manifest(policy)
    expected = next((item for item in STAGES if item[0] == stage), None)
    if expected is None or expected[1] != app or revision != policy["cluster"]["targetCommit"]:
        _reject()
    current_time = now or datetime.now(timezone.utc)
    if stage == 7 and not validate_router_gate(router_gate, current_time):
        _reject()
    validate_installation(policy, inspect_path)
    token = read_git_credential_fd(policy, inspect_path=inspect_path)
    try:
        kubeconfig = read_text(KUBECONFIG)
    except (OSError, RuntimeError, TypeError, ValueError):
        _reject()
    if not isinstance(kubeconfig, str) or not kubeconfig.strip():
        _reject()
    validate_installation(policy, inspect_path)
    _attest_tag(policy, token=token)
    scope_names = [item[1] for item in (STAGES[:1] if stage == 1 else STAGES[:2] if stage == 2 else STAGES)]
    live_scope = []
    for name in scope_names:
        result = _run(run_process, (*ARGO_PREFIX, "app", "get", name, "--app-namespace", "argocd", "-o", "json"))
        if getattr(result, "returncode", 1) != 0:
            _reject()
        try:
            live_scope.append(json.loads(getattr(result, "stdout", "")))
        except (json.JSONDecodeError, TypeError):
            _reject()
    normalized_scope = validate_stage_live_scope(stage, live_scope, policy)
    current = normalized_scope[stage - 1]
    state = classify_stage_state(stage, current, policy)
    if state == "completed":
        _attest_tag(policy, token=token)
        stdout.write(json.dumps({"stage": stage, "app": app, "status": "already-ready"}, separators=(",", ":")) + "\n")
        return 0
    if stage == 1:
        result = _run(run_process, (*ARGO_PREFIX, "app", "set", app, "--app-namespace", "argocd", "--revision", policy["cluster"]["targetTag"]))
        if getattr(result, "returncode", 1) != 0:
            _reject()
        converged = False
        start = monotonic()
        while monotonic() - start <= convergence_timeout:
            candidate = _read_application(run_process, app)
            if (
                all(item == policy["cluster"]["targetTag"] for item in candidate.get("sourceRevisions", []))
                and candidate.get("reportedRevision") == policy["cluster"]["targetTagObject"]
                and candidate.get("commitSha") == policy["cluster"]["targetCommit"]
                and candidate.get("sync") == "OutOfSync"
                and candidate.get("health") == "Missing"
                and candidate.get("operation") is None
            ):
                converged = True
                break
            sleep(1.0)
        if not converged:
            _reject()
    validate_installation(policy, inspect_path)
    result = _run(run_process, (*ARGO_PREFIX, "app", "sync", app, "--app-namespace", "argocd", "--timeout", "600"))
    if getattr(result, "returncode", 1) != 0:
        _reject()
    result = _run(run_process, (*ARGO_PREFIX, "app", "wait", app, "--app-namespace", "argocd", "--sync", "--health", "--operation", "--timeout", "600"))
    if getattr(result, "returncode", 1) != 0:
        _reject()
    final_scope = []
    for name in scope_names:
        result = _run(run_process, (*ARGO_PREFIX, "app", "get", name, "--app-namespace", "argocd", "-o", "json"))
        if getattr(result, "returncode", 1) != 0:
            _reject()
        try:
            final_scope.append(json.loads(getattr(result, "stdout", "")))
        except (json.JSONDecodeError, TypeError):
            _reject()
    final_normalized = validate_stage_live_scope(stage, final_scope, policy)
    if classify_stage_state(stage, final_normalized[stage - 1], policy) != "completed":
        _reject()
    validate_installation(policy, inspect_path)
    _attest_tag(policy, token=token)
    stdout.write(json.dumps({"stage": stage, "app": app, "status": "synced"}, separators=(",", ":")) + "\n")
    return 0


def _load_manifest(path: str) -> Mapping[str, Any]:
    try:
        value = json.loads(open(path, "r", encoding="utf-8").read())
    except (OSError, json.JSONDecodeError):
        _reject()
    validate_manifest(value)
    return value


def main(
    argv: Optional[Sequence[str]] = None, *,
    inspect_path: Callable[[str], Mapping[str, Any]] = inspect_path,
    open_fd: Callable[[str, int], int] = os.open,
    read_fd: Callable[[int, int], bytes] = os.read,
    fstat_fd: Callable[[int], Any] = os.fstat,
    close_fd: Callable[[int], None] = os.close,
    run_process: Callable[..., Any] = subprocess.run,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True, type=int)
    parser.add_argument("--app", required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args(argv)
    if os.environ.get("WGC_GITOPS_INGRESS_RECOVERY_APPROVED") != "1":
        _reject()
    policy = read_promotion_manifest_fd(inspect_path=inspect_path, open_fd=open_fd, read_fd=read_fd, fstat_fd=fstat_fd, close_fd=close_fd)
    router_gate = read_router_gate_fd(inspect_path=inspect_path) if args.stage == 7 else None
    return execute_stage(
        args.stage, args.app, args.revision, policy,
        inspect_path=inspect_path,
        read_text=lambda path: read_attested_text_fd(policy, "kubeconfig", inspect_path=inspect_path, open_fd=open_fd, read_fd=read_fd, fstat_fd=fstat_fd, close_fd=close_fd),
        router_gate=router_gate,
        run_process=run_process,
        stdout=stdout,
        stderr=stderr,
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PolicyError:
        sys.stderr.write("ingress recovery policy rejected\n")
        raise SystemExit(1)
