#!/usr/bin/env python3
"""Standalone test to import backend.main"""

import importlib.util
import sys

sys.path.insert(0, '.')

spec = importlib.util.spec_from_file_location("backend.main", "backend/main.py")
module = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(module)
    print("✓✓✓ Successfully loaded backend.main ✓✓✓")
    print(f"FastAPI app: {module.app}")
except Exception as e:
    import traceback
    print("ERROR:")
    traceback.print_exc()
    sys.exit(1)
