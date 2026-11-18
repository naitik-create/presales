"""Customer infrastructure size parser (app.common.sizes)."""
import pytest

from app.common.sizes import parse_sizes


@pytest.mark.parametrize("text,expected", [
    ("Around 1,200 network devices and 450 servers across 35 branches", {"network_devices": 1200, "servers": 450, "sites": 35}),
    ("25k EPS sustained", {"eps": 25000}),
    ("1.5 lakh endpoints, 120 technicians", {"endpoints": 150000, "technicians": 120}),
    ("NCCM devices: 300", {"nccm_devices": 300}),
    ("15% growth over a 3 year contract", {"growth": 0.15, "term_years": 3}),
])
def test_size_parser(text, expected):
    got = parse_sizes(text)
    for k, v in expected.items():
        assert got.get(k) == v, (k, got)
