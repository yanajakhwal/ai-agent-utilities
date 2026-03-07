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
    """Find up to MAX_DOCS downloadable items on the current page and save them.

    The UARB site uses a two-step flow:
        1. Click "GO GET IT" → a modal dialog appears showing the filename
        2. Click the filename link inside the dialog → triggers the real download
        3. Click "Close" to dismiss the dialog
    """
    downloaded: List[Path] = []

    go_elements = page.locator("text=/GO GET IT/i")
    n = go_elements.count()
    print(f"  [scraper] Found {n} 'GO GET IT' element(s)")

    for idx in range(min(n, MAX_DOCS)):
        el = go_elements.nth(idx)
        try:
            el.click(timeout=5_000)
            page.wait_for_timeout(1500)

            # The modal shows a filename link (e.g. "100243.pdf") — find and click it
            pdf_link = page.locator("a:has-text('.pdf')").first
            if pdf_link.count() == 0:
                pdf_link = page.locator("text=/.+\\.pdf/i").first

            try:
                with page.expect_download(timeout=20_000) as dl_info:
                    pdf_link.click(timeout=5_000)
                download = dl_info.value
                filename = download.suggested_filename or f"{matter_number}_{idx + 1}.pdf"
                path = download_dir / filename
                download.save_as(str(path))
                downloaded.append(path)
                print(f"  [scraper]   saved {filename}")
            except Exception as e:
                print(f"  [scraper]   download failed for item {idx + 1}: {e}")

            # Dismiss the modal
            close_btn = page.locator("text=Close").first
            try:
                close_btn.click(timeout=3_000)
                page.wait_for_timeout(800)
            except Exception:
                page.keyboard.press("Escape")
                page.wait_for_timeout(800)

        except Exception as e:
            print(f"  [scraper]   could not open item {idx + 1}: {e}")
            continue

    return downloaded


def _filename_from_response(resp, matter_number: str, index: int) -> str:
    """Derive a filename from the response headers or fall back to a numbered name."""
    cd = resp.headers.get("content-disposition", "")
    match = re.search(r'filename="?([^";]+)"?', cd)
    if match:
        return match.group(1).strip()
    return f"{matter_number}_{index + 1}.pdf"


_HEADER_RE = re.compile(
    r'\b(Title|Matter|Date|Type|Status|Outcome|Category|Description|Received|Decision)\b',
    re.IGNORECASE,
)


def _extract_metadata(page: Page, matter_number: str) -> Dict[str, str]:
    """Scrape metadata and document-tab counts from the GWT results page.

    Uses JavaScript to collect all visible text elements with their bounding
    boxes, then matches headers to values and tab labels to count numbers
    by spatial proximity.
    """
    raw = page.evaluate("""() => {
        const items = [];
        for (const d of document.querySelectorAll('div, span')) {
            const t = d.textContent.trim();
            if (!t) continue;
            const r = d.getBoundingClientRect();
            if (r.width <= 0 || r.height <= 0) continue;
            const hasKids = d.children.length > 0;
            items.push({text: t, x: r.x, y: r.y, w: r.width, h: r.height, leaf: !hasKids});
        }
        return items;
    }""")

    if not raw:
        return {"matter_number": matter_number, "fields": {}, "doc_counts": {}}

    leaf_els = [e for e in raw if e["leaf"]]
    elements = sorted(leaf_els, key=lambda e: (round(e["y"] / 10), e["x"]))

    # --- Group into rows (within ~15px vertical tolerance) ---
    rows: list[list[dict]] = []
    cur_row: list[dict] = []
    cur_y = -100.0
    for el in elements:
        if abs(el["y"] - cur_y) > 15:
            if cur_row:
                rows.append(sorted(cur_row, key=lambda e: e["x"]))
            cur_row = [el]
            cur_y = el["y"]
        else:
            cur_row.append(el)
    if cur_row:
        rows.append(sorted(cur_row, key=lambda e: e["x"]))

    metadata: Dict[str, str] = {"matter_number": matter_number}
    fields: Dict[str, str] = {}
    doc_counts: Dict[str, str] = {}

    # --- Identify the HEADER row ---
    # Must contain at least 2 recognisable header words (Title, Matter, Date …)
    # and must NOT look like a data row (no M-numbers, no long text).
    header_row = None
    header_idx = -1
    for i, row in enumerate(rows):
        texts = [e["text"] for e in row]
        hits = sum(1 for t in texts if _HEADER_RE.search(t))
        has_matter_value = any(re.match(r"^M\d{4,}", t) for t in texts)
        if hits >= 2 and not has_matter_value:
            header_row = row
            header_idx = i
            break

    if header_row:
        data_rows = rows[header_idx + 1:]
        for data_row in data_rows:
            for el in data_row:
                best_h = None
                best_d = 999
                for h in header_row:
                    d = abs(el["x"] - h["x"])
                    if d < best_d:
                        best_d = d
                        best_h = h
                if best_h and best_d < 200:
                    key = best_h["text"].strip()
                    val = el["text"].strip()
                    if key and val and key != val:
                        nk = re.sub(r'[^a-z0-9]+', '_', key.lower()).strip('_')
                        if nk not in fields:
                            fields[nk] = val

    # --- Extract document-tab counts via JS (more reliable than row matching) ---
    doc_counts = page.evaluate("""() => {
        const labels = ["Exhibits", "Key", "Other", "Transcripts", "Recordings"];
        const all = [...document.querySelectorAll('div, span')];
        const result = {};

        for (const keyword of labels) {
            // Find the narrowest element containing the keyword
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

            // Find the closest number-only leaf element below this label
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

    metadata["fields"] = fields
    metadata["doc_counts"] = doc_counts or {}

    for key, val in fields.items():
        metadata[key] = val

    return metadata
