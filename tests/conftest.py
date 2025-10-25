"""
pytest configuration for tests

@FEAT:testing @COMP:test @TYPE:config
"""

import sys
import os

# Add web_server to Python path for importing app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'web_server'))
