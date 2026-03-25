#!/usr/bin/env python3
"""
Script to enable Claude Code proxy configuration.
Usage: claude_enable.py <master_key>
"""
import json
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
        try:
            with open(settings_file, 'r') as f:
                settings = json.load(f)
        except (json.JSONDecodeError, IOError):
            settings = {}

    # Add proxy configuration
    settings['env'] = {
        'ANTHROPIC_AUTH_TOKEN': master_key,
        'ANTHROPIC_BASE_URL': 'http://localhost:4444',
        'ANTHROPIC_MODEL': 'claude-sonnet-4-5',
        'ANTHROPIC_SMALL_FAST_MODEL': 'gpt-4'
    }

    # Update model to use
    settings['model'] = 'claude-sonnet-4-5'

    # Add schema if it's a new file
    if '$schema' not in settings:
        settings['$schema'] = 'https://json.schemastore.org/claude-code-settings.json'

    # Save updated settings
    with open(settings_file, 'w') as f:
        json.dump(settings, f, indent=2)

    print('[OK] Updated settings while preserving existing configuration')

if __name__ == '__main__':
    main()