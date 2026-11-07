"""Gitless PAPER release attestation: offline fixtures only; no VPS runtime."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import pytest

from tools.vps_release_identity import (
    ReleaseIdentityBlocked, git_blob_hash, verify_release, create_manifest, main,
)


def example(root: Path):
    source = root / "terminal/runtime/paper_http_server.py"
    verifier = root / "tools/vps_release_identity.py"
    source.parent.mkdir(parents=True)
    verifier.parent.mkdir(parents=True)
    source.write_bytes(b"paper backend")
    verifier.write_bytes(b"release verifier")
    blobs = {
        "terminal/runtime/paper_http_server.py": git_blob_hash(source.read_bytes()),
        "tools/vps_release_identity.py": git_blob_hash(verifier.read_bytes()),
    }
    manifest = root / "release-manifest.json"
    manifest.write_text(json.dumps({"build_sha": "a" * 40, "blobs": blobs}))
    return manifest, source, blobs


def test_exact_blobs_verified_in_gitless_install():
    with TemporaryDirectory() as temp:
        root = Path(temp)
        manifest, _, _ = example(root)
        assert verify_release(root, manifest, require_protected_manifest=False) == "a" * 40


def test_unprotected_manifest_is_rejected_before_reading_files():
    with TemporaryDirectory() as temp:
        root = Path(temp)
        manifest, _, _ = example(root)
        with mock.patch.object(Path, "stat", return_value=mock.Mock(st_uid=1001, st_mode=0o100644)):
            with pytest.raises(ReleaseIdentityBlocked, match="release_manifest_not_root_protected"):
                verify_release(root, manifest)


def test_tampered_installed_code_rejected():
    with TemporaryDirectory() as temp:
        root = Path(temp)
        manifest, source, _ = example(root)
        source.write_bytes(b"other backend")
        with pytest.raises(ReleaseIdentityBlocked, match="tracked_content_mismatch"):
            verify_release(root, manifest, require_protected_manifest=False)


def test_missing_or_symlink_manifest_rejected():
    with TemporaryDirectory() as temp:
        root = Path(temp)
        manifest, _, _ = example(root)
        manifest.unlink()
        with pytest.raises(ReleaseIdentityBlocked, match="release_manifest_missing_or_symlink"):
            verify_release(root, manifest, require_protected_manifest=False)
        other = root / "other.json"
        other.write_text("{}")
        manifest.symlink_to(other)
        with pytest.raises(ReleaseIdentityBlocked, match="release_manifest_missing_or_symlink"):
            verify_release(root, manifest, require_protected_manifest=False)


def test_traversal_and_symlinked_tracked_paths_rejected():
    with TemporaryDirectory() as temp:
        root = Path(temp)
        manifest, _, blobs = example(root)
        blobs["../outside"] = git_blob_hash(b"x")
        manifest.write_text(json.dumps({"build_sha": "a" * 40, "blobs": blobs}))
        with pytest.raises(ReleaseIdentityBlocked, match="invalid_manifest_path"):
            verify_release(root, manifest, require_protected_manifest=False)
        blobs.pop("../outside")
        external = root / "external"
        external.mkdir()
        (external / "file.py").write_bytes(b"x")
        (root / "external-link").symlink_to(external, target_is_directory=True)
        blobs["external-link/file.py"] = git_blob_hash(b"x")
        manifest.write_text(json.dumps({"build_sha": "a" * 40, "blobs": blobs}))
        with pytest.raises(ReleaseIdentityBlocked, match="tracked_symlink_not_supported"):
            verify_release(root, manifest, require_protected_manifest=False)


def test_sha_without_complete_tracked_manifest_rejected():
    with TemporaryDirectory() as temp:
        root = Path(temp)
        manifest, _, blobs = example(root)
        del blobs["tools/vps_release_identity.py"]
        manifest.write_text(json.dumps({"build_sha": "a" * 40, "blobs": blobs}))
        with pytest.raises(ReleaseIdentityBlocked, match="backend_or_verifier_not_tracked"):
            verify_release(root, manifest, require_protected_manifest=False)


def test_incorrect_sha_staging_ref_rejected_before_any_manifest_output():
    with TemporaryDirectory() as temp:
        root = Path(temp)
        example(root)
        def command(argv, **kw):
            if argv[1] == "rev-parse":
                return mock.Mock(stdout=(("b" * 40) + "\n").encode())
            raise AssertionError("must not read tree after SHA mismatch")
        with mock.patch("tools.vps_release_identity.subprocess.run", side_effect=command):
            with pytest.raises(ReleaseIdentityBlocked, match="staging_commit_mismatch"):
                create_manifest(root, "a" * 40)


def test_exact_git_tree_manifest_generation():
    with TemporaryDirectory() as temp:
        root = Path(temp)
        _, _, blobs = example(root)
        tree = b"".join(
            b"100644 blob " + digest.encode() + b"\t" + name.encode() + b"\0"
            for name, digest in blobs.items()
        )
        def command(argv, **kw):
            return mock.Mock(stdout=(("a" * 40) + "\n").encode()
                             if argv[1] == "rev-parse" else tree)
        with mock.patch("tools.vps_release_identity.subprocess.run", side_effect=command):
            assert create_manifest(root, "a" * 40) == {
                "build_sha": "a" * 40, "blobs": blobs,
            }


def test_exec_backend_passes_only_verified_sha_into_same_pid():
    with TemporaryDirectory() as temp:
        root = Path(temp)
        manifest, _, _ = example(root)
        with mock.patch("tools.vps_release_identity.verify_release", return_value="a" * 40):
            with mock.patch("tools.vps_release_identity.os.execve") as execve:
                with mock.patch("tools.vps_release_identity.os.environ", {"BYBITSCANNER_BUILD_SHA": "untrusted"}):
                    assert main(["exec-backend"]) == 3
                execve.assert_called_once()
                env = execve.call_args.args[2]
                assert env["BYBITSCANNER_BUILD_SHA"] == "a" * 40
                assert execve.call_args.args[1][-2:] == [
                    "-m", "terminal.runtime.paper_http_server",
                ]
