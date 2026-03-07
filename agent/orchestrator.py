from pathlib import Path
from typing import Dict, Any

from .email_parser import parse_email
from .scraper import fetch_documents_and_metadata
from .zipper import create_zip
from .mailer import send_email_with_zip


def run_agent(email_text: str, download_root: Path, smtp_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    High-level orchestration function:
    - Parse incoming email
    - Scrape documents and metadata
    - Create ZIP archive
    - Email the result
    """
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

    # 5. Send the email back to the original requester
    # In a real integration, you'd pass in or derive the requester's address.
    send_email_with_zip(
        to_address="requester@example.com",
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

