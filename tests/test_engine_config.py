from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ethoscopy as etho

from ethoscopy_mcp import EthoscopyService, Settings
from ethoscopy_mcp.errors import InvalidExperimentError
from test_preview import _survival_recipe, _write_transfer_fixture
from ethoscopy_mcp import ExperimentManifest


class EngineConfigTests(unittest.TestCase):
    def test_service_selects_k(self):
        with tempfile.TemporaryDirectory() as directory:
            etho.set_sleep_rule('classic')
            EthoscopyService(Settings.create([directory]))
            self.assertEqual(etho.get_sleep_rule(), 'k')

    def test_survival_rejects_old_loaded_engine(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            a, b, mapping = _write_transfer_fixture(root)
            service = EthoscopyService(Settings.create([root]))
            recipe = _survival_recipe(mapping)
            manifest = ExperimentManifest(experiment_id=recipe.experiment_id, source_paths=(a, b))
            with patch('ethoscopy_mcp.preview.etho.__version__', '2.4.0'):
                with self.assertRaisesRegex(InvalidExperimentError, '3.0.0'):
                    service.preview_analysis(manifest, recipe)
