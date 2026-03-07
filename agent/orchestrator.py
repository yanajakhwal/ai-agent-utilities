from pathlib import Path
from typing import Dict, Any

from .email_parser import parse_email
from .scraper import fetch_documents_and_metadata
from .zipper import create_zip
from .mailer import send_email_with_zip


def run_agent(
    email_text: str,
    download_root: Path,
    smtp_config: Dict[str, Any] | None = None,
    to_address: str | None = None,
    *,
    headless: bool = True,
) -> Dict[str, Any]:
    """
    High-level orchestration function:
    - Parse incoming email
    - Scrape documents and metadata
    - Create ZIP archive
    - Optionally email the result (if smtp_config is provided)
    """
    # 1. Parse the incoming email
    request = parse_email(email_text)

    # 2. Fetch documents + metadata from the regulatory site
    download_dir = download_root / request.matter_number
    files, metadata = fetch_documents_and_metadata(
        matter_number=request.matter_number,
        document_type=request.document_type,
        download_dir=download_dir,
        headless=headless,
    )

    # 3. Create ZIP archive
    zip_path = create_zip(files, request.matter_number, download_root)

    # 4. Build a rich email body with metadata and document counts
    body = _compose_email_body(metadata, request.document_type, len(files))

    # 5. Send the email if SMTP is configured; fall back to saving locally
    email_sent = False
    email_draft_path = None

    if smtp_config and to_address:
        try:
            send_email_with_zip(
                to_address=to_address,
                subject=f"Documents for {request.matter_number}",
                body=body,
                zip_path=zip_path,
                smtp_host=smtp_config["host"],
                smtp_port=smtp_config["port"],
                smtp_user=smtp_config["user"],
                smtp_password=smtp_config["password"],
            )
            email_sent = True
        except Exception as e:
            print(f"\n[!] Could not send email: {e}")
            print("    Your network may be blocking outbound SMTP (ports 465/587).")
            print("    Saving email draft locally instead.\n")

    # Always save the draft so the email content is never lost
    draft_path = download_root / f"{request.matter_number}_email_draft.txt"
    draft_path.write_text(
        f"To: {to_address or '(not set)'}\n"
        f"Subject: Documents for {request.matter_number}\n"
        f"Attachment: {zip_path}\n"
        f"\n{body}\n"
    )
    email_draft_path = str(draft_path)

    return {
        "zip_path": str(zip_path),
        "metadata": metadata,
        "file_count": len(files),
        "email_body": body,
        "email_sent": email_sent,
        "email_draft": email_draft_path,
    }


def _compose_email_body(metadata: Dict[str, Any], document_type: str, downloaded: int) -> str:
    """
    Compose a human-friendly email body from dynamically extracted metadata.
    All field names and document-tab labels come from the page itself.
    """
    matter = metadata.get("matter_number", "unknown")
    fields = metadata.get("fields", {})
    doc_counts = metadata.get("doc_counts", {})

    lines = ["Hi User,\n"]

    # Title — use whichever field key contains "title" or "description"
    title = _find_field(fields, "title", "description")
    if title:
        lines.append(f"{matter} is about the {title}.")
    else:
        lines.append(f"Here are the results for matter {matter}.")

    # Type and Category
    type_val = _find_field(fields, "type")
    category_val = _find_field(fields, "category")
    if type_val and category_val:
        lines.append(f"It relates to {type_val} within the {category_val} category.")
    elif category_val:
        lines.append(f"It falls under the {category_val} category.")
    elif type_val:
        lines.append(f"It is classified as {type_val}.")

    # Dates — use whatever date fields were found
    date_fields = {k: v for k, v in fields.items() if "date" in k or "received" in k or "filing" in k}
    if date_fields:
        date_parts = [f"{_humanize_key(k)}: {v}" for k, v in date_fields.items()]
        lines.append(f"The matter had {' and '.join(date_parts)}.")

    # Document counts — built from whatever tabs the page showed
    if doc_counts:
        count_parts = []
        for label, count_str in doc_counts.items():
            n = int(count_str) if count_str.isdigit() else 0
            count_parts.append(f"no {label}" if n == 0 else f"{n} {label}")

        if len(count_parts) > 1:
            count_summary = ", ".join(count_parts[:-1]) + ", and " + count_parts[-1]
        else:
            count_summary = count_parts[0]
        lines.append(f"\nI found {count_summary}.")

        # Total in requested document type (check both directions since
        # the page might abbreviate e.g. "Other Docs" → "Other")
        total_in_type = 0
        dt_lower = document_type.lower()
        for label, count_str in doc_counts.items():
            lbl = label.lower()
            if lbl in dt_lower or dt_lower in lbl or any(w in dt_lower for w in lbl.split()):
                total_in_type = int(count_str) if count_str.isdigit() else 0
                break

        if total_in_type > 0:
            lines.append(
                f"I downloaded {downloaded} out of the {total_in_type} {document_type} "
                f"and am attaching them as a ZIP here."
            )
        else:
            lines.append(
                f"I downloaded {downloaded} documents and am attaching them as a ZIP here."
            )
    else:
        lines.append(f"\nI downloaded {downloaded} documents and am attaching them as a ZIP here.")

    return " ".join(lines)


def _find_field(fields: Dict[str, str], *keywords: str) -> str:
    """Return the first field value whose key contains any of the given keywords."""
    for key, val in fields.items():
        for kw in keywords:
            if kw in key:
                return val
    return ""


def _humanize_key(key: str) -> str:
    """Turn a snake_case key like 'date_received' into 'Date Received'."""
    return key.replace("_", " ").title()

