"""
client_gui.py
GUI-based TCP chat client (Assignment 6), matched to the provided server.py.

This single file contains everything: the networking layer (ChatConnection),
the Nord color palette + ttk styling, and all widget/layout/event-handling
code. The networking class has no dependency on Tkinter internally — it only
talks through a thread-safe queue — so it stays cleanly separable even
though it now lives in the same file as the GUI code.

Protocol notes (matches the provided server.py exactly):
  - On connect, the server sends a "NAME" prompt FIRST. The client must
    reply with its username before anything else.
  - Broadcast messages arrive as "sender: message" (no brackets), and the
    server does NOT echo a sender's own broadcast back to them.
  - Private messages arrive as "[PRIVATE] sender: text". Again, the server
    does NOT confirm success back to the sender — only failures are
    reported, as the literal string "User not found."
  - /list replies with a multi-line block:
        ===== ONLINE USERS =====
        name1
        name2
        ========================
  - Join/leave notifications look like: "*** name joined the chat ***"
  - There is no /stats command and no /quit handshake — disconnecting is
    just closing the socket; the server detects it via a failed recv().

IMPORTANT: since the server never echoes a client's own sent messages back,
this client echoes its own sent text LOCALLY the moment Send is pressed.
"""

import re
import queue
import socket
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox


# ─────────────────────────────────────────────────────────────────────────────
# Networking layer — talks to the outside world only through a thread-safe
# queue, so it has no real dependency on Tkinter even though it lives here.
# ─────────────────────────────────────────────────────────────────────────────

SERVER_IP = "10.0.0.1"     # h1 inside Mininet
PORT = 5000
USERNAME_PATTERN = re.compile(r'^[A-Za-z]+$')

LIST_START_MARKER = "===== ONLINE USERS ====="
LIST_END_MARKER = "========================"


def is_valid_username(username: str) -> bool:
    return bool(USERNAME_PATTERN.fullmatch(username))


