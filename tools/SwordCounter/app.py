"""SwordCounter S3: compact always-on-top Windows window.

Reads open Bybit positions with S1 (read-only) and counts swords with S2 on a background
thread every ``REFRESH_INTERVAL_S`` seconds, starting immediately. The Tk thread only
renders. Independent of MetaScalp and of the BybitScanner trading runtime; it never sends
trading commands.

Run: ``python -m tools.SwordCounter`` (or ``tools\\SwordCounter\\start_sword_counter.bat``).
The Read-Only API key comes only from the Windows Credential Manager; it is entered, checked
and saved in the ⚙ settings window, section «Подключение Bybit» (see ``connection``).
"""

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from typing import Callable

from tools.SwordCounter.bybit_positions import fetch_open_positions
from tools.SwordCounter.connection import ConnectionController
from tools.SwordCounter.credential_store import CredentialStore, WindowsCredentialStore, resolve_credentials
from tools.SwordCounter.settings_store import (
    AppSettings, default_settings_path, load_settings, parse_ro_usdt, parse_total_swords,
    save_settings, to_sword_settings,
)
from tools.SwordCounter.swords import count_swords_from_api
from tools.SwordCounter.view_model import GREY, WORKER_FAILED, build_display, header_text

REFRESH_INTERVAL_S = 10
POLL_MS = 500
SWORDS_ICON = "⚔"   # crossed swords
GEAR_ICON = "⚙"
FONT = "Segoe UI"
SECRET_MASK = "•"


class Refresher:
    """Background loop: count now, then every interval or when woken; posts each outcome."""

    def __init__(self, count: Callable[[], object], post: Callable[[object], None],
                 interval_s: float = REFRESH_INTERVAL_S) -> None:
        self._count = count
        self._post = post
        self._interval = interval_s
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = threading.Thread(target=self._run, name="swordcounter-refresh", daemon=True)
        self._started = False

    def start(self) -> None:
        self._started = True
        self._thread.start()

    def request_now(self) -> None:
        self._wake.set()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._started and self._thread is not threading.current_thread():
            self._thread.join(timeout)

    def is_alive(self) -> bool:
        return self._thread.is_alive()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                outcome = self._count()
            except Exception:
                outcome = WORKER_FAILED
            if self._stop.is_set():
                break
            self._post(outcome)
            self._wake.wait(self._interval)
            self._wake.clear()


def make_live_counter(get_settings: Callable[[], AppSettings]) -> Callable[[], object]:
    """S1 read + S2 count with the settings current at call time.

    The key is SwordCounter's own (Windows Credential Manager). A missing or unreadable key is
    "Нет соединения"; no network request is made without it.
    """
    def count():
        return count_swords_from_api(lambda: fetch_open_positions(resolve_credentials()[0]),
                                     to_sword_settings(get_settings()))
    return count


def bind_clipboard_keys(entry: tk.Entry) -> Callable[[object], str | None]:
    """Ctrl+V/C/X/A by physical key: Tk's default bindings miss them on a Russian layout."""
    events = {86: "<<Paste>>", 67: "<<Copy>>", 88: "<<Cut>>"}

    def on_control(event) -> str | None:
        if event.keycode in events:
            entry.event_generate(events[event.keycode])
            return "break"
        if event.keycode == 65:
            entry.select_range(0, "end")
            entry.icursor("end")
            return "break"
        return None

    entry.bind("<Control-KeyPress>", on_control)
    return on_control


