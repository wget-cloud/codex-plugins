"""Credential and process boundaries of the bundled MCP launcher (no network)."""
import contextlib
import importlib.util
import io
import json
import subprocess
import tempfile
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / 'plugins/wget-cloud-implementation'
spec = importlib.util.spec_from_file_location('youtrack_launcher', PLUGIN/'scripts/youtrack_mcp.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class YouTrackLauncherTests(unittest.TestCase):
    def test_bundled_entrypoint_and_endpoint_are_portable_and_secret_free(self):
        manifest = json.loads((PLUGIN/'.codex-plugin/plugin.json').read_text())
        self.assertEqual(manifest['mcpServers'], './.mcp.json')
        config = json.loads((PLUGIN/'.mcp.json').read_text())['mcpServers']['youtrack']
        entrypoint = config['args'][0].replace('${PLUGIN_ROOT}', str(PLUGIN))
        self.assertTrue(Path(entrypoint).is_file())
        self.assertNotIn('env', config)
        self.assertNotIn('headers', config)

    def test_token_is_only_in_child_environment_not_arguments_or_input(self):
        env = {'WGC_YOUTRACK_TOKEN': 'synthetic-secret', 'DEBUG': '*', 'NODE_OPTIONS': '--inspect',
               'WGC_YOUTRACK_AUTH_HEADER': 'wrong', 'PATH': '/usr/bin',
               'AWS_SECRET_ACCESS_KEY':'unrelated', 'npm_config_registry':'https://invalid.example',
               'NPM_CONFIG_USERCONFIG':'/untrusted/npmrc', 'GITHUB_TOKEN':'unrelated'}
        args, child = launcher.launch_config(env, 'linux')
        self.assertNotIn('synthetic-secret', repr(args))
        self.assertEqual(child['WGC_YOUTRACK_AUTH_HEADER'], 'Bearer synthetic-secret')
        self.assertNotIn('WGC_YOUTRACK_TOKEN', child)
        self.assertNotIn('DEBUG', child)
        self.assertNotIn('NODE_OPTIONS', child)
        self.assertEqual(set(child), {'PATH', launcher.HEADER_ENV})
        self.assertIn('--registry=https://registry.npmjs.org', args)
        self.assertIn('--ignore-scripts', args)
        self.assertIn('--userconfig=./wgc-user.npmrc', args)
        self.assertIn('--globalconfig=./wgc-global.npmrc', args)
        self.assertEqual(env['WGC_YOUTRACK_AUTH_HEADER'], 'wrong')
        self.assertIn('mcp-remote@0.1.38', args)
        self.assertIn('https://youtrack.wget-cloud.ru/mcp', args)
        self.assertIn('Authorization:${WGC_YOUTRACK_AUTH_HEADER}', args)

    @unittest.skipUnless(shutil.which('npx'), 'Node.js not available')
    def test_npm_accepts_config_isolation_without_network_or_credentials(self):
        args, env = launcher.launch_config({**launcher.os.environ, 'WGC_YOUTRACK_AUTH':'oauth'})
        options = args[:args.index(launcher.PACKAGE)]
        with tempfile.TemporaryDirectory() as cwd:
            result = subprocess.run([shutil.which('npx'), *options, '--version'], env=env, cwd=cwd,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        self.assertEqual(result.returncode, 0, 'npm rejected isolated configuration')

    def test_keychain_lookup_is_scoped_and_never_passes_secret_as_argv(self):
        with patch.object(launcher.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'synthetic-keychain\n')) as run:
            args, child = launcher.launch_config({}, 'darwin')
        self.assertEqual(child['WGC_YOUTRACK_AUTH_HEADER'], 'Bearer synthetic-keychain')
        self.assertEqual(run.call_args.args[0], ['/usr/bin/security', 'find-generic-password', '-s', 'wget-cloud-youtrack', '-a', 'mcp', '-w'])
        self.assertNotIn('synthetic-keychain', repr(args))

    def test_missing_invalid_or_denied_credentials_do_not_connect(self):
        for token in ('', 'header\r\ninjection', 'Bearer secret', 'x'*8193):
            with self.subTest(token_length=len(token)), self.assertRaises(launcher.ConnectionSetupError):
                launcher.launch_config({'WGC_YOUTRACK_TOKEN': token}, 'linux')
        with patch.object(launcher.subprocess, 'run', return_value=subprocess.CompletedProcess([], 44, b'')):
            with self.assertRaises(launcher.ConnectionSetupError):
                launcher.launch_config({}, 'darwin')
        with patch.dict(launcher.os.environ, {'WGC_YOUTRACK_TOKEN': ''}, clear=True), patch.object(launcher.subprocess, 'Popen') as popen:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(launcher.main(), 2)
            popen.assert_not_called()

    def test_oauth_is_explicit_and_does_not_forward_an_existing_token(self):
        with patch.object(launcher, 'load_token') as token:
            args, child = launcher.launch_config({'WGC_YOUTRACK_AUTH': 'oauth', 'WGC_YOUTRACK_TOKEN': 'synthetic'})
        token.assert_not_called()
        self.assertNotIn('--header', args)
        self.assertNotIn('WGC_YOUTRACK_TOKEN', child)
        with self.assertRaises(launcher.ConnectionSetupError):
            launcher.launch_config({'WGC_YOUTRACK_AUTH': 'guess'})

    def test_child_diagnostics_cannot_leak_headers_to_parent_stderr(self):
        err = io.StringIO()
        with patch.dict(launcher.os.environ, {'WGC_YOUTRACK_TOKEN': 'synthetic-secret'}, clear=True), patch.object(launcher.shutil, 'which', return_value='/usr/bin/npx'), patch.object(launcher.subprocess, 'Popen') as popen:
            popen.return_value.wait.return_value = 1
            with contextlib.redirect_stderr(err):
                self.assertEqual(launcher.main(), 1)
            self.assertIs(popen.call_args.kwargs['stderr'], subprocess.DEVNULL)
            self.assertNotIn('shell', popen.call_args.kwargs)
            self.assertIn('wgc-youtrack-mcp-', popen.call_args.kwargs['cwd'])
            self.assertNotIn('synthetic-secret', err.getvalue())


if __name__ == '__main__':
    unittest.main()
