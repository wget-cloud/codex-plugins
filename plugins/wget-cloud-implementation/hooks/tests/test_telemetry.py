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
    def test_agent_usage_reads_only_numeric_metadata_from_own_transcript(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "codex"
            sessions = home / "sessions"
            sessions.mkdir(parents=True)
            transcript = sessions / "agent.jsonl"
            transcript.write_text("\n".join([
                json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {
                    "input_tokens": 120, "output_tokens": 30, "cached_input_tokens": 40,
                    "reasoning_output_tokens": 10, "total_tokens": 150,
                }}}}),
                json.dumps({"type": "event_msg", "payload": {"type": "message", "content": "private prompt"}}),
            ]) + "\n")
            with mock.patch.dict(os.environ, {"CODEX_HOME": str(home), "PLUGIN_DATA": directory}, clear=False):
                telemetry.record("agent_stopped", {"agent_id": "agent", "agent_transcript_path": str(transcript)}, {"project": "backend"}, "implementation")
                event = json.loads(next((Path(directory) / "telemetry").glob("event-*.json")).read_text())
                self.assertEqual(event["schema_version"], 2)
                self.assertEqual(event["usage"], {"input_tokens": 120, "output_tokens": 30, "cached_input_tokens": 40,
                                                  "reasoning_output_tokens": 10, "total_tokens": 150, "source": "codex_transcript"})
                self.assertNotIn("private prompt", json.dumps(event))

                outside = Path(directory) / "outside.jsonl"
                outside.write_text(transcript.read_text())
                self.assertIsNone(telemetry._token_usage({"agent_transcript_path": str(outside)}))
                transcript.write_text(json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": {
                    "total_token_usage": {"input_tokens": 12, "output_tokens": -1, "cached_input_tokens": 0,
                                          "reasoning_output_tokens": 0, "total_tokens": 11}}}}) + "\n")
                self.assertIsNone(telemetry._token_usage({"agent_transcript_path": str(transcript)}))

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
