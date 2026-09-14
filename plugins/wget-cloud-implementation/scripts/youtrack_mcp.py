#!/usr/bin/env python3
"""Launch the official remote YouTrack MCP through a pinned stdio bridge.

Credentials are obtained locally, never sent as argv, written to the plugin,
or printed. Only the bridge's MCP stdout is inherited by the caller.
"""
import os
import shutil
import subprocess
import sys
import tempfile

ENDPOINT = "https://youtrack.wget-cloud.ru/mcp"
PACKAGE = "mcp-remote@0.1.38"
KEYCHAIN_SERVICE = "wget-cloud-youtrack"
KEYCHAIN_ACCOUNT = "mcp"
TOKEN_ENV = "WGC_YOUTRACK_TOKEN"
HEADER_ENV = "WGC_YOUTRACK_AUTH_HEADER"
SAFE_ENV = {"PATH", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "SystemRoot",
            "SYSTEMROOT", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL", "LC_CTYPE"}


class ConnectionSetupError(Exception):
    """Messages must be fixed strings; never include a credential or child output."""


def load_token(environ, platform=sys.platform):
    token = environ.get(TOKEN_ENV)
    if token is None and platform == "darwin":
        try:
            result = subprocess.run(
                ["/usr/bin/security", "find-generic-password", "-s", KEYCHAIN_SERVICE,
                 "-a", KEYCHAIN_ACCOUNT, "-w"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15, check=False,
            )
            if result.returncode == 0:
                token = result.stdout.decode("utf-8").rstrip("\r\n")
        except (OSError, subprocess.TimeoutExpired, UnicodeError):
            raise ConnectionSetupError("YouTrack: cannot read the local credential store.") from None
    if not token:
        raise ConnectionSetupError(
            "YouTrack: set WGC_YOUTRACK_TOKEN in the MCP process environment or add "
            "a Keychain password (service wget-cloud-youtrack, account mcp). "
            "Do not paste the token into chat."
        )
    if len(token) > 8192 or any(ord(c) < 33 or ord(c) > 126 for c in token):
        raise ConnectionSetupError("YouTrack: invalid local token format.")
    return token


def launch_config(environ, platform=sys.platform):
    # Do not expose unrelated credentials or npm/debug configuration to the bridge.
    child_env = {name: value for name, value in environ.items() if name in SAFE_ENV}
    mode = environ.get("WGC_YOUTRACK_AUTH", "token")
    args = ["--yes", "--registry=https://registry.npmjs.org", "--userconfig=./wgc-user.npmrc",
            "--globalconfig=./wgc-global.npmrc", "--ignore-scripts", PACKAGE, ENDPOINT, "--silent"]
    if mode == "token":
        child_env[HEADER_ENV] = "Bearer " + load_token(environ, platform)
        # mcp-remote expands this literal internally, never in a shell.
        args += ["--header", "Authorization:${WGC_YOUTRACK_AUTH_HEADER}"]
    elif mode != "oauth":
        raise ConnectionSetupError("YouTrack: WGC_YOUTRACK_AUTH must be token or oauth.")
    child_env.pop(TOKEN_ENV, None)
    return args, child_env


def main():
    try:
        args, child_env = launch_config(os.environ)
        executable = shutil.which("npx")
        if not executable:
            raise ConnectionSetupError("YouTrack: Node.js and npx must be available to the MCP process.")
        # Do not forward third-party diagnostic output that may include headers.
        # stdout remains the MCP stream; stderr has only our bounded status below.
        # An empty working directory prevents repository .npmrc configuration
        # from redirecting dependency downloads. npm checks registry integrity;
        # this is not a vendored, fully locked transitive dependency tree.
        with tempfile.TemporaryDirectory(prefix="wgc-youtrack-mcp-") as bridge_cwd:
            process = subprocess.Popen([executable, *args], env=child_env, cwd=bridge_cwd,
                                       stderr=subprocess.DEVNULL)
            try:
                code = process.wait()
            except KeyboardInterrupt:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                return 130
        if code:
            print("YouTrack: MCP connection ended unsuccessfully; check local auth and connectivity.", file=sys.stderr)
        return code if code >= 0 else 1
    except ConnectionSetupError as error:
        print(str(error), file=sys.stderr)
        return 2
    except OSError:
        print("YouTrack: cannot start the MCP bridge.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
