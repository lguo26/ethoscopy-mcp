"""Errors must be useful over MCP without weakening source boundaries."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mcp import Client

from ethoscopy_mcp import EthoscopyService, Settings
from ethoscopy_mcp.errors import (
    ConfigurationError, InvalidExperimentError, SourceChangedError,
    UnsafePathError, UnsupportedSourceError,
)
from ethoscopy_mcp.server import create_server


class FailingService:
    def __init__(self, error):
        self.error = error

    def get_artifact(self, analysis_id, artifact_id):
        raise self.error


class ToolErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_outside_root_reports_reason_without_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted = root / 'trusted'
            trusted.mkdir()
            outside = root / 'Downloads' / 'experiment.pkl'
            outside.parent.mkdir()
            outside.write_bytes(b'not a pickle: must never be loaded')
            service = EthoscopyService(Settings.create([trusted]))
            async with Client(create_server(service=service), raise_exceptions=False,
                              read_timeout_seconds=10) as client:
                with patch('ethoscopy_mcp.service.load_behaviour_pickle') as loader:
                    result = await client.call_tool('inspect_experiment', {
                        'manifest': {'experiment_id': 'outside', 'source_paths': [str(outside)]}})
                loader.assert_not_called()
                self.assertTrue(result.is_error)
                message = '\n'.join(getattr(c, 'text', '') for c in result.content)
                self.assertIn('UnsafePathError: Source is outside the configured trusted roots', message)
                self.assertEqual(service.settings.trusted_roots, (trusted.resolve(),))
                self.assertEqual(outside.read_bytes(), b'not a pickle: must never be loaded')

    async def test_known_domain_errors_keep_their_explanations(self):
        for error_type in (ConfigurationError, InvalidExperimentError, SourceChangedError,
                           UnsafePathError, UnsupportedSourceError):
            with self.subTest(error=error_type.__name__):
                async with Client(create_server(service=FailingService(error_type('review this input'))),
                                  raise_exceptions=False, read_timeout_seconds=10) as client:
                    result = await client.call_tool('get_artifact', {
                        'analysis_id': 'example', 'artifact_id': 'example'})
                    self.assertTrue(result.is_error)
                    message = '\n'.join(getattr(c, 'text', '') for c in result.content)
                    self.assertIn(f'{error_type.__name__}: review this input', message)

    async def test_unexpected_errors_remain_masked(self):
        async with Client(create_server(service=FailingService(RuntimeError('private internal detail'))),
                          raise_exceptions=False, read_timeout_seconds=10) as client:
            result = await client.call_tool('get_artifact', {'analysis_id': 'example', 'artifact_id': 'example'})
            self.assertTrue(result.is_error)
            message = '\n'.join(getattr(c, 'text', '') for c in result.content)
            self.assertIn('Error executing tool get_artifact', message)
            self.assertNotIn('private internal detail', message)

    async def test_configuration_errors_at_lazy_initialization_are_visible(self):
        server = create_server()
        with patch('ethoscopy_mcp.server.Settings.from_env',
                   side_effect=ConfigurationError('ETHOSCOPY_DATA_ROOTS must contain a trusted directory')):
            async with Client(server, raise_exceptions=False, read_timeout_seconds=10) as client:
                result = await client.call_tool('list_experiments', {})
                self.assertTrue(result.is_error)
                message = '\n'.join(getattr(c, 'text', '') for c in result.content)
                self.assertIn('ConfigurationError: ETHOSCOPY_DATA_ROOTS', message)
