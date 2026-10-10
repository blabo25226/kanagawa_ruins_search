# Rule 00 — Phase Gate

- Current phase: **Phase 1-B / historical imagery and terrain foundation**, explicitly authorized by the user on 2026-10-10. Phase 1-A was merged as PR #3.
- Allowed: inspect existing imagery/metadata, georeference existing XYZ tiles, create COGs, implement GCP correction and DEM terrain tools, test synthetic data, audit derivatives, research official specifications/acquisition conditions.
- New derivatives only under `$RUINS_DATA_ROOT/processed/phase1b/`, after genuine Drive mount verification and SHA-256 readback. Raw, acquisition ledger and Phase 1-A derivatives are immutable. Synthetic DEMs remain temporary.
- No new dataset downloads, accounts, terms acceptance, login, purchases, applications, scraping, candidate inference/ranking, shrine-symbol detection, abandonment judgments or external publication.
- Unknown dates, CRS, vertical datum, footprint accuracy and licensing remain unknown. Center points do not establish photo coverage. Synthetic tests do not establish real-map/DEM accuracy.
- Preserve Phase 0 and Phase 1-A historical reports. Work from latest main on `codex/phase1b-historical-raster-foundation`; commit, push, create PR, then STOP for independent review. No direct main push or merge without a later explicit user instruction.
