.PHONY: doctor test sources dry-fetch fetch

doctor:
	python scripts/check_environment.py --output reports/environment_check.json

test:
	python -m unittest discover -s tests -v

sources:
	python scripts/fetch_sources.py --list

dry-fetch:
	python scripts/fetch_sources.py --dry-run --all-approved

fetch:
	python scripts/fetch_sources.py --execute --all-approved
