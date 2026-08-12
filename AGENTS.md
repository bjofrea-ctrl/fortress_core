# AGENTS.md — Fortress Core

Punto de entrada automático para agentes de IA. Este archivo es solo la guía de arranque —
**leé `ONBOARDING.md` completo antes de tocar cualquier cosa**, es el documento fuente.

## Antes de empezar

1. Leé `ONBOARDING.md` (raíz) → después `ROADMAP.md` (pendientes con estado).
2. Si tocás investigación/motor: chequéa primero `PLAN_MEJORA_MATEMATICA.md` y
   `RESUMEN_VALIDACION_VARIABLES.md` — muchas ideas "nuevas" ya se probaron y refutaron.
3. Si tocás código/API/frontend: revisá el hallazgo en `AUDITORIA_TECNICA.md` antes de arreglar a ciegas.

## Reglas no negociables (detalle y porqué en ONBOARDING.md)

1. **Verificá TODO contra el artefacto real** — archivo, test, commit. Nunca confíes en resúmenes
   (propios ni ajenos) sin abrir la fuente.
2. **Ningún trial sin criterio pre-registrado** (umbral, corrección, criterio de éxito escritos
   ANTES de correr). Si no cumple: revertir automáticamente.
3. **Nada de credenciales en el chat** — si un secreto aparece en la conversación, se asume
   comprometido → pedí rotación. No lo repitas ni lo guardes en archivos trackeados.
4. **Actualizá `ROADMAP.md` cuando algo se cierra o aparece** — lo que no está en la tabla, para
   el próximo agente no existe.
5. **Repo público en GitHub** (`bjofrea-ctrl/fortress_core`) — sin secretos, sin datos personales,
   sin nada que no quieras público en commits.

## Ritual de cierre de sesión

Al terminar: estado (`ROADMAP.md` + `SESSION_LOG.md`) → commit descriptivo → `git push origin main`
→ espejo en `/Volumes/EMPRESA/fortress_core_backups/current/` (rsync, ver ONBOARDING.md) →
memoria del agente (Engram, proyecto **"boris"**). No cerrar sesión sin este rastro.

## Contexto operativo

- Repo real: `~/Desktop/fortress_core`. Cuidado: puede abrirse desde otra ruta — verificar siempre.
- Backend: `backend/.venv` (Python 3.9.6 real; el `Dockerfile` dice 3.11 — inconsistencia conocida).
- Bóveda de claves: `BOVEDA-CLAVES-FORTRESS-CORE.md.enc` en Escritorio + `/Volumes/EMPRESA`
  (abrir con `Abrir-Boveda-FortressCore.command`). Passphrase: SOLO en Llavero macOS
  (servicio `BovedaFortressCoreMasterKey`). Nunca en archivos ni chats.
- Memoria persistente del agente: Engram, proyecto "boris" (no el proyecto del cwd).
- GitHub: `gh` autenticado como `bjofrea-ctrl`. QuantConnect/LEAN: token en `~/.lean/credentials`
  + Apple Notes "Token quantconnect" (vigente).