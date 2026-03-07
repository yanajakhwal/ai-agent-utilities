from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple

from playwright.sync_api import sync_playwright, Page

MAX_DOCS = 10
BASE_URL = "https://uarb.novascotia.ca/fmi/webd/UARB15"

DOC_TYPE_KEYWORDS: Dict[str, str] = {
    "other documents": "Other",
    "key documents":   "Key",
    "exhibits":        "Exhibit",
    "transcripts":     "Transcript",
    "recordings":      "Recording",
    "evidence":        "Evidence",
    "decision":        "Decision",
    "order":           "Order",
}


def _click_element_by_text(page: Page, text: str, *, max_width: int = 300) -> bool:
    """Find a small leaf-ish element whose trimmed text matches *text* and
    click it by bounding-box coordinates.  Returns True if clicked."""
    box = page.evaluate(f"""() => {{
        const els = document.querySelectorAll('div, span, button, a');
        for (const el of els) {{
            if (el.textContent.trim() === {repr(text)}) {{
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.width < {max_width} && r.height > 0 && r.height < 60) {{
                    return {{x: r.x + r.width / 2, y: r.y + r.height / 2}};
                }}
            }}
        }}
        return null;
    }}""")
    if box:
        page.mouse.click(box["x"], box["y"])
        return True
    return False


def _click_count_button_by_keyword(page: Page, keyword: str) -> bool:
    """Find a blue count-number button associated with a tab label containing
    *keyword* and click it.

    GWT may split labels like "Other Docs" into separate divs ("Other", "Docs").
    So we search for ANY small element whose text contains the keyword, then
    find the closest number-only element below it and click that number.
    """
    box = page.evaluate(f"""() => {{
        const keyword = {repr(keyword)}.toLowerCase();
        const all = [...document.querySelectorAll('div, span')];

        // 1. Gather label candidates: small leaf-ish elements containing keyword
        const labels = [];
        for (const d of all) {{
            const t = d.textContent.trim().toLowerCase();
            if (t.includes(keyword) && t.length < 40) {{
                const r = d.getBoundingClientRect();
                if (r.width > 0 && r.height > 0 && r.width < 200) {{
                    labels.push({{x: r.x + r.width / 2, y: r.y + r.height / 2, w: r.width}});
                }}
            }}
        }}

        // 2. Gather number candidates: leaf divs whose text is digits only
        const numbers = [];
        for (const d of all) {{
            if (d.children.length === 0) {{
                const t = d.textContent.trim();
                if (/^\\d+$/.test(t)) {{
                    const r = d.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0 && r.width < 80) {{
                        numbers.push({{x: r.x + r.width / 2, y: r.y + r.height / 2, text: t}});
                    }}
                }}
            }}
        }}

        // 3. For each label pick the narrowest (most specific) match
        labels.sort((a, b) => a.w - b.w);

        // 4. For the best label, find the closest number below it
        for (const label of labels) {{
            let best = null;
            let bestDist = 999;
            for (const num of numbers) {{
                const dx = Math.abs(num.x - label.x);
                const dy = num.y - label.y;
                if (dx < 60 && dy > 0 && dy < 80) {{
                    const dist = dx + dy;
                    if (dist < bestDist) {{
                        bestDist = dist;
                        best = num;
                    }}
                }}
            }}
            if (best) return {{x: best.x, y: best.y}};
        }}
        return null;
    }}""")
    if box:
        page.mouse.click(box["x"], box["y"])
        return True
    return False


def _navigate_to_doc_tab(page: Page, document_type: str) -> bool:
    """Click the count-number button for the requested document type tab."""
    keyword = DOC_TYPE_KEYWORDS.get(document_type.lower())
    if keyword and _click_count_button_by_keyword(page, keyword):
        print(f"  [scraper] Clicked count button near '{keyword}'")
        return True
    # Fallback: try clicking the document_type text directly
    if _click_element_by_text(page, document_type, max_width=400):
        print(f"  [scraper] Clicked tab label '{document_type}'")
        return True
    print(f"  [scraper] Could not find tab for '{document_type}'")
    return False


