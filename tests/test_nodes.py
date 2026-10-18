"""Pure helpers in busabase_dify.nodes."""

import pytest

from busabase_dify.nodes import broaden_queries, flatten_tree, parse_queries, slugify


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('["写周报", "weekly report"]', ["写周报", "weekly report"]),
        ("weekly report\n写周报", ["weekly report", "写周报"]),
        ("a | b ; c，d", ["a", "b", "c", "d"]),
        (["x", "x", " y "], ["x", "y"]),
        ("", []),
        (None, []),
    ],
)
def test_parse_queries(raw, expected):
    assert parse_queries(raw) == expected


def test_broaden_queries_splits_words_and_drops_short_ones():
    assert broaden_queries(["qualify a lead", "lead"]) == ["qualify"]
    assert broaden_queries(["写周报"]) == []


@pytest.mark.parametrize(
    ("name", "slug"),
    [("Q3 Launch Plan", "q3-launch-plan"), ("  Café — notes!  ", "cafe-notes"), ("周报", ""), ("a" * 80, "a" * 60)],
)
def test_slugify(name, slug):
    assert slugify(name) == slug


def test_flatten_tree_marks_unloaded_children():
    tree = [{"id": "a", "type": "folder", "slug": "a", "name": "A", "parentId": None, "hasChildren": True, "children": []}]
    assert flatten_tree(tree)[0]["hasMoreChildren"] is True
