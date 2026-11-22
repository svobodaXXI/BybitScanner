"""Offline regression for versioned Machine Time dependency reuse."""
from contextlib import nullcontext
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.local_replay_viewer import launch_environment as env


class SharedEnvironmentTests(unittest.TestCase):
    def test_releases_reuse_same_verified_environment_without_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "local"
            first, second = root / "release-one", root / "release-two"
            (first / "python-wheels").mkdir(parents=True)
            second.mkdir()
            cache = app / "BybitScanner" / "MachineTime" / "python-envs" / env.CACHE_KEY

            def bootstrap(target, wheels):
                self.assertEqual(target, cache)
                self.assertEqual(wheels, first / "python-wheels")
                target.mkdir(parents=True)
                return True

            with patch.object(env, "_environment_lock", return_value=nullcontext()), \
                 patch.object(env, "_usable", side_effect=lambda path: (path / ".machine-time-ready").is_file()), \
                 patch.object(env, "_bootstrap", side_effect=bootstrap) as setup:
                self.assertEqual(env.select_python(first, app), env._interpreter(cache))
                self.assertEqual(env.select_python(second, app), env._interpreter(cache))
                setup.assert_called_once()
            self.assertFalse((first / ".wedge-python").exists())
            self.assertFalse((second / ".wedge-python").exists())

    def test_published_broken_cache_is_not_repaired_and_legacy_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "app"
            release = Path(tmp) / "release"
            (release / "python-wheels").mkdir(parents=True)
            legacy = release / ".wedge-python"
            cache = app / "BybitScanner" / "MachineTime" / "python-envs" / env.CACHE_KEY
            cache.mkdir(parents=True)
            (cache / ".machine-time-ready").touch()
            with patch.object(env, "_usable", side_effect=lambda path: path == legacy), \
                 patch.object(env, "_bootstrap") as setup:
                self.assertEqual(env.select_python(release, app), env._interpreter(legacy))
                setup.assert_not_called()

    def test_missing_dependencies_or_failed_build_does_not_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "app"
            release = Path(tmp) / "release"
            (release / "python-wheels").mkdir(parents=True)
            with patch.object(env, "_environment_lock", return_value=nullcontext()), \
                 patch.object(env, "_usable", return_value=False), \
                 patch.object(env, "_bootstrap", return_value=False):
                self.assertIsNone(env.select_python(release, app))
            root = app / "BybitScanner" / "MachineTime" / "python-envs"
            self.assertFalse((root / env.CACHE_KEY / ".machine-time-ready").exists())


if __name__ == "__main__":
    unittest.main()
