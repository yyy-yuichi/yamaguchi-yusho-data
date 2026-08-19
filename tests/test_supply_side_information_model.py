import hashlib
import json
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "data" / "work1_supply_side_information_model.json"
MANIFEST_PATH = ROOT / "data" / "source_freshness_manifest.json"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


class SupplySideInformationModelContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = load_json(MODEL_PATH)
        cls.manifest = load_json(MANIFEST_PATH)
        cls.categories = cls.model["categories"]
        cls.items = [item for category in cls.categories for item in category["items"]]
        cls.item_by_id = {item["item_id"]: item for item in cls.items}
        cls.source_mapping = {
            item["source_id"]: item for item in cls.model["accepted_source_mapping"]
        }

    def test_identity_and_unrecorded_deeper_motivation_boundary(self):
        self.assertEqual(
            self.model["schema_version"],
            "WORK1-SUPPLY-SIDE-INFORMATION-MODEL-1",
        )
        self.assertEqual(
            self.model["task_id"],
            "WORK1-SUPPLY-SIDE-INFORMATION-MODEL-DEFINITION-1",
        )
        hypothesis = self.model["working_hypothesis"]
        self.assertEqual(hypothesis["text"], "山口県の地域交通は弱いのではないか")
        self.assertEqual(
            hypothesis["deeper_motivation"],
            "intentionally_not_recorded_or_inferred",
        )
        self.assertIn("推測", hypothesis["boundary"])
        self.assertIn("結論ではない", hypothesis["role"])

    def test_reference_frameworks_are_reference_only_official_https(self):
        references = self.model["reference_frameworks"]
        self.assertEqual(len(references), 3)
        self.assertTrue(all(item["accepted_original"] is False for item in references))
        self.assertTrue(
            all(item["adoption_status"] == "taxonomy_reference_only" for item in references)
        )
        self.assertTrue(
            all(item["url"].startswith("https://www.mlit.go.jp/") for item in references)
        )

    def test_gap_types_and_status_vocabulary_are_closed(self):
        self.assertEqual(
            {item["code"] for item in self.model["gap_types"]},
            {"information_gap", "measurement_gap", "service_gap"},
        )
        statuses = {item["code"]: item for item in self.model["status_vocabulary"]}
        self.assertEqual(
            set(statuses),
            {
                "VISIBLE_CURRENT",
                "ACCEPTED_SOURCE_UNMEASURED",
                "ADDITIONAL_SOURCE_REQUIRED",
                "DEMAND_COMPARATOR_REQUIRED",
            },
        )
        self.assertIsNone(statuses["VISIBLE_CURRENT"]["gap_type"])
        self.assertEqual(
            statuses["ACCEPTED_SOURCE_UNMEASURED"]["gap_type"],
            "measurement_gap",
        )
        self.assertEqual(
            statuses["ADDITIONAL_SOURCE_REQUIRED"]["gap_type"],
            "information_gap",
        )
        self.assertEqual(
            statuses["DEMAND_COMPARATOR_REQUIRED"]["gap_type"],
            "service_gap",
        )

    def test_eight_categories_and_unique_items_use_only_known_statuses(self):
        expected_categories = {
            "C1_EVIDENCE_PROVENANCE",
            "C2_SERVICE_INVENTORY",
            "C3_SPATIAL_SUPPLY",
            "C4_TEMPORAL_SUPPLY",
            "C5_ACCESS_CONDITIONS_AND_COST",
            "C6_ACTUAL_OPERATION_AND_CAPACITY",
            "C7_USE_AND_SUSTAINABILITY",
            "C8_DEMAND_AND_ACTIVITY_COMPARATOR",
        }
        self.assertEqual({item["category_id"] for item in self.categories}, expected_categories)
        self.assertEqual(len(self.categories), 8)
        item_ids = [item["item_id"] for item in self.items]
        self.assertEqual(len(item_ids), len(set(item_ids)))
        allowed_statuses = {item["code"] for item in self.model["status_vocabulary"]}
        self.assertTrue(
            all(item["current_status"] in allowed_statuses for item in self.items)
        )
        comparator = next(
            item
            for item in self.categories
            if item["category_id"] == "C8_DEMAND_AND_ACTIVITY_COMPARATOR"
        )
        self.assertEqual(comparator["domain"], "comparator_not_supply")
        self.assertTrue(
            all(
                item["current_status"] == "DEMAND_COMPARATOR_REQUIRED"
                for item in comparator["items"]
            )
        )

    def test_seven_accepted_sources_match_manifest_exactly(self):
        manifest_sources = {item["source_id"]: item for item in self.manifest["sources"]}
        self.assertEqual(self.manifest["expected_source_count"], 7)
        self.assertEqual(len(self.source_mapping), 7)
        self.assertEqual(set(self.source_mapping), set(manifest_sources))
        for source_id, mapping in self.source_mapping.items():
            manifest = manifest_sources[source_id]
            self.assertEqual(mapping["source_type"], manifest["source_type"])
            self.assertEqual(mapping["local_path"], manifest["local_path"])
            local_path = ROOT / mapping["local_path"]
            self.assertTrue(local_path.is_file())
            payload = local_path.read_bytes()
            self.assertEqual(len(payload), manifest["baseline_bytes"])
            self.assertEqual(hashlib.sha256(payload).hexdigest(), manifest["baseline_sha256"])

    def test_every_source_contribution_resolves_to_a_model_item(self):
        all_item_ids = set(self.item_by_id)
        for mapping in self.source_mapping.values():
            self.assertTrue(mapping["contributes_item_ids"])
            self.assertEqual(
                set(mapping["contributes_item_ids"]) - all_item_ids,
                set(),
                mapping["source_id"],
            )
            self.assertTrue(mapping["limitations"])

    def test_declared_gtfs_tables_exist_without_extracting_archives(self):
        gtfs_sources = [
            item for item in self.source_mapping.values() if item["source_type"] == "gtfs_zip"
        ]
        self.assertEqual(len(gtfs_sources), 3)
        required = {
            "agency.txt",
            "routes.txt",
            "trips.txt",
            "stops.txt",
            "stop_times.txt",
            "calendar.txt",
            "calendar_dates.txt",
            "fare_attributes.txt",
            "fare_rules.txt",
            "shapes.txt",
            "feed_info.txt",
        }
        for source in gtfs_sources:
            declared = set(source["declared_tables"])
            self.assertTrue(required.issubset(declared), source["source_id"])
            with zipfile.ZipFile(ROOT / source["local_path"]) as archive:
                self.assertTrue(declared.issubset(set(archive.namelist())), source["source_id"])
        hikari = self.source_mapping["hikari-gtfs"]
        self.assertIn("transfers.txt", hikari["declared_tables"])

    def test_measurement_gaps_have_accepted_sources_and_information_gaps_do_not_claim_absence(self):
        measurement_items = [
            item
            for item in self.items
            if item["current_status"] == "ACCEPTED_SOURCE_UNMEASURED"
        ]
        self.assertGreaterEqual(len(measurement_items), 10)
        self.assertTrue(all(item["accepted_source_ids"] for item in measurement_items))
        accepted_ids = set(self.source_mapping)
        for item in measurement_items:
            self.assertTrue(set(item["accepted_source_ids"]).issubset(accepted_ids))
        information_gap = next(
            item for item in self.model["gap_types"] if item["code"] == "information_gap"
        )
        self.assertIn("存在しない", information_gap["prohibited_conclusion"])

    def test_current_gtfs_has_unmeasured_timetable_location_and_fare_items(self):
        for item_id in (
            "route_identity_and_name",
            "stop_name_and_coordinates",
            "stop_level_timetable",
            "fare_and_payment",
        ):
            item = self.item_by_id[item_id]
            self.assertEqual(item["current_status"], "ACCEPTED_SOURCE_UNMEASURED")
            self.assertEqual(
                set(item["accepted_source_ids"]),
                {"iwakuni-gtfsjp", "hikari-gtfs", "jrbus-chugoku-gtfs"},
            )

    def test_municipality_contract_matches_current_nineteen_municipalities(self):
        contract = self.model["municipality_coverage_contract"]
        self.assertEqual(contract["expected_municipality_count"], 19)
        supply = load_json(ROOT / "docs" / "data" / "municipal_supply.json")
        municipality_gtfs = load_json(ROOT / "data" / "municipality_gtfs.json")
        supply_names = {item["municipality"] for item in supply["municipalities"]}
        gtfs_names = {item["municipality"] for item in municipality_gtfs}
        self.assertEqual(len(supply_names), 19)
        self.assertEqual(supply_names, gtfs_names)
        self.assertEqual(
            {item["availability_status"] for item in municipality_gtfs},
            set(contract["gtfs_access_states"]),
        )
        self.assertEqual(len(contract["required_future_matrix_fields"]), 10)
        rules = "\n".join(contract["rules"])
        self.assertIn("不存在", rules)
        self.assertIn("市町値へ配賦しない", rules)
        self.assertIn("service_gapを自動判定しない", rules)

    def test_priority_uses_accepted_sources_before_new_originals_or_demand(self):
        priorities = self.model["execution_priority"]
        self.assertEqual([item["order"] for item in priorities], [1, 2, 3])
        self.assertEqual(priorities[0]["priority_id"], "accepted_source_exploitation")
        self.assertEqual(priorities[1]["priority_id"], "additional_source_candidates")
        self.assertEqual(priorities[2]["priority_id"], "demand_comparison")
        self.assertIn("新原本を増やす前", priorities[0]["description"])
        self.assertIn("人間承認後", priorities[1]["description"])

    def test_claim_boundaries_and_human_gates_remain_explicit(self):
        claims = "\n".join(self.model["claim_boundaries"])
        self.assertIn("情報不足と測定不足", claims)
        self.assertIn("需要・活動機会・実運行", claims)
        gates = set(self.model["human_approval_gates"])
        self.assertIn("新しい原本の取得・採用", gates)
        self.assertIn("外部関係者への連絡", gates)
        self.assertIn("利用者テストの依頼と同意取得", gates)
        self.assertIn("UDC概要フォーム・本応募", gates)
        self.assertIn("BODIK登録", gates)

    def test_only_one_next_stage_is_defined_and_not_started(self):
        next_stage = self.model["next_stage"]
        self.assertEqual(
            next_stage["task_id"],
            "WORK1-SUPPLY-SIDE-INFORMATION-COVERAGE-MATRIX-1",
        )
        self.assertEqual(next_stage["status"], "DEFINED_NOT_STARTED")
        self.assertIn("19市町", next_stage["goal"])
        self.assertIn("新原本取得・採用", next_stage["boundary"])
        self.assertFalse((ROOT / "docs" / "data" / MODEL_PATH.name).exists())


if __name__ == "__main__":
    unittest.main()
