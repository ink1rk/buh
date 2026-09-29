"""Стойки можно поставить вплотную, повёрнутый щит занимает другую проекцию."""

from itms.domain.floorplan import Box, inside, overlaps


def test_touching_edges_do_not_overlap() -> None:
    rack = Box(0, 0, 600, 1000)
    neighbour = Box(600, 0, 600, 1000)
    assert not overlaps(rack, neighbour)
    assert overlaps(rack, Box(599, 0, 600, 1000))


def test_quarter_turn_swaps_the_footprint() -> None:
    panel = Box(0, 0, 800, 250, rotation=90)
    beside = Box(250, 0, 100, 100)
    assert not overlaps(panel, beside)
    assert overlaps(panel, Box(249, 0, 100, 100))
    assert inside(panel, 1000, 1000)
    # После поворота щит занимает 250×800, поэтому не помещается в комнату высотой 700 мм.
    assert not inside(panel, 1000, 700)
