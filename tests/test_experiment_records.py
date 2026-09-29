import json
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ethoscopy_mcp import EthoscopyService, Settings, ExperimentManifest
from ethoscopy_mcp.experiment_records import ExperimentRecord, ConditionRecord
from ethoscopy_mcp.errors import InvalidExperimentError
from ethoscopy_mcp.registry import sha256_file
from test_preview import _write_transfer_fixture, _survival_recipe


class ExperimentRecordsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.artifacts = self.root/'runs'
        self.artifacts.mkdir()
        self.first, self.second, mapping = _write_transfer_fixture(self.root)
        self.service = EthoscopyService(Settings.create([self.root], artifact_root=self.artifacts))
        self.manifest = ExperimentManifest(experiment_id='synthetic-transfer', source_paths=(self.first,self.second))
        self.recipe = _survival_recipe(mapping)
        self.record = ExperimentRecord(experiment_id=self.manifest.experiment_id,
            title='Synthetic transfer', folder=self.root, source_paths=self.manifest.source_paths,
            question='Synthetic infection comparison', conditions=(
                ConditionRecord(condition_id='control', treatment='PBS', is_control=True, planned_n=2),
                ConditionRecord(condition_id='low', treatment='Synthetic bacteria', od600=0.01, planned_n=1),
                ConditionRecord(condition_id='high', treatment='Synthetic bacteria', od600=0.1, planned_n=1)))

    def run_analysis(self):
        preview=self.service.preview_analysis(self.manifest,self.recipe)
        return self.service.run_analysis(self.manifest,self.recipe,preview.recipe_hash)

    def test_opt_in_auto_update_counts_and_idempotency(self):
        original=sha256_file(self.first)
        self.assertEqual(self.service.list_experiments().experiments,())
        self.assertFalse((self.artifacts/'experiment_registry').exists())
        self.service.register_experiment(self.record)
        result=self.run_analysis()
        self.assertIsNone(result.dashboard_warning)
        self.assertTrue(result.dashboard_path.is_file())
        entry=self.service.list_experiments().experiments[0]
        self.assertEqual(len(entry.analyses),1)
        self.assertEqual(entry.record.recording_status,'unknown')
        self.assertEqual(entry.record.review_status,'needs_review')
        self.assertEqual(entry.analyses[0].group_outcomes,result.group_outcomes)
        self.run_analysis()
        self.assertEqual(self.service.list_experiments().experiments[0].revision,entry.revision)
        self.assertEqual(sha256_file(self.first),original)
        self.service.link_experiment_analysis(result.analysis_id)
        self.assertEqual(self.service.list_experiments().experiments[0].revision,entry.revision)

    def test_revision_conflicts_preserve_results_and_reject_source_changes(self):
        self.service.register_experiment(self.record)
        result=self.run_analysis()
        current=self.service.list_experiments().experiments[0]
        with self.assertRaisesRegex(InvalidExperimentError,'Revision conflict'):
            self.service.register_experiment(self.record,1)
        revised=self.service.register_experiment(self.record.model_copy(update={'recording_status':'finished'}),current.revision)
        self.assertEqual(revised.analyses,current.analyses)
        with self.assertRaisesRegex(InvalidExperimentError,'Cannot change'):
            self.service.register_experiment(self.record.model_copy(update={'source_paths':(self.first,)}),revised.revision)
        self.assertTrue(result.dashboard_path.exists())

    def test_link_existing_run_and_tamper_blocks_dashboard(self):
        result=self.run_analysis()
        self.assertIsNone(result.dashboard_path)
        with self.assertRaisesRegex(InvalidExperimentError,'Register'):
            self.service.link_experiment_analysis(result.analysis_id)
        self.service.register_experiment(self.record)
        linked=self.service.link_experiment_analysis(result.analysis_id)
        self.assertEqual(linked.analyses[0].analysis_id,result.analysis_id)
        path=self.service.build_experiment_dashboard().path
        before=path.read_bytes()
        result.artifacts[0].path.write_text('tampered')
        with self.assertRaises(InvalidExperimentError): self.service.build_experiment_dashboard()
        self.assertEqual(path.read_bytes(),before)

    def test_update_failure_does_not_hide_completed_analysis(self):
        self.service.register_experiment(self.record)
        with patch.object(self.service,'build_experiment_dashboard',side_effect=OSError('disk full')):
            result=self.run_analysis()
        self.assertIn('disk full',result.dashboard_warning)
        self.assertTrue(self.service.get_analysis(result.analysis_id).source_hashes_verified)
        self.assertTrue(self.service.build_experiment_dashboard().path.is_file())

    def test_reject_untrusted_folder_source_mismatch_and_symlink(self):
        with self.assertRaises(InvalidExperimentError):
            self.service.register_experiment(self.record.model_copy(update={'folder':Path('/')}))
        self.service.register_experiment(self.record.model_copy(update={'source_paths':(self.first,)}))
        result=self.run_analysis()
        self.assertIn('sources do not match',result.dashboard_warning)
        self.assertEqual(self.service.list_experiments().experiments[0].analyses,())
        path=self.artifacts/'experiment_registry'/'dashboard.html'
        path.symlink_to(self.first)
        before=sha256_file(self.first)
        with self.assertRaises(InvalidExperimentError): self.service.build_experiment_dashboard()
        self.assertEqual(sha256_file(self.first),before)

    def test_empty_dashboard_and_untrusted_text_escaped(self):
        self.assertEqual(self.service.build_experiment_dashboard().experiments,0)
        evil='</script><script>alert(1)</script>'
        self.service.register_experiment(self.record.model_copy(update={'title':evil}))
        html=self.service.build_experiment_dashboard().path.read_text()
        self.assertNotIn(evil,html)
        data=json.loads(html.split('id="data">')[1].split('</script>')[0])
        self.assertEqual(data[0]['title'],evil)
        self.assertEqual([c['od600'] for c in data[0]['conditions']],[None,0.01,0.1])


class ExperimentRecordToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_typed_registry_tool_calls(self):
        from ethoscopy_mcp.server import create_server
        fixture = ExperimentRecordsTests()
        fixture.setUp()
        self.addCleanup(fixture.tmp.cleanup)
        result = fixture.run_analysis()
        server = create_server(service=fixture.service)
        listed = {tool.name: tool for tool in await server.list_tools()}
        self.assertTrue(listed['list_experiments'].annotations.read_only_hint)
        self.assertFalse(listed['register_experiment'].annotations.read_only_hint)
        async def call(name, arguments):
            return await asyncio.wait_for(server.call_tool(name, arguments), timeout=30)
        registered = await call('register_experiment', {
            'record': fixture.record.model_dump(mode='json'), 'expected_revision': 0})
        self.assertEqual(registered.structured_content['revision'], 1)
        linked = await call('link_experiment_analysis', {'analysis_id': result.analysis_id})
        self.assertEqual(len(linked.structured_content['analyses']), 1)
        records = await call('list_experiments', {})
        self.assertEqual(records.structured_content['experiments'][0]['record']['recording_status'], 'unknown')
        dashboard = await call('build_experiment_dashboard', {})
        self.assertTrue(Path(dashboard.structured_content['path']).is_file())
