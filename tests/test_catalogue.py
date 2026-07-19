import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CatalogueContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalogue = json.loads((ROOT / "skills.json").read_text(encoding="utf-8"))
        cls.records = cls.catalogue["skills"]

    def test_catalogue_covers_every_skill_once(self) -> None:
        folders = sorted(path.name for path in (ROOT / "skills").iterdir() if (path / "SKILL.md").is_file())
        names = [record["name"] for record in self.records]
        self.assertEqual(sorted(names), folders)
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(self.catalogue["skill_count"], len(folders))

    def test_pack_manifests_partition_the_catalogue(self) -> None:
        selected: list[str] = []
        for path in sorted((ROOT / "packs").glob("*.json")):
            manifest = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["skill_count"], len(manifest["skills"]))
            selected.extend(manifest["skills"])
        names = [record["name"] for record in self.records]
        self.assertEqual(sorted(selected), sorted(names))
        self.assertEqual(len(selected), len(set(selected)))

    def test_default_public_pack_excludes_other_trust_classes_and_writes(self) -> None:
        public_manifest = json.loads((ROOT / "packs" / "nz-public-data.json").read_text(encoding="utf-8"))
        self.assertTrue(public_manifest["default"])
        by_name = {record["name"]: record for record in self.records}
        for name in public_manifest["skills"]:
            record = by_name[name]
            self.assertEqual(record["data_class"], "public")
            self.assertFalse(record["writes"])
            self.assertEqual(record["pack"], "nz-public-data")

    def test_specialised_packs_enforce_their_trust_boundaries(self) -> None:
        by_name = {record["name"]: record for record in self.records}
        manifests = {
            path.stem: json.loads(path.read_text(encoding="utf-8"))
            for path in (ROOT / "packs").glob("*.json")
        }
        for name in manifests["nz-personal-data"]["skills"]:
            record = by_name[name]
            self.assertEqual(record["data_class"], "personal")
            self.assertIn(record["auth"], {"personal-token", "mixed"})
        for name in manifests["thecolab-internal"]["skills"]:
            self.assertEqual(by_name[name]["data_class"], "internal")
        for name in manifests["artifact-tools"]["skills"]:
            record = by_name[name]
            self.assertTrue(record["writes"])
            self.assertIn("local_output", record)
        for name in manifests["paid-data-connectors"]["skills"]:
            self.assertEqual(by_name[name]["auth"], "paid-credential")
        for name in manifests["nz-commercial-web"]["skills"]:
            record = by_name[name]
            self.assertEqual(record["data_class"], "public")
            self.assertFalse(record["writes"])
            self.assertIn(record["source_type"], {"commercial", "mixed"})


if __name__ == "__main__":
    unittest.main()
