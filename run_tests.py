#!/usr/bin/env python3
"""
Test runner with proper path setup
"""
import sys
import os

# Add the worktree root to Python path
worktree_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, worktree_root)

# Now run pytest with the correct environment
import subprocess
result = subprocess.run([
    sys.executable, '-m', 'pytest',
    'tests/services/test_websocket_manager.py',
    'tests/services/test_websocket_state_tracking.py',
    'tests/services/test_websocket_thread_safety.py',
    '-v', '--tb=short', '--disable-warnings',
    '--cov=web_server.app.services.websocket_manager',
    '--cov-report=term-missing'
], cwd=worktree_root, env={**os.environ, 'PYTHONPATH': worktree_root})

sys.exit(result.returncode)