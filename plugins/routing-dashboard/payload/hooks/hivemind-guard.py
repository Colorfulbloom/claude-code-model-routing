#!/usr/bin/env python3
"""HiveMind guard hook: thin wrapper around hivemind_lib.guard_main. Always exits 0."""
import os
import sys

sys.dont_write_bytecode = True  # leave no __pycache__ in the installed hooks dir
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import hivemind_lib
    hivemind_lib.guard_main()
except BaseException:
    pass
sys.exit(0)
