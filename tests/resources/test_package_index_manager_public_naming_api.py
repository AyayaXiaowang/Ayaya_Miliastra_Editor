from engine.resources.package_index_manager import PackageIndexManager
from engine.utils.name_utils import sanitize_package_filename


def test_package_index_manager_sanitize_package_id_is_public_and_matches_name_utils() -> None:
    assert hasattr(PackageIndexManager, "sanitize_package_id")
    assert callable(getattr(PackageIndexManager, "sanitize_package_id"))

    for name in ["test2", "", "CON", "a/b\\c", "  hello  "]:
        assert PackageIndexManager.sanitize_package_id(name) == sanitize_package_filename(name)


