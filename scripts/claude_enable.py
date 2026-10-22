#!/usr/bin/env python3
"""
Script to enable Claude Code proxy configuration.
Usage: claude_enable.py <master_key>
"""
import json
import re
import sys
import os
from pathlib import Path

from user_home import resolve_workspace_user_home

def main():
    if len(sys.argv) != 2:
        print("Usage: claude_enable.py <master_key>")
        sys.exit(1)

    master_key = sys.argv[1]
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

    # Add proxy configuration
    settings['env'] = {
        'ANTHROPIC_AUTH_TOKEN': master_key,
        'ANTHROPIC_BASE_URL': 'http://localhost:4444',
        'ANTHROPIC_MODEL': 'claude-opus-4-8',
        'ANTHROPIC_SMALL_FAST_MODEL': 'claude-haiku-4-5',
        'ANTHROPIC_DEFAULT_HAIKU_MODEL': 'claude-haiku-4-5'
    }

    # Update model to use
    settings['model'] = 'claude-opus-4-8'

    # Add schema if it's a new file
    if '$schema' not in settings:
        settings['$schema'] = 'https://json.schemastore.org/claude-code-settings.json'

    # Save updated settings
    with open(settings_file, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=2)

    print('[OK] Updated settings while preserving existing configuration')

if __name__ == '__main__':
    main()
