"""Interactive ordinary-Python qualification and graphics menu. No SPELL imports."""
import json
from pathlib import Path
import subprocess
import sys


def main():
    directory = Path(__file__).resolve().parent
    reference = directory / "test_Python.py"
    graphics = None
    def close_graphics():
        nonlocal graphics
        if graphics and graphics.poll() is None:
            try:
                graphics.stdin.write(json.dumps({"action": "close"}) + "\n"); graphics.stdin.flush()
                graphics.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                graphics.kill(); graphics.wait(timeout=3)
        if graphics and graphics.stdin: graphics.stdin.close()
        graphics = None
    try:
        while True:
            print("\nPython desktop test menu\n"
                  "1  Run all 39 Python qualification topics\n"
                  "2  List Python topics\n3  Run one Python topic\n"
                  "4  Start statistics graphic window\n5  Add a statistics point\n"
                  "6  Close statistics graphic window\n0  Close windows and exit")
            try: choice = input("Choose: ").strip()
            except (EOFError, KeyboardInterrupt): break
            if choice == "0": break
            if choice in {"1", "2", "3"}:
                if not reference.is_file():
                    print("Use the source checkout to access examples/test_Python.py"); continue
                args = [] if choice == "1" else ["--list"] if choice == "2" else ["--section", input("Topic name: ").strip()]
                result = subprocess.run([sys.executable, "-I", "-B", "-u", "-X", "utf8", str(reference), *args])
                print(f"Qualification exit: {result.returncode}")
            elif choice == "4":
                close_graphics()
                graphics = subprocess.Popen([sys.executable, "-I", "-u", str(directory / "graphics_demo.py"), "--commands"],
                    stdin=subprocess.PIPE, text=True, encoding="utf-8")
            elif choice == "5":
                if graphics and graphics.poll() is None:
                    try:
                        value = float(input("Value (0–100): "))
                        graphics.stdin.write(json.dumps({"action": "add", "value": value}) + "\n"); graphics.stdin.flush()
                    except (ValueError, OSError) as error: print(error)
                else: print("Start the statistics window first")
            elif choice == "6": close_graphics()
            else: print("Choose one of the listed numbers")
    finally:
        close_graphics()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
