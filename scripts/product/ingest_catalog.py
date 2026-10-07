"""Pull the shared job catalog into the product DB (once for all tenants)."""
from __future__ import annotations

from jobai.product.db.session import make_engine, make_session_factory, session_scope


def main() -> None:
    from jobai.product.services.catalog import ingest_catalog  # lazy: module is owned elsewhere

    with session_scope(make_session_factory(make_engine())) as session:
        result = ingest_catalog(session)
    print(result)


if __name__ == "__main__":
    main()