def fetch_documents_and_metadata(
    matter_number: str,
    document_type: str,
    download_dir: Path,
    *,
    headless: bool = True,
) -> Tuple[List[Path], Dict[str, str]]:
    """Navigate the UARB regulatory site, search by matter number,
    download up to MAX_DOCS documents, and extract metadata.

    The site uses FileMaker/Vaadin which renders form fields as <div>
    elements, not native <input>.  We interact via mouse coordinates +
    keyboard typing.
    """
    download_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.set_default_timeout(60_000)
        page.set_default_navigation_timeout(60_000)

        page.goto(BASE_URL, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=45_000)

        # --- Wait for GWT to render the matter-number field ---
        try:
            page.wait_for_function(
                """() => {
                    const divs = document.querySelectorAll('div');
                    for (const d of divs) {
                        if (d.children.length === 0 && d.textContent.trim() === 'eg M01234') return true;
                    }
                    return false;
                }""",
                timeout=90_000,
            )
        except Exception:
            debug_path = download_dir / "debug_timeout.png"
            try:
                page.screenshot(path=str(debug_path))
            except Exception:
                pass
            raise TimeoutError(
                f"Could not find the Matter Number field. Screenshot → {debug_path}"
            )

        # --- Type the matter number ---
        box = page.evaluate("""() => {
            const divs = document.querySelectorAll('div');
            for (const d of divs) {
                if (d.children.length === 0 && d.textContent.trim() === 'eg M01234') {
                    const r = d.getBoundingClientRect();
                    return {x: r.x + r.width / 2, y: r.y + r.height / 2};
                }
            }
            return null;
        }""")
        page.mouse.click(box["x"], box["y"])
        page.wait_for_timeout(500)
        page.mouse.click(box["x"], box["y"], click_count=3)
        page.wait_for_timeout(200)
        page.keyboard.type(matter_number, delay=80)

        # --- Click "Search" ---
        _click_element_by_text(page, "Search")
        page.wait_for_timeout(2000)
        page.wait_for_load_state("networkidle", timeout=45_000)
        page.wait_for_timeout(3000)

        # Debug screenshot of the results summary
        try:
            page.screenshot(path=str(download_dir / "debug_results.png"))
        except Exception:
            pass

        # --- Extract metadata from the results summary ---
        metadata = _extract_metadata(page, matter_number)
        print(f"  [scraper] Metadata fields: {metadata.get('fields', {})}")
        print(f"  [scraper] Doc counts: {metadata.get('doc_counts', {})}")

        # --- Navigate to the requested document-type tab ---
        if document_type.lower() != "all documents":
            _navigate_to_doc_tab(page, document_type)
            page.wait_for_timeout(3000)
            page.wait_for_load_state("networkidle", timeout=30_000)
            page.wait_for_timeout(2000)

        # Debug screenshot of the document list
        try:
            page.screenshot(path=str(download_dir / "debug_doc_list.png"))
        except Exception:
            pass

        # --- Download documents ---
        downloaded_files = _download_documents(page, download_dir, matter_number)
        print(f"  [scraper] Downloaded {len(downloaded_files)} file(s)")

        browser.close()

    return downloaded_files, metadata


def _download_documents(page: Page, download_dir: Path, matter_number: str) -> List[Path]:
    """Find up to MAX_DOCS downloadable items on the current page.

    The UARB site paginates the document list, so after processing all visible
    "GO GET IT" buttons we scroll down to reveal more rows and repeat.

    Each "GO GET IT" click opens a modal dialog with the filename; we click
    the filename inside the modal to trigger the actual download.
    """
    downloaded: List[Path] = []
    seen_filenames: set[str] = set()
    scroll_attempts = 0

    while len(downloaded) < MAX_DOCS:
        go_elements = page.locator("text=/GO GET IT/i")
        n = go_elements.count()
        if n == 0:
            break
        print(f"  [scraper] Visible 'GO GET IT' buttons: {n}")

        made_progress = False
        for idx in range(n):
            if len(downloaded) >= MAX_DOCS:
                break

            el = go_elements.nth(idx)
            try:
                el.scroll_into_view_if_needed(timeout=3_000)
                el.click(force=True, timeout=5_000)
                page.wait_for_timeout(2000)

                modal_info = _read_modal(page)

                link_info = _find_download_target(modal_info.get("items", []))
                if not link_info:
                    print(f"  [scraper]   no download target in modal")
                    _dismiss_modal(page)
                    continue

                filename = link_info.get("text", "") or f"{matter_number}_{len(downloaded)+1}.pdf"
                if not filename.endswith(".pdf"):
                    filename = f"{matter_number}_{len(downloaded)+1}.pdf"

                if filename in seen_filenames:
                    _dismiss_modal(page)
                    continue
                seen_filenames.add(filename)

                target = download_dir / filename
                saved = _try_download(page, link_info, target)

                if saved:
                    downloaded.append(target)
                    made_progress = True
                    print(f"  [scraper]   saved {target.name} ({len(downloaded)}/{MAX_DOCS})")
                else:
                    print(f"  [scraper]   could not download {filename}")

                _dismiss_modal(page)

            except Exception as e:
                print(f"  [scraper]   error on item: {e}")
                _dismiss_modal(page)
                continue

        if len(downloaded) >= MAX_DOCS:
            break

        # Scroll down to reveal more rows
        if not made_progress:
            scroll_attempts += 1
            if scroll_attempts >= 3:
                break
        page.evaluate("window.scrollBy(0, 600)")
        page.wait_for_timeout(2000)

    return downloaded


