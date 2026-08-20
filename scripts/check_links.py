#!/usr/bin/env python3
"""
Vérifie tous les liens externes présents dans les pages du wiki (wiki/*.md)
et génère deux pages :

  - wiki/liens-brises.md : la liste des liens non fonctionnels
  - wiki/status.md       : le résumé (nb fonctionnels, total, pourcentage, date/heure)

Ce script est conçu pour être exécuté comme étape "pre-build" (voir makefile),
avant la génération du site par zensical.
"""

from __future__ import annotations

import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WIKI_DIR = REPO_ROOT / "wiki"
EXCEPTIONS_FILE = Path(__file__).resolve().parent / "link_exceptions.yaml"

# Pages générées par ce script : on ne les scanne pas pour éviter les boucles.
GENERATED_PAGES = {"liens-brises.md", "status.md"}

LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^\s)]+)\)")

TIMEOUT = 10  # secondes
MAX_WORKERS = 10
USER_AGENT = (
    "Mozilla/5.0 (compatible; OSINTQuebecLinkChecker/1.0; "
    "+https://osintquebec.profinfo.ca)"
)
TZ = ZoneInfo("America/Toronto")


@dataclass
class LinkOccurrence:
    fichier: str
    texte: str
    url: str


@dataclass
class CheckResult:
    ok: bool
    detail: str
    manuel: bool = False


@dataclass
class ReportData:
    occurrences: list[LinkOccurrence] = field(default_factory=list)
    results: dict[str, CheckResult] = field(default_factory=dict)


def load_exceptions() -> dict[str, dict]:
    """Charge scripts/link_exceptions.yaml : url -> {raison, verifie_le}."""
    if not EXCEPTIONS_FILE.exists():
        return {}
    raw = yaml.safe_load(EXCEPTIONS_FILE.read_text(encoding="utf-8")) or []
    exceptions = {}
    for entry in raw:
        url = (entry.get("url") or "").strip()
        if url:
            exceptions[url] = entry
    return exceptions


def find_markdown_files() -> list[Path]:
    return sorted(
        p for p in WIKI_DIR.glob("*.md") if p.name not in GENERATED_PAGES
    )


def extract_links(path: Path) -> list[LinkOccurrence]:
    occurrences = []
    text = path.read_text(encoding="utf-8")
    for match in LINK_RE.finditer(text):
        texte, url = match.group(1), match.group(2)
        occurrences.append(
            LinkOccurrence(fichier=path.name, texte=texte.strip(), url=url.strip())
        )
    return occurrences


RETRY_STATUS = {403, 408, 429, 500, 502, 503, 504}
RETRY_ATTEMPTS = 3
RETRY_DELAY = 3  # secondes


def check_url_with_retry(url: str) -> CheckResult:
    """Répète le test en cas d'échec potentiellement transitoire (rate-limit,
    blocage anti-bot ponctuel, erreur serveur temporaire) avant de conclure
    qu'un lien est réellement non fonctionnel."""
    result = check_url(url)
    attempt = 1
    while not result.ok and attempt < RETRY_ATTEMPTS:
        code = _status_from_detail(result.detail)
        if code is not None and code not in RETRY_STATUS:
            break  # ex. 404 : ce n'est pas transitoire, inutile d'insister
        time.sleep(RETRY_DELAY)
        result = check_url(url)
        attempt += 1
    return result


def _status_from_detail(detail: str) -> int | None:
    match = re.match(r"HTTP (\d+)", detail)
    return int(match.group(1)) if match else None


def check_url(url: str) -> CheckResult:
    """Teste un lien : HEAD d'abord, puis GET si HEAD est refusé (405, 403, etc.)."""
    ctx = ssl.create_default_context()
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
                status = resp.status
                if status < 400:
                    return CheckResult(ok=True, detail=f"HTTP {status}")
                # code >= 400 mais pas d'exception (rare) : on retente avec GET
                if method == "HEAD":
                    continue
                return CheckResult(ok=False, detail=f"HTTP {status}")
        except urllib.error.HTTPError as e:
            # Certains serveurs refusent HEAD (405/403) mais répondent bien à GET.
            if method == "HEAD" and e.code in (403, 405, 501):
                continue
            if e.code < 400:
                return CheckResult(ok=True, detail=f"HTTP {e.code}")
            return CheckResult(ok=False, detail=f"HTTP {e.code}")
        except urllib.error.URLError as e:
            if method == "HEAD":
                continue
            return CheckResult(ok=False, detail=f"Erreur de connexion : {e.reason}")
        except TimeoutError:
            if method == "HEAD":
                continue
            return CheckResult(ok=False, detail="Délai d'attente dépassé")
        except Exception as e:  # noqa: BLE001 - on veut capturer toute erreur réseau
            if method == "HEAD":
                continue
            return CheckResult(ok=False, detail=f"Erreur : {e}")
    return CheckResult(ok=False, detail="Échec (HEAD et GET)")


