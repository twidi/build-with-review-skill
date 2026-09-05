from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "install.sh"
SOURCE = ROOT / "skill"


class InstallScriptTest(unittest.TestCase):
    def run_install(self, home: Path) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["HOME"] = str(home)
        return subprocess.run(
            [str(SCRIPT)],
            cwd=home,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_installs_shared_copy_and_claude_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)

            result = self.run_install(home)

            self.assertEqual(result.returncode, 0, result.stderr)
            target = home / ".agents/skills/build-with-review"
            claude_link = home / ".claude/skills/build-with-review"
            self.assertEqual(
                (target / "SKILL.md").read_bytes(),
                (SOURCE / "SKILL.md").read_bytes(),
            )
            self.assertTrue(claude_link.is_symlink())
            self.assertEqual(claude_link.resolve(), target.resolve())
            self.assertFalse(any(target.rglob("__pycache__")))
            self.assertFalse(any(target.rglob("*.pyc")))

    def test_updates_an_existing_installation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            first_result = self.run_install(home)
            self.assertEqual(first_result.returncode, 0, first_result.stderr)

            target = home / ".agents/skills/build-with-review"
            claude_link = home / ".claude/skills/build-with-review"
            (target / "SKILL.md").write_text(
                "---\nname: build-with-review\n---\nstale\n",
                encoding="utf-8",
            )
            obsolete = target / "obsolete.md"
            obsolete.write_text("obsolete\n", encoding="utf-8")

            result = self.run_install(home)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                (target / "SKILL.md").read_bytes(),
                (SOURCE / "SKILL.md").read_bytes(),
            )
            self.assertFalse(obsolete.exists())
            self.assertTrue(claude_link.is_symlink())
            self.assertEqual(claude_link.resolve(), target.resolve())
            self.assertFalse((target / "build-with-review").exists())
            self.assertFalse((target / "build-with-review").is_symlink())

    def test_refuses_a_real_entry_at_the_claude_link_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            target = home / ".agents/skills/build-with-review"
            claude_path = home / ".claude/skills/build-with-review"
            claude_path.mkdir(parents=True)

            result = self.run_install(home)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not a symlink", result.stderr)
            self.assertFalse(target.exists())
            self.assertFalse((claude_path / "build-with-review").is_symlink())

    def test_refuses_a_symlink_as_the_canonical_installation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            agents_dir = home / ".agents/skills"
            agents_dir.mkdir(parents=True)
            external = home / "external"
            external.mkdir()
            sentinel = external / "keep.txt"
            sentinel.write_text("keep\n", encoding="utf-8")
            (agents_dir / "build-with-review").symlink_to(external)

            result = self.run_install(home)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must not be a symlink", result.stderr)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep\n")
            self.assertFalse((external / "SKILL.md").exists())

    def test_refuses_an_unrelated_canonical_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            target = home / ".agents/skills/build-with-review"
            target.mkdir(parents=True)
            sentinel = target / "keep.txt"
            sentinel.write_text("keep\n", encoding="utf-8")

            result = self.run_install(home)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("is not a Build With Review installation", result.stderr)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep\n")
            self.assertFalse((target / "SKILL.md").exists())

    def test_corrects_an_existing_claude_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            first_result = self.run_install(home)
            self.assertEqual(first_result.returncode, 0, first_result.stderr)

            target = home / ".agents/skills/build-with-review"
            claude_link = home / ".claude/skills/build-with-review"
            claude_link.unlink()
            claude_link.symlink_to(home / "old-installation")

            result = self.run_install(home)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(claude_link.is_symlink())
            self.assertEqual(claude_link.resolve(), target.resolve())


if __name__ == "__main__":
    unittest.main()
