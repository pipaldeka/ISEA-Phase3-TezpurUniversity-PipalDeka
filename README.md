# ISEA-Phase3-TezpurUniversity-Assignment6

## GUI-Based Multi-Client Chat Application Using TCP

A graphical desktop chat client built with Python/Tkinter on top of a reused, unmodified TCP chat server from Assignment 5. Tested with four simultaneous clients inside a Mininet single-switch topology.

---

## Objective

Convert the terminal-based TCP chat application from Assignment 5 into a graphical desktop application while reusing the existing server implementation with minimal/no modification. This introduces GUI programming, event-driven programming, multithreading for non-blocking network I/O, and user-friendly network application development on top of a networking core that was already validated in Assignment 5.

---

## Software Requirements

| Requirement | Details |
|---|---|
| OS | Linux (developed/tested on Fedora) |
| Python | 3.x |
| Python modules | `tkinter`, `tkinter.ttk`, `tkinter.scrolledtext`, `threading`, `socket`, `queue`, `re`, `csv`, `os`, `datetime` (all standard library — no pip installs required) |
| Emulation | [Mininet](http://mininet.org/) |
| Packet capture (optional) | Wireshark / tshark, filter `tcp.port == 5000` |

---

## Network Topology

Single switch, one server host, four client hosts:

```
sudo mn --topo single,5
```

| Host | Role |
|---|---|
| h1 | Chat Server (`server.py`, listens on `0.0.0.0:5000`) |
| h2 | Client A |
| h3 | Client B |
| h4 | Client C |
| h5 | Client D |

All hosts sit on the same subnet (`10.0.0.0/8`), with the server reachable at `10.0.0.1:5000`. Verify connectivity from the Mininet CLI before running the app:

```
mininet> nodes
mininet> net
mininet> pingall
```

---

## Execution Steps

1. Clone this repository (or copy `server.py` and `client_gui.py`) onto the Mininet VM/host.
2. Start Mininet with the 5-host single-switch topology:
   ```
   sudo mn --topo single,5
   ```
3. Open a terminal on the server host and start the server:
   ```
   mininet> xterm h1
   [h1] python3 server.py
   ```
4. Open a terminal on each client host and launch the GUI client:
   ```
   mininet> xterm h2 h3 h4 h5
   [h2/h3/h4/h5] python3 client_gui.py
   ```
5. In each client's login window, enter a unique username (letters only) and click **Connect**.
6. Once connected, use the chat window to:
   - Type a plain message + **Send** → broadcasts to all other online users
   - Type `/msg <username> <message>`, or double-click a name in the **Online Users** list, to send a private message (usernames autocomplete as you type after `/msg `)
   - Click **Refresh** to re-fetch the online users list
   - Click **Disconnect** to leave the chat
7. (Optional) To verify traffic at the network level, capture on the switch interface with Wireshark/tshark using the filter `tcp.port == 5000` while performing the steps above.

---

## Sample Screenshots

| | |
|---|---|
| **Login Window** | `screenshots/Login_Menu.png` |
| **Successful Connection** | `screenshots/Successful_connection.png` |
| **Main Chat Window** | `screenshots/Chat_Window.png` |
| **Broadcast Messaging** | `screenshots/Broadcast_Message.png` |
| **Private Messaging** | `screenshots/Private_message.png` |
| **User Joining** | `screenshots/User_Joining.png` |
| **User Leaving / Disconnect** | `screenshots/User_Disconnect.png` |

See `report.pdf` for the full write-up, including annotated Wireshark packet captures (`tcp.port == 5000`) covering client connection, broadcast delivery, private-message delivery, and disconnection.

---

## Implementation Overview

- **Server (`server.py`)** — reused unmodified from Assignment 5. A single threaded TCP server on port 5000; every accepted client is handled on its own daemon thread. Maintains an in-memory, lock-protected registry of online clients, supports `/list`, `/stats`, and `/msg <user> <text>` commands, broadcasts plain messages and join/leave events to all clients, and logs every message to `chat_history.csv` and every connect/disconnect event to `server_logs.txt`.

- **Client (`client_gui.py`)** — new for this assignment. Splits cleanly into:
  - `ChatConnection` — the networking layer. Owns the raw socket and a background daemon thread that blocks on `recv()` and pushes decoded lines onto a thread-safe `queue.Queue`. It has no dependency on Tkinter.
  - Tkinter GUI (`LoginFrame`, `ChatFrame`) — the presentation layer. Polls the queue every 100 ms via `root.after(...)` on the main thread to update the chat log and online-users list, so the window never blocks on network I/O.

This separation means all blocking socket calls happen off the GUI thread, keeping the interface responsive while messages are sent and received.

---

## Files

```
server.py          # TCP chat server (reused from Assignment 5, unmodified)
client_gui.py       # Tkinter GUI chat client (new for Assignment 6)
report.pdf          # Full assignment report (design, testing, Wireshark verification, reflection)
screenshots/         # GUI and Wireshark evidence referenced in the report
```
