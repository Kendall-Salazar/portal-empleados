"""Pytest configuration and fixtures for Chronos tests."""
import sys
import os

# Add backend to path for imports
backend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backend')
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

# Add planillas to path
planillas_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'planillas')
if planillas_path not in sys.path:
    sys.path.insert(0, planillas_path)
