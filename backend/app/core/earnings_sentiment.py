"""Pipeline de sentimiento de earnings calls — Tarea B del plan de largo plazo (PASO 1).

FUENTE: SEC EDGAR, formulario 8-K item 2.02 (comunicado de prensa oficial de la
gerencia, publicado en el momento del earnings call, point-in-time). Es la mejor
fuente pública y gratuita disponible; se descartó Seeking Alpha por sus ToS
restrictivos y paywall (regla del proyecto tras el incidente medallion-pub: no
scrapear fuentes dudosas).

LIMITACIÓN DOCUMENTADA (afecta el trial del PASO 2): el 8-K item 2.02 contiene el
COMUNICADO DE PRENSA de la gerencia, no la transcripción verbatim del earnings
call. El tono del comunicado es una proxy razonable pero no idéntica del tono del
call (los comunicados se editan; las preguntas y respuestas del call no aparecen).
Esta limitación se registra acá porque es la base de interpretación del trial
futuro: si el factor sale nulo, puede ser por esta proxy y no por ausencia de
señal — y viceversa.

MODELO: FinBERT (ProsusAI/finbert, HuggingFace). Clasifica el texto en
positive/negative/neutral. El puntaje bruto por label es una probabilidad 0-1;
este módulo lo mapea a [-1, +1] como score = prob_pos - prob_neg (el neutral
queda implícito en el centro). El pipeline de transformers se importa LAZY
(dentro de la función que lo usa): CI y la suite pytest no tienen transformers
instalados y no deben romperse por este módulo; en tests se inyecta un fake.

AGREGACIÓN (metodología documentada, base del trial futuro): el comunicado
excede los 512 tokens del contexto de BERT. Se chunquea por oraciones con
longitud objetivo ~1800 chars (~380 tokens) y el score final es el promedio
ponderado por longitud de chunk: score = sum(score_i * len_i) / sum(len_i).
La ponderación por longitud le da más peso a las secciones de texto que
aportan más evidencia al modelo.

REGLAS NO NEGOCIABLES:
  - EDGAR exige User-Agent declarado (Nombre + email); sin él rechaza (403).
  - Rate limit: máx 10 req/s; este módulo duerme 0.2s entre peticiones.
  - Backfill: acumula los últimos ~8 8-Ks con item 2.02 por símbolo (≈8
    trimestres, datos REALES point-in-time) y luego es incremental: las
    accession ya guardadas no se re-procesan (UNIQUE en la store).
"""
import json
import os
import re
import sqlite3
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------- #
# Constantes.
# --------------------------------------------------------------------------- #
MODEL_NAME = "ProsusAI/finbert"
# EDGAR rechaza (403) los User-Agent con dominio de email inválido (ej.
# @localhost): el WAF exige un contacto con dominio real. Este es un contacto
# genérico de investigación; reemplazarlo por un email controlado vía
# FORTRESS_EDGAR_USER_AGENT si se va a usar en producción.
EDGAR_USER_AGENT = os.environ.get(
    "FORTRESS_EDGAR_USER_AGENT", "fortress-core-research fortressresearch.contact@gmail.com"
)
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{0:010d}.json"
ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

DEFAULT_DB_PATH = "./data/cache/earnings_sentiment.db"
DEFAULT_TICKERS_CACHE = "./data/cache/company_tickers.json"

REQUEST_TIMEOUT = 20.0
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 0.5
RATE_LIMIT_SLEEP_SECONDS = 0.2  # 5 req/s máx — muy por debajo del límite de EDGAR

# Longitud objetivo de chunk (~380 tokens para BERT de 512). Hard cap de
# seguridad: una oración más larga que esto se corta y se trunca en el pipeline.
CHUNK_TARGET_CHARS = 1800
CHUNK_MAX_CHARS = 2500

# Un 8-K cuyo texto extraído quede por debajo de este umbral es "solo
# referencia" (apunta al press release en un exhibit) — se busca el texto real.
MIN_SUBSTANTIVE_CHARS = 400
# Si el primary document MENCIONA el press release como exhibit adjunto
# ("Exhibit 99.1", "ex-99.1"), el comunicado real vive en ese exhibit y el
# primary es solo la referencia administrativa (caso típico de AAPL/NVDA/AMD).
_EXHIBIT_REFERENCE_RE = re.compile(r"(?:ex-?99|exhibit\s*99)", re.IGNORECASE)

