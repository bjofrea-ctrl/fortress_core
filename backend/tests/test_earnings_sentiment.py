"""Tests del pipeline de sentimiento de earnings calls (Tarea B, PASO 1).

REGLAS DE ESTA SUITE: SIN red y SIN transformers real. El import lazy de
transformers en app/core/earnings_sentiment.py existe para que esta suite
corra en CI sin torch; acá se inyecta un pipeline fake (pipeline_factory) o
se monkeypatchean las funciones de red.
"""
import pytest

from app.core.earnings_sentiment import (
    CHUNK_MAX_CHARS,
    CHUNK_TARGET_CHARS,
    ETF_EXCLUSIONS,
    EarningsSentimentStore,
    _pick_exhibit_from_index,
    accumulate_earnings_sentiment,
    aggregate_chunk_scores,
    chunk_text,
    finbert_result_to_probs,
    finbert_score,
    html_to_text,
    parse_company_tickers,
    parse_submissions_json,
    resolve_cik,
    score_from_probs,
)

# --------------------------------------------------------------------------- #
# Fixtures.
# --------------------------------------------------------------------------- #
# Estructura mínima realista de data.sec.gov/submissions/CIK*.json: los
# campos de `recent` son listas paralelas indexadas por filing.
SUBMISSIONS_FIXTURE = {
    "cik": "0000320193",
    "name": "APPLE INC",
    "filings": {
        "recent": {
            "form": ["8-K", "8-K", "10-Q", "8-K", "8-K"],
            "filingDate": ["2026-05-01", "2026-02-01", "2026-04-01", "2025-11-01", "2025-08-01"],
            "accessionNumber": [
                "0000320193-26-000001", "0000320193-26-000002",
                "0000320193-26-000003", "0000320193-25-000004", "0000320193-25-000005",
            ],
            "primaryDocument": [
                "aapl-8k.htm", "aapl-8k2.htm", "aapl-10q.htm", "aapl-8k3.htm", "aapl-8k4.htm",
            ],
            "items": ["2.02,9.01", "2.02", "n/a", "7.01", "2.02 9.01"],
        }
    },
}

PRESS_RELEASE_HTML = """
<html><body>
<script>var x = 1;</script>
<style>.hidden { display: none; }</style>
<h1>Acme Corp Reports Record Results</h1>
<p>Revenue increased <b>25%</b> year over year.</p>
<p>We are excited about the outlook for 2026.</p>
</body></html>
"""


class _FakeResp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeSession:
    """Sesión fake: devuelve contenido según la URL pedida (sin red)."""

    def __init__(self, by_url):
        self.by_url = by_url
        self.headers = {}
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append(url)
        if url not in self.by_url:
            raise RuntimeError(f"URL no simulada: {url}")
        return _FakeResp(self.by_url[url])


class _FakeFinbertPipe:
    """Pipeline fake de FinBERT: score positivo proporcional a "positive" en
    el chunk, negativo proporcional a "negative" — deterministic y sin modelo."""

    def __call__(self, chunks, truncation=True):
        out = []
        for chunk in chunks:
            pos = chunk.count("positive")
            neg = chunk.count("negative")
            total = pos + neg or 1
            if pos > neg:
                out.append({"label": "positive", "score": pos / total})
            elif neg > pos:
                out.append({"label": "negative", "score": neg / total})
            else:
                out.append({"label": "neutral", "score": 1.0})
        return out


# --------------------------------------------------------------------------- #
# Chunking y agregación (funciones puras).
# --------------------------------------------------------------------------- #
def test_chunk_text_divide_texto_largo_por_oraciones():
    text = ". ".join(f"Sentence number {i} with some padding words here." for i in range(200))
    chunks = chunk_text(text)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= CHUNK_MAX_CHARS
    # el texto no se pierde: las oraciones se preservan (join de todo ≈ texto)
    joined = " ".join(chunks)
    assert len(joined) >= len(text) - 40


def test_chunk_text_oracion_gigante_se_corta():
    text = ("word " * 3000).strip()
    chunks = chunk_text(text)
    assert all(len(c) <= CHUNK_MAX_CHARS for c in chunks)
    assert sum(len(c) for c in chunks) >= len(text) - 2 * CHUNK_MAX_CHARS


