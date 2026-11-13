"""End-to-end: a real crawl through a broken local proxy, no internet needed."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent


@pytest.mark.parametrize("mode", ["refused", "drop"])
def test_broken_proxy_connection_gets_new_ips_then_gives_up(mode):
    env = dict(os.environ, PYTHONPATH=str(HERE.parent))
    out = subprocess.run([sys.executable, str(HERE / "dead_proxy_crawl.py"), mode], env=env,
                         capture_output=True, text=True, timeout=120)
    stats = json.loads(out.stdout.strip().splitlines()[-1])
    # first try + 2 new IPs (FUSIONPROXY_MAX_ROTATIONS = 2), Scrapy's RetryMiddleware switched off
    assert stats["fusionproxy/requests"] == 3, stats
    assert stats["fusionproxy/connection_errors"] == 3, stats
    assert stats["fusionproxy/rotations"] == 2, stats
    assert stats["fusionproxy/gave_up"] == 1, stats
