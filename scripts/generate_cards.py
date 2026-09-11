#!/usr/bin/env python3
"""
Génère les pages d'outils du wiki (wiki/canada.md, wiki/quebec.md,
wiki/commerciaux.md, wiki/fichiers.md) à partir de scripts/outils.csv.

Ces pages sont entièrement générées : ne les modifiez pas à la main, vos
changements seraient écrasés au prochain build. Modifiez plutôt
scripts/outils.csv, puis relancez ce script (ou `make build` / `make serve`,
qui l'exécutent automatiquement en pre-build — voir makefile).

Format du CSV (colonnes) :
  page       identifiant de la page, doit être une clé de PAGES ci-dessous
  categorie  titre de section (## ...) ; vide = pas de sous-titre
  nom        nom de l'outil
  description  courte description (une phrase)
  icone      nom d'icône Material Design Icons, sans le préfixe "material-"
             (voir la liste sur https://pictogrammers.com/library/mdi/)
  url        lien vers l'outil ; laisser vide si aucun lien n'est disponible
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WIKI_DIR = REPO_ROOT / "wiki"
CSV_FILE = Path(__file__).resolve().parent / "outils.csv"

# slug (colonne "page" du CSV) -> (fichier de sortie dans wiki/, titre affiché)
PAGES: dict[str, tuple[str, str]] = {
    "canada": ("canada.md", "Gouvernement du Canada"),
    "quebec": ("quebec.md", "Gouvernement du Québec"),
    "commerciaux": ("commerciaux.md", "Ressources commerciales"),
    "fichiers": ("fichiers.md", "Fichiers"),
}

HEADER = """<!--
  Fichier généré automatiquement par scripts/generate_cards.py à partir de
  scripts/outils.csv. Ne modifiez pas ce fichier directement : vos
  changements seraient écrasés au prochain build. Modifiez le CSV, puis
  relancez `python scripts/generate_cards.py` (ou `make build` / `make serve`).
-->

"""


def render_card(nom: str, description: str, icone: str, url: str) -> str:
    """Rend un outil sous forme de carte (syntaxe "grid cards" de Material)."""
    titre = f":material-{icone}:{{ .lg .middle }} **{nom}**" if icone else f"**{nom}**"
    lines = [f"-   {titre}", "", "    ---"]
    if description:
        lines += ["", f"    {description}"]
    if url:
        lines += ["", f"    [:octicons-arrow-right-24: Ouvrir]({url})"]
    return "\n".join(lines)


def render_category(categorie: str, rows: list[dict[str, str]]) -> str:
    """Rend une section (titre optionnel + grille de cartes)."""
    parts = []
    if categorie:
        parts.append(f"## {categorie}\n")
    cards = "\n\n".join(render_card(r["nom"], r["description"], r["icone"], r["url"]) for r in rows)
    parts.append(f'<div class="grid cards" markdown>\n\n{cards}\n\n</div>')
    return "\n".join(parts)


def load_rows() -> dict[str, dict[str, list[dict[str, str]]]]:
    """Lit le CSV et regroupe les lignes par page puis par catégorie, en
    conservant l'ordre d'apparition (utilisé comme ordre d'affichage)."""
    by_page: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    with CSV_FILE.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            by_page[row["page"]][row["categorie"]].append(row)
    return by_page


def main() -> None:
    by_page = load_rows()

    for slug, (filename, title) in PAGES.items():
        categories = by_page.get(slug, {})
        sections = [render_category(cat, rows) for cat, rows in categories.items()]
        content = HEADER + f"# {title}\n\n" + "\n\n".join(sections) + "\n"
        (WIKI_DIR / filename).write_text(content, encoding="utf-8")
        nb_outils = sum(len(rows) for rows in categories.values())
        print(f"✓ wiki/{filename} généré ({nb_outils} outils)")

    pages_inconnues = set(by_page) - set(PAGES)
    if pages_inconnues:
        print(f"⚠ Pages du CSV sans correspondance dans PAGES, ignorées : {', '.join(sorted(pages_inconnues))}")


if __name__ == "__main__":
    main()
