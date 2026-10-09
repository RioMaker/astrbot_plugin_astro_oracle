import json
import os
import socket
import sys
import urllib.request
from urllib.parse import urlparse

import launch_local


def test_launcher_opens_only_after_readiness_and_releases_its_port(monkeypatch):
    opened = []

    def check_and_close(url):
        with urllib.request.urlopen(url + "/health", timeout=2) as response:
            health = json.load(response)
        assert health["ready"] is True and health["pid"] == os.getpid()
        opened.append(url)
        raise KeyboardInterrupt

    monkeypatch.setattr(sys, "argv", ["launch_local.py", "--port", "0"])
    monkeypatch.setattr(launch_local.webbrowser, "open", check_and_close)
    launch_local.main()
    assert len(opened) == 1
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", urlparse(opened[0]).port)) != 0
