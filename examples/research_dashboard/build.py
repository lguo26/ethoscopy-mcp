"""Build a two-page research dashboard from trusted, explicitly selected local files."""
from pathlib import Path
import argparse, hashlib, html, json, re
from urllib.parse import quote, unquote, urlsplit

HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, default=HERE/'source', help='Trusted source directory with index.html and reference_results.html')
parser.add_argument('--output',type=Path,default=HERE/'generated',help='Generated site directory; never a source directory')
args=parser.parse_args()
B=args.source.resolve(strict=True)
OUT=args.output.resolve()
if OUT == B or B.is_relative_to(OUT) or OUT.is_relative_to(B):
    parser.error('Source and output directories must not overlap')
try:
    import markdown as markdown_library
except ImportError:
    parser.error('Install the dashboard extra: python -m pip install -e ".[dashboard]"')
PAGES={'index.html':'index.html','reference_results.html':'reference_results.html'}
ALLOWED={'.md','.csv','.png','.svg','.css'}
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'assets').mkdir(exist_ok=True)
manifest=[]; copied={}; figures={}; documents={}; archive_links=[]

def allowed(p):
    return p.is_relative_to(B) and p.is_file() and p.suffix.lower() in ALLOWED and p.stat().st_size<=10_000_000

def markdown(text):
    return markdown_library.markdown(text,extensions=['tables','fenced_code','toc','sane_lists'])

def bundle(relative):
    p=(B/relative).resolve(strict=True)
    if p in copied:return copied[p]
    if not allowed(p):raise ValueError('Unexpected dashboard asset: '+str(relative))
    raw=p.read_bytes();digest=hashlib.sha256(raw).hexdigest()
    ext='.html' if p.suffix=='.md' else p.suffix
    name=digest[:16]+'-'+p.stem+ext
    url='assets/'+quote(name)
    copied[p]=url  # Register before traversing report links, which can form cycles.
    if p.suffix=='.md':
        body=markdown(p.read_text())
        def relocate(m):
            attr,value=m.group(1),html.unescape(m.group(2))
            parsed=urlsplit(value)
            if parsed.scheme in {'https','http','mailto'} or value.startswith('#'):return m.group(0)
            target=(p.parent/unquote(parsed.path)).resolve()
            if not parsed.scheme and allowed(target):
                link='../'+bundle(str(target))
                if parsed.fragment:link+='#'+quote(unquote(parsed.fragment))
                return attr+'="'+html.escape(link,quote=True)+'"'
            archive_links.append({'report':str(p.relative_to(B)),'target':value})
            return 'class="archive-only" title="Available only in the local analysis archive"' if attr=='href' else 'alt="Figure available only in the local analysis archive"'
        body=re.sub(r'(href|src)="([^"]*)"',relocate,body)
        # Tables scroll independently on small screens; report figures open the viewer.
        body=body.replace('<table>','<div class="report-table"><table>').replace('</table>','</table></div>')
        body=re.sub(r'<img ([^>]*src="([^"]+)"[^>]*)/?>',lambda m:'<a href="'+m.group(2)+'">'+m.group(0)+'</a>',body)
        title=re.search(r'^#\s+(.+)',p.read_text(),re.M)
        title=title.group(1) if title else p.stem
        back='reference_results.html' if 'reference' in p.relative_to(B).parts else 'index.html'
        raw=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><style>
:root{{font:16px/1.7 system-ui,sans-serif;color:#182c32;background:#f2f5f4}}*{{box-sizing:border-box}}body{{margin:0}}nav{{background:#153a3c;padding:20px max(20px,calc((100vw - 1040px)/2));display:flex;gap:24px;flex-wrap:wrap}}nav a{{color:#d5eee6}}main{{max-width:1080px;margin:24px auto;padding:28px;background:white;border:1px solid #dce5e1;border-radius:12px}}h1{{font-size:clamp(25px,4vw,36px);line-height:1.25}}h2,h3{{line-height:1.35;margin-top:1.7em}}a{{color:#086466;overflow-wrap:anywhere}}a:focus-visible,button:focus-visible{{outline:3px solid #ca9f39}}img{{max-width:100%;height:auto}}pre{{overflow:auto;padding:16px;background:#f2f5f4;border-radius:6px}}code{{font-size:.9em;overflow-wrap:anywhere}}blockquote{{border-left:3px solid #6c9d91;margin-left:0;padding-left:18px;color:#526968}}.report-table{{overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{padding:10px;text-align:left;border-bottom:1px solid #dce5e1;min-width:90px}}th{{background:#f2f5f4}}.archive-only{{color:#617673;text-decoration:none}}.archive-only::after{{content:' (local archive)';font-size:.85em}}.report-note{{font-size:13px;color:#617673}}@media(max-width:700px){{main{{margin:12px;padding:18px}}}}@media print{{nav{{display:none}}main{{border:0}}}}
</style></head><body><nav aria-label="Report navigation"><a href="../{back}">← Back to results</a><a href="../index.html">Experiments</a><a href="../reference_results.html">Reference data</a></nav><main><p class="report-note">Saved analysis report. Items labelled “local archive” are not included in this website.</p>{body}</main></body></html>'''.encode()
    (OUT/'assets'/name).write_bytes(raw)
    manifest.append({'source':str(p.relative_to(B)),'web_path':url,'source_sha256':digest,'bytes':len(raw)})
    if p.suffix.lower() in {'.png','.svg'}:
        pair={p.suffix[1:]:url}
        other=p.with_suffix('.svg' if p.suffix=='.png' else '.png')
        if allowed(other):pair[other.suffix[1:]]=bundle(str(other))
        for figure_url in pair.values():figures[figure_url]=pair
    return url

def rewrite(m):
    attr,value=m.group(1),html.unescape(m.group(2))
    if value in PAGES:return attr+'="'+PAGES[value]+'"'
    if value.startswith(('#','https://','http://')):return m.group(0)
    return attr+'="'+bundle(value)+'"'
for name in PAGES:
    documents[name]=re.sub(r'(href|src)="([^"]+)"',rewrite,(B/name).read_text())
viewer=(HERE/'figure_viewer.html').read_text()
def enhance(page,prefix=''):
    mapping={prefix+k:{ext:prefix+v for ext,v in pair.items()} for k,pair in figures.items()}
    return page.replace('</body>',viewer.replace('__FIGURE_FILES__',json.dumps(mapping).replace('<','\\u003c'))+'</body>')
for row in manifest:
    path=OUT/unquote(row['web_path'])
    if path.suffix=='.html':path.write_text(enhance(path.read_text(),'../'))
    raw=path.read_bytes();row['published_sha256']=hashlib.sha256(raw).hexdigest();row['bytes']=len(raw)
for name,page in documents.items():(OUT/name).write_text(enhance(page))
(OUT/'bundle_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(OUT/'archive_links.json').write_text(json.dumps(archive_links,indent=2)+'\n')
(OUT/'README.txt').write_text('Static dashboard with formatted reports and zoomable figures.\nServe index.html, reference_results.html and assets/.\nReports include linked Markdown, CSV and PNG/SVG files up to 10 MB inside the configured source root. Other links are marked local archive.\nSVG downloads are offered only where an existing counterpart is present.\nServe this directory with any static HTTP server, or open index.html locally.\n')
print(f'Built {OUT}: two pages, {len(manifest)} assets, {len(archive_links)} archive-only report links.')
