from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

from playwright.sync_api import sync_playwright

MAX_DOCS = 10
BASE_URL = "https://uarb.novascotia.ca/fmi/webd/UARB15"


def fetch_documents_and_metadata(
    matter_number: str,
    document_type: str,
    download_dir: Path,
) -> Tuple[List[Path], Dict[str, str]]:
    """
    Use Playwright to navigate the regulatory site, select the appropriate
    document tab, download up to MAX_DOCS documents, and extract metadata.

    The CSS selectors used here are based on assumptions and may need to be
    updated against the live site.
    """
    download_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(BASE_URL)

        # Assumption: there is a single matter search field on the landing page
        page.fill("input", matter_number)
        page.click("text=Search")
        page.wait_for_load_state("networkidle")

        # Assumption: document_type corresponds to a visible tab label
        if document_type.lower() != "all documents":
            page.click(f"text={document_type}")
            page.wait_for_load_state("networkidle")

        metadata: Dict[str, str] = {
            "matter_number": matter_number,
            "title": page.text_content("css=[data-testid='matter-title']") or "",
            "category": page.text_content("css=[data-testid='matter-category']") or "",
            "type": page.text_content("css=[data-testid='matter-type']") or "",
            "date_received": page.text_content("css=[data-testid='date-received']") or "",
            "date_final_submissions": page.text_content(
                "css=[data-testid='date-final-submissions']"
            )
            or "",
        }

        # Find up to MAX_DOCS "GO GET IT" links and download them
        links = page.query_selector_all("text=GO GET IT")
        downloaded_files: List[Path] = []

        for idx, link in enumerate(links[:MAX_DOCS], start=1):
            href = link.get_attribute("href")
            if not href:
                continue

            response = page.request.get(href)
            if not response.ok:
                continue

            filename = f"{matter_number}_{idx}.pdf"
            target_path = download_dir / filename
            target_path.write_bytes(response.body())
            downloaded_files.append(target_path)

        browser.close()

    return downloaded_files, metadata