def test_aggregate_chunk_scores_pondera_por_longitud():
    scores = [1.0, -1.0]
    lengths = [300, 100]
    # (1.0*300 + -1.0*100) / 400 = 0.5
    assert aggregate_chunk_scores(scores, lengths) == pytest.approx(0.5)


def test_aggregate_chunk_scores_vacio_es_neutral():
    assert aggregate_chunk_scores([], []) == pytest.approx(0.0)
    assert aggregate_chunk_scores([1.0], [0]) == pytest.approx(0.0)


def test_score_from_probs_mapea_0_1_a_menos1_mas1():
    assert score_from_probs(0.9, 0.05) == pytest.approx(0.85)
    assert score_from_probs(0.0, 1.0) == pytest.approx(-1.0)
    assert score_from_probs(0.5, 0.5) == pytest.approx(0.0)


def test_finbert_result_to_probs_parsea_labels():
    pos, neg = finbert_result_to_probs([{"label": "positive", "score": 0.93}])
    assert pos == pytest.approx(0.93)
    pos, neg = finbert_result_to_probs([{"label": "negative", "score": 0.8}])
    assert neg == pytest.approx(0.8)
    # formato genérico LABEL_0 (finbert: LABEL_0 = positive)
    pos, neg = finbert_result_to_probs([{"label": "LABEL_0", "score": 0.7}])
    assert pos == pytest.approx(0.7)


# --------------------------------------------------------------------------- #
# finbert_score con pipeline FAKE inyectado (sin transformers reales).
# --------------------------------------------------------------------------- #
def test_finbert_score_agrega_chunks_ponderados():
    # 2 chunks: el primero muy positivo, el segundo negativo; el resultado
    # debe ser el promedio ponderado por longitud, no la media simple.
    text = ("positive positive positive. " * 40) + ("negative negative. " * 5)
    result = finbert_score(text, pipeline_factory=lambda: _FakeFinbertPipe())
    assert result["n_chunks"] == 2
    assert -1.0 <= result["score"] <= 1.0
    assert result["score"] > 0.0  # el chunk largo positivo domina


def test_finbert_score_no_importa_transformers_a_nivel_modulo():
    # el módulo core se importó arriba sin transformers — verificar que el
    # atributo del pipeline solo se toca DENTRO de la función (fake acá).
    result = finbert_score("positive words here.", pipeline_factory=lambda: _FakeFinbertPipe())
    assert result["model_version"] == "ProsusAI/finbert"
    assert result["n_chunks"] == 1


# --------------------------------------------------------------------------- #
# Store SQLite — dedup por accession.
# --------------------------------------------------------------------------- #
def test_store_record_y_records_roundtrip(tmp_path):
    store = EarningsSentimentStore(str(tmp_path / "sentiment.db"))
    try:
        inserted = store.record(
            symbol="AAPL", filing_date="2026-05-01", accession="A1",
            score=0.42, n_chunks=3,
        )
        assert inserted is True
        rows = store.records()
        assert len(rows) == 1
        assert rows[0]["symbol"] == "AAPL"
        assert rows[0]["filing_date"] == "2026-05-01"
        assert rows[0]["accession"] == "A1"
        assert rows[0]["score"] == pytest.approx(0.42)
        assert rows[0]["n_chunks"] == 3
        assert rows[0]["model_version"] == "ProsusAI/finbert"
        assert rows[0]["created_at"]
        assert store.count() == 1
    finally:
        store.close()


def test_store_dedup_por_accession(tmp_path):
    store = EarningsSentimentStore(str(tmp_path / "sentiment.db"))
    try:
        assert store.record("AAPL", "2026-05-01", "A1", 0.4, 2) is True
        assert store.record("AAPL", "2026-05-01", "A1", -0.9, 2) is False
        assert store.count() == 1
        assert store.record("NVDA", "2026-05-20", "A2", 0.1, 4) is True
        assert store.count() == 2
        assert store.has_accession("A1") is True
        assert store.has_accession("ZZZ") is False
    finally:
        store.close()


