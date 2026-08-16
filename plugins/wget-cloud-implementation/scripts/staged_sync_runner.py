#!/usr/bin/env python3
"""Fail-closed runner for the approved twc-wise-finch storage sync stages."""

from __future__ import annotations

import argparse
import base64
import binascii
import grp
import hashlib
import json
import os
import pwd
import re
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, TextIO, Tuple


RUNNER = "/usr/local/libexec/wget-cloud-staged-sync/runner.py"
CLI = "/usr/local/libexec/wget-cloud-staged-sync/argocd-v3.0.0-darwin-arm64"
MANIFEST = "/usr/local/libexec/wget-cloud-staged-sync/manifest.json"
KUBECONFIG = "/usr/local/etc/wget-cloud-staged-sync/twc-wise-finch.kubeconfig"
CONTEXT = "twc-wise-finch"
SERVER = "https://200.165.236.215:6443"
REVISION = "6c2c3e9dadde2eec3d13fde830bc6db0392b13b8"
REPO_URL = "ssh://git@github.com/wget-cloud/k8s"
TAG = "twc-wise-finch-ingress-2026-08-15.1"
DESTINATION_SERVER = "https://kubernetes.default.svc"
ESTEV_DARWIN_UUID = "FFFFEEEE-DDDD-CCCC-BBBB-AAAA000001F5"
LS_SHA256 = "0056d8fd617b4af3e6f8ec08a08530747962b7392ccd767b275677e8387dac51"
APPLICATIONS: Tuple[Tuple[int, str, str], ...] = (
    (1, "twc-wise-finch-cluster", "Healthy"),
    (2, "twc-wise-finch-core", "Healthy"),
    (3, "twc-wise-finch-local-path-storage", "Missing"),
    (4, "twc-wise-finch-local-path-smoke", "Healthy"),
    (5, "local-path-storage-smoke", "Missing"),
)
INSTALLED_PATHS = {
    "runner": RUNNER,
    "cli": CLI,
    "manifest": MANIFEST,
    "kubeconfig": KUBECONFIG,
}
MANAGED_DIRECTORIES = {
    "/usr/local/libexec/wget-cloud-staged-sync",
    "/usr/local/etc/wget-cloud-staged-sync",
}
SYSTEM_BINARIES = {"/usr/bin/env", "/usr/bin/python3", "/bin/ls"}
CHILD_ENV = {
    "HOME": "/var/empty",
    "PATH": "/usr/bin:/bin",
    "LANG": "C",
    "LC_ALL": "C",
    "KUBECONFIG": KUBECONFIG,
}
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
SAFE_ACL_PERMISSIONS = ["read", "readattr", "readextattr", "readsecurity"]