# ETFs / vehículos sin earnings calls: se excluyen explícitamente del universo
# (SPY/QQQ/IBB/…). Un 8-K 2.02 de un ETF no es un earnings call.
ETF_EXCLUSIONS = frozenset({"SPY", "QQQ", "IBB", "DIA", "IWM", "EFA", "AGG", "GLD"})

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_WS_RE = re.compile(r"\s+")
_ITEM_SPLIT_RE = re.compile(r"[\s,]+")  # items de EDGAR vienen "2.02,9.01" o "2.02 9.01"


# --------------------------------------------------------------------------- #
# Utilidades puras (testeables sin red).
# --------------------------------------------------------------------------- #
def normalize_text(text: str) -> str:
    """Colapsa whitespace (saltos de línea, tabs, espacios múltiples) en un
    solo espacio y recorta los extremos — el texto plano de salida de
    BeautifulSoup.get_text() viene con ruido de maquetación HTML."""
    return _WS_RE.sub(" ", text).strip()


def html_to_text(html: str) -> str:
    """HTML crudo de un documento EDGAR → texto plano normalizado.

    Función pura para poder testearla sin red. Elimina scripts/estilos (los
    ítems de EDGAR los traen) y devuelve el texto visible colapsado.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return normalize_text(soup.get_text(separator=" "))


def chunk_text(text: str, target_chars: int = CHUNK_TARGET_CHARS) -> List[str]:
    """Divide texto largo en chunks por oraciones con longitud objetivo.

    Agrupa oraciones hasta alcanzar `target_chars`; una oración que sola
    excede `CHUNK_MAX_CHARS` se corta en trozos duros (el pipeline trunca de
    todos modos a 512 tokens como red de seguridad).

    Edge case conocido: la segmentación por `.` rompe abreviaturas del inglés
    financiero ("U.S.", "Mr.", "e.g."). Para un comunicado de prensa es una
    imperfección aceptable (solo afecta los límites de chunk, no el texto).
    """
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0
    for sent in sentences:
        if current and current_len + len(sent) > target_chars:
            chunks.append(" ".join(current))
            current, current_len = [], 0
        if len(sent) > CHUNK_MAX_CHARS:
            if current:
                chunks.append(" ".join(current))
                current, current_len = [], 0
            for i in range(0, len(sent), CHUNK_MAX_CHARS):
                chunks.append(sent[i : i + CHUNK_MAX_CHARS])
            continue
        current.append(sent)
        current_len += len(sent) + 1
    if current:
        chunks.append(" ".join(current))
    return chunks or [""]


def finbert_result_to_probs(output: List[Dict[str, Any]]) -> Tuple[float, float]:
    """Output del pipeline de FinBERT → (prob_pos, prob_neg).

    ProsusAI/finbert tiene 3 labels (positive/negative/neutral). El pipeline
    devuelve [{"label": "positive", "score": 0.93}, ...]; por compatibilidad
    también se acepta el formato genérico LABEL_0/LABEL_1 (finbert mapea
    LABEL_0 = positive, LABEL_1 = negative en su config).
    """
    probs = {d.get("label"): float(d.get("score", 0.0)) for d in output}
    pos = probs.get("positive", 0.0)
    neg = probs.get("negative", 0.0)
    if "positive" not in probs and "negative" not in probs:
        pos = probs.get("LABEL_0", 0.0)
        neg = probs.get("LABEL_1", 0.0)
    return pos, neg


def score_from_probs(prob_pos: float, prob_neg: float) -> float:
    """Mapea las probabilidades 0-1 de FinBERT al rango [-1, +1]:
    score = prob_pos - prob_neg. El neutral (y el texto vacío) queda en ~0."""
    return float(prob_pos - prob_neg)


def aggregate_chunk_scores(scores: List[float], lengths: List[int]) -> float:
    """Promedio ponderado por longitud de chunk — metodología del módulo.

    score_final = sum(score_i * len_i) / sum(len_i). Si no hay chunks (o la
    suma de longitudes es 0) devuelve 0.0 (neutral).
    """
    total_len = sum(lengths)
    if total_len <= 0:
        return 0.0
    return float(sum(s * length for s, length in zip(scores, lengths)) / total_len)


def parse_submissions_json(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parseo PURO del JSON de data.sec.gov/submissions/CIK*.json.

    Filtra únicamente filings form="8-K" con "2.02" en items (los que
    contienen el comunicado de prensa de resultados) y devuelve una lista de
    dicts: {accession, filing_date, primary_document, cik, accession_url}.
    El orden de `recent` (descendente por fecha) se preserva: los primeros
    ítems son los más nuevos.
    """
    cik = str(payload.get("cik", ""))
    filings = payload.get("filings", {}).get("recent", {})
    forms = filings.get("form", [])
    out: List[Dict[str, Any]] = []
    for i, form in enumerate(forms):
        if form != "8-K":
            continue
        items = filings.get("items", [])
        if i >= len(items) or "2.02" not in _ITEM_SPLIT_RE.split(items[i] or ""):
            continue
        accession = filings.get("accessionNumber", [])[i]
        out.append(
            {
                "accession": accession,
                "filing_date": filings.get("filingDate", [])[i],
                "primary_document": filings.get("primaryDocument", [])[i],
                "cik": cik,
                "accession_url": accession_url(cik, accession),
            }
        )
    return out


