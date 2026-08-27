"""
Tests del logger best-effort pipeline_signal_log (Track B — paso 4b).

Verifica:
- Esquema fijo: todos los campos requeridos presentes en cada evento.
- Best-effort: un fallo de disco NO rompe el flujo (swallow).
- No corrupcion: lineas JSON validas, append-only.
- No mutacion: loggear no altera los resultados del pipeline.
"""
import json
import os
import tempfile
import unittest
from unittest import mock

# El modulo vive en scripts/; lo importamos con el mismo path que el pipeline.
from scripts import pipeline_signal_log as psl


class TestSignalLogSchema(unittest.TestCase):
    """Verifica que cada evento emitido tiene el esquema completo."""

    def setUp(self):
        # Redirect LOG_PATH a un temp file aislado por test.
        self._tmpdir = tempfile.TemporaryDirectory()
        self._log_path = os.path.join(self._tmpdir.name, "test_signal_log.jsonl")
        psl.LOG_PATH = self._log_path

    def tearDown(self):
        self._tmpdir.cleanup()
        psl.LOG_PATH = os.path.join("data", "pipeline_signal_log.jsonl")

    def _read_log(self):
        if not os.path.exists(self._log_path):
            return []
        with open(self._log_path, "r", encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def test_log_decision_emits_all_required_fields(self):
        signals = [
            {"symbol": "NVDA", "score": 0.72, "price_ref": 120.5},
            {"symbol": "MSFT", "score": 0.65, "price_ref": 410.0, "checkpoint_override": True},
        ]
        psl.log_decision(signals, "2026-08-26", "202608", {"w_mom_runtime": 0.6642})
        rows = self._read_log()
        self.assertEqual(len(rows), 2)
        for r in rows:
            for field in psl.REQUIRED_FIELDS:
                self.assertIn(field, r, f"falta campo obligatorio: {field}")
            self.assertEqual(r["event"], "decision")
            self.assertEqual(r["phase"], "decide")
            self.assertEqual(r["side"], "buy")
            self.assertIsNone(r["fill_price"])  # decide no ejecuta

    def test_log_execution_enter_emits_all_required_fields(self):
        results = [
            {"action": "buy", "symbol": "NVDA", "sid": "NVDA__2026-08-26",
             "qty": 10, "fill": 121.0, "client_order_id": "fc-enter-202608-NVDA",
             "status": "submitted"},
        ]
        psl.log_execution("enter", results)
        rows = self._read_log()
        self.assertEqual(len(rows), 1)
        r = rows[0]
        for field in psl.REQUIRED_FIELDS:
            self.assertIn(field, r)
        self.assertEqual(r["event"], "execution")
        self.assertEqual(r["phase"], "enter")
        self.assertEqual(r["fill_price"], 121.0)
        self.assertEqual(r["qty"], 10)

    def test_log_execution_exit_emits_all_required_fields(self):
        results = [
            {"action": "sell", "symbol": "NVDA", "sid": "NVDA__2026-07-31",
             "qty": 10, "fill": 130.0, "client_order_id": "fc-exit-202608-NVDA",
             "status": "submitted"},
        ]
        psl.log_execution("exit", results)
        rows = self._read_log()
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["event"], "execution")
        self.assertEqual(r["phase"], "exit")
        self.assertEqual(r["side"], "sell")

    def test_log_skipped_and_error_statuses(self):
        """skip y error tambien se loggean (no solo submitted)."""
        results = [
            {"action": "buy", "symbol": "AAPL", "sid": "AAPL__2026-08-26",
             "skip_reason": "ya_registrado_en_estado", "status": "skipped"},
            {"action": "buy", "symbol": "MSFT", "sid": "MSFT__2026-08-26",
             "error": "timeout", "status": "error"},
        ]
        psl.log_execution("enter", results)
        rows = self._read_log()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["skip_reason"], "ya_registrado_en_estado")
        self.assertEqual(rows[1]["error"], "timeout")


class TestSignalLogBestEffort(unittest.TestCase):
    """Verifica que logging JAMAS rompe el flujo del pipeline."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._log_path = os.path.join(self._tmpdir.name, "test_signal_log.jsonl")
        psl.LOG_PATH = self._log_path

    def tearDown(self):
        self._tmpdir.cleanup()
        psl.LOG_PATH = os.path.join("data", "pipeline_signal_log.jsonl")

    def test_os_error_does_not_raise(self):
        """Si el disco falla, log_decision NO levanta excepcion."""
        with mock.patch("builtins.open", side_effect=OSError("disk full")):
            # No debe lanzar — el pipeline real sigue aunque el log falle.
            psl.log_decision([{"symbol": "NVDA", "score": 0.7}], "2026-08-26", "202608", {})

    def test_json_serialize_error_does_not_raise(self):
        """Si hay un valor no serializable, no rompe."""
        with mock.patch.object(json, "dumps", side_effect=TypeError("not serializable")):
            psl.log_decision([{"symbol": "NVDA", "score": 0.7}], "2026-08-26", "202608", {})

    def test_append_only_no_overwrite(self):
        """Multiples llamadas appendan, no sobreescriben."""
        psl.log_decision([{"symbol": "NVDA", "score": 0.7}], "2026-08-26", "202608", {})
        psl.log_decision([{"symbol": "MSFT", "score": 0.6}], "2026-08-26", "202608", {})
        psl.log_execution("enter", [{"action": "buy", "symbol": "NVDA", "sid": "x", "qty": 1}])
        rows = []
        with open(self._log_path, "r", encoding="utf-8") as fh:
            rows = [json.loads(l) for l in fh if l.strip()]
        self.assertEqual(len(rows), 3)  # 2 decisions + 1 execution


class TestSignalLogDoesNotMutate(unittest.TestCase):
    """Verifica que loggear no altera los datos del pipeline."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._log_path = os.path.join(self._tmpdir.name, "test_signal_log.jsonl")
        psl.LOG_PATH = self._log_path

    def tearDown(self):
        self._tmpdir.cleanup()
        psl.LOG_PATH = os.path.join("data", "pipeline_signal_log.jsonl")

    def test_log_decision_does_not_mutate_input(self):
        signals = [{"symbol": "NVDA", "score": 0.72, "price_ref": 120.5}]
        original = json.dumps(signals)
        psl.log_decision(signals, "2026-08-26", "202608", {"w_mom_runtime": 0.6642})
        self.assertEqual(json.dumps(signals), original)  # sin mutacion

    def test_log_execution_does_not_mutate_input(self):
        results = [{"action": "buy", "symbol": "NVDA", "sid": "x", "qty": 10, "fill": 121.0}]
        original = json.dumps(results)
        psl.log_execution("enter", results)
        self.assertEqual(json.dumps(results), original)


if __name__ == "__main__":
    unittest.main()