def test_store_persiste_en_disco(tmp_path):
    db = str(tmp_path / "sentiment.db")
    s1 = EarningsSentimentStore(db)
    s1.record("MSFT", "2026-01-01", "A1", 0.5, 1)
    s1.close()
    s2 = EarningsSentimentStore(db)
    try:
        assert s2.count() == 1
    finally:
        s2.close()


# --------------------------------------------------------------------------- #
# Parseo de EDGAR (funciones puras).
# --------------------------------------------------------------------------- #
def test_parse_submissions_json_filtra_8k_202():
    out = parse_submissions_json(SUBMISSIONS_FIXTURE)
    assert len(out) == 3  # 8-K con 2.02 (los ítems 0, 1 y 4; el 3 es 7.01, el 2 es 10-Q)
    assert [f["accession"] for f in out] == [
        "0000320193-26-000001", "0000320193-26-000002", "0000320193-25-000005",
    ]
    assert out[0]["filing_date"] == "2026-05-01"
    assert out[0]["primary_document"] == "aapl-8k.htm"
    assert out[0]["cik"] == "0000320193"
    assert out[0]["accession_url"] == (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019326000001/"
    )
    # orden descendente preservado (el más nuevo primero)
    assert out[0]["filing_date"] > out[-1]["filing_date"]


def test_parse_submissions_json_maneja_items_con_coma_y_espacio():
    # ítem 0: "2.02,9.01" (coma); ítem 4: "2.02 9.01" (espacio) — ambos entran
    out = parse_submissions_json(SUBMISSIONS_FIXTURE)
    assert len(out) == 3


def test_parse_company_tickers_y_resolve_cik():
    payload = {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "APPLE INC"},
        "1": {"cik_str": 1067983, "ticker": "BRK.B", "title": "BERKSHIRE HATHAWAY INC"},
    }
    m = parse_company_tickers(payload)
    assert m["AAPL"] == "0000320193"
    assert resolve_cik("AAPL", m) == "0000320193"
    # BRK-B (formato yfinance del universo) → BRK.B (formato EDGAR)
    assert resolve_cik("BRK-B", m) == "0001067983"


def test_resolve_cik_ticker_desconocido_es_error_claro():
    with pytest.raises(KeyError, match="no encontrado"):
        resolve_cik("FAKETKR", {})


# --------------------------------------------------------------------------- #
# Extracción de texto.
# --------------------------------------------------------------------------- #
def test_html_to_text_limpia_y_colapsa():
    text = html_to_text(PRESS_RELEASE_HTML)
    assert "Revenue increased 25% year over year." in text
    assert "var x" not in text
    assert ".hidden" not in text
    # whitespace colapsado: sin dobles espacios ni saltos
    assert "  " not in text and "\n" not in text


def test_pick_exhibit_from_index_elige_ex991():
    index = """
    <html><body>
    <a href="/Archives/edgar/data/1045810/000104581026000024/nvda-8k.htm">8-K</a>
    <a href="/Archives/edgar/data/1045810/000104581026000024/nvda-ex991_6.htm">EX-99.1</a>
    </body></html>
    """
    url = _pick_exhibit_from_index(index)
    assert url.endswith("nvda-ex991_6.htm")
    assert url.startswith("https://www.sec.gov")
    assert _pick_exhibit_from_index("<html></html>") is None


# --------------------------------------------------------------------------- #
# Conductor de acumulación (red y FinBERT mockeados).
# --------------------------------------------------------------------------- #
def _make_filings():
    return [
        {
            "accession": "A1", "filing_date": "2026-05-01",
            "primary_document": "x.htm", "cik": "0000320193",
            "accession_url": "https://www.sec.gov/Archives/edgar/data/320193/000000000000000001/",
        },
        {
            "accession": "A2", "filing_date": "2026-02-01",
            "primary_document": "y.htm", "cik": "0000320193",
            "accession_url": "https://www.sec.gov/Archives/edgar/data/320193/000000000000000002/",
        },
    ]


