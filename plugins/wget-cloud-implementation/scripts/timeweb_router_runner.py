#!/usr/bin/env python3
"""Fail-closed Timeweb Cloud DNAT recovery runner."""

from __future__ import annotations

import argparse
import grp
import hashlib
import json
import os
import pwd
import re
import stat
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence, TextIO


RUNNER = "/usr/local/libexec/wget-cloud-ingress-recovery/router_runner.py"
MANIFEST = "/usr/local/libexec/wget-cloud-ingress-recovery/router-manifest.json"
CREDENTIAL = "/usr/local/etc/wget-cloud-ingress-recovery/timeweb-cloud-token"
API_BASE = "https://api.timeweb.cloud"
ROUTERS_PATH = "/api/v1/routers"
DNAT_PATH = "/api/v1/routers/{router_id}/dnat-rules"
PUBLIC_IP = "72.56.0.250"
LOCAL_IP = "192.168.0.16"
APPROVAL_ID = "twc-wise-finch-argocd-recovery-2026-08-17.1"
DARWIN_USER_UUID = "FFFFEEEE-DDDD-CCCC-BBBB-AAAA000001F5"
SAFE_ACL = [{
    "inherited": False,
    "principal": f"user:{DARWIN_USER_UUID}",
    "type": "allow",
    "permissions": ["read", "readattr", "readextattr", "readsecurity"],
}]
INSTALLED_PATHS = {"runner": RUNNER, "manifest": MANIFEST, "credential": CREDENTIAL}
DESIRED_RULES = (
    {"protocol": "tcp", "local": {"ip": LOCAL_IP, "port": "30080"}, "public": {"ip": PUBLIC_IP, "port": "80"}},
    {"protocol": "tcp", "local": {"ip": LOCAL_IP, "port": "30443"}, "public": {"ip": PUBLIC_IP, "port": "443"}},
)
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
ROUTER_ID_RE = re.compile(r"router-[a-z0-9][a-z0-9-]*\Z")
SYSTEM_DIRECTORIES = (
    "/", "/usr", "/usr/local", "/usr/local/libexec",
    "/usr/local/libexec/wget-cloud-ingress-recovery", "/usr/local/etc",
    "/usr/local/etc/wget-cloud-ingress-recovery",
)
TARGET_TAG_OBJECT = "344a7e5f87e6c9212dd1ac22256336faad0eb002"
TARGET_COMMIT = "925f7a2949c6ff50b76e55ccec80abdfff59178b"
INFRA_API_VERSION = "infrastructure.wget-cloud/v1alpha1"
WORKER_HOSTNAME = "worker-192.168.0.16"


class PolicyError(RuntimeError):
    """A deliberately non-specific fail-closed policy rejection."""


def _reject() -> None:
    raise PolicyError("Timeweb router recovery policy rejected")


def _dict(value: Any, keys: Sequence[str]) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != set(keys):
        _reject()
    return value


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _reject()
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _reject()
    if parsed.tzinfo is None:
        _reject()
    return parsed.astimezone(timezone.utc)


def _artifact(value: Any, mode: str, *, credential: bool = False, sha: bool = True) -> None:
    keys = ["owner", "group", "mode", "acl", "linkCount"]
    if sha:
        keys.append("sha256")
    item = _dict(value, keys)
    if item["owner"] != "root" or item["group"] != "wheel" or item["mode"] != mode or item["linkCount"] != 1:
        _reject()
    if item["acl"] != (SAFE_ACL if credential else []):
        _reject()
    if sha and (not isinstance(item["sha256"], str) or HASH_RE.fullmatch(item["sha256"]) is None):
        _reject()


def _validate_desired_rule(value: Any, expected: Mapping[str, Any]) -> None:
    rule = _dict(value, ("protocol", "local", "public"))
    local = _dict(rule["local"], ("ip", "port"))
    public = _dict(rule["public"], ("ip", "port"))
    if dict(rule) != dict(expected) or local["ip"] != LOCAL_IP or public["ip"] != PUBLIC_IP:
        _reject()
    if rule["protocol"] != "tcp":
        _reject()


def _validate_common(policy: Any, final_key: str) -> Mapping[str, Any]:
    root = _dict(policy, ("schemaVersion", "installedPaths", "artifacts", "api", "router", "desiredRules", final_key))
    if root["schemaVersion"] != 1 or isinstance(root["schemaVersion"], bool):
        _reject()
    if dict(_dict(root["installedPaths"], tuple(INSTALLED_PATHS))) != INSTALLED_PATHS:
        _reject()
    artifacts = _dict(root["artifacts"], tuple(INSTALLED_PATHS))
    _artifact(artifacts["runner"], "0555")
    _artifact(artifacts["manifest"], "0444", sha=False)
    _artifact(artifacts["credential"], "0600", credential=True, sha=False)
    api = _dict(root["api"], ("baseUrl", "routersPath", "dnatPath"))
    if dict(api) != {"baseUrl": API_BASE, "routersPath": ROUTERS_PATH, "dnatPath": DNAT_PATH}:
        _reject()
    router = _dict(root["router"], ("publicIp", "localIp"))
    if dict(router) != {"publicIp": PUBLIC_IP, "localIp": LOCAL_IP}:
        _reject()
    rules = root["desiredRules"]
    if not isinstance(rules, list) or len(rules) != 2:
        _reject()
    for value, expected in zip(rules, DESIRED_RULES):
        _validate_desired_rule(value, expected)
    return root


