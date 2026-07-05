"""CLI de second-brain.

Comandos:
  run        Arranca el bot de Telegram (long polling).
  add        Captura directa desde la terminal (texto, URL o imagen).
  reprocess  Reintenta las notas con estado `pending` (re-extrae contenido).
  enrich     (Re)genera el enriquecimiento IA sin tocar el contenido original.
  index      Reconstruye el índice de búsqueda desde los Markdown.
  search     Busca en el índice.
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime
from pathlib import Path

from second_brain.config import load_config
from second_brain.models import Capture, ProcessOutcome
from second_brain.pipeline import Pipeline
from second_brain.processors.url import is_probable_url, normalize_url


def _print_outcome(outcome: ProcessOutcome) -> None:
    icon = "✅" if outcome.status == "complete" else "📥"
    print(f"{icon} [{outcome.status}] {outcome.title}\n   {outcome.path}")


def cmd_run(args: argparse.Namespace) -> None:
    from second_brain.sources.telegram import run_bot

    run_bot(load_config(args.env))


_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
_AUDIO_SUFFIXES = {".oga", ".ogg", ".mp3", ".m4a", ".wav", ".webm", ".flac"}


def _kind_for_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in _IMAGE_SUFFIXES:
        return "image"
    if suffix in _AUDIO_SUFFIXES:
        return "audio"
    if suffix == ".pdf":
        return "pdf"
    return "file"


def cmd_add(args: argparse.Namespace) -> None:
    pipeline = Pipeline(load_config(args.env))
    now = datetime.now().astimezone()
    text = " ".join(args.text) if args.text else None

    if args.file:
        path = Path(args.file)
        if not path.is_file():
            raise SystemExit(f"No existe el fichero: {path}")
        capture = Capture(
            kind=_kind_for_file(path),
            source="cli",
            captured_at=now,
            text=text,
            file_bytes=path.read_bytes(),
            file_name=path.name,
        )
    elif text and is_probable_url(text):
        url = normalize_url(text)
        duplicate = pipeline.find_duplicate_url(url)
        if duplicate:
            print(f"🔁 Ya existe: «{duplicate['title']}»\n   {duplicate['path']}")
            return
        capture = Capture(kind="url", source="cli", captured_at=now, url=url)
    elif text:
        capture = Capture(kind="text", source="cli", captured_at=now, text=text)
    else:
        raise SystemExit("Indica un texto/URL o --file <imagen|pdf|audio>")

    _print_outcome(pipeline.process(capture))


def cmd_reprocess(args: argparse.Namespace) -> None:
    pipeline = Pipeline(load_config(args.env))
    outcomes = pipeline.reprocess(include_complete=args.all)
    if not outcomes:
        print("No hay notas pendientes.")
        return
    for outcome in outcomes:
        _print_outcome(outcome)
    pending = sum(1 for o in outcomes if o.status == "pending")
    print(f"\nReprocesadas: {len(outcomes)} · siguen pendientes: {pending}")


def cmd_enrich(args: argparse.Namespace) -> None:
    pipeline = Pipeline(load_config(args.env))
    try:
        outcomes = pipeline.enrich_library(force=args.all)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None
    if not outcomes:
        print("Nada que enriquecer: todo está al día con el modelo de conocimiento.")
        return
    for path, status in outcomes:
        icon = {"enriched": "🧠", "error": "⚠️"}[status]
        print(f"{icon} [{status}] {path}")
    errors = sum(1 for _, s in outcomes if s == "error")
    print(f"\nEnriquecidas: {len(outcomes) - errors} · errores: {errors}")


def cmd_index(args: argparse.Namespace) -> None:
    from second_brain.index import sqlite_index

    config = load_config(args.env)
    count = sqlite_index.rebuild(config.library_dir)
    print(f"Índice reconstruido: {count} notas ({sqlite_index.db_path(config.library_dir)})")


def cmd_search(args: argparse.Namespace) -> None:
    from second_brain.index import sqlite_index

    config = load_config(args.env)
    results = sqlite_index.search(config.library_dir, " ".join(args.query))
    if not results:
        print("Sin resultados.")
        return
    for r in results:
        print(f"[{r['type']}] {r['title']}\n   {r['path']}\n   {r['snippet']}\n")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    parser = argparse.ArgumentParser(
        prog="second-brain",
        description="Biblioteca documental personal: captura a Markdown.",
    )
    parser.add_argument("--env", help="ruta a un fichero .env alternativo")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run", help="arranca el bot de Telegram").set_defaults(func=cmd_run)

    p_add = sub.add_parser("add", help="captura directa desde la terminal")
    p_add.add_argument("text", nargs="*", help="texto o URL a capturar")
    p_add.add_argument("--file", help="ruta a una imagen")
    p_add.set_defaults(func=cmd_add)

    p_re = sub.add_parser("reprocess", help="reintenta notas pendientes")
    p_re.add_argument(
        "--all",
        action="store_true",
        help="re-enriquece toda la biblioteca (también las notas completas)",
    )
    p_re.set_defaults(func=cmd_reprocess)

    p_en = sub.add_parser(
        "enrich", help="(re)genera el enriquecimiento IA sin tocar el contenido"
    )
    p_en.add_argument(
        "--all",
        action="store_true",
        help="re-enriquece todo, no solo lo obsoleto respecto al knowledge model",
    )
    p_en.set_defaults(func=cmd_enrich)
    sub.add_parser("index", help="reconstruye el índice de búsqueda").set_defaults(
        func=cmd_index
    )

    p_search = sub.add_parser("search", help="busca en el índice")
    p_search.add_argument("query", nargs="+", help="términos de búsqueda")
    p_search.set_defaults(func=cmd_search)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