class SwordCounterApp:
    def __init__(self, root: tk.Tk, *, settings_path: Path | None = None,
                 counter_factory: Callable[[Callable[[], AppSettings]], Callable[[], object]] = make_live_counter,
                 interval_s: float = REFRESH_INTERVAL_S, start_worker: bool = True,
                 credential_store: CredentialStore | None = None) -> None:
        self.root = root
        self.credential_store = credential_store if credential_store is not None else WindowsCredentialStore()
        self.settings_path = Path(settings_path) if settings_path is not None else default_settings_path()
        self.settings, self._settings_warning = load_settings(self.settings_path)
        self._results: queue.Queue = queue.Queue()
        self._last = None
        self._last_at: float | None = None
        self._closed = False
        self._build()
        self.refresher = Refresher(counter_factory(lambda: self.settings),
                                   lambda outcome: self._results.put((outcome, time.monotonic())),
                                   interval_s=interval_s)
        if start_worker:
            self.refresher.start()
        self.render()
        self._after_id = self.root.after(POLL_MS, self._tick)

    # ---- layout ---------------------------------------------------------
    def _build(self) -> None:
        root = self.root
        root.title("SwordCounter")
        root.attributes("-topmost", True)
        root.resizable(False, False)   # minimize and close stay; no maximize
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.configure(padx=10, pady=8)

        self.header_label = tk.Label(root, text=header_text(self.settings), font=(FONT, 10))
        self.header_label.grid(row=0, column=0, columnspan=2, sticky="w")
        self.gear_button = tk.Button(root, text=GEAR_ICON, font=(FONT, 11), relief="flat",
                                     command=self.open_settings, cursor="hand2")
        self.gear_button.grid(row=0, column=2, sticky="e")

        self.free_value = self._row(1, "Свободно")
        self.used_value = self._row(2, "Задействовано")
        self.status_label = tk.Label(root, text="", font=(FONT, 8), fg=GREY, anchor="w",
                                     wraplength=240, justify="left")
        self.status_label.grid(row=3, column=0, columnspan=3, sticky="we", pady=(4, 0))
        root.columnconfigure(2, weight=1)

    def _row(self, row: int, title: str) -> tk.Label:
        tk.Label(self.root, text=SWORDS_ICON, font=(FONT, 16)).grid(row=row, column=0, sticky="w", padx=(0, 6))
        tk.Label(self.root, text=title, font=(FONT, 11)).grid(row=row, column=1, sticky="w")
        value = tk.Label(self.root, text="…", font=(FONT, 26, "bold"), fg=GREY, anchor="e", width=4)
        value.grid(row=row, column=2, sticky="e", padx=(12, 0))
        return value

    # ---- data -----------------------------------------------------------
    def apply_result(self, outcome, at: float | None = None) -> None:
        self._last = outcome
        self._last_at = time.monotonic() if at is None else at

    def render(self) -> None:
        age = None if self._last_at is None else time.monotonic() - self._last_at
        display = build_display(self.settings, self._last, age)
        self.header_label.configure(text=display.header)
        big = (FONT, 26, "bold") if display.numbers_shown else (FONT, 11, "bold")
        self.free_value.configure(text=display.free_text, fg=display.free_color, font=big,
                                  width=4 if display.numbers_shown else 0)
        self.used_value.configure(text=display.used_text, fg=display.used_color, font=big,
                                  width=4 if display.numbers_shown else 0)
        status = display.status_text
        if self._last is None and self._settings_warning:
            status = self._settings_warning
        self.status_label.configure(text=status)

    def _tick(self) -> None:
        if self._closed:
            return
        while True:
            try:
                outcome, at = self._results.get_nowait()
            except queue.Empty:
                break
            self.apply_result(outcome, at)
        self.render()
        self._after_id = self.root.after(POLL_MS, self._tick)

    # ---- settings -------------------------------------------------------
    def save_settings_from_text(self, total_text: str, ro_text: str) -> AppSettings:
        """Validate, persist and apply. Raises ValueError (input) or OSError (disk) unchanged."""
        new = AppSettings(total_swords=parse_total_swords(total_text), ro_usdt=parse_ro_usdt(ro_text))
        save_settings(new, self.settings_path)
        self.settings = new
        self._settings_warning = None
        self.render()
        self.refresher.request_now()
        return new

    def open_settings(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Настройки")
        dialog.attributes("-topmost", True)
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.configure(padx=10, pady=8)
        total_var = tk.StringVar(value=str(self.settings.total_swords))
        ro_var = tk.StringVar(value=str(self.settings.ro_usdt))
        tk.Label(dialog, text="Всего мечей").grid(row=0, column=0, sticky="w")
        tk.Entry(dialog, textvariable=total_var, width=8).grid(row=0, column=1, padx=(8, 0))
        tk.Label(dialog, text="Стоимость 1 РО, USDT").grid(row=1, column=0, sticky="w", pady=(4, 0))
        tk.Entry(dialog, textvariable=ro_var, width=8).grid(row=1, column=1, padx=(8, 0), pady=(4, 0))
        error = tk.Label(dialog, text="", fg="#D32F2F", wraplength=220, justify="left")
        error.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))

        def save() -> None:
            try:
                self.save_settings_from_text(total_var.get(), ro_var.get())
            except ValueError as problem:
                error.configure(text=str(problem))
                return
            except OSError as problem:
                error.configure(text=f"Не удалось сохранить настройки: {type(problem).__name__}")
                return
            dialog.destroy()

        buttons = tk.Frame(dialog)
        buttons.grid(row=3, column=0, columnspan=2, sticky="e", pady=(8, 0))
        tk.Button(buttons, text="Сохранить", command=save).pack(side="left")
        tk.Button(buttons, text="Отмена", command=dialog.destroy).pack(side="left", padx=(6, 0))
        self._build_connection_section(dialog, row=4)
        dialog.grab_set()

    def _build_connection_section(self, dialog: tk.Toplevel, row: int) -> None:
        """«Подключение Bybit»: visible key, secret with show/hide, check off the GUI thread, save."""
        controller = ConnectionController(self.credential_store)
        frame = tk.LabelFrame(dialog, text="Подключение Bybit (ключ только для чтения)", padx=8, pady=6)
        frame.grid(row=row, column=0, columnspan=2, sticky="we", pady=(10, 0))
        key_var, secret_var = tk.StringVar(), tk.StringVar()
        tk.Label(frame, text="API Key").grid(row=0, column=0, sticky="w")
        key_entry = tk.Entry(frame, textvariable=key_var, width=40)
        key_entry.grid(row=0, column=1, columnspan=2, sticky="we", padx=(8, 0))
        tk.Label(frame, text="API Secret").grid(row=1, column=0, sticky="w", pady=(4, 0))
        secret_entry = tk.Entry(frame, textvariable=secret_var, width=32, show=SECRET_MASK)
        secret_entry.grid(row=1, column=1, sticky="we", padx=(8, 0), pady=(4, 0))
        show_button = tk.Button(frame, text="Показать", width=8)
        show_button.grid(row=1, column=2, padx=(4, 0), pady=(4, 0))
        result = tk.Label(frame, text="", wraplength=330, justify="left", anchor="w")
        result.grid(row=3, column=0, columnspan=3, sticky="we", pady=(6, 0))
        for entry in (key_entry, secret_entry):
            bind_clipboard_keys(entry)

        def toggle_secret() -> None:
            hidden = secret_entry.cget("show") != ""
            secret_entry.configure(show="" if hidden else SECRET_MASK)
            show_button.configure(text="Скрыть" if hidden else "Показать")

        def changed(*_args) -> None:
            controller.fields_changed()
            save_button.configure(state="disabled")
            if not controller.checking:
                result.configure(text="", fg="black")

        def show(outcome_ok: bool | None, text: str) -> None:
            color = {True: "#2E7D32", False: "#D32F2F", None: "black"}[outcome_ok]
            result.configure(text=text, fg=color)

        def poll() -> None:
            if not dialog.winfo_exists():
                return
            outcome = controller.poll()
            if outcome is None:
                dialog.after(150, poll)
                return
            check_button.configure(state="normal")
            show(outcome.ok, outcome.message)
            save_button.configure(state="normal" if controller.confirmed else "disabled")

        def check() -> None:
            text = controller.start_check(key_var.get(), secret_var.get())
            if not controller.checking:
                show(False, text)
                return
            check_button.configure(state="disabled")
            save_button.configure(state="disabled")
            show(None, text)
            dialog.after(150, poll)

        def save_key() -> None:
            outcome = controller.save(key_var.get(), secret_var.get())
            show(outcome.ok, outcome.message)
            if outcome.ok:
                save_button.configure(state="disabled")
                self.refresher.request_now()

        show_button.configure(command=toggle_secret)
        buttons = tk.Frame(frame)
        buttons.grid(row=2, column=0, columnspan=3, sticky="e", pady=(6, 0))
        check_button = tk.Button(buttons, text="Проверить подключение", command=check)
        check_button.pack(side="left")
        save_button = tk.Button(buttons, text="Сохранить ключ", command=save_key, state="disabled")
        save_button.pack(side="left", padx=(6, 0))
        key_var.trace_add("write", changed)
        secret_var.trace_add("write", changed)
        self._connection_widgets = {"key": key_entry, "secret": secret_entry, "show": show_button,
                                    "check": check_button, "save": save_button, "result": result,
                                    "controller": controller}

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.root.after_cancel(self._after_id)
        except Exception:
            pass
        self.refresher.stop(timeout=1.0)
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def run() -> None:
    root = tk.Tk()
    SwordCounterApp(root)
    root.mainloop()
