"""Starts PedalBoard. If a just-installed update fails to start, puts the previous
version back and starts that instead."""
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)


def main():
    import updater
    try:
        import app_v4
        app_v4.main()
    except Exception:   # noqa: BLE001
        err = traceback.format_exc()
        with open(os.path.join(HERE, "pedalboard-error.log"), "a", encoding="utf-8") as f:
            f.write(err + "\n")
        info = updater.pending()
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        if info:
            updater.rollback()
            messagebox.showerror("PedalBoard", f"PedalBoard {info.get('to')} failed to start, so the previous "
                                               f"version ({info.get('from')}) was restored.\n\n{err[-800:]}")
            r.destroy()
            updater.restart()
        else:
            messagebox.showerror("PedalBoard", f"PedalBoard failed to start:\n\n{err[-1200:]}")
            r.destroy()


if __name__ == "__main__":
    main()
