"""
Tests del job runner (Fase 4) — sin TestClient, sin red.

Cubren:
- El job aborta limpio si FMP_API_KEY no está
- El job aborta si FmpClient no está disponible
- --resume no reprocesa símbolos ya completados en state.json
- El job persiste state.json y screen_<date>.json
- Si un símbolo falla, NO se reintenta (se anota y sigue)
- Si el budget se agota, el job para de iterar
- Garantías de aislamiento: no importa predictive_engine ni notifier
"""
import json
import sys
from pathlib import Path

from app.config import settings
from scripts import run_fundamentals_screen as job


def test_job_aborts_clean_when_no_fmp_key(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(settings, "FMP_API_KEY", "")
    called = {"ingest": False}
    def fake_ingester():
        called["ingest"] = True
        class I:
            fmp = type("F", (), {"is_available": lambda s: True})()
        return I()
    monkeypatch.setattr(job, "FundamentalsIngestion", fake_ingester)
    monkeypatch.setattr(job, "CACHE_DIR", str(tmp_path))
    rc = job.main([])
    assert rc == 2
    assert called["ingest"] is False
    assert "FMP_API_KEY" in capsys.readouterr().out


def test_job_aborts_when_fmp_client_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "FMP_API_KEY", "fake-key")
    class FakeFmp:
        is_available = lambda self: False
    class FakeIngester:
        fmp = FakeFmp()
    monkeypatch.setattr(job, "FundamentalsIngestion", lambda: FakeIngester())
    monkeypatch.setattr(job, "CACHE_DIR", str(tmp_path))
    rc = job.main([])
    assert rc == 2


