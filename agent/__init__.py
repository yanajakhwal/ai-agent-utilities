"""
Senpilot regulatory document agent package.

Modules:
- email_parser: extract matter_number and document_type from email text
- scraper: navigate the regulatory site and download documents
- zipper: bundle downloaded files into a ZIP archive
- mailer: send ZIP via email
- orchestrator: high-level run_agent function
"""

