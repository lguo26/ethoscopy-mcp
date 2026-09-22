"""Synthetic public-library sleep workflow with deprivation QC and statistics."""
from pathlib import Path
import sys
import ethoscopy as etho
import pandas as pd
from ethoscopy_mcp import EthoscopyService, ExperimentManifest, NotebookSleepRecipe, Settings

def make_example(root):
    rows = []
    for i, fly in enumerate('abcd'):
        for t in range(0, 4*3600+1, 60):
            asleep = (t//600+i)%2 == 0
            if fly == 'c' and 3600 <= t < 7200:
                asleep = False  # Successful deprivation; d fails, controls stay.
            rows.append({'id':fly,'t':t,'asleep':asleep,'moving':True})
    meta = pd.DataFrame({'id':list('abcd'),'sex':['male']*4,'sleep_deprived':[False,False,True,True],
                         'baseline':[0]*4,'machine_name':['M1','M2','M3','M4']}).set_index('id')
    meta['date']='2025-06-04'
    meta['time']='09-00-00'
    meta['stimulus_range']='2025-06-04 10:00:00  2025-06-04 11:00:00'
    source = root/'sleep.pkl'
    etho.behavpy(pd.DataFrame(rows).set_index('id'),meta,check=True).to_pickle(source)
    mapping = meta.reset_index().rename(columns={'id':'original_id'})
    mapping['analysis_id']=mapping.original_id;mapping['canonical_machine']=mapping.machine_name
    mapping['roi']=1;mapping['date']='2025-06-04'
    mapping.to_csv(root/'mapping.csv',index=False)
    recipe=NotebookSleepRecipe.model_validate({
        'recipe_id':'synthetic-notebook-sleep','experiment_id':'synthetic-notebook-sleep','analysis_type':'sleep_notebook',
        'cohort_filters':{},'group':{'column':'sleep_deprived','levels':[{'value':False,'label':'control'},{'value':True,'label':'sleep deprived'}]},
        'identity_overlay':{'mapping_path':root/'mapping.csv','consistency_columns':['sex','sleep_deprived']},
        'baseline_alignment':{},'time_alignment':{'source_basis':'ZT','output_basis':'ZT','subtract_hours':0},
        'endpoint_policy':'untrimmed','profile_window':{'start_hours':0,'end_hours':4},
        'quantification_window':{'start_hours':2,'end_hours':3},
        'deprivation_qc':{'target_group_label':'sleep deprived','metadata':{'reference_hour':9},'maximum_sleep_fraction':.05},
        'comparison':{'group_labels':['control','sleep deprived'],'method':'exact'},
        'output_requests':[
            {'artifact_type':'table','format':'csv','name':d,'dataset':d}
            for d in ['individuals','comparison','timecourse','statistics','exclusions']]+[
            {'artifact_type':'plot','format':'pdf','name':'quantify','dataset':'comparison'},
            {'artifact_type':'plot','format':'svg','name':'overtime','dataset':'timecourse'},
            {'artifact_type':'plot','format':'png','name':'heatmap','dataset':'heatmap','group_label':'control'}]})
    (root/'runs').mkdir()
    return EthoscopyService(Settings.create([root],artifact_root=root/'runs')),ExperimentManifest(experiment_id='synthetic-notebook-sleep',source_paths=(source,)),recipe


if __name__ == "__main__":
    root = Path(sys.argv[1]).resolve()
    root.mkdir(parents=True, exist_ok=True)
    service, manifest, recipe = make_example(root)
    preview = service.preview_analysis(manifest, recipe)
    result = service.run_analysis(manifest, recipe, preview.recipe_hash)
    (root / "manifest.json").write_text(manifest.model_dump_json(indent=2))
    (root / "recipe.json").write_text(recipe.model_dump_json(indent=2))
    print(result.model_dump_json(indent=2))
