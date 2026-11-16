# Marketer Raja — Clean URL SEO Update

## What changed
- Public content pages now use directory-based clean URLs (for example, `/seo/` and `/google-ads/`).
- Updated internal navigation links, canonical URLs, Open Graph URLs, `sitemap.xml`, `robots.txt`, and `llms.txt`.
- Preserved the old `.html` paths as lightweight compatibility pages that point visitors and crawlers to the new URLs.
- Added `_redirects` with permanent (301) rules for hosting platforms that support this file format.
- Kept the admin page, Google Search Console verification file, and internship OTP verification endpoint at their existing technical paths.

## Deployment
Upload the contents of `Marketerraja-main/` to the website's document root, preserving the directory structure.

**Important hosting limitation:** this project contains a `CNAME` file and appears prepared for GitHub Pages. GitHub Pages does not process the `_redirects` file as server-side 301 redirects. The legacy `.html` pages therefore use canonical tags plus a browser redirect as a compatibility fallback. For true HTTP 301 redirects, configure equivalent redirects at your CDN/host (for example, Cloudflare Redirect Rules) or move to a host that supports `_redirects`. Do not remove the legacy `.html` files until the redirects are active and tested.

## SEO migration checklist
1. Deploy the complete folder structure.
2. Test each new clean URL and confirm it returns HTTP 200.
3. Test each old `.html` URL and confirm it redirects to its clean equivalent. Aim for a single-hop HTTP 301.
4. Submit `https://www.marketerraja.com/sitemap.xml` in Google Search Console.
5. Inspect the clean URLs in Search Console and monitor indexing, impressions, and 404s.
6. Update any external backlinks, ads, social profiles, and campaign URLs that still use `.html` links.

## Notes
The migration changes URL structure only; it does not promise higher rankings by itself. Ranking impact depends on correct redirects, canonicalization, crawlability, content quality, and Google's recrawling.
