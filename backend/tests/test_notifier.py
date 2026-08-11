"""Tests del notificador diario (Pieza 4): dedup de 7 días, formato del
mensaje y canales sin credenciales (degradación silenciosa)."""
import datetime
import json
import os

import pytest

from app.core import notifier
from app.core.notifier import (
    build_message, is_new_opportunity, send_daily_notification,
)


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(notifier, "NOTIFIED_PATH", str(tmp_path / "notified.json"))
    monkeypatch.setattr(notifier.settings, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(notifier.settings, "TELEGRAM_CHAT_ID", "")
    monkeypatch.setattr(notifier.settings, "SMTP_HOST", "")
    yield


def _body(opps=None, as_of="2026-08-11"):
    return {
        "as_of": as_of,
        "regime": {"state": 2, "name": "STAGFLATION", "confidence": 0.99},
        "blocked_reason": None,
        "opportunities": opps or [],
        "concentration": {"alerts": [], "n_pairs_analyzed": 0},
        "track_record": {"n": 0, "sufficient": False},
    }


def _opp(symbol="SPY"):
    return {
        "symbol": symbol,
        "score": 0.62,
        "win_prob": 0.55,
        "gates": {"trend_ok": True, "adx": 25.3, "rsi": 58.1, "volume_ratio": 1.3},
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "take_profit": 110.0,
        "payoff_ratio": 2.0,
        "atr": 2.5,
        "g2_score": None,
        "exit_plan": {
            "partial_tp": {"trigger": "precio >= entrada + 2*ATR", "action": "vender 50%"},
            "trailing_stop": {"trigger": "max > entrada + 1.5*ATR", "action": "cerrar"},
            "technical": {"trigger": "ADX < 20", "action": "cerrar"},
            "regime_stop": {"trigger": "perdida <= -7%", "action": "cerrar"},
        },
    }


def test_is_new_opportunity_dedup_7_days():
    today = datetime.date(2026, 8, 11)
    assert is_new_opportunity("SPY", today, {}) is True, "nunca avisado -> nuevo"
    assert is_new_opportunity("SPY", today, {"SPY": "2026-08-04"}) is True, "7 dias atras -> nuevo"
    assert is_new_opportunity("SPY", today, {"SPY": "2026-08-05"}) is False, "6 dias -> dedup"
    assert is_new_opportunity("SPY", today, {"SPY": "2026-08-11"}) is False, "hoy -> dedup"
    assert is_new_opportunity("SPY", today, {"SPY": "fecha-rota"}) is True, "corrupto -> tratar como nuevo"


def test_build_message_sober_and_complete():
    msg = build_message(_body([_opp()]))
    assert "Fortress Core - Oportunidades 2026-08-11" in msg
    assert "STAGFLATION" in msg
    assert "score 0.6200" in msg
    assert "win 55.0%" in msg
    assert "Entrada 100.00 / Stop 95.00 / TP 110.00" in msg
    assert "ADX 25.3 | RSI 58.1 | Vol 1.30" in msg
    assert "precio >= entrada + 2*ATR" in msg
    assert "perdida <= -7%" in msg
    assert "Historial real: 0 evaluadas (insuficiente" in msg
    assert "no es una orden de compra" in msg
    assert "COMPRAR" not in msg, "sin lenguaje de certeza"


def test_build_message_blocked_reason_explains_empty():
    body = _body()
    body["blocked_reason"] = "Regimen DEFLATION (estado 3): el motor bloquea entradas nuevas por diseño"
    msg = build_message(body)
    assert "Sin sugerencias" in msg


def test_send_daily_notification_no_channels_degrades_gracefully(monkeypatch, tmp_path):
    monkeypatch.setattr(notifier, "send_telegram", lambda text: False)
    monkeypatch.setattr(notifier, "send_email", lambda subject, text: False)

    results = send_daily_notification(_body([_opp("SPY"), _opp("QQQ")]))

    assert results == []
    notified_path = notifier.NOTIFIED_PATH
    assert os.path.exists(notified_path), "aunque no haya canales, el dedup se registra"
    with open(notified_path) as f:
        notified = json.load(f)
    assert notified == {"SPY": "2026-08-11", "QQQ": "2026-08-11"}


def test_send_daily_notification_dedup_persisted(monkeypatch, tmp_path):
    monkeypatch.setattr(notifier, "send_telegram", lambda text: True)
    monkeypatch.setattr(notifier, "send_email", lambda subject, text: False)

    first = send_daily_notification(_body([_opp("SPY")], as_of="2026-08-11"))
    assert first == [{"channel": "telegram", "sent": True}]

    # Día siguiente, mismo símbolo: gate pasa pero dedup lo filtra -> sin aviso
    second = send_daily_notification(_body([_opp("SPY")], as_of="2026-08-12"))
    assert second == [{"channel": "telegram", "sent": True}], "mensaje sin oportunidades se envia igual"
    # Y el dedup NO se machaca: sigue registrado el 11
    with open(notifier.NOTIFIED_PATH) as f:
        assert json.load(f) == {"SPY": "2026-08-11"}
