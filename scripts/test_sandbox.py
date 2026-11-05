"""Test runner for sandbox kernels that do not wake asyncio's self-pipe.
No network is enabled and application code is not patched in production.
Normal hosts should use: python -m unittest discover -s tests -v
"""
import asyncio, unittest, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
original=asyncio.BaseEventLoop._run_once
def poll(self):
    timer=self.call_later(.005,lambda:None)
    try: original(self)
    finally: timer.cancel()
asyncio.BaseEventLoop._run_once=poll
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover('tests'))
    sys.exit(not result.wasSuccessful())
