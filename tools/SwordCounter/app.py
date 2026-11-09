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
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from typing import Callable

from tools.SwordCounter.bybit_positions import fetch_account_balances, fetch_open_positions
from tools.SwordCounter.connection import ConnectionController
from tools.SwordCounter.credential_store import CredentialStore, WindowsCredentialStore, resolve_credentials
from tools.SwordCounter.settings_store import (
    AppSettings, default_settings_path, load_settings, parse_total_swords, save_settings,
)
from tools.SwordCounter.swords import SwordCount, count_swords_with_wallet_balance
from tools.SwordCounter.view_model import GREEN, RED, GREY, WORKER_FAILED, build_display, header_text

REFRESH_INTERVAL_S = 10
POLL_MS = 500
SWORDS_ICON = "⚔"   # crossed swords
WINDOW_TITLE = "SwordCounter"   # the crossed-swords icon sits left of it (swords.ico)
GEAR_ICON = "⚙"
FONT = "Segoe UI"
COUNT_FONT_PT = 23   # reduced from 26; also reduces vertical gap between sword rows
STATUS_FONT_PT = 10  # more legible five-line financial summary
SECRET_MASK = "•"
ICON_PATH = Path(__file__).with_name("swords.ico")
APP_USER_MODEL_ID = "SwordCounter.App"   # own taskbar group: not the generic Python icon


