"""Offline regression checks. Requires Selenium; never starts a browser."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import tempfile

path=Path(__file__).resolve().parents[1]/'tools/site_bug_hunter.py'
spec=importlib.util.spec_from_file_location('hunter',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
with tempfile.TemporaryDirectory() as d:
 a=m.Audit(SimpleNamespace(output=d,url='https://www.marketerraja.com/',max_minutes=1))
 button=Mock();button.is_displayed.return_value=True
 driver=Mock();driver.current_url=a.args.url;driver.page_source='<html></html>'
 active=[True]
 button.click.side_effect=lambda:active.__setitem__(0,False)
 driver.find_elements.side_effect=lambda by,sel: [button] if active[0] else []
 a.driver=driver
 a.close_popup()
 assert button.click.call_count==1 and not active[0]
 assert a.rows[0]['check']=='Lead popup closes'
 a.close_popup()
 assert button.click.call_count==1
 a.add('REVIEW','Same','/','same');a.add('REVIEW','Same','/','same')
 assert len([r for r in a.rows if r['check']=='Same'])==1
 a.add('REVIEW','HTML escaping','/','<script>alert(1)</script>')
 a.report()
 assert '&lt;script&gt;alert(1)&lt;/script&gt;' in (a.out/'report.html').read_text()
 a.enqueue(a.args.url+'#one');a.enqueue(a.args.url+'#two')
 assert len(a.pending)==1
 assert not m.eligible(a.args.url+'delete','www.marketerraja.com')
 assert not m.eligible('https://external.example/','www.marketerraja.com')
print('PASS: real close-button call, disappearance check, duplicate suppression, safe reports and URL scope.')
