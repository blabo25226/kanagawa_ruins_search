"""Synthetic tests for the append-only ledger and Phase 0 snapshot accounting (no Drive)."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from kanagawa_ruins.qa.ledger import (
    load_phase0_snapshot,
    phase1c_manifest_files,
    read_ledger,
    unexplained_files,
    validate_ledger,
)


def make_file(root, rel, content):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return dict(relative_path=rel, size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest())


class LedgerFixture(unittest.TestCase):
    """53 Phase 0 records (audit form) plus up to 7 appended records with real files."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = []
        self.phase0 = []
        for i in range(53):
            rec = make_file(self.root, f"raw/phase0/f{i:02d}.bin", f"phase0-{i}".encode())
            rec["source_id"] = f"src_{i:02d}"
            if i % 2:  # Phase 0 ledgers use both size field names
                rec["bytes"] = rec.pop("size_bytes")
            self.ledger.append(rec)
            self.phase0.append(dict(index=i + 1, relative_path=rec["relative_path"], recorded_size=len(f"phase0-{i}".encode()), recorded_sha256=rec["sha256"]))
        self.appended = []
        for j in range(7):
            rec = make_file(self.root, f"raw/fgd/pkg{j}.zip", f"fgd-{j}".encode() * 10)
            rec["source_id"] = f"gsi_fgd_{j}"
            self.appended.append(rec)
        self.extras = {"raw/administrative/dup.zip", "literature/notes.md", "provenance.jsonl"}

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, ledger, **kw):
        return validate_ledger(ledger, self.phase0, data_root=self.root, verify_sha=True, reserved_paths=self.extras, **kw)


class AppendOnlyLedgerTests(LedgerFixture):
    def test_53_record_ledger_passes(self):
        r = self.check(self.ledger)
        self.assertEqual(r["errors"], [])
        self.assertEqual((r["phase0"], r["appended"]), (53, 0))

    def test_60_record_ledger_passes(self):
        r = self.check(self.ledger + self.appended)
        self.assertEqual(r["errors"], [])
        self.assertEqual((r["phase0"], r["appended"]), (53, 7))

    def test_phase0_record_modified_or_deleted_fails(self):
        changed = [dict(r) for r in self.ledger]
        changed[10]["sha256"] = "0" * 64
        self.assertIn("Phase 0 SHA-256 changed", " ".join(self.check(changed)["errors"]))
        resized = [dict(r) for r in self.ledger]
        resized[11]["bytes"] = 999
        self.assertIn("Phase 0 size changed", " ".join(self.check(resized)["errors"]))
        deleted = self.ledger[:20] + self.ledger[21:] + self.appended
        self.assertTrue(any("changed or moved" in e for e in self.check(deleted)["errors"]))
        truncated = self.ledger[:50]
        self.assertTrue(any("deleted" in e for e in self.check(truncated)["errors"]))

    def test_insertion_before_phase0_end_fails(self):
        inserted = self.ledger[:30] + [self.appended[0]] + self.ledger[30:]
        self.assertTrue(any("changed or moved" in e for e in self.check(inserted)["errors"]))

    def test_duplicate_path_sha_and_source_id_fail(self):
        dup_path = dict(self.appended[1], relative_path=self.appended[0]["relative_path"])
        errs = " ".join(self.check(self.ledger + [self.appended[0], dup_path])["errors"])
        self.assertIn("duplicate relative_path", errs)
        dup_content = make_file(self.root, "raw/fgd/copy.zip", (b"fgd-0") * 10)
        dup_content["source_id"] = "gsi_fgd_copy"
        self.assertIn("duplicate sha256", " ".join(self.check(self.ledger + [self.appended[0], dup_content])["errors"]))
        dup_src = dict(self.appended[2], source_id="src_00")
        self.assertIn("duplicate source_id", " ".join(self.check(self.ledger + [dup_src])["errors"]))

    def test_appended_record_content_checks(self):
        cases = {
            "size mismatch": dict(self.appended[0], size_bytes=self.appended[0]["size_bytes"] + 1),
            "SHA-256 mismatch": dict(self.appended[0], sha256="a" * 64),
            "invalid SHA-256": dict(self.appended[0], sha256="XYZ"),
            "file missing": dict(self.appended[0], relative_path="raw/fgd/absent.zip", sha256="b" * 64),
            "not a contained raw/ path": dict(self.appended[0], relative_path="../outside.zip"),
            "without source_id": {k: v for k, v in self.appended[0].items() if k != "source_id"},
            "invalid size": dict(self.appended[0], size_bytes=0),
            "Phase 0 non-ledger file": dict(self.appended[0], relative_path="raw/administrative/dup.zip"),
        }
        for message, bad in cases.items():
            with self.subTest(message):
                self.assertIn(message, " ".join(self.check(self.ledger + [bad])["errors"]))

    def test_absolute_and_processed_paths_rejected(self):
        for path in ["/raw/fgd/a.zip", "processed/phase1c/x.parquet", "raw/./fgd/a.zip"]:
            with self.subTest(path):
                bad = dict(self.appended[0], relative_path=path)
                self.assertIn("not a contained raw/ path", " ".join(self.check(self.ledger + [bad])["errors"]))

    def test_sha_verification_can_be_limited_to_metadata(self):
        bad = dict(self.appended[0], sha256="c" * 64)
        r = validate_ledger(self.ledger + [bad], self.phase0, data_root=self.root, verify_sha=False)
        self.assertEqual(r["errors"], [])


