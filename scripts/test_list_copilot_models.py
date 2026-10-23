import tempfile
import unittest
from pathlib import Path

from list_copilot_models import refresh_config


class RefreshCopilotModelsTests(unittest.TestCase):
    def test_refresh_creates_a_missing_local_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "copilot-models.local.yaml"
            models = [
                {
                    "id": "claude-opus-4.8",
                    "capabilities": {"type": "chat"},
                    "policy": {"state": "enabled"},
                }
            ]

            self.assertEqual(refresh_config(config_path, models), ["claude-opus-4.8"])
            self.assertIn(
                'model_list:\n  - model_name: "claude-opus-4-8"',
                config_path.read_text(encoding="utf-8"),
            )

    def test_refresh_adds_enabled_chat_models_and_preserves_existing_config(self):
        original = """litellm_settings:
  drop_params: true
model_list:
  - model_name: claude-sonnet
    litellm_params:
      model: github_copilot/claude-sonnet
    model_info:
      input_cost_per_token: 0.000003
# Keep this note
"""
        models = [
            {
                "id": "gpt-new",
                "name": "New GPT",
                "vendor": "GitHub",
                "capabilities": {
                    "type": "chat",
                    "limits": {"max_output_tokens": 1000, "max_context_window_tokens": 8000},
                },
                "policy": {"state": "enabled"},
            },
            {
                "id": "image-new",
                "capabilities": {"type": "image"},
                "policy": {"state": "enabled"},
            },
            {
                "id": "disabled-chat",
                "capabilities": {"type": "chat"},
                "policy": {"state": "disabled"},
            },
            {
                "id": "claude-sonnet",
                "capabilities": {"type": "chat"},
                "policy": {"state": "enabled"},
            },
        ]

        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "copilot-config.yaml"
            config_path.write_text(original, encoding="utf-8")

            self.assertEqual(refresh_config(config_path, models), ["gpt-new"])
            updated = config_path.read_text(encoding="utf-8")
            self.assertIn("# Keep this note", updated)
            self.assertIn("input_cost_per_token: 0.000003", updated)
            self.assertIn('model_name: "gpt-new"', updated)
            self.assertIn('model: "github_copilot/gpt-new"', updated)
            self.assertNotIn("disabled-chat", updated)
            self.assertNotIn("image-new", updated)

            self.assertEqual(refresh_config(config_path, models), [])
            self.assertEqual(config_path.read_text(encoding="utf-8"), updated)


if __name__ == "__main__":
    unittest.main()