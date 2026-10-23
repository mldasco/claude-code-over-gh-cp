import contextlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import run as runner


class WindowsClaudeInstallTests(unittest.TestCase):
    def setUp(self):
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def test_missing_vscode_fails_without_installing(self):
        with patch.object(runner.shutil, "which", return_value=None), patch.object(
            runner, "_run"
        ) as install:
            self.assertEqual(runner._install_windows_claude(), 1)
        install.assert_not_called()

    def test_copies_bundled_executable_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "anthropic.claude-code-2.1.308-win32-x64"
            source = directory / "resources" / "native-binary" / "claude.exe"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"bundled executable")
            result = subprocess.CompletedProcess([], 0, str(directory) + "\n", "")
            with patch.object(runner.shutil, "which", return_value="code.cmd"), patch.object(
                runner.subprocess, "run", return_value=result
            ), patch.object(runner, "_configure_windows_claude_path") as configure, patch.object(
                runner.shutil, "copy2", wraps=runner.shutil.copy2
            ) as copy:
                self.assertEqual(runner._install_windows_claude(), 0)
                self.assertEqual(runner._install_windows_claude(), 0)
                copy.assert_called_once_with(source, directory / "claude.exe")
                configure.assert_called_with(directory)
            self.assertEqual((directory / "claude.exe").read_bytes(), source.read_bytes())

    def test_installs_missing_extension_then_locates_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "resources" / "native-binary" / "claude.exe"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"bundled executable")
            results = [
                subprocess.CompletedProcess([], 1, "", "not installed"),
                subprocess.CompletedProcess([], 0, str(directory), ""),
            ]
            with patch.object(runner.shutil, "which", return_value="code.cmd"), patch.object(
                runner.subprocess, "run", side_effect=results
            ), patch.object(runner, "_run", return_value=0) as install, patch.object(
                runner, "_configure_windows_claude_path"
            ):
                self.assertEqual(runner._install_windows_claude(), 0)
                install.assert_called_once_with(
                    ["code.cmd", "--install-extension", "anthropic.claude-code"]
                )

    def test_path_preserves_other_entries_and_removes_old_extension(self):
        registry = MagicMock()
        directory = Path("C:/Users/example/.vscode/extensions/anthropic.claude-code-2.2-win32-x64")
        old = directory.parent / "anthropic.claude-code-2.1-win32-x64"
        original = f"{old};%APPDATA%/npm;C:/Tools;{directory}"
        registry.QueryValueEx.return_value = (original, 2)
        with patch.dict("sys.modules", {"winreg": registry}), patch.dict(
            os.environ, {"PATH": original}
        ):
            runner._configure_windows_claude_path(directory)
            expected = f"{directory};%APPDATA%/npm;C:/Tools"
            self.assertEqual(os.environ["PATH"], expected)
            registry.SetValueEx.assert_called_once_with(
                registry.CreateKeyEx.return_value.__enter__.return_value,
                "Path", 0, 2, expected,
            )
            registry.QueryValueEx.return_value = (expected, 2)
            registry.SetValueEx.reset_mock()
            runner._configure_windows_claude_path(directory)
            registry.SetValueEx.assert_not_called()

    def test_setup_stops_before_venv_if_claude_setup_fails(self):
        with patch.object(runner.sys, "platform", "win32"), patch.object(
            runner, "cmd_install_claude", return_value=1
        ), patch.object(runner, "_check") as check:
            self.assertEqual(runner.cmd_setup(), 1)
            check.assert_not_called()

    def test_configures_versioned_roaming_user_site(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "checkout"
            home = Path(temporary) / "workspace-user"
            roaming_site = (
                home
                / "AppData"
                / "Roaming"
                / "Python"
                / f"Python{runner.sys.version_info.major}{runner.sys.version_info.minor}"
                / "site-packages"
            )
            with patch.object(runner, "ROOT", root), patch.object(
                runner.sys, "platform", "win32"
            ), patch.object(runner, "resolve_workspace_user_home", return_value=home):
                runner._configure_roaming_user_site()
                pth_file = root / "venv" / "Lib" / "site-packages" / "roaming_user_site.pth"
                self.assertEqual(pth_file.read_text(encoding="utf-8"), f"{roaming_site}\n")
                self.assertTrue(roaming_site.is_dir())

                pth_file.write_text("stale path\n", encoding="utf-8")
                runner._configure_roaming_user_site()
                self.assertEqual(pth_file.read_text(encoding="utf-8"), f"{roaming_site}\n")

    def test_roaming_user_site_is_not_configured_off_windows(self):
        with patch.object(runner.sys, "platform", "linux"), patch.object(
            runner, "resolve_workspace_user_home"
        ) as resolve_home:
            runner._configure_roaming_user_site()
        resolve_home.assert_not_called()


if __name__ == "__main__":
    unittest.main()