APPLICATION_CONTRACTS: Dict[str, Dict[str, Any]] = {
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


class PolicyError(RuntimeError):
    """Raised when any immutable runner policy check fails."""


def _reject() -> None:
    raise PolicyError("staged sync policy rejected")


def _dict(value: Any, keys: Sequence[str]) -> Dict[str, Any]:
    if not isinstance(value, dict) or set(value) != set(keys):
        _reject()
    return value


def _string(value: Any) -> str:
    if not isinstance(value, str) or not value:
        _reject()
    return value


def _mode(value: Any) -> str:
    if not isinstance(value, str) or re.fullmatch(r"0[0-7]{3}", value) is None:
        _reject()
    return value


def _hash(value: Any) -> str:
    if not isinstance(value, str) or HASH_RE.fullmatch(value) is None:
        _reject()
    return value


def _link_count(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        _reject()
    return value


def _validate_acl(value: Any, *, kubeconfig: bool = False) -> None:
    if not isinstance(value, list):
        _reject()
    if not kubeconfig:
        if value:
            _reject()
        return
    if len(value) != 1:
        _reject()
    entry = _dict(
        value[0],
        ("inherited", "principal", "type", "permissions"),
    )
    if entry["inherited"] is not False:
        _reject()
    if entry["principal"] != "user:estev" or entry["type"] != "allow":
        _reject()
    if entry["permissions"] != SAFE_ACL_PERMISSIONS:
        _reject()


def _validate_file_contract(
    value: Any,
    *,
    mode: str,
    acl_kubeconfig: bool = False,
    sha_required: bool = True,
) -> None:
    keys = ["owner", "group", "mode", "acl", "linkCount"]
    if sha_required:
        keys.append("sha256")
    contract = _dict(value, keys)
    if contract["owner"] != "root" or contract["group"] != "wheel":
        _reject()
    if _mode(contract["mode"]) != mode:
        _reject()
    _validate_acl(contract["acl"], kubeconfig=acl_kubeconfig)
    _link_count(contract["linkCount"])
    if sha_required:
        _hash(contract["sha256"])


def _validate_directory_contract(value: Any) -> None:
    contract = _dict(value, ("owner", "group", "mode", "acl"))
    if contract["owner"] != "root" or contract["group"] != "wheel":
        _reject()
    if _mode(contract["mode"]) != "0755":
        _reject()
    _validate_acl(contract["acl"])


def validate_manifest(policy: Any) -> None:
    root = _dict(
        policy,
        (
            "schemaVersion",
            "installedPaths",
            "artifacts",
            "managedDirectories",
            "systemBinaries",
            "cluster",
            "applications",
        ),
    )
    if root["schemaVersion"] != 1 or isinstance(root["schemaVersion"], bool):
        _reject()

    paths = _dict(root["installedPaths"], tuple(INSTALLED_PATHS))
    if paths != INSTALLED_PATHS:
        _reject()

    artifacts = _dict(root["artifacts"], tuple(INSTALLED_PATHS))
    _validate_file_contract(artifacts["runner"], mode="0555")
    _validate_file_contract(artifacts["cli"], mode="0555")
    _validate_file_contract(artifacts["manifest"], mode="0444", sha_required=False)
    _validate_file_contract(
        artifacts["kubeconfig"],
        mode="0400",
        acl_kubeconfig=True,
    )

    directories = _dict(root["managedDirectories"], tuple(MANAGED_DIRECTORIES))
    for path, contract in directories.items():
        if path not in MANAGED_DIRECTORIES:
            _reject()
        _validate_directory_contract(contract)

    binaries = _dict(root["systemBinaries"], tuple(SYSTEM_BINARIES))
    for path, contract in binaries.items():
        if path not in SYSTEM_BINARIES:
            _reject()
        _validate_file_contract(contract, mode="0755")

    cluster = _dict(root["cluster"], ("context", "server", "caSha256", "revision"))
    if cluster["context"] != CONTEXT or cluster["server"] != SERVER:
        _reject()
    if cluster["revision"] != REVISION:
        _reject()
    _hash(cluster["caSha256"])

    applications = root["applications"]
    if not isinstance(applications, list) or len(applications) != len(APPLICATIONS):
        _reject()
    observed: List[Tuple[int, str, str]] = []
    for item in applications:
        app = _dict(item, ("stage", "name", "preState"))
        if isinstance(app["stage"], bool) or not isinstance(app["stage"], int):
            _reject()
        pre_state = _dict(app["preState"], ("sync", "health"))
        if pre_state["sync"] != "OutOfSync":
            _reject()
        observed.append((app["stage"], _string(app["name"]), _string(pre_state["health"])))
    if tuple(observed) != APPLICATIONS:
        _reject()


def _identity(value: os.stat_result) -> Dict[str, int]:
    return {"device": value.st_dev, "inode": value.st_ino}


def _same_descriptor(left: os.stat_result, right: os.stat_result) -> bool:
    fields = ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode", "st_nlink")
    return all(getattr(left, field) == getattr(right, field) for field in fields)


def _fd_sha256(descriptor: int) -> str:
    digest = hashlib.sha256()
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    except OSError:
        _reject()
    return digest.hexdigest()


def _effectively_writable(path: Path) -> bool:
    try:
        return os.access(path, os.W_OK, effective_ids=True)
    except (NotImplementedError, TypeError):
        return os.access(path, os.W_OK)


def _pinned_ls_is_safe() -> bool:
    path = Path("/bin/ls")
    descriptor = -1
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode):
            return False
        if path.resolve(strict=True) != path:
            return False
        if before.st_uid != 0 or before.st_gid != 0:
            return False
        if stat.S_IMODE(before.st_mode) != 0o755 or before.st_nlink != 1:
            return False
        if _effectively_writable(path):
            return False
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(str(path), flags)
        opened = os.fstat(descriptor)
        digest = _fd_sha256(descriptor)
        after = os.fstat(descriptor)
        path_after = path.lstat()
        if not (_same_descriptor(before, opened) and _same_descriptor(opened, after)):
            return False
        if _identity(path_after) != _identity(after) or not _same_descriptor(after, path_after):
            return False
        if digest != LS_SHA256:
            return False
        for ancestor in path.parents:
            ancestor_stat = ancestor.lstat()
            if not stat.S_ISDIR(ancestor_stat.st_mode) or stat.S_ISLNK(ancestor_stat.st_mode):
                return False
            if ancestor.resolve(strict=True) != ancestor:
                return False
            if ancestor_stat.st_uid != 0 or ancestor_stat.st_gid != 0:
                return False
            if stat.S_IMODE(ancestor_stat.st_mode) & 0o022:
                return False
            if _effectively_writable(ancestor):
                return False
    except (OSError, RuntimeError, ValueError):
        return False
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
    return True


def _acl_for_path(path: Path) -> List[Dict[str, Any]]:
    if not _pinned_ls_is_safe():
        _reject()
    try:
        result = subprocess.run(
            ["/bin/ls", "-lde", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=5,
            env={"HOME": "/var/empty", "PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        _reject()
    if result.returncode != 0:
        _reject()
    acl: List[Dict[str, Any]] = []
    for line in result.stdout.splitlines()[1:]:
        match = re.fullmatch(r"\s*\d+:\s+(\S+)\s+(allow|deny)\s+(.+?)\s*", line)
        if match is None:
            _reject()
        permissions = [part.strip() for part in match.group(3).split(",") if part.strip()]
        inherited = "inherited" in permissions
        permissions = [part for part in permissions if part != "inherited"]
        principal = match.group(1)
        normalized_principal = (
            "user:estev" if principal == ESTEV_DARWIN_UUID else f"untrusted:{principal}"
        )
        acl.append(
            {
                "inherited": inherited,
                "principal": normalized_principal,
                "type": match.group(2),
                "permissions": permissions,
            }
        )
    return acl


def inspect_path(path_value: str) -> Dict[str, Any]:
    path = Path(path_value)
    descriptor = -1
    try:
        path_stat = path.lstat()
        canonical = path.resolve(strict=True)
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(str(path), flags)
        descriptor_stat = os.fstat(descriptor)
        if stat.S_ISREG(descriptor_stat.st_mode):
            kind = "file"
            descriptor_hash = _fd_sha256(descriptor)
        elif stat.S_ISDIR(descriptor_stat.st_mode):
            kind = "directory"
            descriptor_hash = None
        else:
            kind = "other"
            descriptor_hash = None
        acl = _acl_for_path(path)
        post_descriptor_stat = os.fstat(descriptor)
        post_descriptor_hash = _fd_sha256(descriptor) if kind == "file" else None
        post_path_stat = path.lstat()
        owner = pwd.getpwuid(descriptor_stat.st_uid).pw_name
        group = grp.getgrgid(descriptor_stat.st_gid).gr_name
    except (KeyError, OSError, RuntimeError):
        _reject()
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
    descriptor_verified = (
        _same_descriptor(path_stat, descriptor_stat)
        and _same_descriptor(descriptor_stat, post_descriptor_stat)
        and _same_descriptor(post_descriptor_stat, post_path_stat)
        and descriptor_hash == post_descriptor_hash
    )
    evidence: Dict[str, Any] = {
        "path": path_value,
        "canonicalPath": str(canonical),
        "kind": kind,
        "symlink": stat.S_ISLNK(path_stat.st_mode),
        "owner": owner,
        "group": group,
        "mode": format(stat.S_IMODE(descriptor_stat.st_mode), "04o"),
        "acl": acl,
        "linkCount": descriptor_stat.st_nlink,
        "pathIdentity": _identity(path_stat),
        "descriptorIdentity": _identity(descriptor_stat),
        "postDescriptorIdentity": _identity(post_descriptor_stat),
        "descriptorVerified": descriptor_verified,
        "effectiveWritable": _effectively_writable(path),
    }
    if kind == "file":
        evidence["sha256"] = descriptor_hash
        evidence["descriptorSha256"] = descriptor_hash
        evidence["postDescriptorSha256"] = post_descriptor_hash
    return evidence


def _path_parents(path_value: str) -> List[str]:
    current = PurePosixPath(path_value)
    parents = [str(parent) for parent in current.parents]
    parents.reverse()
    return parents


def _evidence(inspect: Callable[[str], Mapping[str, Any]], path: str) -> Mapping[str, Any]:
    try:
        value = inspect(path)
    except (KeyError, OSError, RuntimeError, TypeError, ValueError, PolicyError):
        _reject()
    if not isinstance(value, Mapping):
        _reject()
    return value


def _validate_identity(item: Mapping[str, Any], path: str, kind: str) -> None:
    if item.get("path") != path or item.get("canonicalPath") != path:
        _reject()
    if item.get("kind") != kind or item.get("symlink") is not False:
        _reject()
    if item.get("owner") != "root" or item.get("group") != "wheel":
        _reject()
    if item.get("descriptorVerified") is not True or item.get("effectiveWritable") is not False:
        _reject()
    identities = (
        item.get("pathIdentity"),
        item.get("descriptorIdentity"),
        item.get("postDescriptorIdentity"),
    )
    if not all(
        isinstance(identity, dict)
        and set(identity) == {"device", "inode"}
        and all(isinstance(number, int) and not isinstance(number, bool) for number in identity.values())
        for identity in identities
    ):
        _reject()
    if not (identities[0] == identities[1] == identities[2]):
        _reject()


def _validate_ancestor(item: Mapping[str, Any], path: str) -> None:
    _validate_identity(item, path, "directory")
    mode = item.get("mode")
    if not isinstance(mode, str) or re.fullmatch(r"0[0-7]{3}", mode) is None:
        _reject()
    if int(mode, 8) & 0o022:
        _reject()
    if item.get("acl") != []:
        _reject()


def _validate_installed_item(
    item: Mapping[str, Any],
    path: str,
    contract: Mapping[str, Any],
    kind: str,
) -> None:
    _validate_identity(item, path, kind)
    for key in ("owner", "group", "mode", "acl"):
        if item.get(key) != contract.get(key):
            _reject()
    if kind == "file":
        if item.get("linkCount") != contract.get("linkCount"):
            _reject()
        descriptor_hash = item.get("descriptorSha256")
        post_descriptor_hash = item.get("postDescriptorSha256")
        if not isinstance(descriptor_hash, str) or HASH_RE.fullmatch(descriptor_hash) is None:
            _reject()
        if descriptor_hash != post_descriptor_hash:
            _reject()
        if "sha256" in item and item.get("sha256") != descriptor_hash:
            _reject()
        if "sha256" in contract and descriptor_hash != contract.get("sha256"):
            _reject()


def validate_installation(
    policy: Any,
    inspect_path: Callable[[str], Mapping[str, Any]],
) -> None:
    validate_manifest(policy)
    paths: Dict[str, str] = policy["installedPaths"]
    system_paths = [path for path in policy["systemBinaries"] if path != "/bin/ls"]
    all_paths = list(paths.values()) + list(policy["managedDirectories"]) + system_paths
    ancestors = {parent for path in all_paths for parent in _path_parents(path)}
    for ancestor in sorted(ancestors):
        _validate_ancestor(_evidence(inspect_path, ancestor), ancestor)
    for name, path in paths.items():
        _validate_installed_item(
            _evidence(inspect_path, path),
            path,
            policy["artifacts"][name],
            "file",
        )
    for path, contract in policy["managedDirectories"].items():
        _validate_installed_item(_evidence(inspect_path, path), path, contract, "directory")
    for path, contract in policy["systemBinaries"].items():
        _validate_installed_item(_evidence(inspect_path, path), path, contract, "file")


def _json_no_duplicates(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _reject()
        result[key] = value
    return result


def _yaml_scalar(value: str) -> Any:
    value = value.strip()
    if value == "{}":
        return {}
    if value == "[]":
        return []
    if value in {"true", "false"}:
        return value == "true"
    if value in {"null", "~"}:
        return None
    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            _reject()
        if not isinstance(parsed, str):
            _reject()
        return parsed
    if value.startswith("'"):
        if len(value) < 2 or not value.endswith("'"):
            _reject()
        return value[1:-1].replace("''", "'")
    if any(token in value for token in (" #", "&", "*", "!", "|", ">")):
        _reject()
    return value


def _yaml_tokens(text: str) -> List[Tuple[int, str]]:
    result: List[Tuple[int, str]] = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if "\t" in raw or raw.rstrip() != raw:
            _reject()
        indent = len(raw) - len(raw.lstrip(" "))
        if indent % 2:
            _reject()
        result.append((indent, raw[indent:]))
    if not result:
        _reject()
    return result


def _split_yaml_mapping(content: str) -> Tuple[str, str]:
    match = re.fullmatch(r"([A-Za-z0-9_.-]+):(.*)", content)
    if match is None:
        _reject()
    return match.group(1), match.group(2).lstrip(" ")


def _parse_yaml_block(tokens: List[Tuple[int, str]], index: int, indent: int) -> Tuple[Any, int]:
    if index >= len(tokens) or tokens[index][0] != indent:
        _reject()
    if tokens[index][1].startswith("- "):
        result_list: List[Any] = []
        while index < len(tokens) and tokens[index][0] == indent:
            content = tokens[index][1]
            if not content.startswith("- "):
                break
            first = content[2:]
            index += 1
            if not first:
                if index >= len(tokens) or tokens[index][0] <= indent:
                    _reject()
                item, index = _parse_yaml_block(tokens, index, tokens[index][0])
                result_list.append(item)
                continue
            key, value = _split_yaml_mapping(first)
            item_dict: Dict[str, Any] = {}
            if value:
                item_dict[key] = _yaml_scalar(value)
            else:
                if index >= len(tokens) or tokens[index][0] <= indent:
                    _reject()
                child_indent = tokens[index][0]
                child, index = _parse_yaml_block(tokens, index, child_indent)
                item_dict[key] = child
            if index < len(tokens) and tokens[index][0] > indent:
                child_indent = tokens[index][0]
                extra, index = _parse_yaml_block(tokens, index, child_indent)
                if not isinstance(extra, dict):
                    _reject()
                for extra_key, extra_value in extra.items():
                    if extra_key in item_dict:
                        _reject()
                    item_dict[extra_key] = extra_value
            result_list.append(item_dict)
        return result_list, index

    result_dict: Dict[str, Any] = {}
    while index < len(tokens) and tokens[index][0] == indent:
        content = tokens[index][1]
        if content.startswith("- "):
            _reject()
        key, value = _split_yaml_mapping(content)
        if key in result_dict:
            _reject()
        index += 1
        if value:
            result_dict[key] = _yaml_scalar(value)
        else:
            if index >= len(tokens) or (
                tokens[index][0] < indent
                or (tokens[index][0] == indent and not tokens[index][1].startswith("- "))
            ):
                _reject()
            child, index = _parse_yaml_block(tokens, index, tokens[index][0])
            result_dict[key] = child
    return result_dict, index


def _parse_kubeconfig(text: str) -> Dict[str, Any]:
    try:
        value = json.loads(text, object_pairs_hook=_json_no_duplicates)
    except json.JSONDecodeError:
        tokens = _yaml_tokens(text)
        value, index = _parse_yaml_block(tokens, 0, tokens[0][0])
        if index != len(tokens):
            _reject()
    if not isinstance(value, dict):
        _reject()
    return value


def _unique_named(items: Any, entry_keys: Sequence[str], nested_key: str) -> Dict[str, Dict[str, Any]]:
    if not isinstance(items, list) or not items:
        _reject()
    result: Dict[str, Dict[str, Any]] = {}
    for value in items:
        item = _dict(value, entry_keys)
        name = _string(item["name"])
        if name in result or not isinstance(item[nested_key], dict):
            _reject()
        result[name] = item[nested_key]
    return result


def _decode_data(value: Any) -> bytes:
    try:
        return base64.b64decode(_string(value), validate=True)
    except (binascii.Error, ValueError):
        _reject()
    raise AssertionError("unreachable")


def validate_kubeconfig(text: Any, policy: Any) -> None:
    validate_manifest(policy)
    if not isinstance(text, str):
        _reject()
    expected_hash = policy["artifacts"]["kubeconfig"]["sha256"]
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != expected_hash:
        _reject()
    config = _parse_kubeconfig(text)
    allowed_top = {"apiVersion", "kind", "current-context", "contexts", "clusters", "users", "preferences"}
    if set(config) - allowed_top:
        _reject()
    if set(config) < {"apiVersion", "kind", "current-context", "contexts", "clusters", "users"}:
        _reject()
    if config["apiVersion"] != "v1" or config["kind"] != "Config":
        _reject()
    if "preferences" in config and config["preferences"] != {}:
        _reject()

    contexts = _unique_named(config["contexts"], ("name", "context"), "context")
    clusters = _unique_named(config["clusters"], ("name", "cluster"), "cluster")
    users = _unique_named(config["users"], ("name", "user"), "user")
    current = _string(config["current-context"])
    if current != policy["cluster"]["context"] or current not in contexts:
        _reject()
    context = _dict(contexts[current], ("cluster", "user"))
    cluster_name = _string(context["cluster"])
    user_name = _string(context["user"])
    if cluster_name not in clusters or user_name not in users:
        _reject()
    if len(contexts) != 1 or len(clusters) != 1 or len(users) != 1:
        _reject()

    cluster = _dict(clusters[cluster_name], ("server", "certificate-authority-data"))
    if cluster["server"] != policy["cluster"]["server"]:
        _reject()
    ca = _decode_data(cluster["certificate-authority-data"])
    if hashlib.sha256(ca).hexdigest() != policy["cluster"]["caSha256"]:
        _reject()

    user_value = users[user_name]
    if set(user_value) not in (
        {"client-certificate-data", "client-key-data"},
        {"client-certificate-data", "client-key-data", "token"},
    ):
        _reject()
    user = user_value
    if not _decode_data(user["client-certificate-data"]):
        _reject()
    if not _decode_data(user["client-key-data"]):
        _reject()
    if "token" in user and not _string(user["token"]):
        _reject()


def _run(
    argv: Sequence[str],
    run_process: Callable[..., Any],
    timeout: int,
) -> Any:
    try:
        result = run_process(
            list(argv),
            env=dict(CHILD_ENV),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=timeout,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        _reject()
    if not isinstance(result.returncode, int):
        _reject()
    return result


def _read_application(
    name: str,
    run_process: Callable[..., Any],
) -> Dict[str, Any]:
    argv = [
        CLI,
        "--core",
        "--kube-context",
        CONTEXT,
        "app",
        "get",
        name,
        "--app-namespace",
        "argocd",
        "--output",
        "json",
    ]
    result = _run(argv, run_process, 30)
    if result.returncode != 0 or not isinstance(result.stdout, str):
        _reject()
    try:
        value = json.loads(result.stdout, object_pairs_hook=_json_no_duplicates)
    except json.JSONDecodeError:
        _reject()
    if not isinstance(value, dict):
        _reject()
    if value.get("apiVersion") != "argoproj.io/v1alpha1" or value.get("kind") != "Application":
        _reject()
    metadata = value.get("metadata")
    spec = value.get("spec")
    status = value.get("status")
    if not isinstance(metadata, dict) or not isinstance(spec, dict) or not isinstance(status, dict):
        _reject()
    contract = APPLICATION_CONTRACTS.get(name)
    if contract is None:
        _reject()
    labels = metadata.get("labels", {})
    annotations = metadata.get("annotations", {})
    if not isinstance(labels, dict) or not isinstance(annotations, dict):
        _reject()
    annotations = {
        key: item
        for key, item in annotations.items()
        if key != "kubectl.kubernetes.io/last-applied-configuration"
    }
    normalized_metadata = {
        "name": metadata.get("name"),
        "namespace": metadata.get("namespace"),
        "labels": labels,
        "annotations": annotations,
    }
    if normalized_metadata != contract["metadata"]:
        _reject()
    if set(spec) != {"project", "source", "destination", "syncPolicy"}:
        _reject()
    source = spec.get("source")
    destination = spec.get("destination")
    sync_policy = spec.get("syncPolicy")
    if not isinstance(source, dict) or not isinstance(destination, dict) or not isinstance(sync_policy, dict):
        _reject()
    allowed_source_keys = {"repoURL", "targetRevision", "path", "directory"}
    if set(source) - allowed_source_keys or set(source) < {"repoURL", "targetRevision", "path"}:
        _reject()
    normalized_source = {
        "repoURL": source.get("repoURL"),
        "targetRevision": source.get("targetRevision"),
        "path": source.get("path"),
        "directory": source.get("directory", {}),
    }
    if normalized_source != {
        "repoURL": REPO_URL,
        "targetRevision": TAG,
        "path": contract["path"],
        "directory": contract["directory"],
    }:
        _reject()
    if destination != contract["destination"]:
        _reject()
    if sync_policy != {"syncOptions": contract["syncOptions"]}:
        _reject()
    if spec.get("project") != contract["project"]:
        _reject()
    return status


def _operation_safe(value: Any) -> bool:
    if value is None:
        return True
    return isinstance(value, dict) and value.get("phase") == "Succeeded"


def _validate_live_state(
    status: Mapping[str, Any],
    *,
    sync: str,
    health: str,
    revision: str,
) -> None:
    sync_state = status.get("sync")
    health_state = status.get("health")
    if not isinstance(sync_state, dict) or not isinstance(health_state, dict):
        _reject()
    if sync_state.get("status") != sync or sync_state.get("revision") != revision:
        _reject()
    if health_state.get("status") != health:
        _reject()
    if status.get("conditions", []) != []:
        _reject()
    if not _operation_safe(status.get("operationState")):
        _reject()


def execute_stage(
    stage: int,
    app: str,
    revision: str,
    policy: Any,
    *,
    inspect_path: Callable[[str], Mapping[str, Any]] = inspect_path,
    read_text: Callable[[str], str] = lambda path: Path(path).read_text(encoding="utf-8"),
    run_process: Callable[..., Any] = subprocess.run,
    environ: Mapping[str, str] = os.environ,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    del environ, stderr
    validate_manifest(policy)
    try:
        expected = APPLICATIONS[stage - 1]
    except (IndexError, TypeError):
        _reject()
    if isinstance(stage, bool) or expected[:2] != (stage, app) or revision != REVISION:
        _reject()
    validate_installation(policy, inspect_path)
    try:
        kubeconfig_text = read_text(KUBECONFIG)
    except (OSError, RuntimeError, TypeError, UnicodeError):
        _reject()
    validate_kubeconfig(kubeconfig_text, policy)
    validate_installation(policy, inspect_path)

    for previous_stage, previous_app, _ in APPLICATIONS[: stage - 1]:
        del previous_stage
        status = _read_application(previous_app, run_process)
        _validate_live_state(status, sync="Synced", health="Healthy", revision=REVISION)
    target_status = _read_application(app, run_process)
    _validate_live_state(
        target_status,
        sync="OutOfSync",
        health=expected[2],
        revision=REVISION,
    )
    validate_installation(policy, inspect_path)

    sync_argv = [
        CLI,
        "--core",
        "--kube-context",
        CONTEXT,
        "app",
        "sync",
        app,
        "--app-namespace",
        "argocd",
        "--revision",
        REVISION,
        "--timeout",
        "600",
    ]
    if _run(sync_argv, run_process, 630).returncode != 0:
        _reject()
    wait_argv = [
        CLI,
        "--core",
        "--kube-context",
        CONTEXT,
        "app",
        "wait",
        app,
        "--app-namespace",
        "argocd",
        "--sync",
        "--health",
        "--operation",
        "--timeout",
        "600",
    ]
    if _run(wait_argv, run_process, 630).returncode != 0:
        _reject()
    validate_installation(policy, inspect_path)
    final_status = _read_application(app, run_process)
    _validate_live_state(final_status, sync="Synced", health="Healthy", revision=REVISION)
    stdout.write("staged sync completed\n")
    return 0


def _load_manifest(path: str) -> Dict[str, Any]:
    try:
        text = Path(path).read_text(encoding="utf-8")
        value = json.loads(text, object_pairs_hook=_json_no_duplicates)
    except (OSError, UnicodeError, json.JSONDecodeError):
        _reject()
    validate_manifest(value)
    return value


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--stage", required=True, type=int)
    parser.add_argument("--app", required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args(argv)
    try:
        policy = _load_manifest(MANIFEST)
        return execute_stage(args.stage, args.app, args.revision, policy)
    except PolicyError:
        sys.stderr.write("staged sync policy rejected\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
