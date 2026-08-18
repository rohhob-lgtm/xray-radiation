#!/usr/bin/env python3
"""
Batch-index all un-indexed rag_pages with ColPali/OpenCLIP visual embeddings.
Run as: backend/.venv/bin/python backend/scripts/index_pages.py
"""
import os, sys, asyncio, logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["COLPALI_BACKEND"] = "openclip"

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(message)s")

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

url = os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)
engine = create_engine(url)


async def main():
    from api.services.colpali_service import _init_backend, embed_image
    from api.db.crud import update_rag_page_vecs
    from api.db.models import RagPage

    backend = await _init_backend()
    print(f"Backend: {backend}")
    if backend == "disabled":
        print("No visual backend available"); return

    with Session(engine) as db:
        pages = (
            db.query(RagPage)
            .filter(RagPage.colpali_vecs == None)
            .order_by(RagPage.doc_filename, RagPage.page_num)
            .all()
        )
        total = len(pages)
        print(f"Indexing {total} pages …")

        ok = err = 0
        for i, page in enumerate(pages):
            try:
                vecs = await embed_image(bytes(page.image_data))
                if vecs:
                    update_rag_page_vecs(db, page.id, vecs, backend)
                    ok += 1
                    if ok % 25 == 0:
                        print(f"  {ok}/{total} done — last: {page.doc_filename[:40]} p{page.page_num}")
                        sys.stdout.flush()
            except Exception as e:
                err += 1
                if err <= 3:
                    print(f"  [!] {page.id}: {e}")

    print(f"\nFinished: {ok} indexed, {err} errors")


asyncio.run(main())