class AccountingTests(LedgerFixture):
    def test_unexplained_detection_with_53_and_60_records(self):
        snapshot = {r["relative_path"] for r in self.phase0} | self.extras
        later_fgd = {r["relative_path"] for r in self.appended}
        all_files = snapshot | later_fgd | {".provenance.lock"}
        # 53 records: raw/fgd is explained only by the Phase 1-B.5 inventory.
        self.assertEqual(unexplained_files(all_files, snapshot, inventory_paths=later_fgd), [])
        self.assertEqual(unexplained_files(all_files, snapshot), sorted(later_fgd))
        # 60 records: the appended ledger entries explain the same files.
        self.assertEqual(unexplained_files(all_files, snapshot, ledger_paths=later_fgd), [])
        # An unregistered file is still detected.
        stray = all_files | {"raw/unknown/new.zip"}
        self.assertEqual(unexplained_files(stray, snapshot, ledger_paths=later_fgd), ["raw/unknown/new.zip"])

    def test_phase1c_manifest_references(self):
        make_file(self.root, "processed/phase1c/codex/vectors/a.parquet", b"a")
        (self.root / "processed/phase1c/codex/manifests").mkdir(parents=True)
        (self.root / "processed/phase1c/codex/manifests/a.json").write_text(json.dumps({"processed_path": "processed/phase1c/codex/vectors/a.parquet"}))
        make_file(self.root, "processed/phase1c/claude/v1/csv/x.csv", b"x")
        (self.root / "processed/phase1c/claude/v1/run_manifest.json").write_text(json.dumps({"outputs": [{"path": "processed/phase1c/claude/v1/csv/x.csv"}]}))
        make_file(self.root, "processed/phase1c/claude/v1/csv/orphan.csv", b"o")
        make_file(self.root, "processed/phase1c/claude/v1/qa/list.json", b"[1, 2]")
        (self.root / "processed/phase1c/claude/v1/run_manifest.json").write_text(json.dumps({"outputs": [{"path": "processed/phase1c/claude/v1/csv/x.csv"}, {"path": "processed/phase1c/claude/v1/qa/list.json"}]}))
        files = {p.relative_to(self.root).as_posix() for p in (self.root / "processed").rglob("*") if p.is_file()}
        got = phase1c_manifest_files(self.root, files)
        self.assertEqual(files - got, {"processed/phase1c/claude/v1/csv/orphan.csv"})

    def test_snapshot_loader_orders_by_index(self):
        audit = dict(records=list(reversed(self.phase0)), duplicate_files=["raw/administrative/dup.zip"], metadata_files=["literature/notes.md"])
        p = self.root / "audit.json"
        p.write_text(json.dumps(audit))
        _, recs, extras = load_phase0_snapshot(p)
        self.assertEqual([r["index"] for r in recs], list(range(1, 54)))
        self.assertEqual(extras, self.extras)
        (self.root / "provenance.jsonl").write_text("\n".join(json.dumps(r) for r in self.ledger + self.appended) + "\n")
        self.assertEqual(len(read_ledger(self.root / "provenance.jsonl")), 60)


if __name__ == "__main__":
    unittest.main()
