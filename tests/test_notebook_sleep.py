from pathlib import Path
import tempfile
import unittest

import ethoscopy as etho
import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

from ethoscopy_mcp import EthoscopyService, ExperimentManifest, NotebookSleepRecipe, Settings
from ethoscopy_mcp.errors import InvalidExperimentError
from ethoscopy_mcp.schemas import MetadataExclusion, SleepDeprivationQC


def fixture(root):
    rows = []
    for i, fly in enumerate('abcd'):
        for t in range(0, 4*3600+1, 60):
            asleep = (t//600+i)%2 == 0
            if fly == 'c' and 3600 <= t < 7200:
                asleep = False  # Successful deprivation; d fails, controls stay.
            rows.append({'id':fly,'t':t,'asleep':asleep,'moving':True})
    meta = pd.DataFrame({'id':list('abcd'),'sex':['male']*4,'sleep_deprived':[False,False,True,True],
                         'baseline':[0]*4,'machine_name':['M1','M2','M3','M4']}).set_index('id')
    source = root/'sleep.pkl'
    etho.behavpy(pd.DataFrame(rows).set_index('id'),meta,check=True).to_pickle(source)
    mapping = meta.reset_index().rename(columns={'id':'original_id'})
    mapping['analysis_id']=mapping.original_id;mapping['canonical_machine']=mapping.machine_name
    mapping['roi']=1;mapping['date']='2025-06-04'
    mapping.to_csv(root/'mapping.csv',index=False)
    recipe=NotebookSleepRecipe.model_validate({
        'recipe_id':'notebook-test','experiment_id':'notebook-test','analysis_type':'sleep_notebook',
        'cohort_filters':{},'group':{'column':'sleep_deprived','levels':[{'value':False,'label':'control'},{'value':True,'label':'sleep deprived'}]},
        'identity_overlay':{'mapping_path':root/'mapping.csv','consistency_columns':['sex','sleep_deprived']},
        'baseline_alignment':{},'time_alignment':{'source_basis':'ZT','output_basis':'ZT','subtract_hours':0},
        'endpoint_policy':'untrimmed','profile_window':{'start_hours':0,'end_hours':4},
        'quantification_window':{'start_hours':2,'end_hours':3},
        'comparison':{'group_labels':['control','sleep deprived'],'method':'exact'},
        'output_requests':[
            {'artifact_type':'table','format':'csv','name':d,'dataset':d}
            for d in ['individuals','comparison','timecourse','statistics','exclusions']]+[
            {'artifact_type':'plot','format':'pdf','name':'quantify','dataset':'comparison'},
            {'artifact_type':'plot','format':'svg','name':'overtime','dataset':'timecourse'},
            {'artifact_type':'plot','format':'png','name':'heatmap','dataset':'heatmap','group_label':'control'}]})
    (root/'runs').mkdir()
    return EthoscopyService(Settings.create([root],artifact_root=root/'runs')),ExperimentManifest(experiment_id='notebook-test',source_paths=(source,)),recipe


class NotebookSleepTests(unittest.TestCase):
    def test_direct_library_quantification_statistics_and_all_artifacts(self):
        import matplotlib.pyplot as plt
        with tempfile.TemporaryDirectory() as directory:
            service,manifest,recipe=fixture(Path(directory))
            direct=pd.read_pickle(manifest.source_paths[0]).baseline(column='baseline')
            fig,expected=direct.t_filter(start_time=2,end_time=3).plot_quantify(variable='asleep',facet_col='sleep_deprived',facet_arg=[False,True],facet_labels=['control','sleep deprived'])
            plt.close(fig)
            preview=service.preview_analysis(manifest,recipe)
            self.assertTrue(preview.ready_to_approve)
            result=service.run_analysis(manifest,recipe,preview.recipe_hash)
            actual=pd.read_csv(result.run_directory/'individuals.csv')
            for label in ['control','sleep deprived']:
                np.testing.assert_allclose(sorted(actual.loc[actual.comparison_group.eq(label),'asleep_mean']),sorted(expected.loc[expected.sleep_deprived.eq(label),'asleep_mean']))
            test=pd.read_csv(result.run_directory/'statistics.csv').iloc[0]
            expected_test=mannwhitneyu(expected.loc[expected.sleep_deprived.eq('control'),'asleep_mean'],expected.loc[expected.sleep_deprived.eq('sleep deprived'),'asleep_mean'],method='exact')
            self.assertEqual(test.statistic_U,expected_test.statistic)
            self.assertAlmostEqual(test.p_value,expected_test.pvalue)
            self.assertEqual(len(result.artifacts),9)
            self.assertTrue(service.get_analysis(result.analysis_id).reused_existing)

    def test_deprivation_qc_removes_only_failed_deprived_fly(self):
        with tempfile.TemporaryDirectory() as directory:
            service,manifest,recipe=fixture(Path(directory))
            recipe=recipe.model_copy(update={'deprivation_qc':SleepDeprivationQC(target_group_label='sleep deprived',window={'start_hours':1,'end_hours':2})})
            preview=service.preview_analysis(manifest,recipe)
            self.assertEqual({x.label:x.individuals_with_data for x in preview.cohorts},{'control':2,'sleep deprived':1})
            result=service.run_analysis(manifest,recipe,preview.recipe_hash)
            audit=pd.read_csv(result.run_directory/'exclusions.csv')
            self.assertEqual(int(audit.excluded.sum()),1)
            self.assertEqual(audit.loc[audit.excluded,'group'].tolist(),['sleep deprived'])
            self.assertIn('Percent Asleep > 0.05',audit.loc[audit.excluded,'exclusion_reason'].iloc[0])
            self.assertTrue(audit.loc[audit.group.eq('control'),'qc_sleep_fraction'].isna().all())

    def test_explicit_machine_exclusion_and_curation(self):
        with tempfile.TemporaryDirectory() as directory:
            service,manifest,recipe=fixture(Path(directory))
            recipe=recipe.model_copy(update={'endpoint_policy':'curate','exclusions':(
                MetadataExclusion(column='machine_name',values=('M1',),reason='reviewed equipment failure'),)})
            preview=service.preview_analysis(manifest,recipe)
            self.assertEqual({x.label:x.individuals_with_data for x in preview.cohorts},{'control':1,'sleep deprived':2})
            result=service.run_analysis(manifest,recipe,preview.recipe_hash)
            audit=pd.read_csv(result.run_directory/'exclusions.csv')
            self.assertEqual(int(audit.excluded.sum()),1)

    def test_qc_threshold_is_strict_greater_than(self):
        from ethoscopy_mcp.notebook_sleep import apply_notebook_qc
        with tempfile.TemporaryDirectory() as directory:
            _,_,recipe=fixture(Path(directory))
            data=pd.DataFrame({'id':['target']*21+['control']*21,'t':list(range(0,1260,60))*2,
                               'asleep':[True]+[False]*20+[True]*21}).set_index('id')
            meta=pd.DataFrame({'id':['target','control'],'group':['sleep deprived','control'],
                               'comparison_group':['sleep deprived','control']}).set_index('id')
            working=etho.behavpy(data,meta,check=True)
            recipe=recipe.model_copy(update={'deprivation_qc':SleepDeprivationQC(target_group_label='sleep deprived',window={'start_hours':0,'end_hours':1})})
            kept,audit=apply_notebook_qc(working,recipe)
            self.assertEqual(set(kept.index),{'target','control'})
            self.assertAlmostEqual(audit.set_index('subject_id').loc['target','qc_sleep_fraction'],.05)

    def test_qc_missing_window_is_not_a_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            service,manifest,recipe=fixture(Path(directory))
            recipe=recipe.model_copy(update={'deprivation_qc':SleepDeprivationQC(target_group_label='sleep deprived',window={'start_hours':48,'end_hours':72})})
            with self.assertRaises(InvalidExperimentError): service.preview_analysis(manifest,recipe)

    def test_metadata_without_recording_is_audited(self):
        with tempfile.TemporaryDirectory() as directory:
            service,manifest,recipe=fixture(Path(directory))
            frame=pd.read_pickle(manifest.source_paths[0])
            missing=etho.behavpy(pd.DataFrame(frame.loc[frame.index != 'b']),frame.meta,check=False)
            missing.to_pickle(manifest.source_paths[0])
            preview=service.preview_analysis(manifest,recipe)
            self.assertEqual({x.label:x.individuals_with_data for x in preview.cohorts},{'control':1,'sleep deprived':2})
            result=service.run_analysis(manifest,recipe,preview.recipe_hash)
            audit=pd.read_csv(result.run_directory/'exclusions.csv')
            self.assertEqual(int(audit.excluded.sum()),1)
            self.assertIn('recording observations missing',audit.loc[audit.excluded,'exclusion_reason'].iloc[0])

    def test_survival_cannot_mislabel_sleep_outputs(self):
        from pydantic import ValidationError
        from test_preview import _survival_recipe
        from ethoscopy_mcp.schemas import SurvivalRecipe
        recipe = _survival_recipe(Path("/tmp/mapping.csv")).model_dump(mode="json")
        recipe["output_requests"][0]["dataset"] = "statistics"
        with self.assertRaises(ValidationError): SurvivalRecipe.model_validate(recipe)
