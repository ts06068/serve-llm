"""Check cost-sensitive lifecycle behavior without releasing a real GPU."""
import argparse
import contextlib
import io
import ssl
import unittest
import urllib.error
from unittest.mock import patch

from runpod import manage


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.state = patch.object(manage, "deployment", return_value={
            "pod_id": "configured-pod", "volume_id": "persistent-volume",
        })
        self.state.start()
        self.addCleanup(self.state.stop)
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def args(self, action, **overrides):
        return argparse.Namespace(action=action, dry_run=False, no_wait=False,
                                  timeout=1200, interval=10, **overrides)

    def test_start_running_pod_only_checks_readiness(self):
        with patch.object(manage, "cli", return_value={"desiredStatus": "RUNNING"}) as cli, \
             patch.object(manage, "wait_ready") as wait:
            manage.operate(self.args("start"))
            cli.assert_called_once_with("pod", "get", "configured-pod")
            wait.assert_called_once_with(1200, 10, require_outage=False)

    def test_start_stopped_pod_targets_recorded_pod(self):
        with patch.object(manage, "cli", side_effect=[{"desiredStatus": "EXITED"}, {}]) as cli, \
             patch.object(manage, "wait_ready"):
            manage.operate(self.args("start"))
            self.assertEqual(cli.call_args_list[-1].args, ("pod", "start", "configured-pod"))

    def test_capacity_failure_does_not_provision_or_wait(self):
        with patch.object(manage, "cli", side_effect=[{"desiredStatus": "EXITED"},
                         RuntimeError("not enough free GPUs")]) as cli, \
             patch.object(manage, "wait_ready") as wait:
            with self.assertRaisesRegex(RuntimeError, "not enough free GPUs"):
                manage.operate(self.args("start"))
            self.assertEqual(cli.call_count, 2)
            wait.assert_not_called()

    def test_stop_only_stops_recorded_pod(self):
        with patch.object(manage, "cli", side_effect=[{"desiredStatus": "RUNNING"}, {}]) as cli:
            manage.operate(self.args("stop"))
            self.assertEqual([call.args for call in cli.call_args_list], [
                ("pod", "get", "configured-pod"), ("pod", "stop", "configured-pod"),
            ])

    def test_stop_is_idempotent(self):
        with patch.object(manage, "cli", return_value={"desiredStatus": "EXITED"}) as cli:
            manage.operate(self.args("stop"))
            cli.assert_called_once_with("pod", "get", "configured-pod")

    def test_restart_stopped_pod_does_not_start_it(self):
        with patch.object(manage, "cli", return_value={"desiredStatus": "EXITED"}) as cli:
            with self.assertRaisesRegex(RuntimeError, "Use ./start.sh"):
                manage.operate(self.args("restart"))
            cli.assert_called_once_with("pod", "get", "configured-pod")

    def test_restart_waits_for_outage_before_claiming_ready(self):
        with patch.object(manage, "probe", side_effect=[(True, "READY"),
                         (False, "offline"), (True, "READY")]) as probe, \
             patch.object(manage, "config", return_value={"OPENAI_BASE_URL": "https://test/v1"}), \
             patch.object(manage.time, "sleep"):
            manage.wait_ready(1200, 10, require_outage=True)
            self.assertEqual(probe.call_count, 3)

    def test_readiness_timeout_reports_pod_may_still_bill(self):
        with patch.object(manage, "probe", return_value=(False, "HTTP 502")), \
             patch.object(manage.time, "monotonic", side_effect=[0, 2]):
            with self.assertRaisesRegex(RuntimeError, "running and billing"):
                manage.wait_ready(1, 10)

    def test_tls_eof_is_retried_until_endpoint_is_ready(self):
        eof = urllib.error.URLError(ssl.SSLEOFError(8, "UNEXPECTED_EOF_WHILE_READING"))
        response = io.StringIO('{"data":[{"id":"gemma-4-31b-it","max_model_len":32768}]}')
        with patch.object(manage, "config", return_value={"OPENAI_BASE_URL": "https://test/v1"}), \
             patch.object(manage, "request", side_effect=[eof, response]) as request, \
             patch.object(manage.time, "sleep"):
            manage.wait_ready(1200, 10)
            self.assertEqual(request.call_count, 2)

    def test_certificate_error_remains_visible(self):
        error = urllib.error.URLError(ssl.SSLCertVerificationError(1, "CERTIFICATE_VERIFY_FAILED"))
        with patch.object(manage, "config", return_value={"OPENAI_BASE_URL": "https://test/v1"}), \
             patch.object(manage, "request", side_effect=error):
            ready, detail = manage.probe()
            self.assertFalse(ready)
            self.assertIn("CERTIFICATE_VERIFY_FAILED", detail)

    def test_dry_run_makes_no_api_call(self):
        args = self.args("stop")
        args.dry_run = True
        with patch.object(manage, "cli") as cli:
            manage.operate(args)
            cli.assert_not_called()


if __name__ == "__main__":
    unittest.main()