class ChatConnection:
    """
    Wraps the raw TCP socket and hands off received text through a
    thread-safe queue. Callers should:
      1. call connect(username)   -- performs the NAME handshake internally
      2. call send(text) to talk to the server
      3. poll .incoming (a queue.Queue) for messages arriving from the server
      4. call close() when done

    The special string ChatConnection.DISCONNECT_SIGNAL is pushed onto the
    queue if the server closes the connection or a socket error occurs.
    """

    DISCONNECT_SIGNAL = "__DISCONNECTED__"

    def __init__(self, host: str = SERVER_IP, port: int = PORT):
        self.host = host
        self.port = port
        self.sock = None
        self.incoming = queue.Queue()
        self._stop_event = threading.Event()
        self._recv_thread = None

    def connect(self, username: str, timeout: float = 5.0):
        """Opens the socket and performs the server's NAME handshake:
        the server speaks first ("NAME"), then we reply with the username.
        Raises OSError/socket.timeout on failure."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self.sock.connect((self.host, self.port))

        # Server sends "NAME" first — read and discard/verify it.
        prompt = self.sock.recv(1024).decode().strip()
        if prompt != "NAME":
            # Not fatal — some server variants might skip this — but we
            # still proceed to send the username either way.
            pass

        self.sock.send(username.encode())
        self.sock.settimeout(None)

        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()

    def _recv_loop(self):
        """Runs on a background thread for the lifetime of the connection.
        Never touches any GUI state directly — only pushes raw text onto
        the thread-safe queue for the caller to consume."""
        while not self._stop_event.is_set():
            try:
                data = self.sock.recv(4096)
            except OSError:
                break
            if not data:
                self.incoming.put(self.DISCONNECT_SIGNAL)
                break
            self.incoming.put(data.decode())

    def send(self, text: str):
        if self.sock:
            try:
                self.sock.send(text.encode())
            except OSError:
                self.incoming.put(self.DISCONNECT_SIGNAL)

    def close(self):
        """This server has no /quit handshake — disconnecting is just
        closing the socket. The server detects this via a failed recv()."""
        self._stop_event.set()
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Nord color palette
# ─────────────────────────────────────────────────────────────────────────────

BG        = "#2E3440"   # nord0 — main background
CURRENT   = "#3B4252"   # nord1 — panels / inputs / selection background
FG        = "#ECEFF4"   # nord6 — primary text
COMMENT   = "#81A1C1"   # nord9  — secondary text / system messages
CYAN      = "#8FBCBB"   # nord7  — self / sent messages
GREEN     = "#A3BE8C"   # nord14 — broadcast messages
ORANGE    = "#D08770"   # nord12 — unused accent, kept for parity
PINK      = "#B48EAD"   # nord15 — private messages
PURPLE    = "#88C0D0"   # nord8  — primary accent (buttons, focus, title)
RED       = "#BF616A"   # nord11 — errors
YELLOW    = "#EBCB8B"   # nord13 — connecting / warning status

FONT_UI   = ("Segoe UI", 10)
FONT_UI_B = ("Segoe UI", 10, "bold")
FONT_MONO = ("Consolas", 10)


def apply_nord_theme(root: tk.Tk):
    """Configures ttk styles and the root window to match the Nord palette.
    Classic tk widgets (Listbox, Text, Entry, Scrollbar) are NOT themed by
    ttk.Style — those get their colors set directly at creation time below."""

    root.configure(bg=BG)
    # Thin flat edge around the whole window — the native OS titlebar can't
    # be restyled without dropping window decorations entirely.
    root.configure(highlightthickness=2, highlightbackground=CURRENT, highlightcolor=PURPLE)

    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure(".", background=BG, foreground=FG, font=FONT_UI)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=FG, font=FONT_UI)
    style.configure("Hint.TLabel", background=BG, foreground=COMMENT, font=("Segoe UI", 9))
    style.configure("Title.TLabel", background=BG, foreground=PURPLE, font=("Segoe UI", 15, "bold"))
    style.configure("Status.TLabel", background=BG, foreground=GREEN, font=FONT_UI_B)

    style.configure(
        "TButton", background=CURRENT, foreground=FG, borderwidth=0,
        focusthickness=0, padding=(10, 6), font=FONT_UI
    )
    style.map(
        "TButton",
        background=[("active", PURPLE), ("pressed", PURPLE)],
        foreground=[("active", BG), ("pressed", BG)],
    )

    style.configure(
        "Accent.TButton", background=PURPLE, foreground=BG, borderwidth=0,
        padding=(14, 7), font=FONT_UI_B
    )
    style.map("Accent.TButton", background=[("active", PINK)], foreground=[("active", BG)])

    style.configure(
        "Danger.TButton", background=CURRENT, foreground=RED, borderwidth=0, padding=(10, 6)
    )
    style.map("Danger.TButton", background=[("active", RED)], foreground=[("active", BG)])

    style.configure(
        "TEntry", fieldbackground=CURRENT, background=CURRENT, foreground=FG,
        insertcolor=FG, borderwidth=0, padding=8
    )
    style.map("TEntry", fieldbackground=[("focus", CURRENT)])

    # Scrollbars — flat, thin, theme-colored thumb on a background-colored trough
    style.configure(
        "Vertical.TScrollbar", background=CURRENT, troughcolor=BG,
        bordercolor=BG, arrowcolor=FG, relief="flat", borderwidth=0,
        arrowsize=12, width=10
    )
    style.map(
        "Vertical.TScrollbar",
        background=[("active", PURPLE), ("pressed", PURPLE)],
        arrowcolor=[("active", BG)],
    )
    style.configure(
        "Horizontal.TScrollbar", background=CURRENT, troughcolor=BG,
        bordercolor=BG, arrowcolor=FG, relief="flat", borderwidth=0,
        arrowsize=12, width=10
    )
    style.map(
        "Horizontal.TScrollbar",
        background=[("active", PURPLE), ("pressed", PURPLE)],
    )


def style_classic_scrollbar(scrollbar: tk.Scrollbar):
    """Applies theme colors to a classic tk.Scrollbar (e.g. the one built
    into scrolledtext.ScrolledText), which ttk.Style cannot reach."""
    scrollbar.config(
        bg=CURRENT, troughcolor=BG, activebackground=PURPLE,
        relief="flat", borderwidth=0, highlightthickness=0,
        elementborderwidth=0, width=10
    )


# ─────────────────────────────────────────────────────────────────────────────
# Autocomplete popup for "/msg <username>"
# ─────────────────────────────────────────────────────────────────────────────

class SuggestionPopup:
    """A small borderless Toplevel that lists usernames matching what's being
    typed after '/msg '. Built once, shown/hidden as needed."""

    def __init__(self, root, entry, on_pick):
        self.root = root
        self.entry = entry
        self.on_pick = on_pick

        self.top = tk.Toplevel(root)
        self.top.withdraw()
        self.top.overrideredirect(True)
        self.top.configure(bg=PURPLE)

        self.listbox = tk.Listbox(
            self.top, bg=CURRENT, fg=FG, selectbackground=PURPLE,
            selectforeground=BG, activestyle="none", borderwidth=0,
            highlightthickness=0, font=FONT_UI, height=4
        )
        self.listbox.pack(padx=1, pady=1, fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        self.listbox.bind("<Return>", self._on_select)
        self.listbox.bind("<Escape>", lambda e: self.hide())

        self.visible = False

    def show(self, matches, x, y, width):
        if not matches:
            self.hide()
            return
        self.listbox.delete(0, "end")
        for name in matches:
            self.listbox.insert("end", name)
        self.listbox.config(height=min(4, len(matches)))
        self.top.geometry(f"{max(width, 140)}x{min(4, len(matches)) * 22}+{x}+{y}")
        self.top.deiconify()
        self.top.lift()
        self.visible = True

    def hide(self):
        if self.visible:
            self.top.withdraw()
            self.visible = False

    def move_selection(self, delta):
        if not self.visible:
            return
        size = self.listbox.size()
        if size == 0:
            return
        cur = self.listbox.curselection()
        idx = (cur[0] + delta) if cur else 0
        idx = max(0, min(size - 1, idx))
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(idx)
        self.listbox.activate(idx)

    def pick_current(self):
        cur = self.listbox.curselection()
        if cur:
            self.on_pick(self.listbox.get(cur[0]))
        elif self.listbox.size() > 0:
            self.on_pick(self.listbox.get(0))

    def _on_select(self, event):
        self.pick_current()


# ─────────────────────────────────────────────────────────────────────────────
# Login screen
# ─────────────────────────────────────────────────────────────────────────────

class LoginFrame(ttk.Frame):
    def __init__(self, root, on_success):
        super().__init__(root, padding=32)
        self.root = root
        self.on_success = on_success
        self.pack(expand=True, fill="both")

        ttk.Label(self, text="TCP Chat Login", style="Title.TLabel").pack(pady=(0, 20))

        ttk.Label(self, text="Username (letters only)").pack(anchor="w")
        self.username_var = tk.StringVar()
        self.username_entry = ttk.Entry(self, textvariable=self.username_var)
        self.username_entry.pack(fill="x", pady=(4, 6))
        self.username_entry.focus()
        self.username_entry.bind("<Return>", lambda e: self.attempt_connect())

        self.status_label = ttk.Label(self, text="", foreground=RED)
        self.status_label.pack(anchor="w", pady=(2, 14))

        self.connect_btn = ttk.Button(
            self, text="Connect", style="Accent.TButton", command=self.attempt_connect
        )
        self.connect_btn.pack(fill="x")

        ttk.Label(
            self, text=f"Server: {SERVER_IP}:{PORT}", style="Hint.TLabel"
        ).pack(pady=(20, 0))

    def attempt_connect(self):
        username = self.username_var.get().strip()

        if not username:
            self.status_label.config(text="Username cannot be empty.", foreground=RED)
            return
        if not is_valid_username(username):
            self.status_label.config(text="Letters only, no spaces or numbers.", foreground=RED)
            return

        self.connect_btn.config(state="disabled")
        self.status_label.config(text="Connecting...", foreground=YELLOW)
        self.root.update_idletasks()

        conn = ChatConnection(SERVER_IP, PORT)
        try:
            conn.connect(username)
        except (OSError, socket.timeout) as e:
            self.status_label.config(text=f"Connection failed: {e}", foreground=RED)
            self.connect_btn.config(state="normal")
            return

        self.status_label.config(text="Connected!", foreground=GREEN)
        self.root.update_idletasks()
        self.on_success(conn, username)


# ─────────────────────────────────────────────────────────────────────────────
# Main chat screen
# ─────────────────────────────────────────────────────────────────────────────

class ChatFrame(ttk.Frame):
    def __init__(self, root, conn: ChatConnection, username: str):
        super().__init__(root)
        self.root = root
        self.conn = conn
        self.username = username
        self.online_users = []   # kept in sync for /msg autocomplete

        # State for parsing the multi-line /list response
        self._collecting_list = False
        self._collected_names = []

        self.root.title(f"Chat — {username}")
        self.root.geometry("780x520")
        self.root.protocol("WM_DELETE_WINDOW", self.disconnect)

        self.pack(fill="both", expand=True)
        self._build_layout()

        self.suggestion_popup = SuggestionPopup(root, self.input_entry, self._apply_suggestion)

        self._poll_incoming()
        self.conn.send("/list")

    # ---- layout -------------------------------------------------------------

    def _build_layout(self):
        # Status bar (top) — no Stats button: this server has no /stats command
        status_frame = ttk.Frame(self, padding=(12, 10))
        status_frame.pack(fill="x")
        self.status_label = ttk.Label(
            status_frame, text=f"●  Connected as {self.username}", style="Status.TLabel"
        )
        self.status_label.pack(side="left")

        ttk.Button(status_frame, text="Disconnect", style="Danger.TButton",
                   command=self.disconnect).pack(side="right")

        # Main body: chat area (left) + divider + online users (right)
        body = ttk.Frame(self, padding=(12, 0))
        body.pack(fill="both", expand=True)

        # ---- chat display ----
        chat_frame = ttk.Frame(body)
        chat_frame.pack(side="left", fill="both", expand=True)

        self.chat_display = scrolledtext.ScrolledText(
            chat_frame, state="disabled", wrap="word", font=FONT_MONO,
            bg=BG, fg=FG, insertbackground=FG, borderwidth=0,
            highlightthickness=1, highlightbackground=CURRENT, highlightcolor=PURPLE,
            padx=12, pady=10
        )
        self.chat_display.pack(fill="both", expand=True)
        style_classic_scrollbar(self.chat_display.vbar)

        self.chat_display.tag_config("system", foreground=COMMENT)
        self.chat_display.tag_config("private", foreground=PINK)
        self.chat_display.tag_config("error", foreground=RED)
        self.chat_display.tag_config("self", foreground=CYAN)
        self.chat_display.tag_config("broadcast", foreground=GREEN)

        # ---- vertical divider ----
        divider = tk.Frame(body, bg=CURRENT, width=1)
        divider.pack(side="left", fill="y", padx=(12, 0))

        # ---- online users panel ----
        users_frame = ttk.Frame(body, width=190)
        users_frame.pack(side="right", fill="y", padx=(12, 0))
        users_frame.pack_propagate(False)

        ttk.Label(users_frame, text="Online Users",
                  font=FONT_UI_B, foreground=PURPLE, background=BG).pack(anchor="w", pady=(0, 2))
        ttk.Label(users_frame, text="double-click to PM", style="Hint.TLabel").pack(
            anchor="w", pady=(0, 6)
        )

        listbox_wrap = tk.Frame(
            users_frame, bg=CURRENT, highlightthickness=1,
            highlightbackground=CURRENT, highlightcolor=PURPLE
        )
        listbox_wrap.pack(fill="both", expand=True)

        self.user_listbox = tk.Listbox(
            listbox_wrap, bg=CURRENT, fg=FG, selectbackground=PURPLE,
            selectforeground=BG, activestyle="none", borderwidth=0,
            highlightthickness=0, font=FONT_UI
        )
        self.user_listbox.pack(side="left", fill="both", expand=True)
        self.user_listbox.bind("<Double-Button-1>", self._on_user_double_click)

        user_scrollbar = ttk.Scrollbar(
            listbox_wrap, orient="vertical", command=self.user_listbox.yview
        )
        user_scrollbar.pack(side="right", fill="y")
        self.user_listbox.config(yscrollcommand=user_scrollbar.set)

        ttk.Button(users_frame, text="Refresh",
                   command=lambda: self.conn.send("/list")).pack(fill="x", pady=(8, 0))

        # ---- input row (bottom) ----
        input_outer = ttk.Frame(self, padding=(12, 12, 12, 6))
        input_outer.pack(fill="x")

        input_frame = tk.Frame(input_outer, bg=CURRENT)
        input_frame.pack(side="left", fill="both", expand=True, ipady=4)

        self.input_var = tk.StringVar()
        self.input_entry = tk.Entry(
            input_frame, textvariable=self.input_var, bg=CURRENT, fg=FG,
            insertbackground=FG, relief="flat", font=FONT_UI,
            highlightthickness=0, borderwidth=0
        )
        self.input_entry.pack(fill="both", expand=True, padx=(12, 6), ipady=8)
        self.input_entry.bind("<Return>", self._on_entry_return)
        self.input_entry.bind("<KeyRelease>", self._on_entry_key)
        self.input_entry.bind("<Down>", self._on_entry_down)
        self.input_entry.bind("<Escape>", lambda e: self.suggestion_popup.hide())
        self.input_entry.focus()

        ttk.Button(
            input_outer, text="Send ➤", style="Accent.TButton", command=self.send_message
        ).pack(side="left", padx=(10, 0), ipady=2)

        ttk.Label(
            self, text="Tip: type /msg <username> <message> for a private message — "
                        "usernames autocomplete as you type",
            style="Hint.TLabel", padding=(12, 0, 0, 10)
        ).pack(anchor="w")

    # ---- autocomplete ---------------------------------------------------------

    def _on_entry_key(self, event):
        if event.keysym in ("Down", "Up", "Return", "Escape"):
            return
        text = self.input_var.get()
        match = re.match(r'^/msg\s+(\S*)$', text)
        if not match:
            self.suggestion_popup.hide()
            return

        prefix = match.group(1).lower()
        candidates = [
            u for u in self.online_users
            if u != self.username and u.lower().startswith(prefix)
        ]
        if not candidates:
            self.suggestion_popup.hide()
            return

        x = self.input_entry.winfo_rootx()
        y = self.input_entry.winfo_rooty() + self.input_entry.winfo_height() + 2
        width = self.input_entry.winfo_width()
        self.suggestion_popup.show(candidates, x, y, width)

    def _on_entry_down(self, event):
        if self.suggestion_popup.visible:
            self.suggestion_popup.move_selection(1)
            return "break"

    def _on_entry_return(self, event):
        if self.suggestion_popup.visible:
            self.suggestion_popup.pick_current()
            return "break"
        self.send_message()

    def _apply_suggestion(self, username: str):
        self.input_var.set(f"/msg {username} ")
        self.suggestion_popup.hide()
        self.input_entry.focus()
        self.input_entry.icursor("end")

    # ---- actions --------------------------------------------------------------

    def send_message(self):
        text = self.input_var.get().strip()
        if not text:
            return

        self.conn.send(text)

        # This server never echoes a sender's own message back, so we
        # display it locally the moment it's sent.
        if text.startswith("/msg "):
            parts = text.split(" ", 2)
            if len(parts) == 3:
                target, pm_text = parts[1], parts[2]
                self._append_chat(f"[PM to {target}] {pm_text}", tag="private")
            # If malformed, the server will send back a "Usage: ..." error,
            # which _handle_line will display — no local echo needed here.
        elif text == "/list":
            pass  # server response will populate the panel; nothing to echo
        else:
            self._append_chat(f"{self.username}: {text}", tag="self")

        self.input_var.set("")
        self.suggestion_popup.hide()

    def _on_user_double_click(self, event):
        selection = self.user_listbox.curselection()
        if not selection:
            return
        name = self.user_listbox.get(selection[0])
        if name == self.username:
            return
        self.input_var.set(f"/msg {name} ")
        self.input_entry.focus()
        self.input_entry.icursor("end")

    def disconnect(self):
        self.conn.close()
        self.root.destroy()

    # ---- incoming message handling --------------------------------------------

    def _poll_incoming(self):
        try:
            while True:
                raw = self.conn.incoming.get_nowait()
                if raw == ChatConnection.DISCONNECT_SIGNAL:
                    self._handle_disconnect()
                    return
                for line in raw.splitlines():
                    self._handle_line(line)
        except queue.Empty:
            pass

        self.root.after(100, self._poll_incoming)

    def _handle_line(self, line: str):
        stripped = line.strip()

        # --- initial handshake artifact, ignore if it ever leaks through ---
        if stripped == "NAME":
            return

        # --- multi-line /list response ---
        if LIST_START_MARKER in stripped:
            self._collecting_list = True
            self._collected_names = []
            return
        if self._collecting_list:
            if LIST_END_MARKER in stripped:
                self._collecting_list = False
                self._update_user_list(self._collected_names)
                self._append_chat(
                    "[SERVER] Online users: " + ", ".join(self._collected_names),
                    tag="system"
                )
            elif stripped:
                self._collected_names.append(stripped)
            return

        if not stripped:
            return

        # --- join / leave notifications ---
        if stripped.startswith("***") and ("joined the chat" in stripped or "left the chat" in stripped):
            self._append_chat(stripped, tag="system")
            self.conn.send("/list")   # refresh the panel
            return

        # --- private message received ---
        if stripped.startswith("[PRIVATE]"):
            self._append_chat(stripped, tag="private")
            return

        # --- server errors (plain strings, no prefix) ---
        if stripped in ("User not found.",) or stripped.startswith("Usage: /msg"):
            self._append_chat(f"[SERVER] {stripped}", tag="error")
            return

        # --- everything else is a broadcast from another user: "name: text" ---
        self._append_chat(stripped, tag="broadcast")

    def _update_user_list(self, names):
        self.online_users = names
        self.user_listbox.delete(0, "end")
        for name in names:
            self.user_listbox.insert("end", name)

    def _append_chat(self, text: str, tag=None):
        self.chat_display.config(state="normal")
        self.chat_display.insert("end", text + "\n", tag if tag else ())
        self.chat_display.config(state="disabled")
        self.chat_display.see("end")

    def _handle_disconnect(self):
        self.status_label.config(text="●  Disconnected", foreground=RED)
        self._append_chat("[SYSTEM] Connection to server lost.", tag="error")
        messagebox.showwarning("Disconnected", "Lost connection to the server.")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point — single Tk root, frames swapped in place
# ─────────────────────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    root.title("Chat Login")
    root.geometry("380x320")
    root.resizable(False, False)
    apply_nord_theme(root)

    login_frame = LoginFrame(root, on_success=None)

    def on_login_success(conn, username):
        login_frame.destroy()
        root.resizable(True, True)
        ChatFrame(root, conn, username)

    login_frame.on_success = on_login_success

    root.mainloop()


if __name__ == "__main__":
    main()
