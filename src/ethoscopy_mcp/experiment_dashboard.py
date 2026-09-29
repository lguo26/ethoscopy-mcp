"""Offline registry dashboard. All user text is escaped; plots are verified PNGs."""
from datetime import datetime, timezone
import base64
import json
import os

from ethoscopy_mcp.experiment_records import DashboardResult, atomic_write


def build_dashboard(store, verify_run):
    with store.locked() as (_, entries):
        path = store.directory() / 'dashboard.html'
        data = []
        for entry in entries:
            item = entry.record.model_dump(mode='json')
            item['revision'] = entry.revision
            item['analyses'] = []
            for saved in entry.analyses:
                run = verify_run(saved.analysis_id)
                if run.experiment_id != entry.record.experiment_id or run.recipe_hash != saved.recipe_hash:
                    raise ValueError('Registered run identity changed')
                plots = []
                for artifact in run.artifacts:
                    if artifact.artifact_type == 'plot' and artifact.format == 'png':
                        plots.append({'name': artifact.name, 'src': 'data:image/png;base64,' + base64.b64encode(artifact.path.read_bytes()).decode('ascii')})
                item['analyses'].append({'id': run.analysis_id, 'recipe': run.recipe_id,
                    'groups': [g.model_dump() for g in run.group_outcomes], 'plots': plots,
                    'artifacts': [{'name': a.name, 'href': os.path.relpath(a.path, path.parent)} for a in run.artifacts]})
            data.append(item)
        now = datetime.now(timezone.utc)
        payload = json.dumps(data, ensure_ascii=False).replace('<', '\\u003c')
        atomic_write(path, HTML.replace('__DATE__', now.isoformat()).replace('__DATA__', payload))
        return DashboardResult(path=path, experiments=len(data),
            conditions=sum(len(e.record.conditions) for e in entries), built_at=now)


