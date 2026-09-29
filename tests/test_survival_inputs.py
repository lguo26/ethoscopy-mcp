"""Synthetic regression coverage for exclusions, metadata corrections and plots."""
from pathlib import Path
import json
import tempfile
import unittest

import matplotlib.pyplot as plt
import pandas as pd
from pydantic import ValidationError

from ethoscopy_mcp import EthoscopyService, ExperimentManifest, Settings
from ethoscopy_mcp.errors import InvalidExperimentError
from ethoscopy_mcp.execution import _run_recipe, _style_figure
from ethoscopy_mcp.registry import sha256_file
from ethoscopy_mcp.schemas import AnimalExclusion, MetadataCSV, MetadataCorrection, OutputRequest, SurvivalRecipe
from test_preview import _write_transfer_fixture, _survival_recipe


class SurvivalInputTests(unittest.TestCase):
    def fixture(self, root):
        first, second, mapping_path = _write_transfer_fixture(root)
        for path in (first, second):
            frame = pd.read_pickle(path)
            frame.meta['temperature'] = 25
            frame.meta['food'] = 'normal_food'
            frame.to_pickle(path)
        mapping = pd.read_csv(mapping_path)
        mapping['temperature'] = 25
        mapping['food'] = 'normal_food'
        mapping.to_csv(mapping_path, index=False)
        (root/'runs').mkdir()
        service = EthoscopyService(Settings.create([root], artifact_root=root/'runs'))
        manifest = ExperimentManifest(experiment_id='synthetic-transfer', source_paths=(first,second))
        recipe = _survival_recipe(mapping_path).model_copy(update={'output_requests': (
            OutputRequest(artifact_type='table', format='csv', name='individuals', dataset='individuals'),
            OutputRequest(artifact_type='table', format='csv', name='curves', dataset='kaplan_meier'),
            OutputRequest(artifact_type='plot', format='svg', name='survival'),
        )})
        return service, manifest, recipe, mapping

    def test_excludes_whole_transferred_animal_and_exports_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service, manifest, recipe, mapping = self.fixture(root)
            hashes = {p:sha256_file(p) for p in (*manifest.source_paths, recipe.identity_overlay.mapping_path)}
            target = mapping.iloc[4].original_id  # Later segment of the first animal.
            recipe = recipe.model_copy(update={'exclusions':(AnimalExclusion(original_id=target,reason='tracking failure'),)})
            preview = service.preview_analysis(manifest, recipe)
            self.assertEqual(sum(c.individuals_with_data for c in preview.cohorts),3)
            self.assertEqual(len(preview.exclusions),1)
            self.assertEqual(len(preview.exclusions[0].source_ids),2)
            self.assertIn('exclusions.csv',[a.name for a in preview.expected_artifacts])
            run = service.run_analysis(manifest,recipe,preview.recipe_hash)
            artifacts = {a.name:a.path for a in run.artifacts}
            excluded = pd.read_csv(artifacts['exclusions.csv'])
            self.assertEqual(len(excluded),2)
            self.assertTrue(excluded.reason.eq('tracking failure').all())
            endpoints = pd.read_csv(artifacts['individuals'])
            self.assertEqual(len(endpoints),3)
            self.assertFalse(endpoints.id.isin(excluded.analysis_id).any())
            curves = pd.read_csv(artifacts['curves'])
            self.assertEqual(int(curves.n_events.sum()+curves.n_censored.sum()),3)
            self.assertEqual(sum(g.animals for g in run.group_outcomes),3)
            self.assertEqual(json.loads(run.provenance_path.read_text())['exclusions'][0]['reason'],'tracking failure')
            changed = recipe.model_copy(update={'exclusions':(AnimalExclusion(original_id=target,reason='revised reason'),)})
            with self.assertRaises(InvalidExperimentError):
                service.run_analysis(manifest,changed,preview.recipe_hash)
            for path,digest in hashes.items():self.assertEqual(sha256_file(path),digest)

    def test_unknown_duplicate_and_outside_cohort_exclusions_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            service,manifest,recipe,mapping = self.fixture(Path(directory))
            for ids in [('unknown',),(mapping.iloc[0].original_id,mapping.iloc[4].original_id)]:
                bad=recipe.model_copy(update={'exclusions':tuple(AnimalExclusion(original_id=i,reason='reason') for i in ids)})
                with self.assertRaises(InvalidExperimentError):service.preview_analysis(manifest,bad)
            bad=recipe.model_copy(update={'cohort_filters':{'infection':False},'exclusions':(AnimalExclusion(original_id=mapping.iloc[0].original_id,reason='reason'),)})
            with self.assertRaises(InvalidExperimentError):service.preview_analysis(manifest,bad)
        with self.assertRaises(ValidationError):AnimalExclusion(original_id='a',reason='  ')

    def test_mapping_disagreement_blocks_even_without_explicit_consistency_column(self):
        with tempfile.TemporaryDirectory() as directory:
            service,manifest,recipe,mapping=self.fixture(Path(directory))
            mapping['temperature']=29
            mapping.to_csv(recipe.identity_overlay.mapping_path,index=False)
            preview=service.preview_analysis(manifest,recipe)
            self.assertFalse(preview.ready_to_approve)
            conflict=preview.metadata_conflicts[0]
            self.assertEqual((conflict.source,conflict.column,conflict.mismatched_rows),('identity_mapping','temperature',8))
            self.assertEqual(len(conflict.example_ids),5)
            with self.assertRaises(InvalidExperimentError):service.run_analysis(manifest,recipe,preview.recipe_hash)

    def test_csv_corrections_are_hashed_applied_and_audited_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            service,manifest,recipe,mapping=self.fixture(root)
            path=root/'metadata.csv'
            mapping[['original_id','temperature']].assign(temperature=29).to_csv(path,index=False)
            recipe=recipe.model_copy(update={'metadata_csv':MetadataCSV(path=path,key_columns=('original_id',))})
            preview=service.preview_analysis(manifest,recipe)
            self.assertFalse(preview.ready_to_approve)
            self.assertEqual(preview.metadata_conflicts[0].source,'metadata_csv')
            hashes={p:sha256_file(p) for p in (*manifest.source_paths,recipe.identity_overlay.mapping_path,path)}
            corrections=tuple(MetadataCorrection(original_id=i,column='temperature',value=29,reason='confirmed incubator') for i in mapping.original_id)
            recipe=recipe.model_copy(update={'metadata_corrections':corrections,'cohort_filters':{'temperature':29}})
            approved=service.preview_analysis(manifest,recipe)
            self.assertTrue(approved.ready_to_approve)
            self.assertFalse(approved.metadata_conflicts)
            self.assertEqual(len(approved.metadata_corrections),8)
            self.assertNotIn('survival_review.csv',[a.name for a in approved.expected_artifacts])
            run=service.run_analysis(manifest,recipe,approved.recipe_hash)
            artifacts={a.name:a.path for a in run.artifacts}
            self.assertTrue(pd.read_csv(artifacts['individuals']).temperature.eq(29).all())
            audit=pd.read_csv(artifacts['metadata_corrections.csv'])
            self.assertEqual(len(audit),8)
            self.assertTrue(audit.source_value.eq(25).all())
            self.assertTrue(audit.confirmed_value.eq(29).all())
            self.assertIn('29 °C',artifacts['survival'].read_text())
            for p,digest in hashes.items():self.assertEqual(sha256_file(p),digest)
            path.write_text(path.read_text().replace('29','30'))
            with self.assertRaises(InvalidExperimentError):service.run_analysis(manifest,recipe,approved.recipe_hash)

    def test_csv_join_errors_and_identity_corrections_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            service,manifest,recipe,mapping=self.fixture(root)
            path=root/'metadata.csv'
            for frame in (mapping.iloc[:-1],pd.concat([mapping,mapping.iloc[:1]])):
                frame.to_csv(path,index=False)
                bad=recipe.model_copy(update={'metadata_csv':MetadataCSV(path=path,key_columns=('original_id',))})
                with self.assertRaises(InvalidExperimentError):service.preview_analysis(manifest,bad)
            bad=recipe.model_copy(update={'metadata_corrections':(MetadataCorrection(original_id=mapping.iloc[0].original_id,column='date',value='2026-01-01',reason='test'),)})
            with self.assertRaises(InvalidExperimentError):service.preview_analysis(manifest,bad)

    def test_titles_hide_internal_filters_and_preserve_time_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            service,manifest,recipe,mapping=self.fixture(Path(directory))
            mapping['include_survival']=True
            mapping.to_csv(recipe.identity_overlay.mapping_path,index=False)
            recipe=recipe.model_copy(update={'cohort_filters':{'include_survival':True,'temperature':25}})
            preview=service.preview_analysis(manifest,recipe)
            _,figure=_run_recipe(preview,recipe)
            axis=figure.axes[0]
            self.assertEqual(axis.get_title(),'Survival — male — normal food — 25 °C')
            self.assertEqual(axis.get_xlabel(),'Days from first recorded sample')
            self.assertTrue(any('n = 2' in t.get_text() for t in axis.get_legend().get_texts()))
            plt.close(figure)
            custom=recipe.model_copy(update={'plot_title':'Treatment comparison at 25°C'})
            _,figure=_run_recipe(service.preview_analysis(manifest,custom),custom)
            self.assertEqual(figure.axes[0].get_title(),custom.plot_title)
            plt.close(figure)

    def test_long_legend_and_title_fit_inside_export(self):
        figure,axis=plt.subplots()
        for i in range(8):axis.plot([0,1],[1,0],label=f'Treatment {i}: a long scientific label with dose and sample size (n=20)')
        axis.set_title('A readable scientific plot title with experimental context ' * 2)
        _style_figure(figure)
        figure.canvas.draw()
        renderer=figure.canvas.get_renderer()
        for artist in (axis.title,axis.get_legend()):
            box=artist.get_window_extent(renderer).transformed(figure.transFigure.inverted())
            self.assertGreaterEqual(box.x0,0)
            self.assertGreaterEqual(box.y0,0)
            self.assertLessEqual(box.x1,1)
            self.assertLessEqual(box.y1,1)
        plt.close(figure)


if __name__=='__main__':unittest.main()
