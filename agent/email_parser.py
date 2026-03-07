import re
from dataclasses import dataclass


@dataclass
class EmailRequest:
    matter_number: str
    document_type: str


def parse_email(text: str) -> EmailRequest:
    """
    Parse free-form email text to extract matter_number and document_type.

    Example: "Hi Agent, can you give me Other Documents from M12205?"
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