HTML = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Ethoscopy experiment dashboard</title><style>
*{box-sizing:border-box}body{margin:0;background:#f2f6f4;color:#193b3c;font:15px/1.5 system-ui,sans-serif}header{background:#193f40;color:white;padding:30px max(24px,calc((100vw - 1200px)/2))}h1{margin:8px 0;font-size:32px}main{max-width:1248px;margin:auto;padding:24px}a{color:#08696c}button,input,select{font:inherit;padding:9px;border:1px solid #b5ccc5;border-radius:5px;background:white}label{font-size:12px;display:grid;gap:5px}.filters{display:flex;gap:12px;flex-wrap:wrap;align-items:end;padding:18px;background:white;border-radius:10px}.filters label:first-child{flex:1;min-width:180px}.cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.card,.treebox{background:white;border:1px solid #dae5de;border-radius:10px;padding:22px;margin:18px 0;min-width:0}.card{scroll-margin-top:15px}.badge{display:inline-block;background:#edf2ef;border-radius:5px;padding:5px 9px;margin:3px;font-size:12px}.saved{background:#e2f4e8}.small{font-size:12px;color:#587169}summary{cursor:pointer}.treebox ul{list-style:none;margin:10px 0;padding-left:22px;border-left:1px solid #b9d2c8}.treebox li{margin:8px 0;padding-left:6px}.treebox a{overflow-wrap:anywhere}.table{overflow:auto}table{border-collapse:collapse;width:100%;font-size:12px}td,th{padding:8px;text-align:left;border-bottom:1px solid #e2ebe6}img{width:100%;height:auto;border:1px solid #e4ebe6}h2{font-size:20px;margin:0 0 10px}h3{font-size:15px}.actions{background:#f0f6f2;padding:12px;border-radius:5px}.plot{display:block;margin-top:12px}.notes{white-space:pre-wrap;overflow-wrap:anywhere}button{cursor:pointer}a:focus-visible,button:focus-visible,summary:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #b38322;outline-offset:2px}@media(max-width:700px){.cards{grid-template-columns:1fr}main{padding:14px}.card{padding:15px}.treebox{padding:12px}}
</style></head><body><header><div>ETHOSCOPY · LOCAL EXPERIMENT REGISTRY</div><h1>Experiment work records</h1><p>Conditions, verified analyses and next actions.</p></header><main><p>Recording status is supplied explicitly. Saved analyses do not establish that acquisition has finished. Related conditions are not automatically pooled.</p><section class="filters" aria-label="Filters"><label>Search<input id="search" type="search" placeholder="Treatment, question, notes…"></label><label>Date<select id="date"><option value="">All dates</option></select></label><label>Food<select id="food"><option value="">All foods</option></select></label><label>Temperature<select id="temp"><option value="">All temperatures</option></select></label><label>Method<select id="method"><option value="">All methods</option></select></label><button id="reset">Reset</button></section><p id="status" role="status" aria-live="polite"></p><details class="treebox" open><summary><strong>Condition connections</strong></summary><p class="small">Method → food → temperature → treatment → OD600 → date / sex. Controls omit dose. Missing doses remain unrecorded. Leaves show planned counts; verified analysis counts are listed separately by run.</p><button id="expand">Expand branches</button> <button id="collapse">Collapse branches</button><div id="tree"></div></details><div class="cards" id="cards"></div><footer class="small">Built __DATE__. Refresh the browser after the dashboard rebuilds. Figures show their original full analysis cohorts; filters do not redraw them.</footer></main><script type="application/json" id="data">__DATA__</script><script>
'use strict';
const data=JSON.parse(document.getElementById('data').textContent),$=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const temp=c=>c.temperature_c==null?'Unrecorded':c.temperature_c+' °C';
for(const [id,values] of [['date',data.map(e=>e.experiment_date||'Unrecorded')],['food',data.flatMap(e=>e.conditions.map(c=>c.food||'Unrecorded'))],['temp',data.flatMap(e=>e.conditions.map(temp))],['method',data.flatMap(e=>e.conditions.map(c=>c.method))]])for(const v of [...new Set(values)].sort()){const o=document.createElement('option');o.value=v;o.textContent=v;$(id).append(o)}
function match(e,c){return (!$('date').value||$('date').value===(e.experiment_date||'Unrecorded'))&&(!$('food').value||$('food').value===(c.food||'Unrecorded'))&&(!$('temp').value||$('temp').value===temp(c))&&(!$('method').value||$('method').value===c.method)&&(!$('search').value.trim()||JSON.stringify([e.title,e.question,e.notes,e.next_action,c]).toLowerCase().includes($('search').value.trim().toLowerCase()))}
function render(){const root=Object.create(null);let total=0;const cards=[];for(const e of [...data].sort((a,b)=>(b.experiment_date||'').localeCompare(a.experiment_date||''))){const rows=e.conditions.filter(c=>match(e,c));const emptyMatch=!e.conditions.length&&match(e,{method:'',food:null,temperature_c:null});if(!rows.length&&!emptyMatch)continue;total+=rows.length;
for(const c of rows){let node=root;const path=[c.method,c.food||'Food unrecorded',temp(c),c.treatment];if(!c.is_control)path.push(c.od600==null?'OD600 unrecorded':'OD600 '+c.od600);for(const label of path)node=node[label]??=Object.create(null);const leaf=(e.experiment_date||'Date unrecorded')+' · '+(c.sex||'sex unrecorded')+' · planned n='+(c.planned_n??'?')+' · '+c.condition_id+' · '+e.experiment_id;node[leaf]={target:e.experiment_id}}
cards.push(`<article class="card" id="exp-${esc(e.experiment_id)}"><h2>${esc(e.title)}</h2><p class="small">${esc(e.experiment_date||'Date unrecorded')} · revision ${e.revision}</p><span class="badge">Recording · ${esc(e.recording_status)}</span><span class="badge">Review · ${esc(e.review_status)}</span><span class="badge saved">Analysis · ${e.analyses.length?'verified outputs':'awaiting analysis'}</span><p>${esc(e.question)}</p><div class="table"><table><tr><th>Treatment</th><th>Food</th><th>Temperature</th><th>Sex</th><th>OD600</th><th>Planned</th></tr>${rows.map(c=>`<tr><td>${esc(c.treatment)}</td><td>${esc(c.food||'Unrecorded')}</td><td>${esc(temp(c))}</td><td>${esc(c.sex||'Unrecorded')}</td><td>${c.is_control?'—':esc(c.od600??'Unrecorded')}</td><td>${esc(c.planned_n??'?')}</td></tr>`).join('')}</table></div><p class="actions"><strong>Next action</strong><br>${esc(e.next_action||'Not recorded')}</p><details><summary>Notes and OA route</summary><p class="notes">${esc(e.notes)}</p>${rows.map(c=>`<p class="small">${esc(c.treatment)} · OA route: ${esc(c.oa_route||'Not recorded')}</p>`).join('')}</details>${e.analyses.map(r=>`<details open><summary>Analysis: ${esc(r.recipe)}</summary><p class="small">${esc(r.id)} · full run counts; do not sum across overlapping recipes</p>${r.groups.length?`<div class="table"><table><tr><th>Group</th><th>Animals</th><th>Deaths</th><th>Censored</th></tr>${r.groups.map(g=>`<tr><td>${esc(g.label)}</td><td>${g.animals}</td><td>${g.detected_deaths}</td><td>${g.censored}</td></tr>`).join('')}</table></div>`:'<p class="small">See exported tables for analysis-specific counts.</p>'}${r.plots.map(p=>`<div class="plot"><img loading="lazy" src="${p.src}" alt="${esc(p.name)}"></div>`).join('')}<details><summary>Result files</summary>${r.artifacts.map(a=>`<p><a href="${esc(a.href)}">${esc(a.name)}</a></p>`).join('')}</details></details>`).join('')}</article>`)}
function draw(n,depth=0){return '<ul>'+Object.entries(n).map(([label,ch])=>'<li>'+(typeof ch.target==='string'?`<a href="#exp-${esc(ch.target)}">${esc(label)}</a>`:`<details ${depth<2?'open':''}><summary>${esc(label)}</summary>${draw(ch,depth+1)}</details>` )+'</li>').join('')+'</ul>'}
$('tree').innerHTML=Object.keys(root).length?draw(root):'<p>No matching registered conditions.</p>';$('cards').innerHTML=cards.join('')||'<p>No matching experiments. Register an experiment to get started.</p>';$('status').textContent=cards.length+' experiments · '+total+' conditions shown';}
['date','food','temp','method','search'].forEach(id=>$(id).addEventListener(id==='search'?'input':'change',render));$('reset').onclick=()=>{['date','food','temp','method','search'].forEach(id=>$(id).value='');render()};$('expand').onclick=()=>$('tree').querySelectorAll('details').forEach(d=>d.open=true);$('collapse').onclick=()=>$('tree').querySelectorAll('details').forEach(d=>d.open=false);render();
</script></body></html>'''
