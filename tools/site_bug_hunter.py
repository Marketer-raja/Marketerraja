#!/usr/bin/env python3
"""Single-file Selenium website audit. Python 3.10+.
Install: py -m pip install --upgrade selenium
Run: py site_bug_hunter.py --url https://www.marketerraja.com/ --max-pages 40
Optional: --headless --max-minutes 30 --clicks-per-page 4 --output my_audit

One browser, sequential requests, no form submissions. This is a bounded public
site audit, not an exhaustive functional, security, load or accessibility test.
Only same-origin, query-free HTML links are crawled. Recognized Marketer Raja lead popups are closed with their real button.
No login, CAPTCHA solving,
purchases, downloads, external messaging, or arbitrary button clicks.
Reports preserve FAIL, REVIEW, PASS and SKIP separately; no misleading score.
"""
import argparse
from collections import Counter, deque
from datetime import datetime
import hashlib
import html
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import urljoin, urlsplit, urlunsplit, unquote
import webbrowser

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException
except ImportError:
    print('Install Selenium first: py -m pip install --upgrade selenium')
    raise SystemExit(2)

RISK = re.compile(r'(logout|log-out|signout|sign-out|delete|remove|unsubscribe|checkout|purchase|add.to.cart|reset|confirm|activate|cancel|payment)', re.I)
ASSET = re.compile(r'\.(pdf|zip|png|jpe?g|gif|webp|svg|mp[34]|exe|docx?|xlsx?|csv|ico|woff2?|css|js|xml|txt)$', re.I)
LIMITATIONS = ('Discovered public HTML pages only; query URLs, external destinations and downloads are skipped. '
 'Viewport checks simulate dimensions, not real devices. Images are checked after bounded scrolling. '
 'Forms are inventoried and native validity flags inspected; no data is entered or submitted. '
 'Clicks sample ordinary internal links and explicit disclosure controls only. Custom widgets, '
 'hover-only menus, login, backend delivery, payments, security, load, full accessibility and visual '
 'design correctness require dedicated tests. Browser logging is best-effort. PASS applies only '
 'to the named check. REVIEW is an observation, not a confirmed bug.')

DOM = r"""
const visible=e=>!!(e.getClientRects().length) && getComputedStyle(e).visibility!=='hidden';
const label=e=>(e.getAttribute('aria-label')||e.innerText||e.textContent||'').trim().slice(0,180);
return {
 title:document.title, h1:[...document.querySelectorAll('h1')].map(label),
 description:document.querySelector('meta[name="description"]')?.content||'',
 lang:document.documentElement.lang,
 links:[...document.querySelectorAll('a')].map(e=>({href:e.href||'',raw:e.getAttribute('href'),label:label(e),visible:visible(e),download:e.hasAttribute('download')})),
 images:[...document.images].map(e=>({src:e.currentSrc||e.src,complete:e.complete,width:e.naturalWidth,visible:visible(e),alt:e.getAttribute('alt')})),
 forms:[...document.forms].map(f=>({action:f.action,method:f.method,fields:[...f.elements].map(e=>({tag:e.tagName,type:e.type,name:e.name,id:e.id,placeholder:e.getAttribute('placeholder'),required:e.required,disabled:e.disabled,visible:visible(e),ariaHidden:!!e.closest('[aria-hidden="true"]'),willValidate:e.willValidate,valid:e.validity?.valid,valueMissing:e.validity?.valueMissing,label:!!(e.labels?.length||e.getAttribute('aria-label')||e.getAttribute('aria-labelledby')),options:e.options?[...e.options].map(o=>({text:o.text,value:o.value,disabled:o.disabled})):undefined}))})),
 buttons:[...document.querySelectorAll('button,[role="button"]')].map(e=>({label:label(e),type:e.type,expanded:e.getAttribute('aria-expanded'),controls:e.getAttribute('aria-controls'),visible:visible(e)})),
 dialogs:[...document.querySelectorAll('dialog[open],[role="dialog"],[aria-modal="true"]')].filter(visible).map(label),
 ids:[...document.querySelectorAll('[id]')].map(e=>e.id),
 timing:performance.getEntriesByType('navigation').map(n=>({domContentLoadedMs:Math.round(n.domContentLoadedEventEnd),loadMs:Math.round(n.loadEventEnd),responseMs:Math.round(n.responseStart)})),
 bodyText:(document.body?.innerText||'').slice(0,500)
};
"""


