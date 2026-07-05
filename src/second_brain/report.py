"""Parte de estado del sistema: salud de la biblioteca y del espejo.

Lo usan el comando /estado del bot y el parte diario por Telegram. Todo se
calcula leyendo los Markdown (fuente de verdad) y el marcador `.sync/last_ok`
que escribe el sincronizador tras cada espejo correcto.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from second_brain.config import Config
from second_brain.storage import library, markdown

_SYNC_WARN_AFTER = timedelta(minutes=20)


def collect_stats(config: Config) -> dict:
    total = pending = enrich_errors = today = 0
    now = datetime.now().astimezone()
    for path in library.iter_notes(config.library_dir):
        frontmatter, _ = markdown.parse_note(path)
        if not frontmatter.get("id"):
            continue
        total += 1
        if frontmatter.get("status") == "pending":
            pending += 1
        if frontmatter.get("enrichment_error"):
            enrich_errors += 1
        captured = str(frontmatter.get("captured_at", ""))
        if captured[:10] == now.strftime("%Y-%m-%d"):
            today += 1

    marker = config.library_dir / ".sync" / "last_ok"
    sync_age: timedelta | None = None
    if marker.exists():
        mtime = datetime.fromtimestamp(marker.stat().st_mtime, tz=timezone.utc)
        sync_age = datetime.now(tz=timezone.utc) - mtime

    return {
        "total": total,
        "today": today,
        "pending": pending,
        "enrich_errors": enrich_errors,
        "sync_age": sync_age,
    }


def _sync_line(sync_age: timedelta | None) -> str:
    if sync_age is None:
        return "Espejo Drive: sin datos todavía"
    minutes = int(sync_age.total_seconds() // 60)
    if sync_age <= _SYNC_WARN_AFTER:
        return f"Espejo Drive: ✅ OK (hace {minutes} min)"
    return f"Espejo Drive: ⚠️ SIN SEÑAL desde hace {minutes} min — revisar"


def build_report(config: Config) -> str:
    stats = collect_stats(config)
    lines = [
        f"📊 Segundo cerebro — {datetime.now().astimezone():%d/%m/%Y %H:%M}",
        f"Notas: {stats['total']} (hoy: +{stats['today']})",
        f"Pendientes de extracción: {stats['pending']}",
        f"Errores de enriquecimiento: {stats['enrich_errors']}",
        _sync_line(stats["sync_age"]),
    ]
    if stats["pending"]:
        lines.append("→ envía /reprocess para reintentar las pendientes")
    if stats["enrich_errors"]:
        lines.append("→ envía /enrich para reintentar el enriquecimiento")
    return "\n".join(lines)
