"""Smoke tests for the wayfinding package.

Verifies the package can be imported and has expected top-level attributes.
"""


def test_imports():
    """Import the wayfinding package and verify it has a __version__ attribute.

    This test will fail with ModuleNotFoundError until packages/wayfinding/src/wayfinding/
    is created with a proper __init__.py that defines __version__.
    """
    import wayfinding

    assert hasattr(wayfinding, "__version__")
    assert isinstance(wayfinding.__version__, str)
    assert len(wayfinding.__version__) > 0
