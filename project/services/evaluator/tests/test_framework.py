import pytest

from evaluator.framework import BY_KEY, PILLARS, band, describe


@pytest.mark.parametrize("key,value,expected", [
    ("P1", 0.6399, "Weak"), ("P1", 0.64, "Good enough"), ("P1", 0.70, "Better"), ("P1", 0.76, "Best"),
    ("P2", 7.9, "Too simple"), ("P2", 8.0, "Good enough"), ("P2", 12.0, "Best"), ("P2", 14.0, "Good enough"),
    ("P2", 16.5, "Too dense"),
    ("P3a", 0.29, "Weak"), ("P3a", 0.45, "Better"), ("P3a", 0.7999, "Best"), ("P3a", 0.80, "Too close"),
    ("P3b", 0.39, "Weak"), ("P3b", 0.55, "Better"), ("P3b", 0.70, "Best"),
])
def test_a_value_on_a_cut_point_belongs_to_the_higher_band(key, value, expected):
    assert band(BY_KEY[key], value) == expected


def test_every_pillar_has_one_more_label_than_cuts():
    for pillar in PILLARS:
        assert len(pillar.labels) == len(pillar.cuts) + 1
        assert list(pillar.cuts) == sorted(pillar.cuts)


def test_describe_publishes_the_frozen_cut_points():
    data = describe()
    assert [p["key"] for p in data["pillars"]] == ["P1", "P2", "P3a", "P3b"]
    assert data["pillars"][0]["cuts"] == [0.64, 0.70, 0.76]
    assert data["pillars"][1]["zone"] == [10.0, 14.0]
