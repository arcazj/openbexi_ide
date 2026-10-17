"""Submit with session_second.py to exercise configurable parallelism."""
import time

def count():
    for number in range(100):
        print('first', number, flush=True)
        time.sleep(0.2)

count()