def validate_manifest_template(policy: Any) -> None:
    root = _validate_common(policy, "approvalTemplate")
    template = _dict(root["approvalTemplate"], ("id", "maxAgeSeconds", "requiredRouterSnapshot"))
    if dict(template) != {"id": APPROVAL_ID, "maxAgeSeconds": 300, "requiredRouterSnapshot": True}:
        _reject()


def validate_manifest(policy: Any, *, now: Optional[datetime] = None) -> None:
    root = _validate_common(policy, "approval")
    approval = _dict(root["approval"], ("id", "observedAt", "expiresAt", "routerId", "preStateSha256"))
    if approval["id"] != APPROVAL_ID or not isinstance(approval["preStateSha256"], str) or HASH_RE.fullmatch(approval["preStateSha256"]) is None:
        _reject()
    if not isinstance(approval["routerId"], str) or ROUTER_ID_RE.fullmatch(approval["routerId"]) is None:
        _reject()
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        _reject()
    observed, expires = _parse_time(approval["observedAt"]), _parse_time(approval["expiresAt"])
    current = current.astimezone(timezone.utc)
    if observed > current or current >= expires or not (0 < (expires - observed).total_seconds() <= 300):
        _reject()


def _identity_ok(item: Mapping[str, Any]) -> bool:
    identities = (item.get("pathIdentity"), item.get("descriptorIdentity"), item.get("postDescriptorIdentity"))
    return all(isinstance(value, dict) and set(value) == {"device", "inode"} for value in identities) and identities[0] == identities[1] == identities[2]


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
        principal = match.group(1)
        entries.append({
            "inherited": "inherited" in permissions,
            "principal": f"user:{DARWIN_USER_UUID}" if principal in {DARWIN_USER_UUID, "estev"} else f"untrusted:{principal}",
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
        digest = hashlib.sha256()
        if stat.S_ISREG(opened.st_mode):
            for chunk in iter(lambda: os.read(descriptor, 1024 * 1024), b""):
                digest.update(chunk)
        first_hash = digest.hexdigest()
        acl = _acl(path)
        os.lseek(descriptor, 0, os.SEEK_SET)
        post_digest = hashlib.sha256()
        if stat.S_ISREG(opened.st_mode):
            for chunk in iter(lambda: os.read(descriptor, 1024 * 1024), b""):
                post_digest.update(chunk)
        after = os.fstat(descriptor)
        post_path = path.lstat()
        identity = lambda value: {"device": value.st_dev, "inode": value.st_ino}
        stable = all(
            getattr(before, field) == getattr(opened, field) == getattr(after, field) == getattr(post_path, field)
            for field in ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode", "st_nlink")
        ) and first_hash == post_digest.hexdigest()
        result = {
            "path": path_value, "canonicalPath": str(canonical),
            "kind": "file" if stat.S_ISREG(opened.st_mode) else "directory" if stat.S_ISDIR(opened.st_mode) else "other", "symlink": stat.S_ISLNK(before.st_mode),
            "owner": pwd.getpwuid(opened.st_uid).pw_name, "group": grp.getgrgid(opened.st_gid).gr_name,
            "mode": format(stat.S_IMODE(opened.st_mode), "04o"), "acl": acl, "linkCount": opened.st_nlink,
            "pathIdentity": identity(before), "descriptorIdentity": identity(opened), "postDescriptorIdentity": identity(after),
            "descriptorVerified": stable, "effectiveWritable": os.access(path, os.W_OK, effective_ids=True),
            "sha256": first_hash, "descriptorSha256": first_hash, "postDescriptorSha256": post_digest.hexdigest(),
        }
        return result
    except (KeyError, OSError, RuntimeError, TypeError, ValueError):
        _reject()
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _checked_evidence(policy: Mapping[str, Any], inspect_path: Callable[[str], Mapping[str, Any]], name: str) -> Mapping[str, Any]:
    path = policy["installedPaths"][name]
    try:
        item = inspect_path(path)
    except (KeyError, OSError, RuntimeError, TypeError, ValueError):
        _reject()
    contract = policy["artifacts"][name]
    if not isinstance(item, Mapping) or item.get("path") != path or item.get("canonicalPath") != path:
        _reject()
    if item.get("kind") != "file" or item.get("symlink") is not False:
        _reject()
    if item.get("owner") != "root" or item.get("group") != "wheel" or item.get("mode") != contract["mode"]:
        _reject()
    if item.get("acl") != contract["acl"] or item.get("linkCount") != 1:
        _reject()
    if item.get("descriptorVerified") is not True or item.get("effectiveWritable") is not False or not _identity_ok(item):
        _reject()
    if "sha256" in contract:
        digest = contract["sha256"]
        if (item.get("sha256"), item.get("descriptorSha256"), item.get("postDescriptorSha256")) != (digest, digest, digest):
            _reject()
    return item


def _checked_directory(inspect_path: Callable[[str], Mapping[str, Any]], path: str) -> None:
    try:
        item = inspect_path(path)
    except (KeyError, OSError, RuntimeError, TypeError, ValueError):
        _reject()
    if not isinstance(item, Mapping) or item.get("path") != path or item.get("canonicalPath") != path:
        _reject()
    if item.get("kind") != "directory" or item.get("symlink") is not False:
        _reject()
    if item.get("owner") != "root" or item.get("group") != "wheel" or item.get("mode") != "0755":
        _reject()
    if item.get("acl") != [] or item.get("descriptorVerified") is not True or item.get("effectiveWritable") is not False:
        _reject()
    if not _identity_ok(item):
        _reject()


def read_credential_fd(
    policy: Mapping[str, Any], *,
    inspect_path: Callable[[str], Mapping[str, Any]],
    open_fd: Callable[[str, int], int] = os.open,
    read_fd: Callable[[int, int], bytes] = os.read,
    fstat_fd: Callable[[int], Any] = os.fstat,
    close_fd: Callable[[int], None] = os.close,
) -> str:
    root = _validate_common(policy, "approval")
    approval = _dict(root["approval"], ("id", "observedAt", "expiresAt", "routerId", "preStateSha256"))
    if approval["id"] != APPROVAL_ID or not isinstance(approval["routerId"], str) or ROUTER_ID_RE.fullmatch(approval["routerId"]) is None:
        _reject()
    if not isinstance(approval["preStateSha256"], str) or HASH_RE.fullmatch(approval["preStateSha256"]) is None:
        _reject()
    item = _checked_evidence(policy, inspect_path, "credential")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = open_fd(CREDENTIAL, flags)
        opened = fstat_fd(descriptor)
        identity = item["descriptorIdentity"]
        if getattr(opened, "st_dev", None) != identity["device"] or getattr(opened, "st_ino", None) != identity["inode"]:
            _reject()
        chunks = []
        total = 0
        while True:
            chunk = read_fd(descriptor, 4096)
            if not chunk:
                break
            if not isinstance(chunk, bytes):
                _reject()
            total += len(chunk)
            if total > 16384:
                _reject()
            chunks.append(chunk)
        reopened = fstat_fd(descriptor)
        if getattr(reopened, "st_dev", None) != identity["device"] or getattr(reopened, "st_ino", None) != identity["inode"]:
            _reject()
        try:
            token = b"".join(chunks).decode("utf-8").strip()
        except UnicodeDecodeError:
            _reject()
        if not token or any(character.isspace() for character in token):
            _reject()
        return token
    except (OSError, RuntimeError, TypeError, ValueError):
        _reject()
    finally:
        if descriptor >= 0:
            try:
                close_fd(descriptor)
            except OSError:
                pass


def read_materialized_manifest_fd(
    *, now: datetime,
    inspect_path: Callable[[str], Mapping[str, Any]],
    open_fd: Callable[[str, int], int] = os.open,
    read_fd: Callable[[int, int], bytes] = os.read,
    fstat_fd: Callable[[int], Any] = os.fstat,
    close_fd: Callable[[int], None] = os.close,
) -> Mapping[str, Any]:
    for directory in SYSTEM_DIRECTORIES:
        _checked_directory(inspect_path, directory)
    try:
        item = inspect_path(MANIFEST)
    except (KeyError, OSError, RuntimeError, TypeError, ValueError):
        _reject()
    if not isinstance(item, Mapping) or item.get("path") != MANIFEST or item.get("canonicalPath") != MANIFEST:
        _reject()
    if item.get("kind") != "file" or item.get("symlink") is not False or item.get("owner") != "root" or item.get("group") != "wheel":
        _reject()
    if item.get("mode") != "0444" or item.get("acl") != [] or item.get("linkCount") != 1:
        _reject()
    if item.get("descriptorVerified") is not True or item.get("effectiveWritable") is not False or not _identity_ok(item):
        _reject()
    identity = item["descriptorIdentity"]
    descriptor = -1
    try:
        descriptor = open_fd(MANIFEST, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0))
        before = fstat_fd(descriptor)
        if (getattr(before, "st_dev", None), getattr(before, "st_ino", None)) != (identity["device"], identity["inode"]):
            _reject()
        chunks, total = [], 0
        while True:
            chunk = read_fd(descriptor, 65536)
            if not chunk:
                break
            if not isinstance(chunk, bytes):
                _reject()
            total += len(chunk)
            if total > 1024 * 1024:
                _reject()
            chunks.append(chunk)
        after = fstat_fd(descriptor)
        if (getattr(after, "st_dev", None), getattr(after, "st_ino", None)) != (identity["device"], identity["inode"]):
            _reject()
        value = json.loads(b"".join(chunks).decode("utf-8"))
        validate_materialized_manifest(value, now=now)
        return value
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RuntimeError, TypeError, ValueError):
        _reject()
    finally:
        if descriptor >= 0:
            try:
                close_fd(descriptor)
            except OSError:
                pass