def accession_url(cik: str, accession: str) -> str:
    """URL del directorio de la accession en el archivo EDGAR (sin guiones)."""
    cik_clean = cik.lstrip("0") if cik.isdigit() else cik
    acc_clean = accession.replace("-", "")
    return f"{ARCHIVES_BASE}/{cik_clean}/{acc_clean}/"


def parse_company_tickers(payload: Dict[str, Any]) -> Dict[str, str]:
    """Parseo PURO del JSON de company_tickers.json de SEC.

    {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "APPLE INC"}, ...}
    → {"AAPL": "0000320193"} (CIK con padding a 10 dígitos, formato EDGAR).
    """
    out: Dict[str, str] = {}
    for entry in payload.values():
        if not isinstance(entry, dict):
            continue
        ticker = (entry.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        out[ticker] = f"{int(entry['cik_str']):010d}"
    return out


def resolve_cik(ticker: str, ticker_map: Dict[str, str]) -> str:
    """Ticker → CIK de 10 dígitos. Maneja el formato de EDGAR con punto
    (BRK-B del universo → "BRK.B" en company_tickers.json). Levanta KeyError
    con mensaje claro si el ticker no está en el mapa."""
    ticker = ticker.strip().upper()
    if ticker in ticker_map:
        return ticker_map[ticker]
    dotted = ticker.replace("-", ".")
    if dotted in ticker_map:
        return ticker_map[dotted]
    raise KeyError(
        f"Ticker {ticker!r} no encontrado en company_tickers.json (ni como {dotted!r})"
    )


# --------------------------------------------------------------------------- #
# Persistencia SQLite (mismo patrón que execution_costs.py: sqlite3 directo,
# conn persistente con close()).
# --------------------------------------------------------------------------- #
_SCHEMA_SENTIMENT = """
CREATE TABLE IF NOT EXISTS sentiment (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol        TEXT    NOT NULL,
    filing_date   TEXT    NOT NULL,
    accession     TEXT    NOT NULL UNIQUE,
    score         REAL    NOT NULL,
    n_chunks      INTEGER NOT NULL,
    model_version TEXT    NOT NULL,
    created_at    TEXT    NOT NULL
);
"""


class EarningsSentimentStore:
    """Persistencia SQLite de los scores de sentimiento por earnings call.

    Dedup por accession (UNIQUE): un 8-K ya procesado nunca se re-procesa,
    eso hace que la acumulación sea incremental de forma natural.
    """

    def __init__(self, db_path: str = "") -> None:
        if not db_path:
            db_path = os.environ.get("FORTRESS_SENTIMENT_DB", DEFAULT_DB_PATH)
        self.db_path = db_path
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(_SCHEMA_SENTIMENT)
        self._conn.commit()

    def record(
        self,
        symbol: str,
        filing_date: str,
        accession: str,
        score: float,
        n_chunks: int,
        model_version: str = MODEL_NAME,
        created_at: Optional[str] = None,
    ) -> bool:
        """Persiste un score. Devuelve True si se insertó, False si la
        accession ya existía (dedup silencioso, acumulación incremental)."""
        if created_at is None:
            created_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO sentiment "
            "(symbol, filing_date, accession, score, n_chunks, model_version, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (symbol, filing_date, accession, float(score), int(n_chunks),
             model_version, created_at),
        )
        self._conn.commit()
        return cur.rowcount == 1

    def has_accession(self, accession: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM sentiment WHERE accession = ?", (accession,)
        ).fetchone()
        return row is not None

    def records(self) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT symbol, filing_date, accession, score, n_chunks, model_version, "
            "created_at FROM sentiment ORDER BY filing_date, symbol"
        ).fetchall()
        return [
            {
                "symbol": r[0],
                "filing_date": r[1],
                "accession": r[2],
                "score": r[3],
                "n_chunks": r[4],
                "model_version": r[5],
                "created_at": r[6],
            }
            for r in rows
        ]

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM sentiment").fetchone()[0])

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()


