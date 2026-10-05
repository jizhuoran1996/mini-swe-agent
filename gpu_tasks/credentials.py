"""Read authorized credentials transiently without terminal echo or persistence."""
import sys
def read_key():
    if sys.stdin.isatty():
        import termios
        old=termios.tcgetattr(sys.stdin)
        settings=termios.tcgetattr(sys.stdin);settings[3]&=~termios.ECHO
        termios.tcsetattr(sys.stdin,termios.TCSANOW,settings)
        try:return sys.stdin.readline().strip()
        finally:termios.tcsetattr(sys.stdin,termios.TCSANOW,old)
    return sys.stdin.readline().strip()
