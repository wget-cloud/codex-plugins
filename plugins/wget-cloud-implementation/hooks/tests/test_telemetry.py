import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "runtime" / "telemetry.py"
SPEC = importlib.util.spec_from_file_location("wgc_telemetry_test", SCRIPT)
telemetry = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(telemetry)


class TelemetryTest(unittest.TestCase):
    def test_retries_queue_and_deletes_only_after_success(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = {"PLUGIN_DATA": directory, "WGC_CODEX_LOGS_TOKEN": "test-token"}
            with mock.patch.dict(os.environ, environment):
                with mock.patch.object(telemetry.request, "build_opener", side_effect=OSError("offline")):
                    telemetry.record("agent_started", {"session_id": "s", "agent_id": "a", "model": "gpt-test"}, {"project": "backend"}, "implementation")
                queue = Path(directory) / "telemetry"
                self.assertEqual(len(list(queue.glob("event-*.json"))), 1)

                response = mock.MagicMock()
                response.__enter__.return_value.status = 202
                opener = mock.MagicMock()
                opener.open.return_value = response
                with mock.patch.object(telemetry.request, "build_opener", return_value=opener):
                    telemetry.record("agent_stopped", {"session_id": "s", "agent_id": "a", "model": "gpt-test"}, {"project": "backend"}, "implementation")
                self.assertEqual(list(queue.glob("event-*.json")), [])
                request_object = opener.open.call_args.args[0]
                self.assertEqual(request_object.full_url, telemetry.ENDPOINT)
                self.assertEqual(request_object.get_header("Authorization"), "Bearer test-token")
                sent = json.loads(request_object.data)
                self.assertEqual({event["kind"] for event in sent["events"]}, {"agent_started", "agent_stopped"})
                self.assertEqual(len({event["event_id"] for event in sent["events"]}), 2)


if __name__ == "__main__":
    unittest.main()
