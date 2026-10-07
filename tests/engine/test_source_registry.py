from jobai.core.config import load_yaml
from jobai.engine.sources.greenhouse import GreenhouseSource
from jobai.engine.sources.registry import SOURCE_TYPES, build_sources
from jobai.product.services.catalog import catalog_sources


def _entry(name, type_, ident):
    return {"name": name, "source": {"type": type_, "identifier": ident}}


def test_build_sources_dedupes_by_type_and_identifier_and_skips_unknown_types():
    sources = build_sources([
        _entry("Acme", "greenhouse", "acme"),
        _entry("Acme again", "greenhouse", "acme"),
        _entry("Mystery", "workday", "x"),
    ])
    assert [type(s) for s in sources] == [GreenhouseSource]


def test_catalog_config_only_uses_known_adapters_and_verified_entries():
    companies = load_yaml("sources_catalog.yaml")["companies"]
    assert companies, "catalog config must list employers"
    for c in companies:
        assert c["source"]["type"] in SOURCE_TYPES, c["name"]
        assert c.get("verified", {}).get("date"), f"{c['name']} has no verification record"


def test_catalog_includes_legacy_boards_without_duplicates():
    keys = [(type(s).__name__, s.identifier) for s in catalog_sources()]
    assert len(keys) == len(set(keys))
    assert len(keys) > len(load_yaml("sources_catalog.yaml")["companies"])