def test_accumulate_end_to_end_con_fakes(tmp_path, monkeypatch):
    store = EarningsSentimentStore(str(tmp_path / "sentiment.db"))
    try:
        monkeypatch.setattr(
            "app.core.earnings_sentiment.fetch_submissions",
            lambda cik, count=8, session=None: _make_filings(),
        )
        monkeypatch.setattr(
            "app.core.earnings_sentiment.fetch_document_text",
            lambda url, session=None: "positive positive positive revenue growth",
        )
        monkeypatch.setattr(
            "app.core.earnings_sentiment.finbert_score",
            lambda text, pipeline_factory=None: {"score": 0.75, "n_chunks": 1, "model_version": "fake"},
        )
        summary = accumulate_earnings_sentiment(
            ["AAPL", "NVDA"],
            store,
            ticker_map={"AAPL": "0000320193", "NVDA": "0001045810"},
            log=lambda m: None,
        )
        assert summary["processed"] == ["AAPL", "NVDA"]
        assert summary["new_filings"] == 4
        assert summary["errors"] == {}
        assert store.count() == 4
    finally:
        store.close()


def test_accumulate_es_incremental_por_accession(tmp_path, monkeypatch):
    store = EarningsSentimentStore(str(tmp_path / "sentiment.db"))
    try:
        store.record("AAPL", "2026-05-01", "A1", 0.5, 1)  # ya procesada
        monkeypatch.setattr(
            "app.core.earnings_sentiment.fetch_submissions",
            lambda cik, count=8, session=None: _make_filings(),
        )
        monkeypatch.setattr(
            "app.core.earnings_sentiment.fetch_document_text",
            lambda url, session=None: "positive words",
        )
        monkeypatch.setattr(
            "app.core.earnings_sentiment.finbert_score",
            lambda text, pipeline_factory=None: {"score": 0.5, "n_chunks": 1, "model_version": "fake"},
        )
        summary = accumulate_earnings_sentiment(
            ["AAPL"], store, ticker_map={"AAPL": "0000320193"}, log=lambda m: None,
        )
        assert summary["new_filings"] == 1  # solo A2 es nueva
        assert store.count() == 2
    finally:
        store.close()


def test_accumulate_excluye_etfs_explicitamente(tmp_path, monkeypatch):
    store = EarningsSentimentStore(str(tmp_path / "sentiment.db"))
    try:
        assert {"SPY", "QQQ"}.issubset(ETF_EXCLUSIONS)
        monkeypatch.setattr(
            "app.core.earnings_sentiment.fetch_submissions",
            lambda cik, count=8, session=None: (_ for _ in ()).throw(AssertionError("no debe llamarse")),
        )
        summary = accumulate_earnings_sentiment(
            ["SPY", "QQQ", "AAPL"], store, ticker_map={"AAPL": "0000320193"},
            log=lambda m: None,
        )
        assert summary["etf_excluded"] == ["SPY", "QQQ"]
        assert summary["errors"] == {}
        assert store.count() == 0
    finally:
        store.close()


def test_accumulate_no_aborta_por_error_de_un_simbolo(tmp_path, monkeypatch):
    store = EarningsSentimentStore(str(tmp_path / "sentiment.db"))
    try:
        def boom(cik, count=8, session=None):
            raise RuntimeError("EDGAR 403")

        monkeypatch.setattr("app.core.earnings_sentiment.fetch_submissions", boom)
        monkeypatch.setattr(
            "app.core.earnings_sentiment.fetch_document_text",
            lambda url, session=None: "positive words",
        )
        monkeypatch.setattr(
            "app.core.earnings_sentiment.finbert_score",
            lambda text, pipeline_factory=None: {"score": 0.1, "n_chunks": 1, "model_version": "fake"},
        )
        summary = accumulate_earnings_sentiment(
            ["AAPL", "MSFT"], store, ticker_map={"AAPL": "0000320193", "MSFT": "0000789019"},
            log=lambda m: None,
        )
        assert set(summary["errors"]) == {"AAPL", "MSFT"}
        assert summary["processed"] == []
        assert store.count() == 0
    finally:
        store.close()
