"""An ordinary Python script. No server or domain plugin required."""
from datetime import datetime


def greet(name: str) -> str:
    return f"Hello, {name}!"


name = "Python"
message = greet(name)
print(message)
print(f"Your workspace is ready. {datetime.now():%H:%M:%S}")
