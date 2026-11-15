"""Run with python tests/check_audit_fixes.py (Node.js required for JS checks)."""
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import tempfile
import json

ROOT = Path(__file__).resolve().parents[1]
class Page(HTMLParser):
    def __init__(self, source):
        super().__init__(); self.scripts=[]; self.attrs={}; self.buf=None; self.ids=set(); self.h1=0; self.titles=0
        self.feed(source)
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if 'id' in attrs: self.ids.add(attrs['id'])
        if tag=='h1': self.h1+=1
        if tag=='title': self.titles+=1
        if tag=='script': self.attrs=attrs; self.buf=''
    def handle_data(self, text):
        if self.buf is not None: self.buf+=text
    def handle_endtag(self, tag):
        if tag=='script' and self.buf is not None:
            self.scripts.append((self.attrs,self.buf)); self.buf=None

with tempfile.TemporaryDirectory() as d:
    script=Path(d)/'check.mjs'
    count=0
    for file in ROOT.glob('*.html'):
        for attrs, code in Page(file.read_text()).scripts:
            if not code.strip() or attrs.get('type','') not in ('','module','text/javascript'):continue
            script.write_text(code)
            subprocess.run(['node','--check',str(script)],check=True,capture_output=True)
            count+=1
    portfolio=Page((ROOT/'portfolio.html').read_text())
    assert portfolio.titles==1 and portfolio.h1==1
    chart_code=next(code for _,code in portfolio.scripts if '// Chart 2: Doughnut Volume' in code)
    chart_code=chart_code[chart_code.index('/* ── CHARTS ── */'):]
    # Execute the actual fallback chart code with only the canvas present in HTML.
    for available in (True,False):
        harness='''const calls=[];
const document={getElementById:id=>id==='compareChart'?{id}:null};
class Chart {constructor(canvas,config){if(!canvas)throw Error('Missing canvas');calls.push(canvas.id);}}
const window={Chart:AVAILABLE?Chart:undefined};
CODE
if(calls.length!==COUNT)throw Error('Unexpected chart initialization count');
'''.replace('AVAILABLE',str(available).lower()).replace('CODE',chart_code).replace('COUNT','1' if available else '0')
        script.write_text(harness);subprocess.run(['node',str(script)],check=True)
    # Run the real homepage module with Firestore stubs; no writes or network calls.
    homepage=Page((ROOT/'index.html').read_text())
    module=next(code for attrs,code in homepage.scripts if 'async function loadPortfolioAndCharts()' in code)
    imports=[line for line in module.splitlines() if line.strip().startswith('import ')]
    assert any(all(x in line for x in ['getDocs','query','orderBy']) for line in imports)
    module='\n'.join(line for line in module.splitlines() if not line.strip().startswith('import '))
    script.write_text('''let reads=0;
const document={getElementById:()=>null,querySelector:()=>null};
const db={}; const collection=()=>({}); const query=()=>({}); const orderBy=()=>({});
const getDocs=async()=>{reads++;return {empty:true}};
const addDoc=()=>{throw Error('Unexpected write')}; const serverTimestamp=()=>0;
'''+module+"\nawait Promise.resolve();if(reads!==0)throw Error('Unused homepage portfolio request');")
    subprocess.run(['node',str(script)],check=True)
print(f'PASS: {count} inline scripts parse; one portfolio H1/title; chart handles missing canvases/library; homepage avoids unused reads.')