def _read_modal(page: Page) -> Dict:
    """Read all elements inside the download modal dialog."""
    return page.evaluate("""() => {
        const all = [...document.querySelectorAll('*')];
        let modalY = null, modalX = null;
        for (const d of all) {
            if (d.textContent.trim() === 'Download Files' && d.children.length === 0) {
                const r = d.getBoundingClientRect();
                if (r.width > 0) { modalY = r.y; modalX = r.x; break; }
            }
        }
        const items = [];
        for (const d of all) {
            const r = d.getBoundingClientRect();
            if (r.width <= 0 || r.height <= 0) continue;
            const cx = r.x + r.width / 2;
            const cy = r.y + r.height / 2;
            if (modalY !== null) {
                if (cy < modalY - 10 || cy > modalY + 300) continue;
                if (cx < modalX - 50 || cx > modalX + 500) continue;
            }
            const tag = d.tagName;
            let text = '';
            if (tag === 'INPUT' || tag === 'TEXTAREA') text = d.value || '';
            else text = d.children.length === 0 ? d.textContent.trim() : '';
            if (!text) continue;
            items.push({tag, text, href: d.href || '', x: cx, y: cy, w: r.width, h: r.height});
        }
        return {modalFound: modalY !== null, items};
    }""")


def _try_download(page: Page, link_info: Dict, target: Path) -> bool:
    """Attempt to download a file using multiple strategies."""
    # Strategy A: direct HTTP download via href
    if link_info.get("href"):
        try:
            resp = page.request.get(link_info["href"])
            if resp.ok and len(resp.body()) > 100:
                target.write_bytes(resp.body())
                return True
        except Exception:
            pass

    # Strategy B: click and catch browser download event
    try:
        with page.expect_download(timeout=20_000) as dl_info:
            page.mouse.click(link_info["x"], link_info["y"])
        dl = dl_info.value
        fname = dl.suggested_filename or target.name
        final = target.parent / fname
        dl.save_as(str(final))
        return True
    except Exception:
        pass

    # Strategy C: check if a new tab/popup opened with the file
    try:
        pages = page.context.pages
        if len(pages) > 1:
            new_page = pages[-1]
            new_page.wait_for_load_state("load", timeout=10_000)
            url = new_page.url
            if url and url != "about:blank":
                resp = page.request.get(url)
                if resp.ok and len(resp.body()) > 100:
                    target.write_bytes(resp.body())
                    new_page.close()
                    return True
            new_page.close()
    except Exception:
        pass

    return False


def _find_download_target(items: List[Dict]) -> Dict | None:
    """Pick the best clickable element from the modal's DOM dump.

    Priority order:
    1. <a> with href containing a filename
    2. <input> or <button> with a .pdf filename
    3. Any element with text like '12345.pdf' (digits + .pdf, len > 4)
    4. Any element with text ending in .pdf and length > 4
    """
    for it in items:
        if it.get("href") and ".pdf" in it["text"].lower():
            return it
    for it in items:
        if it["tag"] in ("INPUT", "BUTTON") and it["text"].endswith(".pdf") and len(it["text"]) > 4:
            return it
    for it in items:
        if re.match(r".+\.pdf$", it["text"], re.IGNORECASE) and len(it["text"]) > 4:
            return it
    return None


def _dismiss_modal(page: Page) -> None:
    """Click "Close" in the download modal, or press Escape as fallback."""
    try:
        close_box = page.evaluate("""() => {
            for (const el of document.querySelectorAll('div, button, span, a')) {
                if (el.textContent.trim() === 'Close') {
                    const r = el.getBoundingClientRect();
                    if (r.width > 0 && r.width < 200 && r.height > 0 && r.height < 60)
                        return {x: r.x + r.width/2, y: r.y + r.height/2};
                }
            }
            return null;
        }""")
        if close_box:
            page.mouse.click(close_box["x"], close_box["y"])
        else:
            page.keyboard.press("Escape")
    except Exception:
        page.keyboard.press("Escape")
    page.wait_for_timeout(1000)



