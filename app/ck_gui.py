"""CorridorKey drop-in window: queue clips, run ck_run.py on each, show progress.

tkinter (bundled with the private Python) + tkinterdnd2 for Explorer drag and
drop. All the real work is ck_run.py; this window only starts it per clip and
reads its JSON events, so the GUI and a future N0DUS node behave identically.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

APP = Path(__file__).resolve().parent
ROOT = APP.parent
PY = ROOT / "venv" / "Scripts" / "python.exe"
RUNNER = APP / "ck_run.py"
SETTINGS = APP / "settings.json"
VIDEO_EXT = {".mp4", ".mov", ".m4v"}
IMAGE_EXT = {".png", ".jpg", ".jpeg"}
VRAM_CHOICES = ["Auto", "4 GB", "6 GB", "8 GB", "12 GB", "16 GB", "24 GB"]
NO_WINDOW = 0x08000000

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAVE_DND = True
except Exception:  # still usable: click the drop area to pick files
    HAVE_DND = False


def fmt_s(s):
    s = int(round(s))
    return f"{s // 60}:{s % 60:02d}"


def vram_arg(choice):
    return "auto" if choice == "Auto" else choice.split()[0]


class Job:
    def __init__(self, path: Path):
        self.path = path
        self.state = "queued"       # queued | running | done | error | cancelled
        self.plan = None
        self.log = None
        self.proc = None
        self.cancel_sent = 0.0
        self.message = ""


class App:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.jobs: list[Job] = []
        self.rows = {}
        self.current: Job | None = None
        self.running = False
        self.settings = self.load_settings()
        root.title("CorridorKey")
        root.geometry(self.settings.get("geometry", "760x520"))
        root.minsize(620, 380)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.build()
        self.refresh_card()
        root.after(100, self.pump)

    # ------------------------------------------------------------ settings
    def load_settings(self):
        try:
            return json.loads(SETTINGS.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_settings(self):
        self.settings.update(out_dir=self.out_var.get(), vram=self.vram_var.get(),
                             copy_original=bool(self.copy_var.get()), png16=bool(self.png16_var.get()),
                             key_anyway=bool(self.keyany_var.get()), geometry=self.root.geometry())
        SETTINGS.write_text(json.dumps(self.settings, indent=1), encoding="utf-8")

    # ------------------------------------------------------------ layout
    def build(self):
        r = self.root
        pad = {"padx": 8, "pady": 4}
        self.drop = tk.Label(r, text=("Drop clips, images or frame folders here" if HAVE_DND
                                      else "Click to add clips or images")
                             + "\n.mp4 .mov · .png .jpg · a folder of numbered frames   (or click to choose files)",
                             relief="groove", bd=2, height=4,
                             bg="#2b2b2b", fg="#dddddd", font=("Segoe UI", 11), cursor="hand2")
        self.drop.pack(fill="x", **pad)
        self.drop.bind("<Button-1>", lambda e: self.pick_files())
        if HAVE_DND:
            self.drop.drop_target_register(DND_FILES)
            self.drop.dnd_bind("<<Drop>>", self.on_drop)
            self.drop.dnd_bind("<<DropEnter>>", lambda e: (self.drop.config(bg="#3d5a99"), e.action)[1])
            self.drop.dnd_bind("<<DropLeave>>", lambda e: (self.drop.config(bg="#2b2b2b"), e.action)[1])

        f = ttk.Frame(r); f.pack(fill="x", **pad)
        ttk.Label(f, text="Output folder").pack(side="left")
        self.out_var = tk.StringVar(value=self.settings.get("out_dir", ""))
        ttk.Entry(f, textvariable=self.out_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(f, text="Browse…", command=self.pick_out).pack(side="left")
        ttk.Button(f, text="Open folder", command=self.open_out).pack(side="left", padx=(6, 0))

        g = ttk.Frame(r); g.pack(fill="x", **pad)
        ttk.Label(g, text="GPU memory").pack(side="left")
        self.vram_var = tk.StringVar(value=self.settings.get("vram", "Auto"))
        cb = ttk.Combobox(g, textvariable=self.vram_var, values=VRAM_CHOICES, state="readonly", width=8)
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: (self.save_settings(), self.replan_all()))
        self.card_var = tk.StringVar(value="detecting GPU…")
        ttk.Label(g, textvariable=self.card_var, foreground="#555").pack(side="left", padx=6)
        self.copy_var = tk.IntVar(value=1 if self.settings.get("copy_original") else 0)
        ttk.Checkbutton(g, text="Also copy the original", variable=self.copy_var,
                        command=self.save_settings).pack(side="right")
        h = ttk.Frame(r); h.pack(fill="x", **pad)
        ttk.Label(h, text="Images / frames:").pack(side="left")
        self.png16_var = tk.IntVar(value=1 if self.settings.get("png16") else 0)
        ttk.Checkbutton(h, text="16-bit PNG", variable=self.png16_var,
                        command=self.save_settings).pack(side="left", padx=6)
        self.keyany_var = tk.IntVar(value=1 if self.settings.get("key_anyway") else 0)
        ttk.Checkbutton(h, text="Key anyway (images that already have alpha)", variable=self.keyany_var,
                        command=lambda: (self.save_settings(), self.replan_all())).pack(side="left", padx=6)

        box = ttk.LabelFrame(r, text="Queue"); box.pack(fill="both", expand=True, **pad)
        self.canvas = tk.Canvas(box, highlightthickness=0)
        sb = ttk.Scrollbar(box, orient="vertical", command=self.canvas.yview)
        self.list = ttk.Frame(self.canvas)
        self.list.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.win = self.canvas.create_window((0, 0), window=self.list, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        b = ttk.Frame(r); b.pack(fill="x", **pad)
        self.start_btn = ttk.Button(b, text="Start", command=self.start)
        self.start_btn.pack(side="left")
        self.cancel_btn = ttk.Button(b, text="Cancel", command=self.cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=6)
        ttk.Button(b, text="Clear finished", command=self.clear_finished).pack(side="left")
        self.status = tk.StringVar(value="Ready." + ("" if HAVE_DND else "  (drag and drop unavailable)"))
        ttk.Label(b, textvariable=self.status).pack(side="right")

    def add_row(self, job):
        fr = ttk.Frame(self.list); fr.pack(fill="x", pady=2, padx=4)
        name = ttk.Label(fr, text=job.path.name + ("/" if job.path.is_dir() else ""), width=28, anchor="w")
        name.pack(side="left")
        win = ttk.Label(fr, text="…", width=7, anchor="w"); win.pack(side="left")
        bar = ttk.Progressbar(fr, maximum=1000, length=200); bar.pack(side="left", fill="x", expand=True, padx=6)
        info = ttk.Label(fr, text="queued", width=26, anchor="w"); info.pack(side="left")
        logb = ttk.Button(fr, text="Log", width=4, command=lambda j=job: self.open_log(j))
        logb.pack(side="left")
        rm = ttk.Button(fr, text="✕", width=3, command=lambda j=job: self.remove(j)); rm.pack(side="left", padx=(4, 0))
        info.bind("<Button-1>", lambda e, j=job: j.message and messagebox.showinfo(j.path.name, j.message))
        self.rows[job] = {"frame": fr, "name": name, "win": win, "bar": bar, "info": info, "rm": rm}

    # ------------------------------------------------------------ queue edits
    def on_drop(self, event):
        self.drop.config(bg="#2b2b2b")
        self.add_paths(self.root.tk.splitlist(event.data))
        return event.action

    def pick_files(self):
        paths = filedialog.askopenfilenames(
            title="Add clips or images",
            filetypes=[("Video or image", "*.mp4 *.mov *.m4v *.png *.jpg *.jpeg"), ("All", "*.*")])
        self.add_paths(paths)

    def add_paths(self, paths):
        for p in paths:
            p = Path(p)
            if p.is_dir():
                # A folder: its videos are separate clips; its numbered frames are ONE sequence job.
                # A folder with neither still becomes a row, so the runner can say why.
                kids = [x for x in p.iterdir() if x.is_file()]
                vids = sorted(x for x in kids if x.suffix.lower() in VIDEO_EXT)
                imgs = [x for x in kids if x.suffix.lower() in IMAGE_EXT]
                cands = vids + ([p] if imgs or not vids else [])
            else:
                cands = [p]
            for c in cands:
                c = c.resolve()
                if any(j.path == c and j.state in ("queued", "running") for j in self.jobs):
                    continue
                job = Job(c)
                self.jobs.append(job)
                self.add_row(job)
                if c.is_dir() or c.suffix.lower() in VIDEO_EXT | IMAGE_EXT:
                    self.plan(job)
                else:  # not supported: say so in the queue, never start it
                    job.state = "unsupported"
                    job.message = (f"{c.name}: not supported. Use .mp4/.mov/.m4v video, .png/.jpg/.jpeg images, "
                                   "or a folder of numbered .png/.jpg frames.")
                    self.rows[job]["win"].config(text="—")
                    self.set_info(job, "not supported (click)", "#b00020")
        if self.running and self.current is None:
            self.start_next()

    def remove(self, job):
        if job.state == "running":
            return
        self.jobs.remove(job)
        self.rows.pop(job)["frame"].destroy()

    def clear_finished(self):
        for j in [j for j in self.jobs if j.state in ("done", "error", "cancelled", "skipped", "unsupported")]:
            self.remove(j)

    # ------------------------------------------------------------ GPU plan
    def refresh_card(self):
        def work():
            try:
                sys.path.insert(0, str(APP))
                import gpu_win
                g = gpu_win.gpu_info()
                text = f"{g['name']} {round(g['total_gib'])} GB" if g else "no NVIDIA GPU found"
            except Exception as e:
                text = f"GPU check failed: {e}"
            self.events.put(("card", text))
        threading.Thread(target=work, daemon=True).start()

    def runner_args(self):
        args = ["--vram", vram_arg(self.vram_var.get())]
        if self.copy_var.get():
            args.append("--copy_original")
        if self.png16_var.get():
            args.append("--png16")
        if self.keyany_var.get():
            args.append("--key_anyway")
        return args

    def plan(self, job, out_dir=None, kind="plan"):
        """--plan_only in a thread. kind="plan": queue display (dummy out dir);
        kind="preflight": just before running, against the real output folder."""
        cmd = [str(PY), str(RUNNER), str(job.path), "--out_dir", str(out_dir or ROOT / "tmp"),
               "--plan_only"] + self.runner_args()

        def work():
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                                   stdin=subprocess.DEVNULL, creationflags=NO_WINDOW, timeout=300)
                evs = [json.loads(x) for x in r.stdout.splitlines() if x.startswith("{")]
            except Exception as e:
                evs = [{"event": "error", "message": str(e)}]
            self.events.put((kind, job, evs))
        threading.Thread(target=work, daemon=True).start()

    def replan_all(self):
        for j in self.jobs:
            if j.state == "queued":
                self.rows[j]["win"].config(text="…")
                self.plan(j)

    def show_plan(self, job, evs):
        p = next((e for e in evs if e["event"] == "plan"), None)
        job.plan = p
        row = self.rows.get(job)
        if not row:
            return
        skip = next((e for e in evs if e["event"] == "skipped"), None)
        err = next((e for e in evs if e["event"] == "error"), None)
        if job.state != "queued":
            return
        if skip:
            row["win"].config(text="—")
            job.message = skip["message"]
            self.set_info(job, "has alpha: will skip (click)", "#a06000")
        elif p and p.get("ok"):
            row["win"].config(text=f"{p['chunk']}/{p['stride']}")
            if p.get("kind") == "sequence":
                self.rows[job]["name"].config(text=f"{job.path.name}/ ({p['frames']} frames)")
            card = p["card"] + ("" if self.vram_var.get() == "Auto" else f" (capped {self.vram_var.get()})")
            self.card_var.set(f"{card} → {p['chunk']}/{p['stride']}  ({job.path.stem})")
            self.set_info(job, "queued")
        else:
            row["win"].config(text="—")
            job.message = (err or {}).get("message", "planning failed")
            code = (err or {}).get("code")
            self.set_info(job, {"vram_insufficient": "won't fit this GPU (click)",
                                "unsupported_input": "not supported (click)"}.get(code, "can't run (click)"),
                          "#b00020")

    # ------------------------------------------------------------ run
    def start(self):
        out = self.out_var.get().strip()
        if not out:
            self.pick_out()
            out = self.out_var.get().strip()
            if not out:
                return
        self.save_settings()
        if not any(j.state == "queued" for j in self.jobs):
            self.status.set("Nothing queued.")
            return
        self.running = True
        self.start_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        if self.current is None:
            self.start_next()

    def start_next(self):
        job = next((j for j in self.jobs if j.state == "queued"), None)
        if job is None:
            self.running = False
            self.current = None
            self.start_btn.config(state="normal")
            self.cancel_btn.config(state="disabled")
            self.status.set("Queue finished.")
            return
        # Preflight with the real output folder: the runner knows the exact output
        # names (hundreds for a sequence) and whether the input will be skipped.
        job.state = "running"
        self.current = job
        self.rows[job]["rm"].config(state="disabled")
        self.set_info(job, "checking…")
        self.plan(job, out_dir=Path(self.out_var.get().strip()), kind="preflight")

    def after_preflight(self, job, evs):
        if not self.running:  # Cancel was pressed while checking: nothing started
            job.state = "queued"
            self.current = None
            self.rows[job]["rm"].config(state="normal")
            self.set_info(job, "queued")
            return
        p = next((e for e in evs if e["event"] == "plan"), None)
        skip = next((e for e in evs if e["event"] == "skipped"), None)
        err = next((e for e in evs if e["event"] == "error"), None)

        def finish(state, text, color, message=""):
            job.state, job.message = state, message
            self.set_info(job, text, color)
            self.rows[job]["rm"].config(state="normal")
            self.current = None
            self.root.after(10, self.start_next if self.running else lambda: None)
        if skip:
            return finish("skipped", "skipped: has alpha (click)", "#a06000", skip["message"])
        if err or not p or not p.get("ok"):
            return finish("error", "can't run (click)", "#b00020", (err or {}).get("message", "planning failed"))
        overwrite = False
        if p.get("existing_count"):
            names = [Path(x).name for x in p["existing"][:8]]
            more = p["existing_count"] - len(names)
            overwrite = messagebox.askyesno(
                "Overwrite?", f"{job.path.name}: {p['existing_count']} output file(s) already exist:\n\n"
                + "\n".join(names) + (f"\n… and {more} more" if more > 0 else "") + "\n\nOverwrite them?")
            if not overwrite:
                return finish("cancelled", "skipped (exists)", "#777")
        self.launch(job, overwrite)

    def launch(self, job, overwrite):
        out = Path(self.out_var.get().strip())
        cmd = [str(PY), "-u", str(RUNNER), str(job.path), "--out_dir", str(out)] + self.runner_args()
        if overwrite:
            cmd.append("--overwrite")
        job.state = "running"
        job.cancel_sent = 0.0  # a re-queued clip must not inherit its old Cancel deadline
        job.message = ""
        self.current = job
        self.rows[job]["rm"].config(state="disabled")
        self.set_info(job, "starting…")
        job.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    creationflags=NO_WINDOW)

        def read(j=job):
            for raw in j.proc.stdout:
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith("{"):
                    try:
                        self.events.put(("ev", j, json.loads(line)))
                    except ValueError:
                        pass
            j.proc.wait()
            self.events.put(("exit", j, j.proc.returncode))
        threading.Thread(target=read, daemon=True).start()

    def cancel(self):
        job = self.current
        self.running = False  # the queue stops; remaining clips stay queued
        self.start_btn.config(state="normal")
        if job and job.proc and job.proc.poll() is None:
            self.set_info(job, "cancelling…")
            try:
                job.proc.stdin.write(b"cancel\n")
                job.proc.stdin.flush()
            except OSError:
                pass
            job.cancel_sent = time.monotonic()
        self.cancel_btn.config(state="disabled")

    def pump(self):
        try:
            while True:
                msg = self.events.get_nowait()
                kind = msg[0]
                if kind == "card":
                    if not self.jobs:
                        self.card_var.set(msg[1])
                elif kind == "plan":
                    self.show_plan(msg[1], msg[2])
                elif kind == "preflight":
                    self.after_preflight(msg[1], msg[2])
                elif kind == "ev":
                    self.on_event(msg[1], msg[2])
                elif kind == "exit":
                    self.on_exit(msg[1], msg[2])
        except queue.Empty:
            pass
        j = self.current
        if j and j.cancel_sent and j.proc.poll() is None and time.monotonic() - j.cancel_sent > 30:
            subprocess.run(["taskkill", "/PID", str(j.proc.pid), "/T", "/F"], capture_output=True,
                           creationflags=NO_WINDOW)  # the runner did not answer: force it
            j.cancel_sent = 0.0
        self.root.after(100, self.pump)

    def on_event(self, job, ev):
        e = ev["event"]
        row = self.rows.get(job)
        if e == "plan" and ev.get("ok"):
            row["win"].config(text=f"{ev['chunk']}/{ev['stride']}")
        elif e == "start":
            job.log = ev.get("log")
            self.status.set(ev.get("summary", ""))
        elif e == "attempt":
            row["win"].config(text=ev["window"])
        elif e == "progress":
            row["bar"]["value"] = int(ev["fraction"] * 1000)
            eta = ev.get("eta_s")
            self.set_info(job, (f"{ev['detail']} · {fmt_s(eta)} left" if eta is not None else ev["detail"]))
        elif e == "spill":
            self.set_info(job, f"spilled at {ev['window']}, retrying {ev.get('next_window')}", "#a06000")
        elif e == "warning":
            job.message = (job.message + "\n" if job.message else "") + ev["message"]
        elif e == "done":
            job.state = "done"
            job.log = ev.get("log", job.log)
            row["bar"]["value"] = 1000
            per = f"{ev['s_per_frame']:.2f} s/frame" if ev["frames"] > 1 else f"{ev['inference_s']:.0f} s keying"
            self.set_info(job, f"done in {fmt_s(ev['seconds'])} ({per})", "#006400")
            if ev.get("kind") == "image":
                job.message = f"key: {ev['key']}\nalpha: {ev['alpha']}\n{ev.get('png_bits')}-bit PNG, straight alpha"
            elif ev.get("kind") == "sequence":
                job.message = (f"folder: {ev['folder']}\n{ev['key_first']} … {ev['key_last']} (+ alpha)\n"
                               f"{ev['frames']} frames, window {ev['window']}, {ev.get('png_bits')}-bit PNG")
            else:
                job.message = f"fg: {ev['fg']}\nalpha: {ev['alpha']}\nwindow {ev['window']}"
        elif e == "skipped":
            job.state = "skipped"
            job.log = ev.get("log", job.log)
            job.message = ev.get("message", "")
            self.set_info(job, "skipped: has alpha (click)", "#a06000")
        elif e == "error":
            job.state = "error"
            job.log = ev.get("log", job.log)
            job.message = ev.get("message", "")
            self.set_info(job, "error (click for details)", "#b00020")
        elif e == "cancelled":
            job.state = "cancelled"
            row["bar"]["value"] = 0
            self.set_info(job, "cancelled", "#777")

    def on_exit(self, job, code):
        if job.state == "running":  # died without a final event
            job.state = "error"
            job.message = f"runner exited with code {code}"
            self.set_info(job, "error (click for details)", "#b00020")
        if job.state == "cancelled" and not self.running:
            job.state = "queued"  # Cancel stops the clip; Start runs it again from scratch
            self.set_info(job, "cancelled — queued again", "#777")
        self.rows[job]["rm"].config(state="normal")
        self.current = None
        if self.running:
            self.start_next()
        else:
            self.start_btn.config(state="normal")
            self.cancel_btn.config(state="disabled")

    def set_info(self, job, text, color="#000"):
        row = self.rows.get(job)
        if row:
            row["info"].config(text=text, foreground=color)

    # ------------------------------------------------------------ misc
    def pick_out(self):
        d = filedialog.askdirectory(title="Output folder", initialdir=self.out_var.get() or None)
        if d:
            self.out_var.set(os.path.normpath(d))
            self.save_settings()

    def open_out(self):
        d = self.out_var.get().strip()
        if d and os.path.isdir(d):
            os.startfile(d)
        else:
            messagebox.showinfo("Open folder", "Choose an existing output folder first.")

    def open_log(self, job):
        if job.log and os.path.exists(job.log):
            os.startfile(job.log)
        elif job.message:
            messagebox.showinfo(job.path.name, job.message)

    def on_close(self):
        if self.current and self.current.proc and self.current.proc.poll() is None:
            if not messagebox.askyesno("Quit", "A clip is still running. Cancel it and quit?"):
                return
            self.cancel()
            p = self.current.proc
            try:
                p.wait(timeout=30)
            except subprocess.TimeoutExpired:
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True,
                               creationflags=NO_WINDOW)
        self.save_settings()
        self.root.destroy()


def main():
    root = TkinterDnD.Tk() if HAVE_DND else tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