def normalize(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or '/', p.query, ''))


def eligible(url, origin):
    try:
        p = urlsplit(url)
        if p.scheme not in ('http', 'https') or p.netloc.lower() != origin:
            return False
        return not (p.query or RISK.search(unquote(p.path)) or ASSET.search(p.path))
    except ValueError:
        return False


class Audit:
    def __init__(self, args):
        self.args = args
        self.out = Path(args.output or ('site_audit_' + datetime.now().strftime('%Y%m%d_%H%M%S'))).resolve()
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / 'evidence').mkdir(exist_ok=True)
        self.rows, self.pages, self.skipped = [], [], {}
        self.pending, self.seen, self.queued = deque(), set(), set()
        self.driver = None
        self.started = time.monotonic()
        self.deadline = self.started + args.max_minutes * 60
        self.origin = urlsplit(args.url).netloc.lower()
        self.stopped = 'Running'
        self.titles = {}
        self.inspected = set()
        self.popup_checked = False
        self.row_keys = set()

    def add(self, result, check, url, detail, evidence=''):
        key = (result, check, url, str(detail))
        if key not in self.row_keys:
            self.row_keys.add(key)
            self.rows.append(dict(result=result, check=check, url=url, detail=str(detail), evidence=evidence))

    def alive(self):
        if time.monotonic() > self.deadline:
            raise TimeoutError('Overall time limit reached (checked between browser operations).')

    def save_evidence(self, url, tag):
        name = hashlib.sha256(url.encode()).hexdigest()[:10] + '_' + tag
        rel = 'evidence/' + name
        try:
            self.driver.save_screenshot(str(self.out / (rel + '.png')))
            (self.out / (rel + '.html')).write_text(self.driver.page_source, encoding='utf-8')
            return rel + '.png'
        except Exception:
            return ''

    def load(self, url):
        self.alive()
        self.driver.get(url)
        WebDriverWait(self.driver, self.args.timeout).until(
            lambda d: d.execute_script('return document.readyState') in ('interactive', 'complete'))
        WebDriverWait(self.driver, self.args.timeout).until(lambda d: d.find_elements(By.TAG_NAME, 'body'))
        time.sleep(self.args.settle)
        self.close_popup(wait_seconds=4 if not self.popup_checked else 0)
        self.popup_checked = True

    def close_popup(self, wait_seconds=0):
        url = self.driver.current_url
        selector = '.mr-lp-overlay.mr-show .mr-lp-close'
        if wait_seconds:
            try:
                WebDriverWait(self.driver, wait_seconds).until(
                    lambda d: any(e.is_displayed() for e in d.find_elements(By.CSS_SELECTOR, selector)))
            except TimeoutException:
                return
        buttons = [e for e in self.driver.find_elements(By.CSS_SELECTOR, selector) if e.is_displayed()]
        if not buttons:
            return
        shot = self.save_evidence(url, 'popup_before_close')
        buttons[0].click()
        WebDriverWait(self.driver, 5).until(
            lambda d: not d.find_elements(By.CSS_SELECTOR, '.mr-lp-overlay'))
        self.add('PASS', 'Lead popup closes', url, 'Real close button clicked; overlay removed.', shot)

    def click(self, element):
        self.close_popup()
        self.driver.execute_script('arguments[0].scrollIntoView({block: "center", behavior: "instant"})', element)
        try:
            element.click()
        except ElementClickInterceptedException:
            # Popup may have appeared between the first check and the click.
            self.close_popup()
            raise_if_hidden = not element.is_displayed()
            if raise_if_hidden:
                raise
            element.click()

    def enqueue(self, url):
        u = normalize(url)
        if u not in self.queued and u not in self.seen:
            self.queued.add(u)
            self.pending.append(u)

    def discover(self, data):
        for link in data['links']:
            u = link['href']
            if u and not link['download'] and eligible(u, self.origin):
                self.enqueue(u)
            elif u:
                self.skipped[u] = 'External, query URL, non-HTML asset, download, or excluded action'

    def logs(self, url):
        try:
            for entry in self.driver.get_log('browser'):
                if entry.get('level') == 'SEVERE':
                    self.add('FAIL' if re.search(r'\b(?:ReferenceError|TypeError|SyntaxError)\b', entry.get('message','')) else 'REVIEW', 'Browser console', url, entry.get('message', '')[:2500])
        except Exception as e:
            self.add('SKIP', 'Browser console', url, type(e).__name__)
        try:
            for entry in self.driver.get_log('performance'):
                m = json.loads(entry['message'])['message']
                p = m.get('params', {})
                if m['method'] == 'Network.responseReceived':
                    r = p['response']
                    status = r['status']
                    if status >= 400:
                        # A blocked/rate-limited bot request is not necessarily a site defect.
                        result = 'REVIEW' if status in (401,403,429) else 'FAIL'
                        self.add(result, 'HTTP response', url, f"{status}: {r['url']}")
                    elif p.get('type') == 'Document':
                        self.add('PASS', 'Document HTTP response', url, f"{status}: {r['url']}")
                elif m['method'] == 'Network.loadingFailed' and not p.get('canceled'):
                    self.add('REVIEW', 'Network failure', url, p.get('errorText', 'Unknown network error'))
        except Exception as e:
            self.add('SKIP', 'Network logging', url, type(e).__name__)

    def scan_dom(self, url, data, shot):
        self.add('PASS' if data['title'].strip() else 'REVIEW', 'Page title', url, data['title'] or 'Missing', shot)
        if data['title']:
            previous = self.titles.get(data['title'])
            if previous and previous != url:
                self.add('REVIEW', 'Duplicate page title', url, previous)
            self.titles[data['title']] = url
        for key, label in [('description','Meta description'), ('lang','HTML language')]:
            self.add('PASS' if data[key] else 'REVIEW', label, url, data[key] or 'Missing')
        self.add('PASS' if len(data['h1']) == 1 else 'REVIEW', 'H1 structure', url, data['h1'])
        for identifier, count in Counter(data['ids']).items():
            if count > 1:
                self.add('REVIEW', 'Duplicate HTML ID', url, f'{identifier}: {count}')
        if re.search(r'\b(404|page not found|access denied|verify you are human)\b', data['title']+' '+' '.join(data['h1']), re.I):
            self.add('REVIEW', 'Possible error or challenge page', url, data['title'], shot)
        for dialog in data['dialogs']:
            self.add('REVIEW', 'Visible dialog', url, dialog, shot)
        for link in data['links']:
            if link['raw'] in (None, '', '#'):
                self.add('REVIEW', 'Placeholder link', url, link['label'] or '(unnamed)')
            elif link['raw'].startswith('#') and len(link['raw']) > 1:
                fragment = unquote(link['raw'][1:])
                if fragment not in data['ids'] and not self.driver.find_elements(By.NAME, fragment):
                    self.add('REVIEW', 'Missing anchor target', url, link['raw'])
            if url.startswith('https:') and link['href'].startswith('http:'):
                self.add('REVIEW', 'Insecure link', url, link['href'])
            p = urlsplit(link['href'])
            if p.hostname == 'wa.me':
                number = p.path.strip('/')
                self.add('PASS' if number.isdigit() and 7 <= len(number) <= 15 else 'REVIEW',
                         'WhatsApp number format only', url, link['href'])
        for im in data['images']:
            if im['visible'] and im['src']:
                if im['complete'] and not im['width']:
                    self.add('FAIL', 'Broken rendered image', url, im['src'], shot)
                elif not im['complete']:
                    self.add('REVIEW', 'Image still loading', url, im['src'], shot)
            if im['alt'] is None:
                self.add('REVIEW', 'Image missing alt attribute', url, im['src'])
        for i, form in enumerate(data['forms'], 1):
            self.add('PASS', 'Form discovered', url, f"Form {i}: {len(form['fields'])} controls; {form['method']} {form['action']}")
            for field in form['fields']:
                if field.get('type') in ('hidden','submit','button','reset') or field.get('disabled') or field.get('ariaHidden') or not field.get('visible'):
                    continue
                name = field.get('name') or field.get('id') or field.get('placeholder') or '(unnamed)'
                if not field.get('label'):
                    self.add('REVIEW', 'Form accessible label', url, f'Form {i}: {name} has no associated label/ARIA name')
                if field.get('required') and field.get('willValidate'):
                    self.add('PASS', 'Required field constraint present', url, f'{name}: valueMissing={field.get("valueMissing")}; browser constraint only')
            self.add('SKIP', 'Form end-to-end submission', url, f'Form {i}: delivery and server validation require a dedicated controlled test')
        if not data['forms']:
            self.add('SKIP', 'Form checks', url, 'No native form element found; custom forms may need dedicated selectors')
        for t in data['timing']:
            self.add('REVIEW' if t['loadMs'] > 5000 else 'INFO', 'Single-run load timing', url, str(t)+'; not a benchmark or Core Web Vitals assessment')

    def viewports(self, url):
        for width, height in [(1440,900),(768,1024),(390,844)]:
            self.alive()
            self.driver.execute_cdp_cmd('Emulation.setDeviceMetricsOverride',
                dict(width=width,height=height,deviceScaleFactor=1,mobile=False))
            self.driver.execute_script('window.scrollTo({top:0,behavior:"instant"})')
            time.sleep(self.args.settle)
            for position in ('top','bottom'):
                if position == 'bottom':
                    self.driver.execute_script('window.scrollTo({top:document.documentElement.scrollHeight,behavior:"instant"})')
                    time.sleep(.3)
                dims = self.driver.execute_script('return {viewport:innerWidth,content:document.documentElement.scrollWidth}')
                ok = dims['content'] <= dims['viewport'] + 2
                shot = self.save_evidence(url, f'{width}_{position}')
                self.add('PASS' if ok else 'REVIEW', 'Horizontal overflow', url, f'{width}px {position}: {dims}', shot)
            self.mobile_menu(url, width)
            self.disclosures(url, width)
        self.driver.execute_cdp_cmd('Emulation.clearDeviceMetricsOverride', {})
        self.driver.execute_script('window.scrollTo({top:0,behavior:"instant"})')

    def mobile_menu(self, url, width):
        toggles = self.driver.find_elements(By.CSS_SELECTOR, '#nav-toggle')
        if not toggles or not toggles[0].is_displayed():
            return
        toggle = toggles[0]
        try:
            if toggle.get_attribute('aria-expanded') == 'true':
                self.click(toggle)
            self.click(toggle)
            WebDriverWait(self.driver, 5).until(lambda d: toggle.get_attribute('aria-expanded') == 'true')
            links = self.driver.find_elements(By.CSS_SELECTOR, '#nav-links a[href]')
            shown = [e for e in links if e.is_displayed()]
            if not shown:
                raise AssertionError('Menu opened but no links are visible')
            self.add('PASS', 'Mobile menu opens', url, f'{width}px: {len(shown)} visible links')
            self.discover(self.driver.execute_script(DOM))
            self.click(toggle)
            WebDriverWait(self.driver, 5).until(lambda d: toggle.get_attribute('aria-expanded') == 'false')
            self.add('PASS', 'Mobile menu closes', url, f'{width}px: expanded state returns to false')
        except Exception as e:
            self.add('REVIEW', 'Mobile menu', url, str(e)[:500], self.save_evidence(url, f'{width}_menu_error'))

    def disclosures(self, url, width):
        # Only semantic non-form disclosure controls; unknown buttons are not clicked.
        controls = self.driver.find_elements(By.CSS_SELECTOR, 'details > summary, button[type="button"][aria-expanded][aria-controls]')
        tested = 0
        for element in controls[:12]:
            self.alive()
            try:
                self.close_popup()
                if element.get_attribute("id") == "nav-toggle":
                    continue
                if not element.is_displayed() or element.find_elements(By.XPATH, './ancestor::form'):
                    continue
                if RISK.search(element.text):
                    continue
                summary = element.tag_name == 'summary'
                parent = element.find_element(By.XPATH,'..') if summary else element
                attribute = 'open' if summary else 'aria-expanded'
                before = parent.get_attribute(attribute)
                self.click(element)
                WebDriverWait(self.driver, 4).until(lambda d: parent.get_attribute(attribute) != before)
                self.add('PASS', 'Disclosure state toggles', url, f'{width}px: {element.text[:120]}')
                self.discover(self.driver.execute_script(DOM))
                self.click(element)
                WebDriverWait(self.driver, 4).until(lambda d: parent.get_attribute(attribute) == before)
                tested += 1
            except Exception as e:
                self.add('REVIEW', 'Disclosure interaction', url, f'{width}px: {type(e).__name__}: {str(e)[:350]}', self.save_evidence(url, f'{width}_disclosure'))
        self.add('INFO' if tested else 'SKIP', 'Disclosure coverage', url, f'{width}px: {tested} controls toggled both ways; unrecognized custom controls not exercised')

    def click_links(self, url, links):
        candidates = []
        for link in links:
            target = link['href']
            if link['visible'] and not link['download'] and eligible(target, self.origin) and normalize(target) != normalize(url) and not urlsplit(target).fragment:
                if target not in candidates:
                    candidates.append(target)
        for target in candidates[:self.args.clicks_per_page]:
            self.alive()
            home = self.driver.current_window_handle
            old_handles = set(self.driver.window_handles)
            try:
                self.load(url)
                matches = [a for a in self.driver.find_elements(By.CSS_SELECTOR,'a[href]')
                           if a.get_attribute('href') == target and a.is_displayed()]
                if not matches:
                    self.add('SKIP', 'Real link click', url, f'Not visible on reload: {target}')
                    continue
                self.click(matches[0])
                WebDriverWait(self.driver, self.args.timeout).until(
                    lambda d: normalize(d.current_url) != normalize(url) or set(d.window_handles) != old_handles)
                new = set(self.driver.window_handles) - old_handles
                if new:
                    self.driver.switch_to.window(next(iter(new)))
                    WebDriverWait(self.driver, self.args.timeout).until(lambda d: d.current_url != 'about:blank')
                actual = self.driver.current_url
                exact = normalize(actual) == normalize(target)
                self.add('PASS' if exact else 'INFO', 'Real link click' if exact else 'Link redirected - destination needs crawl check', url,
                         f'Expected {target}; reached {actual}. Destination content is checked by crawl.')
            except Exception as e:
                self.add('REVIEW', 'Real link click blocked or incomplete', url,
                         f'{target}: {type(e).__name__}: {str(e)[:500]}', self.save_evidence(url,'click_failure'))
            finally:
                try:
                    for handle in set(self.driver.window_handles) - old_handles:
                        self.driver.switch_to.window(handle)
                        self.driver.close()
                    self.driver.switch_to.window(home)
                except Exception:
                    pass
                self.logs(url)
        self.add('INFO', 'Link click coverage', url, f'Attempted up to {min(len(candidates),self.args.clicks_per_page)} of {len(candidates)} unique visible eligible destinations; hidden links still discovered for crawl')

    def scan(self, url):
        print(f'[{len(self.seen)}/{self.args.max_pages}] {url}', flush=True)
        self.driver.set_window_size(1440,1000)
        self.driver.execute_cdp_cmd('Emulation.clearDeviceMetricsOverride', {})
        self.load(url)
        actual = self.driver.current_url
        if urlsplit(actual).netloc.lower() != self.origin:
            self.add('SKIP','Off-origin redirect',url,actual)
            return
        self.seen.add(normalize(actual))
        if normalize(actual) in self.inspected:
            self.add('INFO', 'Redirect alias', url, f'Already inspected {actual}')
            return
        self.inspected.add(normalize(actual))
        # Trigger lazy loading, bounded to avoid endless feeds.
        for step in range(12):
            self.alive()
            finished = self.driver.execute_script('window.scrollBy({top:Math.max(400,innerHeight*.8),behavior:"instant"}); return scrollY+innerHeight >= document.documentElement.scrollHeight-3')
            time.sleep(.2)
            if finished:
                break
        try:
            WebDriverWait(self.driver, 3).until(lambda d: d.execute_script('return [...document.images].filter(i=>i.getClientRects().length).every(i=>i.complete)'))
        except TimeoutException:
            pass
        self.driver.execute_script('window.scrollTo({top:0,behavior:"instant"})')
        self.close_popup()
        data = self.driver.execute_script(DOM)
        self.pages.append(dict(url=url, final_url=actual, data=data))
        shot = self.save_evidence(url,'desktop')
        self.discover(data)
        self.scan_dom(actual, data, shot)
        self.logs(actual)
        self.viewports(actual)
        self.click_links(actual, data['links'])
        self.logs(actual)

    def report(self):
        counts = Counter(r['result'] for r in self.rows)
        payload = dict(site=self.args.url, stopped=self.stopped, counts=dict(counts),
                       duration_seconds=round(time.monotonic()-self.started), limits=vars(self.args),
                       limitations=LIMITATIONS, findings=self.rows, pages=self.pages,
                       remaining=list(self.pending), skipped_urls=self.skipped)
        (self.out/'results.json').write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')
        esc = lambda value: html.escape(str(value), quote=True)
        priority = {'FAIL':0,'REVIEW':1,'SKIP':2,'INFO':3,'PASS':4}
        rows = []
        for r in sorted(self.rows, key=lambda r:priority[r['result']]):
            evidence = f'<a href="{esc(r["evidence"])}">Screenshot</a>' if r['evidence'] else ''
            rows.append(f'<tr data-status="{r["result"]}"><td><b>{r["result"]}</b></td><td>{esc(r["check"])}</td><td>{esc(r["url"])}</td><td>{esc(r["detail"])}</td><td>{evidence}</td></tr>')
        content = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Website audit</title>