def set_taskbar_identity() -> None:
    """Windows: give the process its own AppUserModelID so the taskbar shows the swords icon."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass   # cosmetic only


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
    """Wallet Balance + open positions + S2 count with the settings current at call time.

    1 RO = Wallet Balance / total swords, recomputed on every refresh. The key is SwordCounter's
    own (Windows Credential Manager). A missing or unreadable key is "Нет соединения"; no network
    request is made without it.
    """
    def count():
        credentials = None

        def creds():
            nonlocal credentials
            if credentials is None:
                credentials = resolve_credentials()[0]
            return credentials

        return count_swords_with_wallet_balance(lambda: fetch_open_positions(creds()),
                                        lambda: fetch_account_balances(creds()),
                                        get_settings().total_swords)
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
        self._result_epoch = 0
        self._closed = False
        self._build()
        counter = counter_factory(lambda: self.settings)

        def count_with_epoch():
            # Capture the identity BEFORE starting a potentially slow Bybit
            # read. Responses from a previous key/settings generation cannot
            # be displayed under a newer account, even when they arrive late.
            epoch = self._result_epoch
            try:
                value = counter()
            except Exception:
                value = WORKER_FAILED
            return epoch, value

        self.refresher = Refresher(count_with_epoch,
                                   lambda pair: self._results.put(
                                       (pair[0], pair[1], time.monotonic())),
                                   interval_s=interval_s)
        if start_worker:
            self.refresher.start()
        self.render()
        self._after_id = self.root.after(POLL_MS, self._tick)

    # ---- layout ---------------------------------------------------------
    def _build(self) -> None:
        root = self.root
        root.title(WINDOW_TITLE)
        try:   # default= also covers the settings dialog; title bar and taskbar use this icon
            root.iconbitmap(default=str(ICON_PATH))
        except tk.TclError:
            pass   # missing icon file: keep the default, never block the counter
        root.attributes("-topmost", True)
        root.resizable(False, False)   # minimize and close stay; no maximize
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.configure(padx=10, pady=8)

        self.header_label = tk.Label(root, text=header_text(), font=(FONT, 10))
        self.header_label.grid(row=0, column=0, columnspan=2, sticky="w")
        self.gear_button = tk.Button(root, text=GEAR_ICON, font=(FONT, 11), relief="flat",
                                     command=self.open_settings, cursor="hand2")
        self.gear_button.grid(row=0, column=2, sticky="e")

        self.free_value = self._row(1, "Свободно")
        self.used_value = self._row(2, "Задействовано")
        # Text tags allow coloring just the over-limit count and deposit value,
        # without changing the rest of each line. Read-only, no focus or border.
        self.status_label = tk.Text(root, font=(FONT, STATUS_FONT_PT), fg=GREY,
                                    bg=root.cget("bg"), borderwidth=0, relief="flat",
                                    highlightthickness=0, wrap="word", width=36, height=1,
                                    padx=0, pady=0, takefocus=0, cursor="arrow")
        self.status_label.tag_configure("limit_over", foreground=RED)
        self.status_label.tag_configure("deposit_balance", foreground=GREEN)
        self.status_label.configure(state="disabled")
        self.status_label.grid(row=3, column=0, columnspan=3, sticky="w", pady=(3, 0))
        root.columnconfigure(2, weight=1)

    def _row(self, row: int, title: str) -> tk.Label:
        tk.Label(self.root, text=SWORDS_ICON, font=(FONT, 16)).grid(row=row, column=0, sticky="w", padx=(0, 6))
        tk.Label(self.root, text=title, font=(FONT, 11)).grid(row=row, column=1, sticky="w")
        value = tk.Label(self.root, text="…", font=(FONT, COUNT_FONT_PT, "bold"), fg=GREY, anchor="e", width=4)
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
        big = (FONT, COUNT_FONT_PT, "bold") if display.numbers_shown else (FONT, 11, "bold")
        self.free_value.configure(text=display.free_text, fg=display.free_color, font=big,
                                  width=4 if display.numbers_shown else 0)
        self.used_value.configure(text=display.used_text, fg=display.used_color, font=big,
                                  width=4 if display.numbers_shown else 0)
        status = display.status_text
        if self._last is None and self._settings_warning:
            status = self._settings_warning
        self._render_status(status, show_values=display.numbers_shown)

    def _render_status(self, status: str, *, show_values: bool) -> None:
        """Draw the current text with selective emphasis; never color errors or stale data."""
        widget = self.status_label
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", status)
        widget.tag_remove("limit_over", "1.0", "end")
        widget.tag_remove("deposit_balance", "1.0", "end")
        lines = status.splitlines()
        if show_values and isinstance(self._last, SwordCount):
            prefix = "Превышение лимита: "
            if self._last.over_limit and lines and lines[0].startswith(prefix):
                count = str(self._last.used_swords)
                if lines[0].startswith(prefix + count + " из "):
                    widget.tag_add("limit_over", f"1.{len(prefix)}",
                                   f"1.{len(prefix) + len(count)}")
            deposit_prefix = "Общий депозит: "
            if lines and lines[-1].startswith(deposit_prefix):
                line_number = len(lines)
                widget.tag_add("deposit_balance", f"{line_number}.{len(deposit_prefix)}",
                               f"{line_number}.end")
        # Keep ordinary one-line errors compact; allow long messages to wrap.
        widget.configure(height=max(1, sum(max(1, (len(line) + 34) // 35) for line in lines)), state="disabled")

    def _tick(self) -> None:
        if self._closed:
            return
        while True:
            try:
                epoch, outcome, at = self._results.get_nowait()
            except queue.Empty:
                break
            if epoch == self._result_epoch:
                self.apply_result(outcome, at)
        self.render()
        self._after_id = self.root.after(POLL_MS, self._tick)

    def _invalidate_result(self) -> None:
        # Called only on the GUI thread after persistent settings or
        # verified credentials change. Pending old worker results are tagged
        # and ignored, not accidentally shown as belonging to the new key.
        self._result_epoch += 1
        self._last = None
        self._last_at = None
        self.render()

    # ---- settings -------------------------------------------------------
    def save_settings_from_text(self, total_text: str) -> AppSettings:
        """Validate, persist and apply. Raises ValueError (input) or OSError (disk) unchanged."""
        new = AppSettings(total_swords=parse_total_swords(total_text))
        save_settings(new, self.settings_path)
        self.settings = new
        self._settings_warning = None
        self._invalidate_result()
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
        tk.Label(dialog, text="Всего мечей").grid(row=0, column=0, sticky="w")
        tk.Entry(dialog, textvariable=total_var, width=8).grid(row=0, column=1, padx=(8, 0))
        tk.Label(dialog, text="1 РО = Общий депозит / всего мечей (авто, до целых USDT)", fg=GREY
                 ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        error = tk.Label(dialog, text="", fg="#D32F2F", wraplength=220, justify="left")
        error.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))

        def save() -> None:
            try:
                self.save_settings_from_text(total_var.get())
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
                self._invalidate_result()
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
    set_taskbar_identity()
    root = tk.Tk()
    SwordCounterApp(root)
    root.mainloop()
