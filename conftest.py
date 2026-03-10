"""Root conftest for pytest — ensures PYTHONPATH includes project root."""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
