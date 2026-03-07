from pathlib import Path
from typing import Iterable
import zipfile


def create_zip(files: Iterable[Path], matter_number: str, output_dir: Path) -> Path:
    zip_path = output_dir / f"{matter_number}_documents.zip"
    output_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in files:
            fp = Path(fp)
            if not fp.exists():
                continue
            zf.write(fp, arcname=fp.name)

    return zip_path

