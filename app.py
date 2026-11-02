"""Route-planning API for a city bike-share.

Riders ask for a route between two docking stations. The planner searches the city's
cycle-lane graph three times (fastest, flattest and quietest route) and returns all three,
so every /route request is CPU-heavy by design.

Endpoints:
  GET /route?from=<station>&to=<station>   three route options
  GET /stations                            docking stations with free bikes and docks
  GET /stations/<id>                       one station
  GET /healthz                             liveness
  GET /ready                               readiness (city graph loaded)
  GET /version                             app version and pod name
"""
import heapq
import json
import math
import os
import random
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

VERSION = os.environ.get("APP_VERSION", "dev")
POD = os.environ.get("HOSTNAME", "local")
PORT = int(os.environ.get("PORT", "8080"))
GRID = int(os.environ.get("CITY_GRID", "60"))  # GRID x GRID street intersections

PROFILES = {
    # weight of (distance, climb, traffic) for each route profile
    "fastest": (1.0, 0.2, 0.1),
    "flattest": (1.0, 3.0, 0.1),
    "quietest": (1.0, 0.3, 2.5),
}

city = {"nodes": {}, "edges": {}, "stations": {}}
ready = threading.Event()


def log(msg):
    print(f"{time.strftime('%H:%M:%S')} {POD} {msg}", flush=True)


def build_city():
    """Builds a deterministic street grid with elevation, traffic and docking stations."""
    rnd = random.Random(2026)
    nodes, edges = {}, {}
    for x in range(GRID):
        for y in range(GRID):
            elevation = 40 * math.sin(x / 9) + 25 * math.cos(y / 7) + rnd.uniform(0, 5)
            nodes[(x, y)] = elevation
    for (x, y), elev in nodes.items():
        out = []
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nb = (x + dx, y + dy)
            if nb not in nodes:
                continue
            if rnd.random() < 0.08:  # missing cycle lane on this block
                continue
            length = rnd.uniform(80, 160)
            climb = max(0.0, nodes[nb] - elev)
            traffic = rnd.choice((0.1, 0.3, 0.6, 1.0)) if (x % 10 == 0 or y % 10 == 0) else rnd.uniform(0, 0.3)
            out.append((nb, length, climb, traffic))
        edges[(x, y)] = out
    stations = {}
    sid = 1
    for x in range(2, GRID, 6):
        for y in range(3, GRID, 6):
            docks = rnd.choice((12, 16, 20, 24))
            bikes = rnd.randint(0, docks)
            stations[sid] = {"id": sid, "name": f"Station {sid:03d}", "at": [x, y],
                             "docks": docks, "bikes": bikes}
            sid += 1
    city.update(nodes=nodes, edges=edges, stations=stations)


def plan(start, goal, profile):
    """Dijkstra over the street grid with a profile-specific edge cost."""
    w_len, w_climb, w_traffic = PROFILES[profile]
    dist = {start: 0.0}
    prev = {}
    queue = [(0.0, start)]
    seen = set()
    while queue:
        cost, node = heapq.heappop(queue)
        if node in seen:
            continue
        seen.add(node)
        if node == goal:
            break
        for nb, length, climb, traffic in city["edges"][node]:
            step = w_len * length + w_climb * climb * 10 + w_traffic * traffic * length
            new = cost + step
            if new < dist.get(nb, float("inf")):
                dist[nb] = new
                prev[nb] = node
                heapq.heappush(queue, (new, nb))
    if goal not in dist:
        return None
    path = [goal]
    while path[-1] != start:
        path.append(prev[path[-1]])
    path.reverse()
    metres = climb = 0.0
    for a, b in zip(path, path[1:]):
        for nb, length, c, _ in city["edges"][a]:
            if nb == b:
                metres += length
                climb += c
                break
    return {"profile": profile, "blocks": len(path) - 1, "metres": round(metres),
            "climb_m": round(climb, 1), "minutes": round(metres / 250 + climb / 12, 1)}


def route(from_id, to_id):
    stations = city["stations"]
    if from_id not in stations or to_id not in stations:
        return 404, {"error": "unknown station"}
    if from_id == to_id:
        return 400, {"error": "start and end station are the same"}
    a, b = tuple(stations[from_id]["at"]), tuple(stations[to_id]["at"])
    options = [plan(a, b, p) for p in PROFILES]
    options = [o for o in options if o]
    if not options:
        return 404, {"error": "no cycle route between these stations"}
    return 200, {"from": stations[from_id]["name"], "to": stations[to_id]["name"],
                 "bikes_at_start": stations[from_id]["bikes"],
                 "free_docks_at_end": stations[to_id]["docks"] - stations[to_id]["bikes"],
                 "options": options, "served_by": POD, "version": VERSION}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_json(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        if url.path == "/healthz":
            return self.send_json(200, {"status": "ok"})
        if url.path == "/ready":
            if ready.is_set():
                return self.send_json(200, {"status": "ready"})
            return self.send_json(503, {"status": "loading city graph"})
        if url.path == "/version":
            return self.send_json(200, {"version": VERSION, "pod": POD})
        if not ready.is_set():
            return self.send_json(503, {"error": "starting"})
        if parts == ["stations"]:
            return self.send_json(200, list(city["stations"].values()))
        if len(parts) == 2 and parts[0] == "stations" and parts[1].isdigit():
            st = city["stations"].get(int(parts[1]))
            return self.send_json(200 if st else 404, st or {"error": "unknown station"})
        if parts == ["route"]:
            q = parse_qs(url.query)
            try:
                from_id, to_id = int(q["from"][0]), int(q["to"][0])
            except (KeyError, ValueError):
                return self.send_json(400, {"error": "use /route?from=<id>&to=<id>"})
            status, body = route(from_id, to_id)
            return self.send_json(status, body)
        return self.send_json(404, {"error": "not found"})


def main():
    server = ThreadingHTTPServer(("", PORT), Handler)

    def stop(*_):
        log("SIGTERM received, shutting down")
        threading.Thread(target=server.shutdown).start()

    signal.signal(signal.SIGTERM, stop)
    log(f"route planner {VERSION} starting, building city graph")
    build_city()
    ready.set()
    log(f"city graph loaded: {GRID * GRID} intersections, {len(city['stations'])} stations")
    server.serve_forever()
    sys.exit(0)


if __name__ == "__main__":
    main()
