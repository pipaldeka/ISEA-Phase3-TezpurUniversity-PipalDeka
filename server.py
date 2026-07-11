import socket
import threading
import os
import csv
from datetime import datetime

HOST = "0.0.0.0"
PORT = 5000
EVENT_LOG = "server_logs.txt"
HISTORY_FILE = "chat_history.csv"

# clients: socket -> {username, ip, port, login_time, status}
clients = {}
clients_lock = threading.Lock()

# Global counters
stats = {
    "messages_processed": 0,
    "broadcast_messages": 0,
    "private_messages": 0,
}
stats_lock = threading.Lock()

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind((HOST, PORT))
server_socket.listen()
print(f"[SERVER] Listening on port {PORT}")

# Make sure chat_history.csv exists with a header
if not os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "sender", "receiver", "message_type", "message"])


def get_timestamp():
    return datetime.now().strftime("%H:%M:%S")


def write_event_log(event: str, username: str, ip: str):
    with open(EVENT_LOG, "a", encoding="utf-8") as f:
        f.write(f"{get_timestamp()},{event},{username},{ip}\n")
    print(f"[LOG] {get_timestamp()},{event},{username},{ip}")


def write_history(sender: str, receiver: str, message_type: str, message: str):
    with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([get_timestamp(), sender, receiver, message_type, message])


def get_last_messages(username: str, count: int = 5):
    """Return the last `count` messages sent BY this username, oldest first."""
    if not os.path.exists(HISTORY_FILE):
        return []
    rows = []
    with open(HISTORY_FILE, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["sender"] == username:
                rows.append(row)
    return rows[-count:]


def find_socket_by_username(username: str):
    with clients_lock:
        for sock, info in clients.items():
            if info["username"] == username:
                return sock
    return None


def safe_send(sock, text: str):
    try:
        sock.send(text.encode())
        return True
    except OSError:
        return False


def broadcast(message: str, sender_socket=None):
    """Send message to every client except the sender."""
    with clients_lock:
        targets = [s for s in clients if s is not sender_socket]
    for sock in targets:
        safe_send(sock, message)


def broadcast_all(message: str):
    with clients_lock:
        targets = list(clients.keys())
    for sock in targets:
        safe_send(sock, message)


def get_stats_snapshot():
    with clients_lock:
        online_count = len(clients)
        online_names = [info["username"] for info in clients.values()]
    with stats_lock:
        snap = dict(stats)
    return online_count, online_names, snap


def handle_client(client_socket: socket.socket, client_address: tuple):
    ip, port = client_address

    try:
        username = client_socket.recv(1024).decode().strip()
        if not username:
            client_socket.close()
            return
    except OSError:
        client_socket.close()
        return

    login_time = datetime.now()
    with clients_lock:
        clients[client_socket] = {
            "username": username,
            "ip": ip,
            "port": port,
            "login_time": login_time,
            "status": "online",
        }

    write_event_log("CONNECTED", username, ip)
    broadcast_all(f"[SERVER] {username} has joined the chat.")

    # Show last 5 messages this user previously sent (reconnect history)
    previous = get_last_messages(username, 5)
    if previous:
        safe_send(client_socket, "[SERVER] Your last 5 messages:")
        for row in previous:
            safe_send(
                client_socket,
                f"  ({row['timestamp']}) -> {row['receiver']}: {row['message']}"
            )

    try:
        while True:
            try:
                data = client_socket.recv(1024)
            except OSError:
                break
            if not data:
                break

            message = data.decode().strip()
            if not message:
                continue

            # ---- /quit ----
            if message == "/quit":
                break

            # ---- /list ----
            if message == "/list":
                with clients_lock:
                    names = [info["username"] for info in clients.values()]
                safe_send(client_socket, "[SERVER] Online users: " + ", ".join(names))
                continue

            # ---- /stats ----
            if message == "/stats":
                online_count, online_names, snap = get_stats_snapshot()
                reply = (
                    f"[SERVER] Connected users: {online_count} ({', '.join(online_names)}) | "
                    f"Messages processed: {snap['messages_processed']} | "
                    f"Broadcast: {snap['broadcast_messages']} | "
                    f"Private: {snap['private_messages']}"
                )
                safe_send(client_socket, reply)
                continue

            # ---- /msg <username> <message> ----
            if message.startswith("/msg "):
                parts = message.split(" ", 2)
                if len(parts) < 3:
                    safe_send(client_socket, "[SERVER] Usage: /msg <username> <message>")
                    continue
                target_name, priv_text = parts[1], parts[2]
                target_sock = find_socket_by_username(target_name)
                if target_sock is None:
                    safe_send(client_socket, f"[SERVER] Error: user '{target_name}' not found.")
                    continue

                formatted = f"[PM from {username}] {priv_text}"
                delivered = safe_send(target_sock, formatted)
                if delivered:
                    safe_send(client_socket, f"[PM to {target_name}] {priv_text}")
                    write_history(username, target_name, "private", priv_text)
                    with stats_lock:
                        stats["messages_processed"] += 1
                        stats["private_messages"] += 1
                else:
                    safe_send(client_socket, f"[SERVER] Error: could not deliver to '{target_name}'.")
                continue

            # ---- Performance test: broadcast-type ----
            if message.startswith("PERF_BCAST:"):
                broadcast(message, sender_socket=client_socket)
                safe_send(client_socket, message)  # ack back to sender for RTT timing
                write_history(username, "ALL", "broadcast", message)
                with stats_lock:
                    stats["messages_processed"] += 1
                    stats["broadcast_messages"] += 1
                continue

            # ---- Performance test: private-type ----
            if message.startswith("PERF_PRIV:"):
                # format: PERF_PRIV:<target>:<index>
                try:
                    _, target_name, idx = message.split(":", 2)
                except ValueError:
                    continue
                target_sock = find_socket_by_username(target_name)
                if target_sock is not None:
                    safe_send(target_sock, message)
                    write_history(username, target_name, "private", message)
                    with stats_lock:
                        stats["messages_processed"] += 1
                        stats["private_messages"] += 1
                safe_send(client_socket, message)  # ack back to sender for RTT timing
                continue

            # ---- Normal broadcast chat message ----
            formatted = f"[{username}] {message}"
            broadcast(formatted, sender_socket=client_socket)
            safe_send(client_socket, formatted)
            write_history(username, "ALL", "broadcast", message)
            with stats_lock:
                stats["messages_processed"] += 1
                stats["broadcast_messages"] += 1

    finally:
        with clients_lock:
            clients.pop(client_socket, None)
        client_socket.close()
        write_event_log("DISCONNECTED", username, ip)
        broadcast_all(f"[SERVER] {username} has left the chat.")


try:
    while True:
        client_socket, client_address = server_socket.accept()
        t = threading.Thread(
            target=handle_client,
            args=(client_socket, client_address),
            daemon=True,
        )
        t.start()
except KeyboardInterrupt:
    print("\n[SERVER] Shutting down.")
finally:
    server_socket.close()
