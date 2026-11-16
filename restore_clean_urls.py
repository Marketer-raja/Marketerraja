#!/usr/bin/env python3
"""
Restore real page content into clean-URL folders (seo/index.html, etc.).

WHY: the old *.html files were overwritten with "Page moved" stubs, but the
destination folders were never created. /seo/ therefore serves the stub,
which redirects to /seo/ again -> redirect loop, and the real content is gone.

USAGE (run from the repository root, where .git lives):
    python restore_clean_urls.py                # uses commit 22de78d (pre-stub)
    python restore_clean_urls.py <good-commit>  # or any commit that still has the real pages

Then check the output, commit, push. Old *.html stubs are left in place
(they now redirect to REAL pages, so there is no loop).
"""
import re
import subprocess
import sys
from pathlib import Path

REV = sys.argv[1] if len(sys.argv) > 1 else "22de78d00bfab733dca213a57508f22470fd3d2a"

# old file -> new clean path (folder with index.html)
PAGES = {
    "seo.html": "seo",
    "google_ads.html": "google-ads",
    "meta_ads.html": "meta-ads",
    "web.html": "web-development",
    "contact.html": "contact",
    "blog.html": "blog",
    "portfolio.html": "portfolio",
    "internship.html": "internship",
    "digital-marketing-course.html": "digital-marketing-course",
    "digital-marketing-agency-salem.html": "digital-marketing-agency/salem",
    "digital-marketing-agency-sankagiri.html": "digital-marketing-agency/sankagiri",
    "digital-marketing-agency-ellampillai.html": "digital-marketing-agency/ellampillai",
}
HOST = "https://www.marketerraja.com"


def git_show(rev, path):
    r = subprocess.run(["git", "show", f"{rev}:{path}"], capture_output=True)
    if r.returncode != 0:
        sys.exit(f"ERROR: {path} not found in {rev}. Pick an earlier commit.\n{r.stderr.decode()}")
    return r.stdout.decode("utf-8")


def rewrite(html, old, new):
    # 1) links to old .html pages -> clean URLs (relative, root-relative, absolute, with/without www)
    for o, n in PAGES.items():
        for prefix in ("", "/", "./", f"{HOST}/", "https://marketerraja.com/"):
            html = re.sub(rf'(["\']){re.escape(prefix + o)}(?=[\'"#?])', rf'\1/{n}/', html) \
                if prefix in ("", "/", "./") else html.replace(prefix + o, f"{HOST}/{n}/")
    # 2) relative asset / script / module paths break one folder deeper -> make root-absolute
    def abs_attr(m):
        attr, q, val = m.group(1), m.group(2), m.group(3)
        if re.match(r'(https?:|//|/|#|mailto:|tel:|data:|javascript:|\{)', val) or not val:
            return m.group(0)
        return f'{attr}={q}/{val.lstrip("./")}{q}'
    html = re.sub(r'\b(src|href)=(["\'])([^"\']*)\2', abs_attr, html)
    html = re.sub(r'(from\s+["\'])\./', r'\1/', html)         # import ... from "./firebase-config.js"
    html = re.sub(r'(import\(\s*["\'])\./', r'\1/', html)     # dynamic import('./x.js')
    return html


def main():
    for old, new in PAGES.items():
        src = rewrite(git_show(REV, old), old, new)
        out = Path(new) / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(src, encoding="utf-8")
        print(f"restored {old:45s} -> {out}")
    print("\nDone. Review a couple of pages locally (python -m http.server), then commit & push.")


if __name__ == "__main__":
    main()