def _extract_metadata(page: Page, matter_number: str) -> Dict[str, str]:
    """Extract metadata and document-tab counts directly via JavaScript.

    Rather than trying to match headers to values by spatial position (which
    breaks because GWT header cells have child sort-arrow buttons and aren't
    leaf divs), we classify data elements by their content patterns and
    relative position to the matter number.
    """
    fields = page.evaluate("""(matterNum) => {
        const all = [...document.querySelectorAll('div, span')];
        const leaves = [];
        for (const d of all) {
            if (d.children.length > 0) continue;
            const t = d.textContent.trim();
            if (!t) continue;
            const r = d.getBoundingClientRect();
            if (r.width <= 0 || r.height <= 0) continue;
            leaves.push({text: t, x: r.x, y: r.y, w: r.width, h: r.height});
        }

        // Anchor: find the matter number element
        const matterRe = new RegExp('^' + matterNum + '$');
        const matterEl = leaves.find(e => matterRe.test(e.text));
        if (!matterEl) return {};

        // Collect data elements near the matter number row (±50px vertically)
        const nearby = leaves.filter(e =>
            Math.abs(e.y - matterEl.y) < 50 && e.w < 500
        );
        nearby.sort((a, b) => a.x - b.x);

        const result = {};

        // Status: just below matter number, same x-column
        const statusEl = nearby.find(e =>
            Math.abs(e.x - matterEl.x) < 40 &&
            e.y > matterEl.y + 5 &&
            !matterRe.test(e.text)
        );
        if (statusEl) result.status = statusEl.text;

        // Title: the longest text in the row (> 20 chars, to the right of matter)
        const titleEl = nearby
            .filter(e => e.text.length > 20 && e.x > matterEl.x + 40)
            .sort((a, b) => b.text.length - a.text.length)[0];
        if (titleEl) result.title = titleEl.text;

        // Dates: MM/DD/YYYY pattern, sorted left-to-right
        const dateEls = nearby
            .filter(e => /^\\d{2}\\/\\d{2}\\/\\d{4}$/.test(e.text))
            .sort((a, b) => a.x - b.x);
        if (dateEls.length >= 1) result.date_received = dateEls[0].text;
        if (dateEls.length >= 2) result.decision_date = dateEls[1].text;

        // Type & Category: between title and first date, stacked vertically
        const titleX = titleEl ? titleEl.x + titleEl.w : matterEl.x + 200;
        const dateX = dateEls.length ? dateEls[0].x : 9999;
        const typeCat = nearby.filter(e =>
            e.x >= titleX - 10 &&
            e.x + e.w < dateX + 10 &&
            e.text !== (titleEl && titleEl.text) &&
            !/^\\d{2}\\//.test(e.text) &&
            !matterRe.test(e.text) &&
            e.text.length < 40
        ).sort((a, b) => a.y - b.y);
        if (typeCat.length >= 1) result.type = typeCat[0].text;
        if (typeCat.length >= 2) result.category = typeCat[1].text;

        return result;
    }""", matter_number)

    # --- Extract document-tab counts ---
    doc_counts = page.evaluate("""() => {
        const labels = ["Exhibits", "Key", "Other", "Transcripts", "Recordings"];
        const all = [...document.querySelectorAll('div, span')];
        const result = {};

        for (const keyword of labels) {
            let bestLabel = null;
            let bestW = 9999;
            for (const d of all) {
                const t = d.textContent.trim();
                if (t.toLowerCase().includes(keyword.toLowerCase()) && t.length < 40) {
                    const r = d.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0 && r.width < 200 && r.width < bestW) {
                        bestW = r.width;
                        bestLabel = {x: r.x + r.width / 2, y: r.y + r.height / 2, text: t};
                    }
                }
            }
            if (!bestLabel) continue;

            let bestNum = null;
            let bestDist = 999;
            for (const d of all) {
                if (d.children.length > 0) continue;
                const t = d.textContent.trim();
                if (!/^\\d+$/.test(t)) continue;
                const r = d.getBoundingClientRect();
                if (r.width <= 0 || r.height <= 0 || r.width > 80) continue;
                const cx = r.x + r.width / 2;
                const cy = r.y + r.height / 2;
                const dx = Math.abs(cx - bestLabel.x);
                const dy = cy - bestLabel.y;
                if (dx < 60 && dy > 0 && dy < 80) {
                    const dist = dx + dy;
                    if (dist < bestDist) {
                        bestDist = dist;
                        bestNum = t;
                    }
                }
            }
            if (bestNum !== null) {
                result[bestLabel.text] = bestNum;
            }
        }
        return result;
    }""")

    metadata: Dict[str, str] = {
        "matter_number": matter_number,
        "fields": fields or {},
        "doc_counts": doc_counts or {},
    }
    for key, val in (fields or {}).items():
        metadata[key] = val

    return metadata
