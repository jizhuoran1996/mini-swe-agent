"""Read the authorized API credential into transient host memory only."""
import sys


def read_key():
    if not sys.stdin.isatty():
        return sys.stdin.readline().strip()
    import termios
    old = termios.tcgetattr(sys.stdin)
    settings = termios.tcgetattr(sys.stdin)
    settings[3] &= ~termios.ECHO
    termios.tcsetattr(sys.stdin, termios.TCSANOW, settings)
    try:
        return sys.stdin.readline().strip()
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSANOW, old)
