#!/usr/bin/env python3
"""
Script to disable Claude Code proxy configuration.
Usage: claude_disable.py
"""
import json
import sys
from pathlib import Path

from user_home import resolve_workspace_user_home

def main():
    claude_dir = resolve_workspace_user_home() / '.claude'
    settings_file = claude_dir / 'settings.json'

    if not settings_file.exists():
        print('[OK] No settings file found - using Claude Code defaults')
        return

    try:
        # Load current settings
        with open(settings_file, 'r') as f:
            settings = json.load(f)

        # Remove proxy configuration
        if 'env' in settings:
            del settings['env']

        # Restore model to opusplan if it was claude-sonnet-4
        if 'model' in settings and settings['model'] in ('claude-sonnet-4', 'claude-sonnet-4-5'):
            settings['model'] = 'opusplan'

        # Save updated settings
        with open(settings_file, 'w') as f:
            json.dump(settings, f, indent=2)

        print('[OK] Removed proxy configuration while preserving other settings')

    except Exception as e:
        print(f'[ERROR] Error updating settings: {e}')
        sys.exit(1)

if __name__ == '__main__':
    main()