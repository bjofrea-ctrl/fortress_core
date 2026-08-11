"""Notificador diario de oportunidades (Pieza 4 del proyecto de sugerencias).

Cadencia: 16:30 ET vía launchd (com.fortresscore.daily_notify.plist).

Criterio "oportunidad nueva" (pre-registrado, PLAN_SENTIMIENTO.md §10):
- El símbolo pasó el gate completo + score >= 0.6 HOY (lo que el endpoint
  /api/opportunities/today ya filtra).
- Y NO fue avisado en los últimos 7 días naturales (dedup anti-spam).

Canales (cada uno opcional, según .env):
- Telegram: TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID (BotFather).
- Email: SMTP_HOST/PORT/USER/PASSWORD/FROM/TO (fallback cuando Telegram no).

Sin credenciales configuradas, el notifier escribe el mensaje al log y sale
con éxito — un canal desactivado nunca rompe el pipeline.

Uso manual:  python -m app.core.notifier
"""
import datetime
import json
import os
import smtplib
import sys
from email.mime.text import MIMEText
from typing import Dict, List

import requests

from app.config import settings

NOTIFIED_PATH = os.path.join("data", "cache", "notified.json")
DEDUP_DAYS = 7


def _load_notified() -> Dict[str, str]:
    if not os.path.exists(NOTIFIED_PATH):
        return {}
    try:
        with open(NOTIFIED_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_notified(notified: Dict[str, str]) -> None:
    os.makedirs(os.path.dirname(NOTIFIED_PATH), exist_ok=True)
    with open(NOTIFIED_PATH, "w") as f:
        json.dump(notified, f, indent=2, sort_keys=True)


def is_new_opportunity(symbol: str, today: datetime.date, notified: Dict[str, str]) -> bool:
    """No se avisó en los últimos DEDUP_DAYS días naturales (el gate+score
    ya lo filtra el endpoint)."""
    last = notified.get(symbol)
    if last is None:
        return True
    try:
        last_date = datetime.date.fromisoformat(last)
    except ValueError:
        return True
    return (today - last_date).days >= DEDUP_DAYS


def build_message(body: Dict) -> str:
    """Texto plano sobrio: números crudos, plan de salida, sin semáforos
    ni lenguaje de certeza."""
    regime = body["regime"]
    lines = [
        f"Fortress Core - Oportunidades {body['as_of']}",
        f"Regimen: {regime['name']} (estado {regime['state']}, conf {regime['confidence']:.0%})",
        "",
    ]

    if body.get("blocked_reason"):
        lines += [
            "Sin sugerencias: " + body["blocked_reason"].split("—")[0].strip(),
            "",
        ]

    conc = body.get("concentration", {})
    alerts = conc.get("alerts", [])
    if alerts:
        pairs = ", ".join(a["pair"] for a in alerts)
        lines += [f"ALERTA concentracion: {len(alerts)} par(es) de cola ALTA ({pairs})", ""]

    opps = body.get("opportunities", [])
    if not opps and not body.get("blocked_reason"):
        lines += ["Ningun activo paso el gate completo hoy.", ""]

    for o in opps:
        lines += [
            f"{o['symbol']} - score {o['score']:.4f} | win {o['win_prob']:.1%}" if o["win_prob"] is not None
            else f"{o['symbol']} - score {o['score']:.4f} | win n/d",
            f"  Entrada {o['entry_price']:.2f} / Stop {o['stop_loss']:.2f} / TP {o['take_profit']:.2f}",
            f"  ADX {o['gates']['adx']:.1f} | RSI {o['gates']['rsi']:.1f} | Vol {o['gates']['volume_ratio']:.2f}",
            f"  Salidas: {o['exit_plan']['partial_tp']['trigger']}; "
            f"{o['exit_plan']['trailing_stop']['trigger']}; "
            f"{o['exit_plan']['technical']['trigger']}; {o['exit_plan']['regime_stop']['trigger']}",
            "",
        ]

    tr = body.get("track_record", {})
    if tr:
        if tr.get("sufficient"):
            lines.append(f"Historial real: {tr['n']} evaluadas, win {tr['win_rate']:.1%}, Brier {tr['brier']:.3f}")
        else:
            lines.append(f"Historial real: {tr['n']} evaluadas (insuficiente, n>=5)")

    lines.append("")
    lines.append("Sugerencia informativa - no es una orden de compra.")
    return "\n".join(lines)


def send_telegram(text: str) -> bool:
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={"chat_id": settings.TELEGRAM_CHAT_ID, "text": text}, timeout=15)
    return resp.ok


def send_email(subject: str, text: str) -> bool:
    if not (settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD):
        return False
    msg = MIMEText(text, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = settings.SMTP_TO
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)
    return True


def send_daily_notification(body: Dict) -> List[Dict]:
    """Filtra por dedup, registra lo avisado y despacha a los canales activos."""
    today = datetime.date.fromisoformat(body["as_of"])
    notified = _load_notified()

    new_opps = [o for o in body.get("opportunities", []) if is_new_opportunity(o["symbol"], today, notified)]

    report_body = dict(body)
    report_body["opportunities"] = new_opps
    message = build_message(report_body)

    results = []
    if send_telegram(message):
        results.append({"channel": "telegram", "sent": True})
    elif settings.TELEGRAM_BOT_TOKEN or settings.TELEGRAM_CHAT_ID:
        results.append({"channel": "telegram", "sent": False, "reason": "config parcial"})

    if send_email(f"Fortress Core - Oportunidades {body['as_of']}", message):
        results.append({"channel": "email", "sent": True})

    for o in new_opps:
        notified[o["symbol"]] = today.isoformat()
    _save_notified(notified)

    return results


def main() -> int:
    import asyncio

    from app.api.routes.opportunities import opportunities_today

    body = asyncio.run(opportunities_today())
    results = send_daily_notification(body)

    channels = ", ".join(f"{r['channel']}={r['sent']}" for r in results) or "ningun canal configurado"
    print(f"[notifier] {body['as_of']}: {len(body['opportunities'])} candidatos, avisos por {channels}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
