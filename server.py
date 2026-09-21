#!/usr/bin/env python3
"""워크샵 점수판 — 같은 와이파이의 노트북끼리 점수를 맞추는 작은 서버.

설치할 것 없음. 파이썬 기본 기능만 쓴다.
    python3 server.py

한 노트북에서 이걸 켜면, 같은 와이파이에 있는 다른 노트북이
화면에 찍히는 주소로 접속해 같은 점수판을 본다.
인터넷은 필요 없다. 두 노트북이 같은 공유기에만 붙어 있으면 된다.
"""

import json
import os
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SAVE = os.path.join(HERE, "score-state.json")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
TEAMS = 6

lock = threading.Lock()
seen = set()                                  # 이미 붙은 기기
state = {
    "v": 0,                                  # 바뀔 때마다 1씩 오른다
    "rounds": [[0] * TEAMS],                 # rounds[라운드][팀]
    "cur": 0,
    "vals": [1, 3, 5],
    "history": [],                           # 되돌리기
}


def load():
    """서버를 다시 켜도 점수가 남아 있게 한다."""
    if not os.path.exists(SAVE):
        return
    try:
        with open(SAVE, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d.get("rounds"), list) and d["rounds"]:
            state.update({k: d[k] for k in ("rounds", "cur", "vals", "history") if k in d})
            print(f"이전 점수를 불러왔습니다 ({len(state['rounds'])}라운드)")
    except Exception as e:
        print("저장 파일을 읽지 못했습니다:", e)


def save():
    try:
        with open(SAVE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except Exception as e:
        print("저장 실패:", e)


def public():
    return {k: state[k] for k in ("v", "rounds", "cur", "vals")}


def apply(op):
    """클라이언트가 보낸 조작 하나를 적용한다. 점수는 증감값으로 받는다."""
    kind = op.get("op")
    if kind == "add":
        t, d = int(op["t"]), int(op["d"])
        if 0 <= t < TEAMS and d:
            state["rounds"][state["cur"]][t] += d
            state["history"].append({"r": state["cur"], "t": t, "d": d})
    elif kind == "undo":
        if state["history"]:
            h = state["history"].pop()
            state["rounds"][h["r"]][h["t"]] -= h["d"]
    elif kind == "round":
        n = max(0, int(op["n"]))
        while len(state["rounds"]) <= n:
            state["rounds"].append([0] * TEAMS)
        state["cur"] = n
    elif kind == "vals":
        v = [max(1, int(x)) for x in op["vals"][:3]]
        if len(v) == 3:
            state["vals"] = v
    elif kind == "reset":
        state["rounds"] = [[0] * TEAMS]
        state["cur"] = 0
        state["history"] = []
    else:
        return
    state["v"] += 1
    save()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/state"):
            with lock:
                body = json.dumps(public(), ensure_ascii=False).encode()
            return self._send(200, body)
        path = os.path.join(HERE, "index.html")
        if not os.path.exists(path):
            return self._send(404, b"index.html not found", "text/plain; charset=utf-8")
        with open(path, "rb") as f:
            self._send(200, f.read(), "text/html; charset=utf-8")

    def do_POST(self):
        if self.path != "/op":
            return self._send(404, b'{"error":"not found"}')
        try:
            n = int(self.headers.get("Content-Length", 0))
            op = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, b'{"error":"bad json"}')
        with lock:
            apply(op)
            body = json.dumps(public(), ensure_ascii=False).encode()
        self._send(200, body)

    def log_message(self, *a):
        pass                                  # 폴링 로그로 터미널을 더럽히지 않는다

    def handle_one_request(self):
        ip = self.client_address[0]
        if ip not in seen:                    # 새 기기가 붙은 것만 알린다
            seen.add(ip)
            print(f"  접속: {ip}", flush=True)
        super().handle_one_request()


def lan_ip():
    """이 노트북이 공유기에서 받은 주소. 인터넷에 안 나가도 알아낼 수 있다."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    load()
    ip = lan_ip()
    print()
    print("  점수판 서버가 떴습니다. 이 창을 닫으면 꺼집니다.")
    print()
    print(f"  이 노트북에서       http://localhost:{PORT}")
    print(f"  다른 노트북에서     http://{ip}:{PORT}")
    print()
    print("  다른 기기가 붙으면 아래에 「접속」 으로 찍힙니다.")
    print()
    print("  같은 와이파이에 붙어 있어야 합니다. 인터넷은 필요 없습니다.")
    print(f"  점수는 {os.path.basename(SAVE)} 에 저장돼서 서버를 다시 켜도 남습니다.")
    print()
    try:
        ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\n  서버를 껐습니다.")
