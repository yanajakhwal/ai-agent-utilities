# Coding Agent Session

## Goal
Build an AI agent that:
1. Receives an email containing a **matter number** and **document type**
2. Navigates the Nova Scotia Regulatory Board public database
3. Downloads up to **10 documents**
4. Compresses them into a **ZIP file**
5. Emails the ZIP file back with **metadata about the matter**

Example input email:
"Hi Agent, can you give me Other Documents from M12205?"

---

# System Design

I broke the problem into independent components so the agent could build and test each step quickly.

### Components
1. **Email Parser**
   - Extract `matter_number`
   - Extract `document_type`

2. **Website Navigation**
   - Navigate to:
   https://uarb.novascotia.ca/fmi/webd/UARB15
   - Enter matter number
   - Open relevant document tab

3. **Document Scraper**
   - Count available documents
   - Download up to 10 using the **GO GET IT** links

4. **Metadata Extractor**
   Extract:
   - Matter title
   - Category
   - Type
   - Date received
   - Date final submissions

5. **ZIP Compressor**
   - Bundle downloaded files

6. **Email Response**
   - Attach ZIP
   - Include metadata summary
   - Include document counts

---

# Coding Agent Interaction

## Initial Prompt

I asked the coding agent to design a scraper capable of navigating the regulatory site and downloading documents automatically.

Prompt:

> Build a Python script that navigates the Nova Scotia Regulatory Board public document database, searches by matter number, downloads up to 10 documents from a selected tab, and compresses them into a ZIP file.

The agent suggested using:

- `Playwright` for browser automation
- `requests` for downloads
- `zipfile` for compression
- `smtplib` for sending email

---

# Implementation

This section shows the core end-to-end flow the agent uses. The real project would split these into separate modules, but here I focus on clarity over structure.

### Email Parsing

```python
import re
from dataclasses import dataclass

@dataclass
class EmailRequest:
    matter_number: str
    document_type: str

def parse_email(text: str) -> EmailRequest:
    """
    Example: 'Hi Agent, can you give me Other Documents from M12205?'
    """
    matter_match = re.search(r"M\d{5}", text)
    if not matter_match:
        raise ValueError("Could not find matter number in email.")

    type_match = re.search(
        r"\b(Other Documents|Evidence|Decision|Order|All Documents)\b",
        text,
        flags=re.IGNORECASE,
    )
    document_type = type_match.group(1) if type_match else "All Documents"

    return EmailRequest(
        matter_number=matter_match.group(0),
        document_type=document_type,
    )
```

### Website Automation, Scraping, and Metadata

```python
from pathlib import Path
from typing import List, Tuple, Dict
from playwright.sync_api import sync_playwright

MAX_DOCS = 10

def fetch_documents_and_metadata(
    matter_number: str,
    document_type: str,
    download_dir: Path,
) -> Tuple[List[Path], Dict[str, str]]:
    download_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto("https://uarb.novascotia.ca/fmi/webd/UARB15")

        # Assumption: there is a single matter search field on the landing page
        page.fill("input", matter_number)
        page.click("text=Search")
        page.wait_for_load_state("networkidle")

        # Assumption: document_type corresponds to a visible tab label
        if document_type.lower() != "all documents":
            page.click(f"text={document_type}")
            page.wait_for_load_state("networkidle")

        # Extract core matter metadata from a details panel/table
        metadata = {
            "matter_number": matter_number,
            "title": page.text_content("css=[data-testid='matter-title']") or "",
            "category": page.text_content("css=[data-testid='matter-category']") or "",
            "type": page.text_content("css=[data-testid='matter-type']") or "",
            "date_received": page.text_content("css=[data-testid='date-received']") or "",
            "date_final_submissions": page.text_content("css=[data-testid='date-final-submissions']") or "",
        }

        # Find up to 10 'GO GET IT' links and download them
        links = page.query_selector_all("text=GO GET IT")
        downloaded_files: List[Path] = []

        for idx, link in enumerate(links[:MAX_DOCS], start=1):
            href = link.get_attribute("href")
            if not href:
                continue

            # Use Playwright's built-in request client to fetch the file bytes
            response = page.request.get(href)
            if not response.ok:
                continue

            filename = f"{matter_number}_{idx}.pdf"
            target_path = download_dir / filename
            target_path.write_bytes(response.body())
            downloaded_files.append(target_path)

        browser.close()

    return downloaded_files, metadata
```

### Zipping and Email Response

```python
import zipfile
from email.message import EmailMessage
import smtplib
from pathlib import Path
from typing import List

def create_zip(files: List[Path], matter_number: str, output_dir: Path) -> Path:
    zip_path = output_dir / f"{matter_number}_documents.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in files:
            zf.write(fp, arcname=fp.name)
    return zip_path

def send_email_with_zip(
    to_address: str,
    subject: str,
    body: str,
    zip_path: Path,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
):
    msg = EmailMessage()
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.set_content(body)

    msg.add_attachment(
        zip_path.read_bytes(),
        maintype="application",
        subtype="zip",
        filename=zip_path.name,
    )

    with smtplib.SMTP_SSL(smtp_host, smtp_port) as smtp:
        smtp.login(smtp_user, smtp_password)
        smtp.send_message(msg)
```

### End-to-End Orchestrator

```python
from pathlib import Path

def run_agent(email_text: str, download_root: Path, smtp_config: dict) -> dict:
    # 1. Parse the incoming email
    request = parse_email(email_text)

    # 2. Fetch documents + metadata from the regulatory site
    download_dir = download_root / request.matter_number
    files, metadata = fetch_documents_and_metadata(
        matter_number=request.matter_number,
        document_type=request.document_type,
        download_dir=download_dir,
    )

    # 3. Create ZIP archive
    zip_path = create_zip(files, request.matter_number, download_root)

    # 4. Build response body with metadata and counts
    body = (
        f"Matter {metadata.get('matter_number')} — {metadata.get('title')}\n"
        f"Category: {metadata.get('category')} | Type: {metadata.get('type')}\n"
        f"Date received: {metadata.get('date_received')}\n"
        f"Date final submissions: {metadata.get('date_final_submissions')}\n\n"
        f"Attached are {len(files)} documents matching '{request.document_type}'."
    )

    # 5. Send the email back to the original requester (omitted: parsing 'from' address)
    send_email_with_zip(
        to_address="yjakhwal@uwaterloo.ca",
        subject=f"Documents for {request.matter_number}",
        body=body,
        zip_path=zip_path,
        smtp_host=smtp_config["host"],
        smtp_port=smtp_config["port"],
        smtp_user=smtp_config["user"],
        smtp_password=smtp_config["password"],
    )

    return {
        "zip_path": str(zip_path),
        "metadata": metadata,
        "file_count": len(files),
    }
```