"""Persistent decisions: continuity, explicit overrides and approval invalidation."""
import asyncio
import json
from pathlib import Path
import shutil
import unittest

from ethoscopy_mcp import EthoscopyService
from ethoscopy_mcp.schemas import ExclusionDecisionRequest, AnimalExclusion, DecisionResolution
from ethoscopy_mcp.errors import InvalidExperimentError
import test_experiment_records as fixtures


class ReviewedDecisionTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ExperimentRecordsTests()
        self.f.setUp()
        self.addCleanup(self.f.tmp.cleanup)
        self.s = self.f.service
        import pandas as pd
        self.target = str(pd.read_csv(self.f.recipe.identity_overlay.mapping_path).iloc[0].original_id)
        self.request = ExclusionDecisionRequest(decision_id='reviewed-exclusion',
            exclusions=(AnimalExclusion(original_id=self.target,reason='Reviewed tracking failure'),),
            scope_description='Synthetic survival only',confirmed_by='Test researcher',
            confirmation_note='Explicit synthetic test decision')
        self.s.register_experiment(self.f.record)
        self.entry = self.s.record_exclusion_decision(self.f.manifest.experiment_id,self.request,1)

    def recipe(self, action='apply', revision=1):
        return self.f.recipe.model_copy(update={'decision_resolutions':(DecisionResolution(
            experiment_id=self.f.manifest.experiment_id,decision_id=self.request.decision_id,
            revision=revision,action=action,reason='Researcher reviewed this test resolution'),)})

    def test_missing_resolution_blocks_and_inspection_discovers(self):
        inspection=self.s.inspect_experiment(self.f.manifest)
        self.assertEqual(len(inspection.reviewed_exclusions),1)
        p=self.s.preview_analysis(self.f.manifest,self.f.recipe)
        self.assertFalse(p.ready_to_approve)
        self.assertEqual(p.decision_reviews[0].status,'unresolved')
        with self.assertRaisesRegex(InvalidExperimentError,'blocking'):
            self.s.run_analysis(self.f.manifest,self.f.recipe,p.recipe_hash)

    def test_apply_persists_across_service_and_exports_provenance(self):
        self.s=EthoscopyService(self.s.settings)
        recipe=self.recipe();p=self.s.preview_analysis(self.f.manifest,recipe)
        self.assertTrue(p.ready_to_approve)
        self.assertEqual(sum(c.individuals_with_data for c in p.cohorts),3)
        self.assertEqual(len(p.exclusions[0].source_ids),2)
        result=self.s.run_analysis(self.f.manifest,recipe,p.recipe_hash)
        provenance=json.loads(result.provenance_path.read_text())
        self.assertEqual(provenance['reviewed_exclusion_decisions'][0]['status'],'applied')
        self.assertEqual(provenance['recipe']['exclusions'][0]['original_id'],self.target)
        self.assertEqual(sum(g.animals for g in result.group_outcomes),3)

    def test_sensitivity_override_retains_animals_and_decision(self):
        recipe=self.recipe('sensitivity_include');p=self.s.preview_analysis(self.f.manifest,recipe)
        self.assertTrue(p.ready_to_approve)
        self.assertEqual(sum(c.individuals_with_data for c in p.cohorts),4)
        result=self.s.run_analysis(self.f.manifest,recipe,p.recipe_hash)
        prov=json.loads(result.provenance_path.read_text())
        self.assertEqual(prov['reviewed_exclusion_decisions'][0]['status'],'sensitivity_include')
        self.assertEqual(self.s.list_experiments().experiments[0].exclusion_decisions[0].status,'active')
        conflict=recipe.model_copy(update={'exclusions':self.request.exclusions})
        self.assertFalse(self.s.preview_analysis(self.f.manifest,conflict).ready_to_approve)

    def test_changed_decision_invalidates_approval_and_preserves_history(self):
        recipe=self.recipe();p=self.s.preview_analysis(self.f.manifest,recipe)
        revised=self.request.model_copy(update={'confirmation_note':'Additional review'})
        entry=self.s.record_exclusion_decision(self.f.manifest.experiment_id,revised,2)
        self.assertEqual([d.revision for d in entry.exclusion_decisions],[1,2])
        self.assertFalse(self.s.preview_analysis(self.f.manifest,recipe).ready_to_approve)
        with self.assertRaisesRegex(InvalidExperimentError,'hash'):
            self.s.run_analysis(self.f.manifest,recipe,p.recipe_hash)
        self.assertTrue(self.s.preview_analysis(self.f.manifest,self.recipe(revision=2)).ready_to_approve)
        # Ordinary work-record updates cannot erase decisions.
        entry=self.s.register_experiment(self.f.record,entry.revision)
        self.assertEqual(len(entry.exclusion_decisions),2)

    def test_matching_copies_and_new_names_cannot_bypass_decisions(self):
        paths=[]
        for p in self.f.manifest.source_paths:
            q=p.with_name('copy-'+p.name);shutil.copy2(p,q);paths.append(q)
        m=self.f.manifest.model_copy(update={'experiment_id':'renamed','source_paths':tuple(paths)})
        r=self.f.recipe.model_copy(update={'experiment_id':'renamed'})
        p=self.s.preview_analysis(m,r)
        self.assertFalse(p.ready_to_approve)
        self.assertEqual(p.decision_reviews[0].decision.experiment_id,self.f.manifest.experiment_id)

    def test_source_change_requires_reconfirmation(self):
        import pandas as pd
        data=pd.read_pickle(self.f.first);data.iloc[0,data.columns.get_loc('moving')]=False;data.to_pickle(self.f.first)
        p=self.s.preview_analysis(self.f.manifest,self.recipe())
        self.assertEqual(p.decision_reviews[0].status,'source_changed')
        self.assertFalse(p.ready_to_approve)
        self.s.record_exclusion_decision(self.f.manifest.experiment_id,self.request,2)
        self.assertTrue(self.s.preview_analysis(self.f.manifest,self.recipe(revision=2)).ready_to_approve)

    def test_outside_cohort_retirement_and_revision_conflicts(self):
        r=self.f.recipe.model_copy(update={'cohort_filters':{'infection':False},
            'group':self.f.recipe.group.model_copy(update={'levels':tuple(l for l in self.f.recipe.group.levels if l.value is False)})})
        p=self.s.preview_analysis(self.f.manifest,r)
        self.assertEqual(p.decision_reviews[0].status,'outside_cohort')
        self.assertTrue(p.ready_to_approve)
        with self.assertRaisesRegex(InvalidExperimentError,'Revision conflict'):
            self.s.record_exclusion_decision(self.f.manifest.experiment_id,self.request,1)
        retired=self.request.model_copy(update={'status':'retired','confirmation_note':'Explicit withdrawal'})
        self.s.record_exclusion_decision(self.f.manifest.experiment_id,retired,2)
        p=self.s.preview_analysis(self.f.manifest,self.f.recipe)
        self.assertTrue(p.ready_to_approve)
        self.assertEqual(p.decision_reviews[0].status,'retired')

    def test_invalid_ids_and_unknown_resolution_rejected(self):
        bad=self.request.model_copy(update={'exclusions':(AnimalExclusion(original_id='absent',reason='test'),)})
        with self.assertRaisesRegex(InvalidExperimentError,'absent'):
            self.s.record_exclusion_decision(self.f.manifest.experiment_id,bad,2)
        r=self.recipe();r=r.model_copy(update={'decision_resolutions':(r.decision_resolutions[0].model_copy(update={'decision_id':'unknown'}),)})
        with self.assertRaisesRegex(ValueError,'unknown'):
            self.s.preview_analysis(self.f.manifest,r)


class DecisionToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_transport_schema_and_record_tool(self):
        from ethoscopy_mcp.server import create_server
        f=fixtures.ExperimentRecordsTests();f.setUp();self.addCleanup(f.tmp.cleanup)
        f.service.register_experiment(f.record)
        server=create_server(service=f.service)
        listed={t.name:t for t in await server.list_tools()}
        self.assertIn('record_exclusion_decision',listed)
        import pandas as pd
        target=str(pd.read_csv(f.recipe.identity_overlay.mapping_path).iloc[0].original_id)
        request=ExclusionDecisionRequest(decision_id='test',exclusions=(AnimalExclusion(original_id=target,reason='test'),),scope_description='test',confirmed_by='Researcher',confirmation_note='Explicit test')
        result=await asyncio.wait_for(server.call_tool('record_exclusion_decision',{
            'experiment_id':f.manifest.experiment_id,'decision':request.model_dump(mode='json'),'expected_revision':1}),30)
        self.assertEqual(result.structured_content['exclusion_decisions'][0]['revision'],1)
