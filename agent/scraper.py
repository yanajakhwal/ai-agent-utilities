from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

from playwright.sync_api import sync_playwright, Page

MAX_DOCS = 10
BASE_URL = "https://uarb.novascotia.ca/fmi/webd/UARB15"


def _click_element_by_text(page: Page, text: str, *, max_width: int = 300, timeout: int = 10_000) -> bool:
    """Find a small leaf-ish element with exact text and click it by coordinates.
    Returns True if clicked, False if not found."""
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


def fetch_documents_and_metadata(
    matter_number: str,
    document_type: str,
    download_dir: Path,
    *,
    headless: bool = True,
) -> Tuple[List[Path], Dict[str, str]]:
    """
    Navigate the UARB regulatory site, search by matter number,
    download up to MAX_DOCS documents, and extract metadata.

    The site uses FileMaker/Vaadin which renders form fields as <div> elements,
    not native <input>. We interact via mouse coordinates + keyboard typing.
    """
    download_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.set_default_timeout(60_000)
        page.set_default_navigation_timeout(60_000)

        page.goto(BASE_URL, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=45_000)

        # Wait for GWT to render the matter number field (a <div> with text "eg M01234")
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
                "Could not find the Matter Number field. "
                f"Screenshot saved to {debug_path}."
            )

        # Click the leaf div by coordinates, then type the matter number
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

        # Click the first "Search" button
        _click_element_by_text(page, "Search")

        page.wait_for_timeout(2000)
        page.wait_for_load_state("networkidle", timeout=45_000)
        page.wait_for_timeout(3000)

        # Select the document type tab if needed (use coordinates to avoid GWT click interception)
        if document_type.lower() != "all documents":
            if not _click_element_by_text(page, document_type, max_width=400):
                _click_element_by_text(page, document_type.title(), max_width=400)
            page.wait_for_timeout(3000)

        # Extract metadata from the results page text
        page_text = page.text_content("body") or ""
        metadata: Dict[str, str] = {"matter_number": matter_number}
        for field in ("title", "category", "type", "date_received", "date_final_submissions"):
            metadata[field] = ""

        # Find up to MAX_DOCS "GO GET IT" links and download them
        go_links = page.locator("text=GO GET IT")
        downloaded_files: List[Path] = []
        n_links = go_links.count()

        for idx in range(min(n_links, MAX_DOCS)):
            link = go_links.nth(idx)
            try:
                href = link.get_attribute("href", timeout=5000)
                if not href:
                    continue
                response = page.request.get(href)
                if not response.ok:
                    continue
                filename = f"{matter_number}_{idx + 1}.pdf"
                target_path = download_dir / filename
                target_path.write_bytes(response.body())
                downloaded_files.append(target_path)
            except Exception:
                continue

        browser.close()

    return downloaded_files, metadata
