"""A standard-library Tkinter animation with pause, resume and clean shutdown.

Requires the desktop's Tk installation. Use --close-after 2000 for automation.
"""
import argparse
import math
import tkinter as tk

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--close-after', type=int)
args = parser.parse_args()
root = tk.Tk()
root.title('Python support: animated sine wave')
root.geometry('760x400')
canvas = tk.Canvas(root, background='#122334', highlightthickness=0)
canvas.pack(fill='both', expand=True)
running = True
phase = 0.0
timer = None


def toggle():
    global running
    running = not running
    button.configure(text='Pause' if running else 'Resume')


def draw():
    global phase, timer
    if running:
        phase += .08
    width, height = max(8, canvas.winfo_width()), max(8, canvas.winfo_height())
    points = []
    for x in range(0, width, 4):
        points.extend((x, height/2 + math.sin(x/70 + phase)*height*.32))
    canvas.delete('wave')
    canvas.create_line(*points, fill='#59d6ba', width=3, tags='wave')
    timer = root.after(30, draw)


def close():
    if timer is not None:
        root.after_cancel(timer)
    root.destroy()


button = tk.Button(root, text='Pause', command=toggle)
button.pack(pady=8)
root.protocol('WM_DELETE_WINDOW', close)
if args.close_after is not None:
    root.after(max(1, args.close_after), close)
draw()
print('TK_GRAPHICS_OPEN', flush=True)
root.mainloop()
print('TK_GRAPHICS_CLOSED', flush=True)
