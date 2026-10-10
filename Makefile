CONDA_ENV ?= kanagawa-ruins
PYTHON ?= conda run -n $(CONDA_ENV) python

.PHONY: doctor test sources dry-fetch fetch validate-fast validate-full audit

doctor:
	$(PYTHON) scripts/check_environment.py --output reports/environment_check.json

test:
	$(PYTHON) -m unittest discover -s tests -v

sources:
	$(PYTHON) scripts/fetch_sources.py --list

dry-fetch:
	$(PYTHON) scripts/fetch_sources.py --dry-run --all-approved

fetch:
	$(PYTHON) scripts/fetch_sources.py --execute --all-approved

validate-fast:
	$(PYTHON) scripts/validate_databank.py --mode fast

validate-full:
	$(PYTHON) scripts/validate_databank.py --mode full

audit:
	$(PYTHON) scripts/audit_databank.py --mode full --check-all-hashes --json-output reports/databank_audit.json --markdown-output reports/data_inventory.md --integrity-output reports/phase0_4_1_integrity_audit.md

.PHONY: phase1a-plan phase1a-verify phase1a-audit test-all
phase1a-plan:
	$(PYTHON) scripts/phase1a_ingest.py --dry-run --area tsukui

phase1a-verify:
	$(PYTHON) scripts/phase1a_verify.py --report reports/phase1a_verification.json

phase1a-audit:
	$(PYTHON) scripts/audit_databank.py --mode full --check-all-hashes --json-output reports/phase1a_final_audit.json

test-all:
	$(PYTHON) -m pytest tests/ -v
