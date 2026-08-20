# Variables
# zensical exige Python >= 3.10 (voir https://pypi.org/project/zensical/) ;
PYTHON      := $(shell command -v python3.12 || command -v python3.13 || command -v python3.11 || command -v python3.10 || command -v python3)
VENV        := venv
VENV_BIN    := $(VENV)/bin
DOCS_DIR    := wiki
SITE_DIR    := site
SCRIPTS_DIR := overrides/scripts

.PHONY: help install build serve clean pre-build rebuild deploy

help:
	@echo "Cibles disponibles :"
	@echo "  make install     - Crée le venv et installe les dépendances"
	@echo "  make build       - Pipeline complet : pre-build -> zensical"
	@echo "  make serve       - Lance le serveur de dev Zensical"
	@echo "  make clean       - Supprime le dossier site/ et les caches"
	@echo "  make rebuild     - clean + build"
	@echo "  make deploy      - build + rsync vers le serveur"

# --- Installation ---
$(VENV)/bin/activate:
	@$(PYTHON) -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || \
		(echo "Erreur : zensical exige Python >= 3.10, mais $(PYTHON) est en $$($(PYTHON) --version 2>&1)."; \
		 echo "Installez une version récente (ex. brew install python@3.12) et relancez make."; exit 1)
	$(PYTHON) -m venv $(VENV)
	$(VENV_BIN)/pip install --upgrade pip
	$(VENV_BIN)/pip install -r requirements.txt

install: $(VENV)/bin/activate

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

# --- Nettoyage ---
clean:
	rm -rf $(SITE_DIR)
	rm -rf .cache
	find . -type d -name __pycache__ -exec rm -rf {} +

rebuild: clean build