def _canonical_rule(rule: Mapping[str, Any]) -> Mapping[str, Any]:
    if "local" in rule:
        local = rule.get("local")
        public = rule.get("public")
        if not isinstance(local, Mapping) or not isinstance(public, Mapping):
            _reject()
        return {
            "id": rule.get("id"), "localIp": local.get("ip"), "localPort": local.get("port", "1-65535"),
            "protocol": rule.get("protocol", "tcp_udp"), "publicIp": public.get("ip"), "publicPort": public.get("port", "1-65535"),
        }
    return {key: rule.get(key) for key in ("id", "localIp", "localPort", "protocol", "publicIp", "publicPort")}


def canonical_digest(rules: Sequence[Mapping[str, Any]]) -> str:
    normalized = sorted(
        (_canonical_rule(rule) for rule in rules),
        key=lambda item: (str(item["publicIp"]), str(item["publicPort"]), str(item["protocol"]), str(item["localIp"]), str(item["localPort"]), str(item.get("id") or "")),
    )
    return hashlib.sha256(json.dumps(normalized, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def plan_digest(rules: Sequence[Mapping[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(list(rules), separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def object_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def published_digest(value: Any) -> str:
    return "sha256:" + object_digest(value)


def validate_foundation_evidence(value: Any, *, now: datetime) -> str:
    root = _dict(value, (
        "observedAt", "expiresAt", "stage5", "service", "endpointSlice",
        "nodePortProbes", "dns", "offlinePlans",
    ))
    current = now.astimezone(timezone.utc) if isinstance(now, datetime) and now.tzinfo is not None else None
    if current is None:
        _reject()
    observed, expires = _parse_time(root["observedAt"]), _parse_time(root["expiresAt"])
    if observed > current or current >= expires or not (0 < (expires - observed).total_seconds() <= 300):
        _reject()
    stage5 = _dict(root["stage5"], ("application", "reportedRevision", "commitSha", "sync", "health", "operation"))
    if dict(stage5) != {
        "application": "ingress-canary", "reportedRevision": TARGET_TAG_OBJECT,
        "commitSha": TARGET_COMMIT, "sync": "Synced", "health": "Healthy",
        "operation": "Succeeded",
    }:
        _reject()
    service = _dict(root["service"], ("apiVersion", "kind", "namespace", "name", "type", "ports"))
    if {key: service[key] for key in ("apiVersion", "kind", "namespace", "name", "type")} != {
        "apiVersion": "v1", "kind": "Service", "namespace": "traefik", "name": "traefik", "type": "NodePort",
    }:
        _reject()
    expected_ports = [
        {"name": "web", "protocol": "TCP", "port": 80, "nodePort": 30080},
        {"name": "websecure", "protocol": "TCP", "port": 443, "nodePort": 30443},
    ]
    if service["ports"] != expected_ports:
        _reject()
    endpoint = _dict(root["endpointSlice"], ("apiVersion", "kind", "namespace", "serviceName", "addresses", "ready"))
    if dict(endpoint) != {
        "apiVersion": "discovery.k8s.io/v1", "kind": "EndpointSlice", "namespace": "traefik",
        "serviceName": "traefik", "addresses": [LOCAL_IP], "ready": True,
    }:
        _reject()
    if root["nodePortProbes"] != [
        {"address": f"{LOCAL_IP}:30080", "protocol": "tcp", "reachable": True},
        {"address": f"{LOCAL_IP}:30443", "protocol": "tcp", "reachable": True},
    ]:
        _reject()
    dns = _dict(root["dns"], ("host", "type", "expected", "observed"))
    if dict(dns) != {"host": "argocd.wget-cloud.ru", "type": "A", "expected": PUBLIC_IP, "observed": PUBLIC_IP}:
        _reject()
    plans = _dict(root["offlinePlans"], ("k8sRouterPlanSha256", "dnsPlanSha256", "k8sRouterPlan", "dnsPlan"))
    k8s_plan = _dict(plans["k8sRouterPlan"], ("path", "tagObjectSha", "commitSha", "offlinePlanOnly"))
    dns_plan = _dict(plans["dnsPlan"], ("path", "host", "type", "value", "offlinePlanOnly"))
    if dict(k8s_plan) != {
        "path": "infrastructure/k8s/components/clusters/twc-wise-finch/dns/router-recovery.yaml",
        "tagObjectSha": TARGET_TAG_OBJECT, "commitSha": TARGET_COMMIT, "offlinePlanOnly": True,
    }:
        _reject()
    if dict(dns_plan) != {
        "path": "infrastructure/k8s/components/clusters/twc-wise-finch/dns/cutover.yaml",
        "host": "argocd.wget-cloud.ru", "type": "A", "value": PUBLIC_IP, "offlinePlanOnly": True,
    }:
        _reject()
    if plans["k8sRouterPlanSha256"] != object_digest(k8s_plan) or plans["dnsPlanSha256"] != object_digest(dns_plan):
        _reject()
    return object_digest(root)


def _json_response(response: Any, statuses: Sequence[int]) -> Mapping[str, Any]:
    if getattr(response, "status", None) not in statuses:
        _reject()
    try:
        value = json.loads(getattr(response, "body", b"").decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
        _reject()
    if not isinstance(value, dict):
        _reject()
    return value


def _call(http_request: Callable[..., Any], method: str, url: str, token: str, body: Optional[bytes] = None) -> Any:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    try:
        return http_request(method, url, headers, body, 15)
    except (OSError, RuntimeError, TypeError, ValueError):
        _reject()


def _extract_list(value: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    result = value.get(key)
    if not isinstance(result, list) or not all(isinstance(item, Mapping) for item in result):
        _reject()
    return list(result)


def _exact(rule: Mapping[str, Any], desired: Mapping[str, Any]) -> bool:
    normalized = _canonical_rule(rule)
    expected = _canonical_rule(desired)
    return all(normalized[key] == expected[key] for key in ("localIp", "localPort", "protocol", "publicIp", "publicPort"))


def _port_interval(value: Any) -> tuple[int, int]:
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{1,5}(?:-[0-9]{1,5})?", value) is None:
        _reject()
    parts = [int(part) for part in value.split("-")]
    low, high = (parts[0], parts[-1])
    if low < 1 or high > 65535 or low > high:
        _reject()
    return low, high


def _conflicts(rule: Mapping[str, Any], desired: Mapping[str, Any]) -> bool:
    normalized = _canonical_rule(rule)
    expected = _canonical_rule(desired)
    if normalized["publicIp"] != expected["publicIp"]:
        return False
    if normalized["protocol"] not in {"tcp", "tcp_udp"} or expected["protocol"] not in {"tcp", "tcp_udp"}:
        return False
    left = _port_interval(normalized["publicPort"])
    right = _port_interval(expected["publicPort"])
    return max(left[0], right[0]) <= min(left[1], right[1])


def _published_router_contract() -> Mapping[str, Any]:
    return {
        "apiVersion": INFRA_API_VERSION,
        "kind": "TimewebRouterRecovery",
        "metadata": {"name": "twc-wise-finch"},
        "spec": {
            "api": {
                "baseUrl": API_BASE,
                "bearerTokenSource": "protectedRunnerFd",
                "dnatResponseFields": ["id", "localIp", "localPort", "publicIp", "publicPort", "protocol"],
                "endpoints": {
                    "listRouters": "/api/v1/routers",
                    "getRouter": "/api/v1/routers/{router_id}",
                    "listDnatRules": "/api/v1/routers/{router_id}/dnat-rules",
                    "getDnatRule": "/api/v1/routers/{router_id}/dnat-rules/{dnat_id}",
                    "createDnatRule": "/api/v1/routers/{router_id}/dnat-rules",
                    "deleteDnatRule": "/api/v1/routers/{router_id}/dnat-rules/{dnat_id}",
                },
            },
            "desiredRules": [dict(rule) for rule in DESIRED_RULES],
            "evidenceFreshness": {"maxAgeSeconds": 300, "maxFutureSkewSeconds": 30},
            "offlinePlanOnly": True,
            "requiredDns": {"host": "argocd.wget-cloud.ru", "provider": "timeweb", "type": "A", "value": PUBLIC_IP, "zone": "wget-cloud.ru"},
            "routerSelector": {"uniquePublicIPv4": PUBLIC_IP},
            "target": {"privateIPv4": LOCAL_IP, "workerHostname": WORKER_HOSTNAME},
        },
    }


def _published_foundation(
    router_id: str, rules: Sequence[Mapping[str, Any]], observed_at: str, *,
    resource_version: str = "184467", endpoint_slice_name: str = "traefik-7f84c",
    endpoint_address: str = "10.244.16.27", dns_record_id: str = "record-actual-517",
) -> Mapping[str, Any]:
    return {
        "gitOpsStage5": {
            "name": "ingress-canary", "targetRevision": APPROVAL_ID, "syncStatus": "Synced",
            "healthStatus": "Healthy", "resourceVersion": resource_version,
            "reportedRevision": TARGET_TAG_OBJECT, "commitSha": TARGET_COMMIT,
            "operationPhase": "Succeeded",
        },
        "routerSnapshot": {
            "apiVersion": INFRA_API_VERSION, "kind": "TimewebRouterSnapshot",
            "spec": {
                "observedAt": observed_at, "readOnly": True,
                "routers": [{"id": router_id, "name": "twc-wise-finch", "publicIps": [PUBLIC_IP]}],
                "selectedRouter": {"id": router_id, "publicIPv4": PUBLIC_IP, "dnatRules": [dict(rule) for rule in rules]},
            },
        },
        "ingressService": {
            "apiVersion": INFRA_API_VERSION, "kind": "TimewebIngressServiceEvidence",
            "spec": {
                "observedAt": observed_at, "readOnly": True,
                "service": {
                    "apiVersion": "v1", "kind": "Service", "metadata": {"name": "traefik", "namespace": "traefik"},
                    "spec": {"type": "NodePort", "externalTrafficPolicy": "Local", "ports": [
                        {"name": "http", "protocol": "TCP", "nodePort": 30080},
                        {"name": "https", "protocol": "TCP", "nodePort": 30443},
                    ]},
                },
                "endpointSlice": {
                    "apiVersion": "discovery.k8s.io/v1", "kind": "EndpointSlice",
                    "metadata": {"name": endpoint_slice_name, "namespace": "traefik", "labels": {"kubernetes.io/service-name": "traefik"}},
                    "readyEndpoints": [{"workerHostname": WORKER_HOSTNAME, "addresses": [endpoint_address], "ready": True}],
                },
            },
        },
        "dnsSnapshot": {
            "apiVersion": INFRA_API_VERSION, "kind": "TimewebDnsSnapshot",
            "spec": {"observedAt": observed_at, "readOnly": True, "provider": "timeweb", "zone": "wget-cloud.ru", "records": [
                {"recordId": dns_record_id, "name": "argocd.wget-cloud.ru", "type": "A", "values": [PUBLIC_IP], "ttlSeconds": 300},
            ]},
        },
        "readinessEvidence": {
            "apiVersion": INFRA_API_VERSION, "kind": "TimewebRouterRecoveryReadiness",
            "spec": {"observedAt": observed_at, "readOnly": True, "ingressIPv4": PUBLIC_IP, "directNodePortProbes": [
                {"protocol": "HTTP", "targetIPv4": LOCAL_IP, "targetPort": 30080, "ready": True},
                {"protocol": "HTTPS", "targetIPv4": LOCAL_IP, "targetPort": 30443, "ready": True},
            ]},
        },
    }


def _published_plan(router_id: str, rules: Sequence[Mapping[str, Any]], foundation: Mapping[str, Any]) -> Mapping[str, Any]:
    actions = []
    for desired in DESIRED_RULES:
        exact = [rule for rule in rules if _exact(rule, desired)]
        if len(exact) > 1:
            _reject()
        if exact:
            rule_id = exact[0].get("id")
            if not isinstance(rule_id, str) or ID_RE.fullmatch(rule_id) is None:
                _reject()
            actions.append({"disposition": "adopt", "existingRuleId": rule_id, "desiredRule": dict(desired), "rollback": {"action": "preserve", "delete": False}})
        else:
            actions.append({
                "disposition": "create",
                "request": {"method": "POST", "path": f"/api/v1/routers/{router_id}/dnat-rules", "body": dict(desired)},
                "response": {"ruleIdSemantics": "captureCreatedRuleId"},
                "rollback": {"method": "DELETE", "path": f"/api/v1/routers/{router_id}/dnat-rules/{{created_dnat_id}}", "createdByThisRunOnly": True},
            })
    lineage = {
        "contractDigest": published_digest(_published_router_contract()),
        "routerSnapshotDigest": published_digest(foundation["routerSnapshot"]),
        "ingressServiceDigest": published_digest(foundation["ingressService"]),
        "dnsSnapshotDigest": published_digest(foundation["dnsSnapshot"]),
        "readinessEvidenceDigest": published_digest(foundation["readinessEvidence"]),
        "actionDigest": published_digest(actions),
    }
    return {
        "apiVersion": INFRA_API_VERSION, "kind": "TimewebRouterRecoveryPlan", "metadata": {"name": "twc-wise-finch"},
        "spec": {"dryRun": True, "approvedForApply": False, "routerId": router_id, "actions": actions, **lineage, "finalDigest": published_digest(lineage)},
    }


def _base_policy(policy: Mapping[str, Any]) -> Mapping[str, Any]:
    keys = ("schemaVersion", "installedPaths", "artifacts", "api", "router", "desiredRules", "approval")
    try:
        return {key: policy[key] for key in keys}
    except KeyError:
        _reject()


def validate_materialized_manifest(policy: Any, *, now: datetime) -> None:
    expected_keys = {"schemaVersion", "installedPaths", "artifacts", "api", "router", "desiredRules", "approval", "foundationEvidence", "foundationEvidenceSha256", "routerPlan", "routerPlanSha256"}
    if not isinstance(policy, Mapping) or set(policy) != expected_keys:
        _reject()
    base = _base_policy(policy)
    validate_manifest(base, now=now)
    router_id = base["approval"]["routerId"]
    foundation = policy["foundationEvidence"]
    if not isinstance(foundation, Mapping):
        _reject()
    try:
        rules = foundation["routerSnapshot"]["spec"]["selectedRouter"]["dnatRules"]
    except (KeyError, TypeError):
        _reject()
    if not isinstance(rules, list) or not all(isinstance(rule, Mapping) for rule in rules):
        _reject()
    try:
        resource_version = foundation["gitOpsStage5"]["resourceVersion"]
        endpoint_slice = foundation["ingressService"]["spec"]["endpointSlice"]
        endpoint_slice_name = endpoint_slice["metadata"]["name"]
        endpoint_address = endpoint_slice["readyEndpoints"][0]["addresses"][0]
        dns_record_id = foundation["dnsSnapshot"]["spec"]["records"][0]["recordId"]
    except (KeyError, IndexError, TypeError):
        _reject()
    if not isinstance(resource_version, str) or re.fullmatch(r"[1-9][0-9]*", resource_version) is None:
        _reject()
    if not isinstance(endpoint_slice_name, str) or re.fullmatch(r"traefik-[a-z0-9]+", endpoint_slice_name) is None:
        _reject()
    if not isinstance(endpoint_address, str) or re.fullmatch(r"10\.244\.[0-9]{1,3}\.[0-9]{1,3}", endpoint_address) is None:
        _reject()
    if not isinstance(dns_record_id, str) or ID_RE.fullmatch(dns_record_id) is None:
        _reject()
    expected_foundation = _published_foundation(
        router_id, rules, base["approval"]["observedAt"], resource_version=resource_version,
        endpoint_slice_name=endpoint_slice_name, endpoint_address=endpoint_address,
        dns_record_id=dns_record_id,
    )
    if foundation != expected_foundation or policy["foundationEvidenceSha256"] != published_digest(foundation):
        _reject()
    if canonical_digest(rules) != base["approval"]["preStateSha256"]:
        _reject()
    for rule in rules:
        if not any(_exact(rule, desired) for desired in DESIRED_RULES) and any(_conflicts(rule, desired) for desired in DESIRED_RULES):
            _reject()
    expected_plan = _published_plan(router_id, rules, foundation)
    if policy["routerPlan"] != expected_plan or policy["routerPlanSha256"] != published_digest(expected_plan):
        _reject()


def execute_recovery(
    policy: Mapping[str, Any], *,
    foundation_evidence: Mapping[str, Any],
    router_plan: Optional[Mapping[str, Any]] = None,
    inspect_path: Callable[[str], Mapping[str, Any]],
    read_token: Callable[[], str],
    http_request: Callable[..., Any],
    now: datetime,
    environ: Optional[Mapping[str, str]] = None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    emit_result: bool = True,
) -> Mapping[str, Any]:
    del environ, stderr
    if router_plan is None:
        runtime_policy = policy
        validate_manifest(runtime_policy, now=now)
        foundation_sha = validate_foundation_evidence(foundation_evidence, now=now)
        if (foundation_evidence.get("observedAt"), foundation_evidence.get("expiresAt")) != (
            runtime_policy["approval"]["observedAt"], runtime_policy["approval"]["expiresAt"],
        ):
            _reject()
        plan_actions = None
    else:
        validate_materialized_manifest(policy, now=now)
        runtime_policy = _base_policy(policy)
        if foundation_evidence != policy["foundationEvidence"] or router_plan != policy["routerPlan"]:
            _reject()
        foundation_sha = object_digest(foundation_evidence)
        plan_actions = router_plan["spec"]["actions"]
    for directory in SYSTEM_DIRECTORIES:
        _checked_directory(inspect_path, directory)
    _checked_evidence(runtime_policy, inspect_path, "runner")
    _checked_evidence(runtime_policy, inspect_path, "manifest")
    _checked_evidence(runtime_policy, inspect_path, "credential")
    try:
        token = read_token()
    except (OSError, RuntimeError, TypeError, ValueError):
        _reject()
    if not isinstance(token, str) or not token or any(character.isspace() for character in token):
        _reject()
    base = runtime_policy["api"]["baseUrl"]
    routers_value = _json_response(_call(http_request, "GET", base + ROUTERS_PATH, token), (200,))
    matches = []
    for router in _extract_list(routers_value, "routers"):
        ips = router.get("ips")
        if isinstance(ips, list) and any(isinstance(ip, Mapping) and ip.get("ip") == PUBLIC_IP for ip in ips):
            matches.append(router)
    if len(matches) != 1 or not isinstance(matches[0].get("id"), str) or ID_RE.fullmatch(matches[0]["id"]) is None:
        _reject()
    router_id = matches[0]["id"]
    if router_id != runtime_policy["approval"]["routerId"]:
        _reject()
    router_url = base + ROUTERS_PATH + "/" + router_id
    detail = _json_response(_call(http_request, "GET", router_url, token), (200,)).get("router")
    if not isinstance(detail, Mapping) or detail.get("id") != router_id or detail.get("status") != "on":
        _reject()
    if not any(isinstance(ip, Mapping) and ip.get("ip") == PUBLIC_IP for ip in detail.get("ips", [])):
        _reject()
    dnat_url = base + DNAT_PATH.format(router_id=router_id)
    rules = _extract_list(_json_response(_call(http_request, "GET", dnat_url, token), (200,)), "dnatRules")
    if canonical_digest(rules) != runtime_policy["approval"]["preStateSha256"]:
        _reject()
    for rule in rules:
        if not any(_exact(rule, desired) for desired in runtime_policy["desiredRules"]):
            if any(_conflicts(rule, desired) for desired in runtime_policy["desiredRules"]):
                _reject()
    adopted: list[str] = []
    created: list[str] = []
    created_rules: dict[str, Mapping[str, Any]] = {}
    try:
        for index, desired in enumerate(runtime_policy["desiredRules"]):
            exact = [rule for rule in rules if _exact(rule, desired)]
            if len(exact) > 1:
                _reject()
            if exact:
                rule_id = exact[0].get("id")
                if not isinstance(rule_id, str) or ID_RE.fullmatch(rule_id) is None:
                    _reject()
                if plan_actions is not None and plan_actions[index] != {"disposition": "adopt", "existingRuleId": rule_id, "desiredRule": desired, "rollback": {"action": "preserve", "delete": False}}:
                    _reject()
                adopted.append(rule_id)
                continue
            if plan_actions is not None:
                expected_action = {
                    "disposition": "create",
                    "request": {"method": "POST", "path": DNAT_PATH.format(router_id=router_id), "body": desired},
                    "response": {"ruleIdSemantics": "captureCreatedRuleId"},
                    "rollback": {"method": "DELETE", "path": DNAT_PATH.format(router_id=router_id) + "/{created_dnat_id}", "createdByThisRunOnly": True},
                }
                if plan_actions[index] != expected_action:
                    _reject()
            body = json.dumps(desired, separators=(",", ":"), sort_keys=True).encode()
            created_value = _json_response(_call(http_request, "POST", dnat_url, token, body), (200, 201)).get("dnatRule")
            if not isinstance(created_value, Mapping) or not _exact(created_value, desired):
                _reject()
            rule_id = created_value.get("id")
            if not isinstance(rule_id, str) or ID_RE.fullmatch(rule_id) is None:
                _reject()
            verify_url = dnat_url + "/" + rule_id
            verified = _json_response(_call(http_request, "GET", verify_url, token), (200,)).get("dnatRule")
            if not isinstance(verified, Mapping) or dict(verified) != dict(created_value):
                _reject()
            created.append(rule_id)
            created_rules[rule_id] = dict(created_value)
            rules.append(dict(created_value))
        final_rules_raw = _extract_list(_json_response(_call(http_request, "GET", dnat_url, token), (200,)), "dnatRules")
        if len(final_rules_raw) != len(runtime_policy["desiredRules"]):
            _reject()
        final_ids: list[str] = []
        for rule in final_rules_raw:
            rule_id = rule.get("id")
            if not isinstance(rule_id, str) or ID_RE.fullmatch(rule_id) is None or rule_id in final_ids:
                _reject()
            final_ids.append(rule_id)
        if set(final_ids) != set(adopted + created) or len(final_ids) != len(adopted) + len(created):
            _reject()
        for desired in runtime_policy["desiredRules"]:
            if len([rule for rule in final_rules_raw if _exact(rule, desired)]) != 1:
                _reject()
        for rule in final_rules_raw:
            if not any(_exact(rule, desired) for desired in runtime_policy["desiredRules"]):
                _reject()
    except PolicyError:
        for rule_id in reversed(created):
            verify_url = dnat_url + "/" + rule_id
            try:
                verified = _json_response(_call(http_request, "GET", verify_url, token), (200,)).get("dnatRule")
                if isinstance(verified, Mapping) and dict(verified) == dict(created_rules[rule_id]):
                    response = _call(http_request, "DELETE", verify_url, token)
                    if getattr(response, "status", None) not in (200, 204):
                        _reject()
            except PolicyError:
                pass
        raise
    final_rules = sorted((_canonical_rule(rule) for rule in final_rules_raw), key=lambda rule: str(rule["id"]))
    post_state_sha = canonical_digest(final_rules)
    action = {
        "approvalId": runtime_policy["approval"]["id"],
        "routerId": router_id,
        "preStateSha256": runtime_policy["approval"]["preStateSha256"],
        "planSha256": plan_digest(runtime_policy["desiredRules"]),
        "foundationSha256": foundation_sha,
        "adoptedIds": adopted,
        "createdIds": created,
    }
    action_sha = object_digest(action)
    final_plan = {"actionDigest": action_sha, "postStateSha256": post_state_sha, "rules": final_rules}
    result = {
        **action,
        "observedAt": runtime_policy["approval"]["observedAt"],
        "expiresAt": runtime_policy["approval"]["expiresAt"],
        "foundationEvidence": dict(foundation_evidence),
        "postStateSha256": post_state_sha,
        "rules": final_rules,
        "actionDigest": action_sha,
        "planFinalDigest": object_digest(final_plan),
    }
    if emit_result:
        stdout.write(json.dumps(result, separators=(",", ":"), sort_keys=True) + "\n")
    return result


def urllib_request(method: str, url: str, headers: Mapping[str, str], body: Optional[bytes], timeout: int) -> Any:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
    try:
        response = opener.open(request, timeout=timeout)
        return type("Response", (), {"status": response.status, "headers": dict(response.headers), "body": response.read(65537)})()
    except urllib.error.HTTPError as error:
        return type("Response", (), {"status": error.code, "headers": {}, "body": error.read(65537)})()


def _format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main(
    argv: Optional[Sequence[str]] = None, *,
    inspect_path: Callable[[str], Mapping[str, Any]] = inspect_path,
    http_request: Callable[..., Any] = urllib_request,
    now: Optional[datetime] = None,
    poststate_now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args(argv)
    if os.environ.get("WGC_TIMEWEB_ROUTER_RECOVERY_APPROVED") != "1":
        _reject()
    current = now or datetime.now(timezone.utc)
    policy = read_materialized_manifest_fd(now=current, inspect_path=inspect_path)
    result = execute_recovery(
        policy,
        foundation_evidence=policy["foundationEvidence"],
        router_plan=policy["routerPlan"],
        inspect_path=inspect_path,
        read_token=lambda: read_credential_fd(_base_policy(policy), inspect_path=inspect_path),
        http_request=http_request,
        now=current,
        environ={},
        stdout=stdout,
        stderr=stderr,
        emit_result=False,
    )
    ordered_rules = []
    for desired in DESIRED_RULES:
        exact = [rule for rule in result["rules"] if _exact(rule, desired)]
        if len(exact) != 1:
            _reject()
        ordered_rules.append(exact[0])
    observed_poststate = poststate_now()
    if not isinstance(observed_poststate, datetime) or observed_poststate.tzinfo is None:
        _reject()
    poststate = {
        "apiVersion": INFRA_API_VERSION,
        "kind": "TimewebRouterRecoveryPoststate",
        "spec": {
            "observedAt": _format_time(observed_poststate),
            "readOnly": True,
            "routerId": policy["routerPlan"]["spec"]["routerId"],
            "actionDigest": policy["routerPlan"]["spec"]["actionDigest"],
            "planFinalDigest": policy["routerPlan"]["spec"]["finalDigest"],
            "rules": ordered_rules,
        },
    }
    stdout.write(json.dumps(poststate, separators=(",", ":"), sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PolicyError:
        sys.stderr.write("Timeweb router recovery policy rejected\n")
        raise SystemExit(1)
