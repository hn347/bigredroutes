import csv
import io
import zipfile

import requests
from google.transit import gtfs_realtime_pb2

from config import *

# loads the GTFS data, runs route and direction and stop names
def load_gtfs_static_data():

    # downloads data
    resp = requests.get(GTFS_STATIC_ZIP_URL, timeout=30)
    resp.raise_for_status()

    # creates dictionaries for trip map, route stop ids, stop name lookup, and target trip ids
    trip_map = {}
    route_stop_ids = {route_id: set() for route_id in TARGET_ROUTES}
    stop_name_lookup = {}
    target_trip_ids = set()

    # opens zip file and reads
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        with zf.open("stops.txt") as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))

            for row in reader:
                stop_id = row.get("stop_id", "").strip()
                stop_name = row.get("stop_name", "").strip()

                if stop_id and stop_name:
                    stop_name_lookup[stop_id] = stop_name

        with zf.open("trips.txt") as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))

            for row in reader:
                route_id = row.get("route_id", "").strip()

                if route_id not in TARGET_ROUTES:
                    continue

                trip_id = row.get("trip_id", "").strip()
                headsign = row.get("trip_headsign", "").strip()
                direction_id = row.get("direction_id", "").strip()

                if headsign:
                    label = headsign
                elif direction_id != "":
                    label = f"direction_id={direction_id}"
                else:
                    label = "unknown direction"

                if trip_id:
                    target_trip_ids.add(trip_id)
                    trip_map[trip_id] = {
                        "route_id": route_id,
                        "direction": label,
                    }

        with zf.open("stop_times.txt") as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))

            for row in reader:
                trip_id = row.get("trip_id", "").strip()

                if trip_id not in target_trip_ids:
                    continue

                stop_id = row.get("stop_id", "").strip()
                route_id = trip_map[trip_id]["route_id"]

                if stop_id:
                    route_stop_ids[route_id].add(stop_id)

    route_stop_maps = {}

    for route_id, stop_ids in route_stop_ids.items():
        route_stop_maps[route_id] = {
            stop_id: stop_name_lookup.get(stop_id, f"Stop {stop_id}")
            for stop_id in sorted(
                stop_ids,
                key=lambda sid: int(sid) if sid.isdigit() else sid,
            )
        }

    return trip_map, route_stop_maps


def fetch_vehicle_feed(target_routes=None):
    if target_routes is None:
        active_routes = set(TARGET_ROUTES)
    else:
        active_routes = {str(route_id) for route_id in target_routes}
        active_routes = active_routes.intersection(TARGET_ROUTES)

        if not active_routes:
            return []

    resp = requests.get(VEHICLES_URL, timeout=20)
    resp.raise_for_status()

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(resp.content)

    buses = []

    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue

        vehicle = entity.vehicle

        if not vehicle.HasField("trip"):
            continue

        route_id = str(vehicle.trip.route_id)

        if route_id not in active_routes:
            continue

        status_label = "Unknown"
        occupancy_label = "Unknown"

        if vehicle.HasField("current_status"):
            try:
                status_label = gtfs_realtime_pb2.VehiclePosition.VehicleStopStatus.Name(
                    vehicle.current_status
                )
            except ValueError:
                status_label = str(vehicle.current_status)

        if vehicle.HasField("occupancy_status"):
            try:
                occupancy_label = gtfs_realtime_pb2.VehiclePosition.OccupancyStatus.Name(
                    vehicle.occupancy_status
                )
            except ValueError:
                occupancy_label = str(vehicle.occupancy_status)

        buses.append({
            "vehicle_id": entity.id,
            "trip_id": vehicle.trip.trip_id if vehicle.trip.trip_id else "",
            "route_id": route_id,
            "stop_id": str(vehicle.stop_id) if vehicle.stop_id else "",
            "current_stop_sequence": int(vehicle.current_stop_sequence)
            if vehicle.current_stop_sequence
            else None,
            "timestamp": int(vehicle.timestamp) if vehicle.timestamp else None,
            "current_status": status_label,
            "occupancy_status": occupancy_label,
        })

    return buses


def normalize_direction(direction_label, route_id=None):
    d = direction_label.lower()
    route_id = str(route_id) if route_id is not None else None

    # route-specific direction rules
    if route_id == "81":
        if "central campus" in d or "bti" in d:
            return "inbound"
        if "north campus" in d or "a lot" in d:
            return "outbound"

    if route_id == "92":
        if "collegetown" in d:
            return "inbound"
        if "north campus" in d:
            return "outbound"

    if "ithaca mall" in d or "mall" in d or "lansing" in d:
        return "outbound"

    if "commons" in d or "collegetown" in d or "cornell" in d or "cu" in d:
        return "inbound"

    if "direction_id=0" in d:
        return "outbound"

    if "direction_id=1" in d:
        return "inbound"

    return "unknown"

# Returns the current bus state for buses that have a corresponding LED pixels
def build_bus_snapshot(buses, trip_direction_map, stop_to_pixel):

    snapshot = {}

    for bus in buses:
        bus_id = bus["vehicle_id"]
        trip_id = bus["trip_id"]
        route_id = bus["route_id"]
        stop_id = bus["stop_id"]
        stop_key = (route_id, stop_id)

        if not stop_id or stop_key not in stop_to_pixel:
            continue

        trip_info = trip_direction_map.get(trip_id, {})

        direction = (
            bus.get("recorded_direction")
            or bus.get("direction")
            or trip_info.get("direction", "unknown direction")
        )

        direction_type = normalize_direction(direction, route_id=route_id)

        snapshot[bus_id] = {
            "route_id": route_id,
            "stop_id": stop_id,
            "direction": direction,
            "direction_type": direction_type,
        }

    return snapshot