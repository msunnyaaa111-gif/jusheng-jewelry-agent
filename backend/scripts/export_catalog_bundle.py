from __future__ import annotations

import json
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings
from app.repositories.product_repository import ProductRepository


def main() -> None:
    settings = get_settings()
    repository = ProductRepository(settings)
    repository.load_catalog(force_reload=True)

    bundle_dir = settings.backend_root / "data" / "catalog_bundle"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    output_path = bundle_dir / "products.json"
    output_path.write_text(
        json.dumps(repository.products, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    source_path = repository.catalog_source_path or repository.workbook_path
    media_dir = settings.backend_root / "data" / "catalog_media"

    print("Catalog bundle export complete.")
    print(f"Source: {source_path}")
    print(f"Products: {len(repository.products)}")
    print(f"JSON: {output_path}")
    print(f"Media dir: {media_dir}")


if __name__ == "__main__":
    main()