def collect() -> ReportData:
    data = ReportData()
    for path in find_markdown_files():
        data.occurrences.extend(extract_links(path))

    exceptions = load_exceptions()
    urls = sorted({occ.url for occ in data.occurrences})

    # Liens couverts par une vérification manuelle : pas d'appel réseau.
    urls_a_tester = []
    for url in urls:
        exc = exceptions.get(url)
        if exc:
            raison = exc.get("raison", "").strip()
            verifie_le = exc.get("verifie_le", "?")
            detail = f"Vérifié manuellement le {verifie_le}" + (f" — {raison}" if raison else "")
            data.results[url] = CheckResult(ok=True, detail=detail, manuel=True)
        else:
            urls_a_tester.append(url)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(check_url_with_retry, url): url for url in urls_a_tester}
        for future in as_completed(futures):
            url = futures[future]
            data.results[url] = future.result()

    # Avertir si des exceptions ne correspondent plus à aucun lien du wiki
    # (page modifiée/retirée depuis, entrée devenue obsolète).
    obsoletes = sorted(set(exceptions) - set(urls))
    for url in obsoletes:
        print(f"Avertissement : exception obsolète dans link_exceptions.yaml (lien introuvable dans le wiki) : {url}")

    return data


def write_status_page(data: ReportData, now: datetime) -> None:
    total = len(data.occurrences)
    fonctionnels = sum(1 for occ in data.occurrences if data.results[occ.url].ok)
    pourcentage = (fonctionnels / total * 100) if total else 0.0

    content = f"""# Statut des liens

Cette page est générée automatiquement lors de la construction du site.

| Indicateur | Valeur |
|--|--|
| Liens fonctionnels | {fonctionnels} |
| Liens totaux | {total} |
| Pourcentage fonctionnel | {pourcentage:.1f} % |
| Dernière vérification | {now.strftime('%Y-%m-%d %H:%M:%S %Z')} |

Voir la liste détaillée des liens non fonctionnels : [Liens brisés](liens-brises.md).
"""

    manuels = sorted(
        {occ.url: occ for occ in data.occurrences if data.results[occ.url].manuel}.values(),
        key=lambda occ: occ.url,
    )
    if manuels:
        content += "\n## Liens exclus de la vérification automatique\n\n"
        content += (
            "Ces liens sont bloqués pour les requêtes automatisées (anti-bot, etc.) "
            "mais ont été confirmés fonctionnels manuellement. Voir "
            "`scripts/link_exceptions.yaml`.\n\n"
        )
        content += "| URL | Détail |\n|--|--|\n"
        for occ in manuels:
            content += f"| {occ.url} | {data.results[occ.url].detail} |\n"

    (WIKI_DIR / "status.md").write_text(content, encoding="utf-8")


def write_broken_links_page(data: ReportData, now: datetime) -> None:
    broken = [occ for occ in data.occurrences if not data.results[occ.url].ok]
    broken.sort(key=lambda occ: (occ.fichier, occ.texte.lower()))

    lines = [
        "# Liens non fonctionnels",
        "",
        "Cette page est générée automatiquement lors de la construction du site.",
        f"Dernière vérification : {now.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "",
    ]

    if not broken:
        lines.append("Aucun lien brisé détecté. ✅")
    else:
        lines.append("| Page | Lien | URL | Erreur |")
        lines.append("|--|--|--|--|")
        for occ in broken:
            detail = data.results[occ.url].detail
            lines.append(f"| {occ.fichier} | {occ.texte} | {occ.url} | {detail} |")

    (WIKI_DIR / "liens-brises.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    now = datetime.now(TZ)
    data = collect()
    write_status_page(data, now)
    write_broken_links_page(data, now)

    total = len(data.occurrences)
    fonctionnels = sum(1 for occ in data.occurrences if data.results[occ.url].ok)
    print(f"Vérification terminée : {fonctionnels}/{total} liens fonctionnels.")
    if fonctionnels < total:
        print(f"{total - fonctionnels} lien(s) non fonctionnel(s) — voir wiki/liens-brises.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
