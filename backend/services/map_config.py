"""Static geography shared by the world, administration and data migration."""
import json
from functools import lru_cache
from pathlib import Path

MAP_FILE = Path(__file__).resolve().parents[2] / "content/map_location.json"


def contains(points, x, y):
    inside = False
    for (ax, ay), (bx, by) in zip(points, points[1:] + points[:1]):
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
    return inside


def polygon_area(points):
    return abs(sum(ax * by - bx * ay for (ax, ay), (bx, by) in zip(points, points[1:] + points[:1]))) / 2


def boundary_edges(points):
    return {tuple(sorted((tuple(a), tuple(b)))) for a, b in zip(points, points[1:] + points[:1]) if a != b}


@lru_cache
def config():
    data = json.loads(MAP_FILE.read_text(encoding="utf-8"))
    rows = data["locations"]
    locations = {row["id"]: row for row in rows}
    start = data["map"]["starting_location_id"]
    if (not rows or len(rows) != data["map"]["total_locations"] or len(locations) != len(rows)
            or any(type(key) is not int or key <= 0 for key in locations)
            or len({row["key"] for row in rows}) != len(rows)):
        raise ValueError("Кількість, ID та ключі локацій повинні узгоджуватися з конфігурацією.")
    if [row["id"] for row in rows if row["unlocked_by_default"]] != [start]:
        raise ValueError("На початку доступна лише столиця.")
    if sorted(row["unlock_order"] for row in rows) != list(range(1, len(rows) + 1)):
        raise ValueError("Порядок відкриття повинен містити всі етапи від 1 до кількості локацій.")
    area = polygon_area(data["map"]["playable_area"]["points"])
    if area <= 0:
        raise ValueError("Ігрова територія повинна мати додатну площу.")
    edges = {row["id"]: boundary_edges(row["geometry"]["points"]) for row in rows}
    if abs(sum(polygon_area(row["geometry"]["points"]) for row in rows) - area) > 1e-7:
        raise ValueError("Сектори повинні покривати всю ігрову територію.")
    reached = set()
    for row in sorted(rows, key=lambda row: row["unlock_order"]):
        points = row["geometry"]["points"]
        if (len(set(map(tuple, points))) < 3 or any(len(point) != 2 or not all(0 <= v <= 1 for v in point)
                                                   for point in points)
                or not contains(points, row["marker"]["x"], row["marker"]["y"])):
            raise ValueError(f"Некоректна геометрія локації {row['id']}.")
        links = {link["location_id"]: link for link in row["connections"]}
        if len(links) != len(row["connections"]) or row["id"] in links:
            raise ValueError(f"Некоректні маршрути локації {row['id']}.")
        for other, link in links.items():
            seconds = link["travel_time_seconds"]
            points = link.get("waypoints", [])
            if (not isinstance(points, list) or any(not isinstance(point, list) or len(point) != 2
                    or any(type(value) not in (int, float) or not 0 <= value <= 1 for value in point)
                    for point in points)):
                raise ValueError(f"Некоректні точки маршруту {row['id']} → {other}.")
            reverse = next((route for route in locations.get(other, {}).get("connections", ())
                            if route["location_id"] == row["id"]), None)
            if (reverse is None or not edges[row["id"]].intersection(edges[other])
                    or type(seconds) is not int or seconds <= 0 or reverse["travel_time_seconds"] != seconds
                    or reverse.get("waypoints", []) != points[::-1]):
                raise ValueError(f"Маршрут {row['id']} → {other} повинен бути двостороннім.")
        if row["id"] != start and not reached.intersection(links):
            raise ValueError(f"На етапі {row['unlock_order']} локація ізольована.")
        reached.add(row["id"])
    return data


@lru_cache
def by_key():
    return {row["key"]: row for row in config()["locations"]}


def supports(key, feature):
    location = by_key().get(key)
    return location is None or location["features"].get(feature, False)


@lru_cache
def routes_from(key):
    row = by_key().get(key)
    if row is None:
        return {}
    keys = {location["id"]: location["key"] for location in config()["locations"]}
    return {keys[link["location_id"]]: link["travel_time_seconds"] for link in row["connections"]}


def marker_position(key):
    row = by_key().get(key)
    return tuple(round(100 * row["marker"][axis]) for axis in ("x", "y")) if row else None


def route_waypoints(origin, destination):
    first, second = by_key().get(origin), by_key().get(destination)
    if first and second:
        return next((route.get("waypoints", []) for route in first["connections"]
                     if route["location_id"] == second["id"]), [])
    return []
