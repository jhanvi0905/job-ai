from jobai.assistant.integrations.notion import _page_to_plain_dict, _plain_value


def test_plain_value_title():
    assert _plain_value({"type": "title", "title": [{"plain_text": "AI Engineer"}]}) == "AI Engineer"


def test_plain_value_select_none():
    assert _plain_value({"type": "select", "select": None}) is None


def test_plain_value_rich_text_joins_segments():
    prop = {"type": "rich_text", "rich_text": [{"plain_text": "Hello "}, {"plain_text": "world"}]}
    assert _plain_value(prop) == "Hello world"


def test_page_to_plain_dict_flattens_properties():
    page = {
        "id": "page-1",
        "url": "https://notion.so/page-1",
        "properties": {
            "Opportunity": {"type": "title", "title": [{"plain_text": "AI Engineer — Acme"}]},
            "Company": {"type": "rich_text", "rich_text": [{"plain_text": "Acme"}]},
            "Status": {"type": "select", "select": {"name": "Discovered"}},
        },
    }
    flat = _page_to_plain_dict(page)
    assert flat["notion_page_id"] == "page-1"
    assert flat["Opportunity"] == "AI Engineer — Acme"
    assert flat["Company"] == "Acme"
    assert flat["Status"] == "Discovered"
