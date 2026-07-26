import ast
from pathlib import Path


def test_sources_parse():
    root = Path(__file__).parents[1] / "src" / "querysaas"
    for path in root.glob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_payload_is_embedded_module():
    payload = Path(__file__).parents[1] / "src" / "querysaas" / "xdrz_payload.py"
    assert payload.exists()
    assert "BIP_XDRZ_BASE64" in payload.read_text(encoding="utf-8")
