#!/usr/bin/env python3
"""
Script to enable Claude Code Transurban AI Gateway configuration.

Points Claude Code at the internal AI Gateway (https://tokens.transurban.tech)
instead of the local LiteLLM proxy. See the Confluence playbook
"Claude Code via the Transurban AI Gateway".

Usage: claude_gateway_enable.py <personal_key>
"""
import json
import re
import sys
from pathlib import Path

from user_home import resolve_workspace_user_home

GATEWAY_BASE_URL = 'https://tokens.transurban.tech/'
GATEWAY_MODEL = 'claude-opus-5-5'
GATEWAY_HAIKU_MODEL = 'claude-haiku-5-5'


def main():
    if len(sys.argv) != 2:
        print("Usage: claude_gateway_enable.py <personal_key>")
        sys.exit(1)

    personal_key = sys.argv[1]
    claude_dir = resolve_workspace_user_home() / '.claude'
    settings_file = claude_dir / 'settings.json'

    # Create .claude directory if it doesn't exist
    claude_dir.mkdir(exist_ok=True)

    # Load existing settings or create empty dict
    settings = {}
    if settings_file.exists():
        raw = settings_file.read_text(encoding='utf-8')
        try:
            settings = json.loads(raw)
        except json.JSONDecodeError:
            # Auto-repair known extra closing brace after "env" block if present
            repaired = re.sub(r'(\s*\})\s*\},\s*(\r?\n\s*"permissions"\s*:)', r'\1,\2', raw, count=1)
            try:
                settings = json.loads(repaired)
                print(f"[OK] Repaired extra closing brace in {settings_file}")
            except json.JSONDecodeError as exc:
                print(f"[ERROR] {settings_file} contains invalid JSON ({exc}); refusing to overwrite.")
                sys.exit(1)

    # Point Claude Code at the Transurban AI Gateway
    settings['env'] = {
        'ANTHROPIC_AUTH_TOKEN': personal_key,
        'ANTHROPIC_BASE_URL': GATEWAY_BASE_URL,
        'ANTHROPIC_MODEL': GATEWAY_MODEL,
        'ANTHROPIC_DEFAULT_HAIKU_MODEL': GATEWAY_HAIKU_MODEL,
    }

    # Update model to use
    settings['model'] = GATEWAY_MODEL

    # Add schema if it's a new file
    if '$schema' not in settings:
        settings['$schema'] = 'https://json.schemastore.org/claude-code-settings.json'

    # Save updated settings
    with open(settings_file, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=2)

    print('[OK] Updated settings while preserving existing configuration')


if __name__ == '__main__':
    main()
