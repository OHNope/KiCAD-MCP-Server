import sys
from pathlib import Path

import pytest

PYTHON_DIR = Path(__file__).parent.parent / "python"
sys.path.insert(0, str(PYTHON_DIR))

from commands.routing_quality import evaluate_route_quality, rule_catalog  # noqa: E402
from commands.routing import RoutingCommands  # noqa: E402


NM = 1000000


class _Vec:
    def __init__(self, x_mm, y_mm):
        self.x = int(x_mm * NM)
        self.y = int(y_mm * NM)


class _Uuid:
    def __init__(self, value):
        self._value = value

    def AsString(self):
        return self._value


class _Box:
    def __init__(self, x, y, width, height):
        self._x = int(x * NM)
        self._y = int(y * NM)
        self._width = int(width * NM)
        self._height = int(height * NM)

    def GetX(self):
        return self._x

    def GetY(self):
        return self._y

    def GetWidth(self):
        return self._width

    def GetHeight(self):
        return self._height


class _Track:
    def __init__(self, uuid, net, start, end, layer=0):
        self.m_Uuid = _Uuid(uuid)
        self._net = net
        self._start = _Vec(*start)
        self._end = _Vec(*end)
        self._layer = layer

    def GetClass(self):
        return "PCB_TRACK"

    def GetNetname(self):
        return self._net

    def GetStart(self):
        return self._start

    def GetEnd(self):
        return self._end

    def GetLayer(self):
        return self._layer

    def GetLength(self):
        dx = self._end.x - self._start.x
        dy = self._end.y - self._start.y
        return (dx * dx + dy * dy) ** 0.5


class _Via:
    def __init__(self, uuid, net, pos):
        self.m_Uuid = _Uuid(uuid)
        self._net = net
        self._pos = _Vec(*pos)

    def GetClass(self):
        return "PCB_VIA"

    def GetNetname(self):
        return self._net

    def GetPosition(self):
        return self._pos


class _Pad:
    def __init__(self, net, pos):
        self._net = net
        self._pos = _Vec(*pos)

    def GetNetname(self):
        return self._net

    def GetPosition(self):
        return self._pos


class _Footprint:
    def __init__(self, ref, value, pads):
        self._ref = ref
        self._value = value
        self._pads = pads

    def GetReference(self):
        return self._ref

    def GetValue(self):
        return self._value

    def GetFPIDAsString(self):
        return self._value

    def Pads(self):
        return self._pads


class _Board:
    def __init__(self, tracks, footprints=None):
        self._tracks = tracks
        self._footprints = footprints or []

    def Tracks(self):
        return self._tracks

    def GetFootprints(self):
        return self._footprints

    def GetBoardEdgesBoundingBox(self):
        return _Box(0, 0, 100, 100)


@pytest.mark.unit
def test_always_loaded_failed_rules_are_scored():
    result = evaluate_route_quality(
        {
            "traceUuid": "abc",
            "failedRules": [
                "return_path_crossing_split",
                "gnd_plane_not_fragmented",
            ],
        }
    )

    assert result["traceUuid"] == "abc"
    assert result["score"] == 195
    assert [v["rule"] for v in result["violations"]] == [
        "return_path_crossing_split",
        "gnd_plane_not_fragmented",
    ]


@pytest.mark.unit
def test_dynamic_rules_only_score_when_loaded():
    unloaded = evaluate_route_quality({"failedRules": ["decoupling_loop"]})
    loaded = evaluate_route_quality(
        {
            "dynamicRules": ["decoupling_loop"],
            "failedRules": ["decoupling_loop"],
        }
    )

    assert unloaded["score"] == 0
    assert unloaded["ignoredRules"] == ["decoupling_loop"]
    assert loaded["score"] == 100
    assert loaded["violations"][0]["rule"] == "decoupling_loop"


@pytest.mark.unit
def test_rule_results_false_adds_penalty_true_marks_passed():
    result = evaluate_route_quality(
        {
            "dynamicRules": ["usb_diff_quality"],
            "ruleResults": {
                "reference_plane_continuity": True,
                "usb_diff_quality": False,
            },
        }
    )

    assert result["score"] == 95
    assert result["passedRules"] == ["reference_plane_continuity"]
    assert result["violations"] == [
        {"rule": "usb_diff_quality", "score": 95, "load": "dynamic"}
    ]


@pytest.mark.unit
def test_rule_catalog_exposes_always_and_dynamic_groups():
    catalog = rule_catalog()

    assert len(catalog["alwaysLoaded"]) == 8
    assert len(catalog["dynamic"]) == 12
    assert catalog["alwaysLoaded"][0] == {
        "id": "return_path_crossing_split",
        "score": 100,
        "load": "always",
    }


@pytest.mark.unit
def test_auto_detects_board_edge_missing_return_via_and_detour():
    board = _Board(
        [
            _Track("t1", "USB_D_P", (1, 1), (40, 1)),
            _Track("t2", "USB_D_P", (40, 1), (40, 40)),
            _Track("t3", "USB_D_P", (40, 40), (2, 40)),
            _Via("v1", "USB_D_P", (20, 20)),
        ]
    )

    result = RoutingCommands(board).evaluate_routing_quality({"net": "USB_D_P"})

    assert result["success"] is True
    assert "board_edge_high_speed_emi" in result["violatedRules"]
    assert "via_transition_has_return_path" in result["violatedRules"]
    assert "excessive_detour_for_critical_net" in result["violatedRules"]


@pytest.mark.unit
def test_auto_detects_differential_pair_not_together():
    board = _Board(
        [
            _Track("p1", "USB_D_P", (20, 20), (40, 20)),
            _Track("n1", "USB_D_N", (20, 30), (40, 30)),
        ]
    )

    result = RoutingCommands(board).evaluate_routing_quality(
        {"net": "USB_D_P", "dynamicRules": ["differential_pair_together"]}
    )

    assert "differential_pair_together" in result["violatedRules"]
    detail = result["autoDetection"]["details"]["differential_pair_together"]
    assert detail["mateNet"] == "USB_D_N"
    assert detail["unpairedSegments"]


@pytest.mark.unit
def test_auto_detects_crystal_route_with_via():
    board = _Board(
        [
            _Track("x1", "XIN", (20, 20), (25, 20)),
            _Via("xv1", "XIN", (25, 20)),
        ]
    )

    result = RoutingCommands(board).evaluate_routing_quality(
        {"net": "XIN", "dynamicRules": ["crystal_short_no_via"]}
    )

    assert "crystal_short_no_via" in result["violatedRules"]


@pytest.mark.unit
def test_auto_detects_esd_too_far_from_connector():
    board = _Board(
        tracks=[_Track("u1", "USB_D_P", (10, 10), (40, 10))],
        footprints=[
            _Footprint("J1", "USB-C", [_Pad("USB_D_P", (10, 10))]),
            _Footprint("D1", "USBLC6 ESD", [_Pad("USB_D_P", (30, 10))]),
        ],
    )

    result = RoutingCommands(board).evaluate_routing_quality(
        {
            "net": "USB_D_P",
            "dynamicRules": ["esd_close_to_connector"],
            "connectorRefs": ["J1"],
            "esdRefs": ["D1"],
        }
    )

    assert "esd_close_to_connector" in result["violatedRules"]