<style>body{font:15px system-ui;background:#f3f5fa;color:#182333;margin:32px}main{max-width:1500px;margin:auto}h1{font-size:34px}section{background:white;padding:20px;border-radius:12px;margin:18px 0}table{width:100%;border-collapse:collapse}th:nth-child(1){min-width:75px}th:nth-child(2){min-width:150px}th:nth-child(3){min-width:190px}th:nth-child(5){min-width:90px}td,th{padding:12px;border-bottom:1px solid #ddd;text-align:left;vertical-align:top;overflow-wrap:anywhere}tr[data-status=FAIL] b{color:#b42318}tr[data-status=REVIEW] b{color:#965700}tr[data-status=PASS] b{color:#087044}input,select{padding:10px;margin:8px}small{color:#536176}.scroll{overflow:auto}a{color:#2857b8}</style><main><h1>Website audit</h1>'''
        content += f'<p>{esc(self.args.url)}</p><section><b>{esc(self.stopped)}</b><p>{len(self.pages)} pages inspected · {len(self.pending)} queued URLs remaining · {esc(dict(counts))}</p><p>{esc(LIMITATIONS)}</p><a href="results.json">Detailed JSON and element inventory</a></section>'
        content += '<section><label>Filter <select id="status"><option>ALL</option><option>FAIL</option><option>REVIEW</option><option>SKIP</option><option>PASS</option><option>INFO</option></select></label><input id="search" placeholder="Search URL, check or error"><div class="scroll"><table><thead><tr><th>Result</th><th>Check</th><th>Page</th><th>Evidence / detail</th><th>Image</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div></section>'
        content += '''<script>function filter(){const s=document.getElementById('status').value,q=document.getElementById('search').value.toLowerCase();document.querySelectorAll('tbody tr').forEach(r=>r.hidden=!((s==='ALL'||r.dataset.status===s)&&r.innerText.toLowerCase().includes(q)));}document.getElementById('status').onchange=filter;document.getElementById('search').oninput=filter;</script></main></html>'''
        tmp = self.out/'report.tmp'
        tmp.write_text(content,encoding='utf-8')
        tmp.replace(self.out/'report.html')

    def run(self):
        try:
            opts = webdriver.ChromeOptions()
            opts.page_load_strategy = 'normal'
            opts.set_capability('goog:loggingPrefs', {'browser':'ALL','performance':'ALL'})
            opts.set_capability('unhandledPromptBehavior', 'dismiss and notify')
            opts.add_experimental_option('prefs', {'profile.default_content_setting_values.notifications':2})
            if self.args.headless:
                opts.add_argument('--headless=new')
            if self.args.chrome_binary:
                opts.binary_location = self.args.chrome_binary
            self.driver = webdriver.Chrome(options=opts)
            self.driver.set_page_load_timeout(self.args.timeout)
            self.driver.set_script_timeout(self.args.timeout)
            # Resolve the root's normal www / non-www redirect before fixing crawl origin.
            self.load(self.args.url)
            self.origin = urlsplit(self.driver.current_url).netloc.lower()
            self.enqueue(self.driver.current_url)
            attempts = 0
            while self.pending and attempts < self.args.max_pages:
                self.alive()
                url = self.pending.popleft()
                if url in self.seen:
                    continue
                self.seen.add(url)
                attempts += 1
                try:
                    self.scan(url)
                except TimeoutError:
                    raise
                except Exception as e:
                    self.add('REVIEW','Page scan incomplete',url,f'{type(e).__name__}: {str(e)[:1200]}',self.save_evidence(url,'error'))
                    try:
                        self.driver.switch_to.alert.dismiss()
                    except Exception:
                        pass
                self.report()  # Checkpoint after each page.
            self.stopped = 'Page limit reached; crawl incomplete' if self.pending else 'Finished discovered eligible pages'
        except KeyboardInterrupt:
            self.stopped = 'Interrupted by user; partial results'
        except TimeoutError:
            self.stopped = 'Time limit reached; partial results'
        except Exception as e:
            self.stopped = 'Stopped by setup or browser error; partial results'
            self.add('REVIEW','Runner error',self.args.url,f'{type(e).__name__}: {str(e)[:2000]}')
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
            self.report()
            print('\n'+self.stopped+'\nReport: '+str(self.out/'report.html'),flush=True)
            if not self.args.no_open:
                webbrowser.open((self.out/'report.html').as_uri())
        return 1 if any(r['result']=='FAIL' for r in self.rows) else (2 if 'Stopped' in self.stopped else 0)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--url',default='https://www.marketerraja.com/')
    p.add_argument('--max-pages',type=int,default=40)
    p.add_argument('--max-minutes',type=int,default=30)
    p.add_argument('--clicks-per-page',type=int,default=3)
    p.add_argument('--timeout',type=int,default=25)
    p.add_argument('--settle',type=float,default=1.0)
    p.add_argument('--headless',action='store_true')
    p.add_argument('--no-open',action='store_true')
    p.add_argument('--output')
    p.add_argument('--chrome-binary',help='Optional custom Chrome/Chromium executable path')
    args = p.parse_args()
    if urlsplit(args.url).scheme not in ('http','https') or not urlsplit(args.url).netloc:
        p.error('--url must be a full http(s) URL')
    if min(args.max_pages,args.max_minutes,args.timeout) < 1 or args.clicks_per_page < 0 or args.settle < 0:
        p.error('Limits must be positive; clicks and settle may be zero')
    return Audit(args).run()


if __name__ == '__main__':
    raise SystemExit(main())
