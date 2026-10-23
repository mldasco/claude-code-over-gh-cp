import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import run as runner
import start_litellm


class RoamingUserSiteTests(unittest.TestCase):
    def test_runtime_config_combines_settings_with_local_models(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base_config = root / "copilot-config.yaml"
            model_config = root / "copilot-models.local.yaml"
            output = root / "venv/copilot-config.generated.yaml"
            output.parent.mkdir()
            base_config.write_text("litellm_settings:\n  drop_params: true\n", encoding="utf-8")
            model_config.write_text(
                "model_list:\n  - model_name: local-model\n"
                "    litellm_params:\n      model: github_copilot/local-model\n",
                encoding="utf-8",
            )

            self.assertEqual(
                start_litellm._write_runtime_config(base_config, model_config, output),
                output,
            )
            import yaml

            data = yaml.safe_load(output.read_text(encoding="utf-8"))
            self.assertTrue(data["litellm_settings"]["drop_params"])
            self.assertEqual(data["model_list"][0]["model_name"], "local-model")

    def test_setup_cleanup_preserves_only_pip_and_roaming_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            packages = root / "venv/Lib/site-packages"
            for name in ("pip", "pip-26.2.1.dist-info", "pydantic_core", "litellm"):
                (packages / name).mkdir(parents=True)
            for name in ("roaming_user_site.pth", "pywin32.pth"):
                (packages / name).touch()
            marker = root / "venv/.cost_tracking_ready"
            marker.touch()
            with patch.object(runner.sys, "platform", "win32"), patch.object(runner, "ROOT", root):
                runner._clean_windows_venv_dependencies()
                runner._clean_windows_venv_dependencies()
                self.assertEqual(runner._windows_venv_dependencies(), [])
            self.assertEqual(
                sorted(entry.name for entry in packages.iterdir()),
                ["pip", "pip-26.2.1.dist-info", "roaming_user_site.pth"],
            )
            self.assertTrue(marker.exists())

    def test_start_rejects_mixed_venv_before_stopping_proxy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            python = root / "venv/Scripts/python.exe"
            python.parent.mkdir(parents=True)
            python.touch()
            (root / "venv/Lib/site-packages/pydantic_core").mkdir(parents=True)
            with patch.object(runner.sys, "platform", "win32"), patch.object(
                runner, "ROOT", root
            ), patch.object(runner.subprocess, "run") as stop, patch.object(
                runner, "_apply_litellm_patches"
            ) as apply_patches, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(runner.cmd_start(), 1)
                stop.assert_not_called()
                apply_patches.assert_not_called()

    def test_failed_import_check_does_not_stop_proxy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            python = root / "venv/Scripts/python.exe"
            python.parent.mkdir(parents=True)
            python.touch()
            with patch.object(runner.sys, "platform", "win32"), patch.object(
                runner, "ROOT", root
            ), patch.object(runner, "_configure_roaming_user_site"), patch.object(
                runner, "_run", return_value=1
            ) as preflight, patch.object(runner.subprocess, "run") as stop, patch.object(
                runner, "_apply_litellm_patches"
            ) as apply_patches, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(runner.cmd_start(), 1)
                self.assertEqual(preflight.call_args.args[0][0], str(python))
                stop.assert_not_called()
                apply_patches.assert_not_called()

    def test_roaming_is_added_in_current_and_new_interpreters(self):
        original_path = sys.path[:]
        self.addCleanup(sys.path.__setitem__, slice(None), original_path)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(runner.sys, "platform", "win32"), patch.object(
                runner, "ROOT", root
            ), patch.object(runner, "resolve_workspace_user_home", return_value=root / "home"):
                roaming = runner._configure_roaming_user_site()
                self.assertIn(str(roaming), sys.path)
                runner._configure_roaming_user_site()
                self.assertEqual(sys.path.count(str(roaming)), 1)
                sys.path.remove(str(roaming))
                pth = root / "venv/Lib/site-packages/roaming_user_site.pth"
                exec(pth.read_text(encoding="utf-8"))
                self.assertIn(str(roaming), sys.path)

    def test_windows_setup_installs_into_roaming(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".env").touch()
            with patch.object(runner.sys, "platform", "win32"), patch.object(
                runner, "ROOT", root
            ), patch.object(runner, "_configure_roaming_user_site", return_value=root / "roaming"), patch.object(
                runner, "cmd_install_claude", return_value=0
            ), patch.object(runner, "_check") as check, patch.object(
                runner, "_apply_litellm_patches"
            ), patch.object(runner, "_auto_setup_cost_tracking"), patch.object(
                runner, "_refresh_copilot_model_config", return_value=0
            ) as refresh, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(runner.cmd_setup(), 0)
                refresh.assert_called_once_with()
                self.assertEqual(
                    check.call_args_list[1].args[0],
                    [str(runner._venv_python()), "-m", "pip", "install", "--target",
                     str(root / "roaming"), "--upgrade", "-r", "requirements.txt"],
                )
                self.assertIn("from litellm import run_server", check.call_args_list[2].args[0][-1])

    def test_model_refresh_authenticates_before_fetching_models(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            python = root / "venv" / "Scripts" / "python.exe"
            with patch.object(runner, "ROOT", root), patch.object(
                runner, "_venv_python", return_value=python
            ), patch.object(runner, "_run", side_effect=[0, 0]) as run:
                self.assertEqual(runner._refresh_copilot_model_config(), 0)

            self.assertEqual(
                [call.args[0] for call in run.call_args_list],
                [
                    [str(python), str(runner.SCRIPTS / "start_litellm.py"), "--auth-only"],
                    [str(python), str(runner.SCRIPTS / "list_copilot_models.py"), "--refresh-config"],
                ],
            )

    def test_setup_does_not_report_success_when_installed_packages_fail_to_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(runner.sys, "platform", "win32"), patch.object(
                runner, "ROOT", root
            ), patch.object(runner, "_configure_roaming_user_site", return_value=root / "roaming"), patch.object(
                runner, "cmd_install_claude", return_value=0
            ), patch.object(
                runner, "_check", side_effect=[None, None, subprocess.CalledProcessError(1, "import check")]
            ), patch.object(runner, "_apply_litellm_patches") as apply_patches, patch.object(
                runner, "_auto_setup_cost_tracking"
            ) as cost_tracking, contextlib.redirect_stdout(io.StringIO()) as output:
                with self.assertRaises(subprocess.CalledProcessError):
                    runner.cmd_setup()
                self.assertNotIn("[OK] Setup complete", output.getvalue())
                apply_patches.assert_not_called()
                cost_tracking.assert_not_called()

    def test_schema_prefers_roaming_over_venv(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            roaming = root / "roaming"
            schema = roaming / "litellm/proxy/schema.prisma"
            schema.parent.mkdir(parents=True)
            schema.touch()
            with patch.object(runner.sys, "platform", "win32"), patch.object(
                runner, "ROOT", root
            ), patch.object(runner, "_roaming_user_site", return_value=roaming):
                self.assertEqual(runner._find_litellm_schema(), schema)

    def test_prisma_lookup_uses_roaming_installation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            roaming = root / "roaming"
            (roaming / "prisma").mkdir(parents=True)
            cli = roaming / "Scripts/prisma.exe"
            cli.parent.mkdir()
            cli.touch()
            with patch.object(runner.sys, "platform", "win32"), patch.object(
                runner, "ROOT", root
            ), patch.object(runner, "_roaming_user_site", return_value=roaming):
                self.assertTrue(runner._prisma_in_venv())
                self.assertEqual(runner._prisma_bin(), cli)

    def test_non_windows_leaves_user_site_unchanged(self):
        with patch.object(runner.sys, "platform", "linux"):
            self.assertIsNone(runner._configure_roaming_user_site())


if __name__ == "__main__":
    unittest.main()