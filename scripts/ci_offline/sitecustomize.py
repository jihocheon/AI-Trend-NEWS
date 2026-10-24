"""Block Python network operations during CI checks, after dependency installation."""
import os
import sys


def offline_only(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
        raise OSError("CI checks prohibit network access")


sys.addaudithook(offline_only)
os.environ["RADAR_CI_NETWORK_BLOCKED"] = "1"
