# Marketer Raja audit fixes — 15 November 2026

Prepared from repository commit 22de78d00bfab733dca213a57508f22470fd3d2a.
These are source changes prepared for review/upload; they have not been pushed to GitHub or deployed.

## What changed

- index.html: import all Firestore query functions used by the portfolio loader; skip its unused query when no portfolio UI exists; name the four enquiry controls for assistive technology.
- portfolio.html: add the page title; keep one H1; remove chart initialization for removed canvases; retain the existing comparison chart and database updates; guard the chart-library dependency; accept numeric metric values without a string-method exception.
- google_ads.html and web.html: reproduce and fix tablet overflow caused by the Refund Policy panel. Use the existing bottom-sheet policy layout up to 900px. The content is not clipped to hide the defect.
- google_ads.html: initialize the menu handler at its existing location after the navigation markup.
- Public navigation buttons: add type="button" and aria-controls="nav-links" to describe and test the controlled menu.
- blog.html and assets/blog-placeholder.svg: accessible thumbnail text and a local fallback when an external image fails. No database article records were edited. The failed external request can still appear in an audit until its source thumbnail URL is replaced in your admin panel.
- tools/site_bug_hunter.py: close the actual lead popup and verify removal; instantaneous test scrolling; menu open/close checks; deduplicate findings and redirect-alias page scans; avoid hidden anti-spam field warnings; classify JS ReferenceError/TypeError/SyntaxError as FAIL; treat observed redirects as information rather than automatically broken links; improve report column widths.

## Upload the website changes

1. Back up your current production source. If the repository has changed since the commit above, merge the changes rather than overwriting newer work.
2. Upload the changed HTML files listed below and the new assets/blog-placeholder.svg to the repository root, preserving their paths. Do not delete other site files.
3. Commit the update and wait for your existing hosting deployment to complete.
4. Check the deployed homepage, portfolio, blog and tablet layout. The source ZIP is a full repository snapshot without Git history; the patch is supplied for developers who prefer applying a diff.

Changed HTML files:
blog.html, contact.html, digital-marketing-agency-ellampillai.html,
digital-marketing-agency-salem.html, digital-marketing-agency-sankagiri.html,
digital-marketing-course.html, google_ads.html, index.html, internship.html,
meta_ads.html, portfolio.html, seo.html, web.html.

Your Firebase configuration, enquiry destinations and existing popup timing are preserved.

## Run the updated scanner on Windows

Copy tools/site_bug_hunter.py into your existing website-testing folder, replacing the old copy.
Open Command Prompt in website-testing and run:

```bat
py -m pip install --upgrade selenium
py -m py_compile site_bug_hunter.py
py site_bug_hunter.py --url https://www.marketerraja.com/ --max-pages 40 --max-minutes 30
```

The report opens automatically. Upload results.json for interpretation. An observed redirect is not a broken-link verdict; inspect the crawled destination too. PASS is specific to a check, not a site-wide certification.

## Validation performed

- Parsed all 66 inline JavaScript blocks with Node's syntax checker.
- Executed the actual fallback chart block with missing canvases and an unavailable chart library; no missing-canvas construction occurs.
- Executed homepage module with Firestore stubs to verify it does not fetch portfolio data without a portfolio UI; checked required imports.
- Offline scanner regression: real close-button call, overlay disappearance condition, duplicate suppression, report escaping and URL scope.
- Python compile check and git diff whitespace check.
- Local preview in Chrome: portfolio loads 12 database-backed cards, has one H1 and the new title; no new chart error observed. Closed the popup through its Close control and followed Services -> SEO successfully.
- Tablet iframe preview (768px outer width): reproduced Google Ads/Web overflow from refund policy panels; after the change, document width equals viewport width. Tablet menu keyboard open/close verified on Google Ads.

## Remaining checks / limits

The complete updated Selenium crawl has not been run against deployed changes. Touch-device behavior, full keyboard accessibility and all custom widgets still require dedicated testing. No real enquiry was submitted. After deploying, send one clearly labeled test using your own contact details, then confirm both success feedback and the stored enquiry/notification delivery. Do not use real customer details in automated test files.

To run developer regression checks (Node.js plus Python/Selenium required):

```text
python tests/check_audit_fixes.py
python tests/check_scanner.py
```