# --------------------------------------------------------------------------- #
# Capa de red (EDGAR) — con retry simple y rate limiting.
# --------------------------------------------------------------------------- #
def _edgar_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {"User-Agent": EDGAR_USER_AGENT, "Accept-Encoding": "gzip, deflate"}
    )
    return s


def _get_with_retry(
    url: str, session: requests.Session, sleep: float = RATE_LIMIT_SLEEP_SECONDS
) -> requests.Response:
    """GET con timeout y reintentos (backoff corto), respetando el rate limit."""
    last_exc: Optional[Exception] = None
    for attempt in range(MAX_RETRIES + 1):
        time.sleep(sleep)
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp
        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
    raise RuntimeError(f"Fallo EDGAR tras {MAX_RETRIES + 1} intentos para {url}: {last_exc}")


def fetch_submissions(cik: str, count: int = 8, session: Optional[requests.Session] = None) -> List[Dict[str, Any]]:
    """Lista los últimos `count` 8-Ks con item 2.02 del CIK (los más recientes
    primero). `cik` debe ser el de 10 dígitos (formato EDGAR)."""
    own_session = session is None
    sess = session if session is not None else _edgar_session()
    try:
        url = SUBMISSIONS_URL.format(int(cik))
        payload = _get_with_retry(url, sess).json()
        filings = parse_submissions_json(payload)
        return filings[:count]
    finally:
        if own_session and session is None:
            sess.close()


def _index_document_url(filing: Dict[str, Any]) -> str:
    """URL del archivo .htm del comunicado dentro de la accession.

    Usa primary_document si existe; si no, devuelve la URL del índice de la
    accession (index.json, que lista los archivos del directorio).
    """
    primary = filing.get("primary_document") or ""
    if primary:
        return filing["accession_url"] + primary
    return filing["accession_url"] + "index.json"


def _pick_exhibit_from_index(index_html: str) -> Optional[str]:
    """Del índice HTML de una accession, elige el .htm que parece el press
    release (ex-99.x). Función pura, testable. Devuelve la URL completa (el
    href del índice puede ser relativo o absoluto). None si no hay."""
    soup = BeautifulSoup(index_html, "html.parser")
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if not href.lower().endswith(".htm"):
            continue
        name = href.split("/")[-1].lower()
        if "ex-99" in name or "ex99" in name:
            if href.startswith("http"):
                return href
            if href.startswith("/"):
                return "https://www.sec.gov" + href
            return href
    return None


def fetch_document_text(
    url: str,
    session: Optional[requests.Session] = None,
    _fallback_index: bool = True,
) -> str:
    """Descarga el texto plano del documento (el comunicado de la gerencia).

    Estrategia en dos pasos, documentada porque define la calidad de los datos
    (y por lo tanto del trial futuro):
      1. Descarga el primary document. Si este es "solo referencia" (menciona
         que el press release se adjunta como Exhibit 99.x — caso típico de
         los 8-K de resultados de las grandes tecnológicas) o queda por debajo
         de MIN_SUBSTANTIVE_CHARS, busca en el índice de la accession el .htm
         del exhibit 99.x y usa ESE texto (el comunicado real).
      2. Si no hay exhibit, usa el primary document tal cual (algunos 8-Ks
         llevan el comunicado completo en el cuerpo).
    """
    own_session = session is None
    sess = session if session is not None else _edgar_session()
    try:
        primary_html = _get_with_retry(url, sess).text
        text = html_to_text(primary_html)
        if _fallback_index and (
            len(text) < MIN_SUBSTANTIVE_CHARS or _EXHIBIT_REFERENCE_RE.search(text)
        ):
            index_url = url.rsplit("/", 1)[0] + "/index.html"
            index_html = _get_with_retry(index_url, sess).text
            exhibit = _pick_exhibit_from_index(index_html)
            if exhibit:
                full_url = exhibit if exhibit.startswith("http") else url.rsplit("/", 1)[0] + "/" + exhibit.split("/")[-1]
                exhibit_text = html_to_text(_get_with_retry(full_url, sess).text)
                if len(exhibit_text) >= MIN_SUBSTANTIVE_CHARS:
                    return exhibit_text
        return text
    finally:
        if own_session and session is None:
            sess.close()


def load_ticker_cik_map(cache_path: str = "", session: Optional[requests.Session] = None) -> Dict[str, str]:
    """Mapa ticker→CIK de todo el mercado (company_tickers.json de SEC).

    Se descarga una sola vez y se reutiliza el cache local; si la descarga
    falla y no hay cache, se reporta el error claro (sin fallback hardcodeado).
    """
    path = cache_path or DEFAULT_TICKERS_CACHE
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return parse_company_tickers(json.load(fh))
    own_session = session is None
    sess = session if session is not None else _edgar_session()
    try:
        payload = _get_with_retry(COMPANY_TICKERS_URL, sess).json()
    finally:
        if own_session and session is None:
            sess.close()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    return parse_company_tickers(payload)


