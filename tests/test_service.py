from pathlib import Path
import tempfile
import unittest

import ethoscopy as etho
import pandas as pd

from ethoscopy_mcp.config import Settings
from ethoscopy_mcp.registry import sha256_file
from ethoscopy_mcp.schemas import ExperimentManifest
from ethoscopy_mcp.service import EthoscopyService


class ServiceInspectionTests(unittest.TestCase):
    def test_inspects_behavpy_pickle_without_changing_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "synthetic.pkl"
            data = pd.DataFrame(
                {
                    "id": ["fly-1", "fly-1", "fly-2", "fly-2"],
                    "t": [0, 10, 0, 10],
                    "moving": [True, False, True, True],
                }
            ).set_index("id")
            metadata = pd.DataFrame(
                {
                    "id": ["fly-1", "fly-2"],
                    "sex": ["male", "female"],
                    "infection": [False, True],
                }
            ).set_index("id")
            frame = etho.behavpy(data, metadata, canvas=None, check=True)
            frame.to_pickle(source_path)
            hash_before = sha256_file(source_path)

            service = EthoscopyService(Settings.create([root]))
            summary = service.inspect_experiment(
                ExperimentManifest(
                    experiment_id="synthetic-001",
                    source_paths=(source_path,),
                )
            )

            self.assertEqual(summary.data_rows, 4)
            self.assertEqual(summary.metadata_rows, 2)
            self.assertEqual(summary.animals_in_data, 2)
            self.assertEqual(summary.animals_in_metadata, 2)
            self.assertEqual(summary.time_range.minimum_seconds, 0)
            self.assertEqual(summary.time_range.maximum_seconds, 10)
            groups = {group.column: group.counts for group in summary.groups}
            self.assertEqual(groups["sex"], {"male": 1, "female": 1})
            self.assertEqual(groups["infection"], {"false": 1, "true": 1})
            self.assertTrue(summary.source_hashes_verified)
            self.assertEqual(summary.warnings, ())
            self.assertEqual(hash_before, sha256_file(source_path))

    def test_reports_missing_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "missing-meta.pkl"
            data = pd.DataFrame(
                {"id": ["fly-1", "fly-2"], "t": [0, 0], "moving": [True, True]}
            ).set_index("id")
            metadata = pd.DataFrame({"id": ["fly-1"], "sex": ["male"]}).set_index(
                "id"
            )
            frame = etho.behavpy(data, metadata, canvas=None, check=False)
            frame.to_pickle(source_path)

            summary = EthoscopyService(Settings.create([root])).inspect_experiment(
                ExperimentManifest(
                    experiment_id="missing-metadata",
                    source_paths=(source_path,),
                )
            )

            self.assertIn("animals_missing_metadata", {w.code for w in summary.warnings})


if __name__ == "__main__":
    unittest.main()
