# Variables
# zensical exige Python >= 3.10 (voir https://pypi.org/project/zensical/) ;
PYTHON      := $(shell command -v python3.12 || command -v python3.13 || command -v python3.11 || command -v python3.10 || command -v python3)
VENV        := venv
VENV_BIN    := $(VENV)/bin
DOCS_DIR    := wiki
SITE_DIR    := site
SCRIPTS_DIR := overrides/scripts

.PHONY: help install build serve clean pre-build rebuild deploy check-links

help:
	@echo "Cibles disponibles :"
	@echo "  make install     - Crée le venv et installe les dépendances"
	@echo "  make check-links - Vérifie les liens externes (à lancer localement, voir note ci-dessous)"
	@echo "  make build       - Pipeline complet : pre-build -> zensical"
	@echo "  make serve       - Lance le serveur de dev Zensical"
	@echo "  make check-serve - vérifie les liens et lance le serveur de dev Zensical"
	@echo "  make clean       - Supprime le dossier site/ et les caches"
	@echo "  make rebuild     - clean + build"
	@echo "  make deploy      - build + rsync vers le serveur"
	@echo ""
	@echo "Note : make check-links doit être lancé localement (IP résidentielle)."
	@echo "Depuis GitHub Actions, l'IP du runner (datacenter) est bloquée par plusieurs"
	@echo "fournisseurs municipaux (403/timeout), donc ce n'est PAS exécuté en CI."
	@echo "Lancez 'make check-links' localement, puis committez wiki/status.md et"
	@echo "wiki/liens-brises.md."

# --- Installation ---
$(VENV)/bin/activate:
	@$(PYTHON) -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || \
		(echo "Erreur : zensical exige Python >= 3.10, mais $(PYTHON) est en $$($(PYTHON) --version 2>&1)."; \
		 echo "Installez une version récente (ex. brew install python@3.12) et relancez make."; exit 1)
	$(PYTHON) -m venv $(VENV)
	$(VENV_BIN)/pip install --upgrade pip
	$(VENV_BIN)/pip install -r requirements.txt

install: $(VENV)/bin/activate

# --- Vérification des liens externes (LOCAL uniquement, voir `make help`) ---
# Ne pas appeler depuis pre-build/build : l'IP des runners GitHub Actions est
# bloquée par plusieurs fournisseurs municipaux (403/timeout), ce qui produit
# de faux positifs massifs. À lancer manuellement en local, puis committer
# wiki/status.md et wiki/liens-brises.md.
check-links: install
	$(VENV_BIN)/python scripts/check_links.py

# --- Étapes pre-build (avant zensical) ---
pre-build: install
	@echo "==> Pre-build : génération de contenu dynamique"
	@echo "==> Pre-build terminé"

# --- Build Zensical ---
zensical-build: pre-build
	@echo "==> Build Zensical"
	$(VENV_BIN)/zensical build --clean

# Cible principale
build: zensical-build
	@echo "✓ Build complet dans $(SITE_DIR)/"

# --- Dev server (sans post-build, pour le live reload) ---
serve: install pre-build 
	$(VENV_BIN)/zensical serve

# --- Dev server (sans post-build, pour le live reload) ---
check-serve: install pre-build check-links
	$(VENV_BIN)/zensical serve

# --- Nettoyage ---
clean:
	rm -rf $(SITE_DIR)
	rm -rf .cache
	find . -type d -name __pycache__ -exec rm -rf {} +

rebuild: clean build