# --------------------------------------------------------------------------- #
# FinBERT (import LAZY de transformers).
# --------------------------------------------------------------------------- #
def _default_pipeline_factory() -> Any:
    from transformers import pipeline  # import lazy: CI/tests no tienen transformers

    return pipeline("sentiment-analysis", model=MODEL_NAME)


def finbert_score(
    text: str, pipeline_factory: Optional[Callable[[], Any]] = None
) -> Dict[str, Any]:
    """Score de sentimiento FinBERT sobre el texto del comunicado.

    Devuelve {"score" ([-1,1]), "n_chunks", "model_version"}. Chunquea el
    texto, corre el pipeline por chunk y agrega con promedio ponderado por
    longitud (metodología en el docstring del módulo). `pipeline_factory` se
    inyecta en tests para no cargar transformers.
    """
    factory = pipeline_factory if pipeline_factory is not None else _default_pipeline_factory
    pipe = factory()
    chunks = chunk_text(text)
    outputs = pipe(chunks, truncation=True)
    scores = []
    lengths = []
    for chunk, output in zip(chunks, outputs):
        prob_pos, prob_neg = finbert_result_to_probs([output])
        scores.append(score_from_probs(prob_pos, prob_neg))
        lengths.append(len(chunk))
    return {
        "score": aggregate_chunk_scores(scores, lengths),
        "n_chunks": len(chunks),
        "model_version": MODEL_NAME,
    }


# --------------------------------------------------------------------------- #
# Conductor de acumulación.
# --------------------------------------------------------------------------- #
def accumulate_earnings_sentiment(
    symbols: List[str],
    store: EarningsSentimentStore,
    ticker_map: Optional[Dict[str, str]] = None,
    session: Optional[requests.Session] = None,
    pipeline_factory: Optional[Callable[[], Any]] = None,
    count: int = 8,
    log: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Acumula sentimiento de earnings calls para el universo de símbolos.

    Por símbolo: CIK → últimas 8-Ks con item 2.02 → descarga las accession no
    procesadas → score FinBERT → persistencia. Errores por símbolo se
    capturan y reportan sin abortar el resto. Los ETFs (sin earnings calls)
    se excluyen explícitamente. Devuelve un resumen para el script CLI.
    """
    if log is None:
        log = lambda msg: print(msg, flush=True)  # noqa: E731
    if ticker_map is None:
        ticker_map = load_ticker_cik_map(session=session)

    summary: Dict[str, Any] = {
        "symbols": len([s for s in symbols if s not in ETF_EXCLUSIONS]),
        "etf_excluded": [s for s in symbols if s in ETF_EXCLUSIONS],
        "processed": [],
        "new_filings": 0,
        "errors": {},
        "total_in_store": store.count(),
    }

    for symbol in symbols:
        if symbol in ETF_EXCLUSIONS:
            log(f"[ETF] {symbol}: excluido (sin earnings calls)")
            continue
        try:
            cik = resolve_cik(symbol, ticker_map)
            filings = fetch_submissions(cik, count=count, session=session)
            new_for_symbol = 0
            for filing in filings:
                if store.has_accession(filing["accession"]):
                    continue
                url = _index_document_url(filing)
                text = fetch_document_text(url, session=session)
                result = finbert_score(text, pipeline_factory=pipeline_factory)
                inserted = store.record(
                    symbol=symbol,
                    filing_date=filing["filing_date"],
                    accession=filing["accession"],
                    score=result["score"],
                    n_chunks=result["n_chunks"],
                    model_version=result["model_version"],
                )
                new_for_symbol += int(inserted)
                log(
                    f"[{symbol}] {filing['filing_date']} accession={filing['accession']} "
                    f"score={result['score']:+.3f} chunks={result['n_chunks']}"
                )
                time.sleep(RATE_LIMIT_SLEEP_SECONDS)
            summary["processed"].append(symbol)
            summary["new_filings"] += new_for_symbol
            log(f"[{symbol}] OK — {new_for_symbol} 8-K(s) nuevo(s), {len(filings)} listados")
        except Exception as exc:  # noqa: BLE001 — error de símbolo, no abortar el resto
            summary["errors"][symbol] = str(exc)
            log(f"[{symbol}] ERROR: {exc}", )
    summary["total_in_store"] = store.count()
    return summary