def test_job_resume_skips_completed_symbols(monkeypatch, tmp_path):
    """--resume no reprocesa símbolos ya completados en state.json."""
    monkeypatch.setattr(settings, "FMP_API_KEY", "fake-key")
    state_path = Path(tmp_path) / "state.json"
    state_path.write_text(json.dumps({
        "completed_symbols": ["AAPL"],
        "failed_symbols": [],
        "calls_used": 5,
    }))
    monkeypatch.setattr(job, "STATE_PATH", str(state_path))
    monkeypatch.setattr(job, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(job, "DAILY_FMP_BUDGET", 240)

    processed = []
    def fake_screen_payload(payload):
        return {"balde": "Neutral"}
    class FakeFmp:
        is_available = lambda self: True
    class FakeIngester:
        fmp = FakeFmp()
        def ingest_symbol(self, sym):
            processed.append(sym)
            return {"symbol": sym, "income_statement": [], "balance_sheet": [],
                    "cash_flow": [], "profile": {}, "price_target_consensus": {}}
    monkeypatch.setattr(job, "FundamentalsIngestion", lambda: FakeIngester())
    monkeypatch.setattr(job, "screen_payload", fake_screen_payload)

    rc = job.main(["run_fundamentals_screen", "--resume",
                                       "--universe", "AAPL,MSFT,GOOGL",
                                       "--date", "2026-08-27"])
    assert rc == 0
    assert "AAPL" not in processed
    assert processed == ["MSFT", "GOOGL"]


def test_job_writes_state_and_artifact(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "FMP_API_KEY", "fake-key")
    monkeypatch.setattr(job, "STATE_PATH", str(Path(tmp_path) / "state.json"))
    monkeypatch.setattr(job, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(job, "DAILY_FMP_BUDGET", 240)

    def fake_screen_payload(payload):
        return {"balde": "Neutral", "cal": "BUENA", "punt": 5}
    class FakeFmp:
        is_available = lambda self: True
    class FakeIngester:
        fmp = FakeFmp()
        def ingest_symbol(self, sym):
            return {"symbol": sym, "income_statement": [], "balance_sheet": [],
                    "cash_flow": [], "profile": {"symbol": sym, "price": 100},
                    "price_target_consensus": {}}
    monkeypatch.setattr(job, "FundamentalsIngestion", lambda: FakeIngester())
    monkeypatch.setattr(job, "screen_payload", fake_screen_payload)

    rc = job.main(["run_fundamentals_screen",
                                       "--universe", "AAPL,MSFT",
                                       "--date", "2026-08-27"])
    assert rc == 0
    state = json.loads(Path(tmp_path, "state.json").read_text())
    assert state["completed_symbols"] == ["AAPL", "MSFT"]
    assert state["calls_used"] == 10
    assert state["last_successful_date"] == "2026-08-27"
    artifact = json.loads(Path(tmp_path, "screen_2026-08-27.json").read_text())
    assert set(artifact["results"].keys()) == {"AAPL", "MSFT"}


def test_job_no_retry_on_symbol_failure(monkeypatch, tmp_path):
    """Si un símbolo falla, NO se reintenta. Se anota y se sigue.

    Esta es la política de cuota FMP clave: si una llamada falla, no se
    reintenta el mismo día (quema la cuota del día siguiente y los datos
    no van a aparecer hoy de todos modos). El job continua con el
    siguiente símbolo y guarda el fallido en state.json para retomar
    mañana con --resume.
    """
    monkeypatch.setattr(settings, "FMP_API_KEY", "fake-key")
    monkeypatch.setattr(job, "STATE_PATH", str(Path(tmp_path) / "state.json"))
    monkeypatch.setattr(job, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(job, "DAILY_FMP_BUDGET", 240)

    class FakeFmp:
        is_available = lambda self: True
    class FakeIngester:
        fmp = FakeFmp()
        def ingest_symbol(self, sym):
            if sym == "BAD":
                return None
            return {"symbol": sym, "income_statement": [], "balance_sheet": [],
                    "cash_flow": [], "profile": {"symbol": sym, "price": 100},
                    "price_target_consensus": {}}
    def fake_screen_payload(payload):
        return {"balde": "Neutral"}
    monkeypatch.setattr(job, "FundamentalsIngestion", lambda: FakeIngester())
    monkeypatch.setattr(job, "screen_payload", fake_screen_payload)

    rc = job.main(["run_fundamentals_screen",
                                       "--universe", "AAPL,BAD,MSFT",
                                       "--date", "2026-08-27"])
    assert rc == 0
    state = json.loads(Path(tmp_path, "state.json").read_text())
    assert "AAPL" in state["completed_symbols"]
    assert "MSFT" in state["completed_symbols"]
    assert "BAD" not in state["completed_symbols"]
    assert any(f["symbol"] == "BAD" for f in state["failed_symbols"])


def test_job_budget_stops_loop(monkeypatch, tmp_path):
    """Si el budget se agota, el job para de iterar y guarda el state."""
    monkeypatch.setattr(settings, "FMP_API_KEY", "fake-key")
    monkeypatch.setattr(job, "STATE_PATH", str(Path(tmp_path) / "state.json"))
    monkeypatch.setattr(job, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(job, "DAILY_FMP_BUDGET", 10)

    class FakeFmp:
        is_available = lambda self: True
    class FakeIngester:
        fmp = FakeFmp()
        def ingest_symbol(self, sym):
            return {"symbol": sym, "income_statement": [], "balance_sheet": [],
                    "cash_flow": [], "profile": {"symbol": sym, "price": 100},
                    "price_target_consensus": {}}
    def fake_screen_payload(payload):
        return {"balde": "Neutral"}
    monkeypatch.setattr(job, "FundamentalsIngestion", lambda: FakeIngester())
    monkeypatch.setattr(job, "screen_payload", fake_screen_payload)

    rc = job.main(["run_fundamentals_screen",
                                       "--universe", "A,MSFT,GOOGL,AMZN",
                                       "--date", "2026-08-27"])
    assert rc == 0
    state = json.loads(Path(tmp_path, "state.json").read_text())
    assert len(state["completed_symbols"]) == 2
    assert state["calls_used"] == 10


# ============================================================================
# Garantías de aislamiento (regla 5 de Boris: avisar ANTES de tocar)
# ============================================================================

def test_job_does_not_import_predictive_engine():
    """Fase 4 — la regla 5 de Boris: el job NO debe importar predictive_engine.
    Buscamos específicamente `import predictive_engine` o `from predictive_engine`
    (no la palabra suelta, porque aparece en el docstring explicando la regla)."""
    job_path = Path("scripts/run_fundamentals_screen.py")
    content = job_path.read_text()
    assert "import predictive_engine" not in content, (
        "Fase 4: el job NO debe importar predictive_engine. Si lo necesitás, "
        "avisale a Boris ANTES según la regla 5 del plan."
    )
    assert "from predictive_engine" not in content, (
        "Fase 4: el job NO debe importar predictive_engine. Si lo necesitás, "
        "avisale a Boris ANTES según la regla 5 del plan."
    )


def test_job_does_not_import_notifier():
    job_path = Path("scripts/run_fundamentals_screen.py")
    content = job_path.read_text()
    assert "import notifier" not in content, (
        "Fase 4: el job NO debe importar notifier. Si lo necesitás, "
        "avisale a Boris ANTES según la regla 5 del plan."
    )
    assert "from notifier" not in content, (
        "Fase 4: el job NO debe importar notifier. Si lo necesitás, "
        "avisale a Boris ANTES según la regla 5 del plan."
    )


def test_router_does_not_import_predictive_engine_or_notifier():
    r_path = Path("app/api/routes/fundamentals_screen.py")
    content = r_path.read_text()
    assert "import predictive_engine" not in content
    assert "import notifier" not in content
    assert "from predictive_engine" not in content
    assert "from notifier" not in content

# ============================================================================
# Procesamiento en LOTES (robustez A6.3-style)
# ============================================================================

def test_job_processes_in_batches_with_checkpoints(monkeypatch, tmp_path):
    """El job procesa en lotes de BATCH_SIZE, con checkpoint de state.json
    después de CADA lote. Si el proceso muere a mitad del lote 3, el state.json
    tiene los lotes 1-2 completos y la corrida siguiente con --resume retoma."""
    monkeypatch.setattr(settings, "FMP_API_KEY", "fake-key")
    monkeypatch.setattr(job, "STATE_PATH", str(Path(tmp_path) / "state.json"))
    monkeypatch.setattr(job, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(job, "DAILY_FMP_BUDGET", 240)
    monkeypatch.setattr(job, "BATCH_SIZE", 5)  # 5 = el default
    monkeypatch.setattr(job, "BATCH_PAUSE_SECONDS", 0)  # sin pausa en tests

    # Instrumentar _write_state para detectar checkpoints
    checkpoints = []
    original_write_state = job._write_state
    def tracked_write_state(state):
        checkpoints.append({
            "completed": list(state["completed_symbols"]),
            "failed": list(state["failed_symbols"]),
            "calls_used": state["calls_used"],
        })
        return original_write_state(state)
    monkeypatch.setattr(job, "_write_state", tracked_write_state)

    # Capturar el orden de ingestas para verificar el orden de procesamiento
    ingest_order = []
    def fake_screen_payload(payload):
        return {"balde": "Neutral"}
    class FakeFmp:
        is_available = lambda self: True
    class FakeIngester:
        fmp = FakeFmp()
        def ingest_symbol(self, sym):
            ingest_order.append(sym)
            return {"symbol": sym, "income_statement": [], "balance_sheet": [],
                    "cash_flow": [], "profile": {"symbol": sym, "price": 100},
                    "price_target_consensus": {}}
    monkeypatch.setattr(job, "FundamentalsIngestion", lambda: FakeIngester())
    monkeypatch.setattr(job, "screen_payload", fake_screen_payload)

    universe = [f"S{i:02d}" for i in range(12)]  # 12 símbolos = 3 lotes de 5 (último con 2)
    monkeypatch.setattr(sys, "argv", ["run_fundamentals_screen",
                                       "--universe", ",".join(universe),
                                       "--date", "2026-08-27"])
    rc = job.main()
    assert rc == 0

    # Se procesaron los 12 en orden
    assert ingest_order == universe
    # calls_used = 12 × 5 = 60
    state = json.loads(Path(tmp_path, "state.json").read_text())
    assert state["calls_used"] == 60
    assert len(state["completed_symbols"]) == 12

    # Hubo EXACTAMENTE 3 checkpoints (uno por lote), más el _write_state final
    # que ya existía. Verificamos que los 3 checkpoints intermedios tienen
    # los símbolos esperados.
    assert len(checkpoints) >= 3, f"esperaba >=3 checkpoints, encontré {len(checkpoints)}"
    # Checkpoint 1: lote 1 = símbolos 0-4
    assert checkpoints[0]["completed"] == ["S00", "S01", "S02", "S03", "S04"]
    # Checkpoint 2: lote 2 = símbolos 0-9
    assert checkpoints[1]["completed"] == ["S00", "S01", "S02", "S03", "S04",
                                            "S05", "S06", "S07", "S08", "S09"]
    # Checkpoint 3: lote 3 (último, sólo 2) = 0-11
    assert len(checkpoints[2]["completed"]) == 12


def test_job_resume_continues_from_last_checkpoint(monkeypatch, tmp_path):
    """Si un lote ya está commiteado, --resume no reprocesa y sigue desde
    donde quedó. La idempotencia se mantiene a nivel de símbolo."""
    monkeypatch.setattr(settings, "FMP_API_KEY", "fake-key")
    # Estado pre-existente: lote 1 completo (S00-S04), lote 2 empezado con
    # S05 hecho y S06 pendiente.
    state_path = Path(tmp_path) / "state.json"
    state_path.write_text(json.dumps({
        "completed_symbols": ["S00", "S01", "S02", "S03", "S04", "S05"],
        "failed_symbols": [],
        "calls_used": 30,  # 6 × 5
    }))
    monkeypatch.setattr(job, "STATE_PATH", str(state_path))
    monkeypatch.setattr(job, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(job, "DAILY_FMP_BUDGET", 240)
    monkeypatch.setattr(job, "BATCH_SIZE", 5)
    monkeypatch.setattr(job, "BATCH_PAUSE_SECONDS", 0)

    ingest_order = []
    def fake_screen_payload(payload):
        return {"balde": "Neutral"}
    class FakeFmp:
        is_available = lambda self: True
    class FakeIngester:
        fmp = FakeFmp()
        def ingest_symbol(self, sym):
            ingest_order.append(sym)
            return {"symbol": sym, "income_statement": [], "balance_sheet": [],
                    "cash_flow": [], "profile": {"symbol": sym, "price": 100},
                    "price_target_consensus": {}}
    monkeypatch.setattr(job, "FundamentalsIngestion", lambda: FakeIngester())
    monkeypatch.setattr(job, "screen_payload", fake_screen_payload)

    universe = [f"S{i:02d}" for i in range(12)]
    monkeypatch.setattr(sys, "argv", ["run_fundamentals_screen", "--resume",
                                       "--universe", ",".join(universe),
                                       "--date", "2026-08-27"])
    rc = job.main()
    assert rc == 0

    # --resume saltó los 6 ya hechos. Procesó S06-S11 (6 más).
    assert ingest_order == ["S06", "S07", "S08", "S09", "S10", "S11"]
    state = json.loads(state_path.read_text())
    assert state["completed_symbols"] == ["S00", "S01", "S02", "S03", "S04",
                                          "S05", "S06", "S07", "S08", "S09",
                                          "S10", "S11"]


def test_job_does_not_retry_within_batch_on_failure(monkeypatch, tmp_path):
    """Si un símbolo falla, NO se reintenta: se anota y sigue con el resto
    del lote. La política de cuota FMP lo exige (250/día sin margen)."""
    monkeypatch.setattr(settings, "FMP_API_KEY", "fake-key")
    monkeypatch.setattr(job, "STATE_PATH", str(Path(tmp_path) / "state.json"))
    monkeypatch.setattr(job, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(job, "DAILY_FMP_BUDGET", 240)
    monkeypatch.setattr(job, "BATCH_SIZE", 5)
    monkeypatch.setattr(job, "BATCH_PAUSE_SECONDS", 0)

    # Contar cuántas veces se llama a ingest_symbol para el símbolo malo
    bad_calls = {"BAD": 0}
    ingest_order = []

    def fake_screen_payload(payload):
        return {"balde": "Neutral"}

    class FakeFmp:
        is_available = lambda self: True

    class FakeIngester:
        fmp = FakeFmp()
        def ingest_symbol(self, sym):
            ingest_order.append(sym)
            if sym == "BAD":
                bad_calls["BAD"] += 1
                return None  # fallo
            return {"symbol": sym, "income_statement": [], "balance_sheet": [],
                    "cash_flow": [], "profile": {"symbol": sym, "price": 100},
                    "price_target_consensus": {}}
    monkeypatch.setattr(job, "FundamentalsIngestion", lambda: FakeIngester())
    monkeypatch.setattr(job, "screen_payload", fake_screen_payload)

    universe = ["A", "BAD", "B", "C", "D", "E"]  # BAD está en medio del lote 1
    monkeypatch.setattr(sys, "argv", ["run_fundamentals_screen",
                                       "--universe", ",".join(universe),
                                       "--date", "2026-08-27"])
    rc = job.main()
    assert rc == 0
    # BAD se llamó UNA sola vez (no retry)
    assert bad_calls["BAD"] == 1
    # BAD está en failed, los otros 5 en completed
    state = json.loads(Path(tmp_path, "state.json").read_text())
    assert "BAD" in [f["symbol"] for f in state["failed_symbols"]]
    assert sorted(state["completed_symbols"]) == ["A", "B", "C", "D", "E"]
    # El orden de ingestas muestra que el lote siguió: A, BAD, B, C, D
    assert "BAD" in ingest_order


def test_job_batch_continues_even_if_inner_break(monkeypatch, tmp_path):
    """Si un símbolo agota el budget (break del bucle interno), el lote
    siguiente arranca desde el siguiente símbolo, no reintenta."""
    monkeypatch.setattr(settings, "FMP_API_KEY", "fake-key")
    monkeypatch.setattr(job, "STATE_PATH", str(Path(tmp_path) / "state.json"))
    monkeypatch.setattr(job, "CACHE_DIR", str(tmp_path))
    # Budget de 12: alcanza para 2 símbolos (10 calls), el tercero aborta
    monkeypatch.setattr(job, "DAILY_FMP_BUDGET", 12)
    monkeypatch.setattr(job, "BATCH_SIZE", 3)
    monkeypatch.setattr(job, "BATCH_PAUSE_SECONDS", 0)

    def fake_screen_payload(payload):
        return {"balde": "Neutral"}
    class FakeFmp:
        is_available = lambda self: True
    class FakeIngester:
        fmp = FakeFmp()
        def ingest_symbol(self, sym):
            return {"symbol": sym, "income_statement": [], "balance_sheet": [],
                    "cash_flow": [], "profile": {"symbol": sym, "price": 100},
                    "price_target_consensus": {}}
    monkeypatch.setattr(job, "FundamentalsIngestion", lambda: FakeIngester())
    monkeypatch.setattr(job, "screen_payload", fake_screen_payload)

    # 6 símbolos en 2 lotes de 3. Budget 12: alcanza para 2 del lote 1, el
    # tercero (3ro) hace break interno. Lote 2 NO se procesa (budget=2).
    universe = ["A", "B", "C", "D", "E", "F"]
    monkeypatch.setattr(sys, "argv", ["run_fundamentals_screen",
                                       "--universe", ",".join(universe),
                                       "--date", "2026-08-27"])
    rc = job.main()
    assert rc == 0
    state = json.loads(Path(tmp_path, "state.json").read_text())
    # Sólo 2 hechos (A y B); C, D, E, F pendientes
    assert state["completed_symbols"] == ["A", "B"]
    assert state["calls_used"] == 10
    # D, E, F NO se procesaron (break interno del lote 1 detuvo el bucle externo)


def test_job_default_batch_size_is_5():
    """El tamaño de lote default es 5 (10 lotes para el universo de 50)."""
    # Leemos el módulo fresco (puede ser que el test de otro archivo ya lo
    # modificó con monkeypatch).
    import importlib
    importlib.reload(job)
    assert job.BATCH_SIZE == 5, f"esperaba 5, encontré {job.BATCH_SIZE}"
    assert job.BATCH_PAUSE_SECONDS >= 0
