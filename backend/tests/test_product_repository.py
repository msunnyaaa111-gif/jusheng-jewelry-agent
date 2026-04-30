from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.repositories.product_repository import ProductRepository


class ProductRepositoryQrDedupTests(unittest.TestCase):
    def test_duplicate_qr_assets_fall_back_to_product_image_for_later_items(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend_root = Path(temp_dir)
            media_dir = backend_root / "data" / "catalog_media"
            media_dir.mkdir(parents=True, exist_ok=True)

            duplicate_bytes = b"same-qr-poster"
            unique_bytes = b"unique-qr-poster"
            (media_dir / "dup-a.png").write_bytes(duplicate_bytes)
            (media_dir / "dup-b.png").write_bytes(duplicate_bytes)
            (media_dir / "unique.png").write_bytes(unique_bytes)

            json_path = backend_root / "products.json"
            json_path.write_text(
                json.dumps(
                    [
                        {
                            "product_name": "A",
                            "product_code": "A001",
                            "product_image_url": "/static/catalog_media/a.jpeg",
                            "product_qr_url": "/static/catalog_media/dup-a.png",
                        },
                        {
                            "product_name": "B",
                            "product_code": "B001",
                            "product_image_url": "/static/catalog_media/b.jpeg",
                            "product_qr_url": "/static/catalog_media/dup-b.png",
                        },
                        {
                            "product_name": "C",
                            "product_code": "C001",
                            "product_image_url": "/static/catalog_media/c.jpeg",
                            "product_qr_url": "/static/catalog_media/unique.png",
                        },
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            settings = SimpleNamespace(
                product_json_path=str(json_path),
                product_xlsx_path="",
                backend_root=backend_root,
                project_root=backend_root,
            )
            repository = ProductRepository(settings)

            repository.load_catalog()

            self.assertEqual(repository.products[0]["product_qr_url"], "/static/catalog_media/dup-a.png")
            self.assertIsNone(repository.products[1]["product_qr_url"])
            self.assertEqual(repository.products[2]["product_qr_url"], "/static/catalog_media/unique.png")


if __name__ == "__main__":
    unittest.main()
