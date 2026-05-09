import json
import os
import queue
import random
import threading
import time

from config import *
from route_data import ROUTE_COLORS
from tcat_api import (
    fetch_vehicle_feed,
    build_bus_snapshot,
)
from audio_announcer import AudioAnnouncer

route_gui_lock = threading.Lock()

route_gui_data = {
    "30": {},
    "81": {},
    "92": {},
}

# loops recorded route 92 data
class Route92Replay:
    def __init__(self, filename):
        self.filename = filename
        self.snapshots = []
        self.index = 0
        self.enabled = False

        self.load_file()

    def load_file(self):
        if not os.path.exists(self.filename):
            print(f"Route 92 replay file not found: {self.filename}")
            return

        with open(self.filename, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()

                if not line:
                    continue

                try:
                    snapshot = json.loads(line)
                except json.JSONDecodeError:
                    continue

                buses = snapshot.get("buses", [])

                # only keep snapshots where the 92 actually had buses
                if buses:
                    self.snapshots.append(snapshot)

        if not self.snapshots:
            print("Route 92 replay file was found, but it had no usable bus data.")
            return

        # randomization of starting point
        self.index = random.randrange(len(self.snapshots))
        self.enabled = True


    def next_buses(self):
        if not self.enabled or not self.snapshots:
            return []

        snapshot = self.snapshots[self.index]

        # move to next snapshot for next time
        self.index = (self.index + 1) % len(self.snapshots)

        replay_buses = []

        for bus in snapshot.get("buses", []):
            stop_id = str(bus.get("stop_id", ""))

            if not stop_id:
                continue

            # convert the recorded data into same format as tcat api data
            replay_buses.append({
                "vehicle_id": str(bus.get("vehicle_id", "route92_replay")),
                "trip_id": bus.get("trip_id", ""),
                "route_id": "92",
                "stop_id": stop_id,
                "current_stop_sequence": bus.get("current_stop_sequence"),
                "timestamp": bus.get("vehicle_timestamp"),
                "current_status": bus.get("status", "Recorded"),
                "occupancy_status": bus.get("occupancy", "Unknown"),

                # Extra recorded fields for the PiTFT display.
                "recorded_last_stop": bus.get("last_stop", "Unknown"),
                "recorded_destination": bus.get("destination", "Unknown"),
                "recorded_direction": bus.get("direction", "Unknown"),
                "is_replay": True,
            })

        return replay_buses


def _generate_unused_pixels(used_pixels, needed):
    pixels = []

    for y in range(13, -1, -1):
        for x in range(WIDTH - 1, -1, -1):
            pixel = (x, y)

            if pixel in used_pixels:
                continue

            pixels.append(pixel)

            if len(pixels) >= needed:
                return pixels

    return pixels


def build_placeholder_route_stop_data(route_stop_map, used_pixels):
    stop_items = sorted(
        route_stop_map.items(),
        key=lambda item: int(item[0]) if item[0].isdigit() else item[0],
    )

    available_pixels = _generate_unused_pixels(used_pixels, len(stop_items))

    if len(available_pixels) < len(stop_items):
        raise RuntimeError("Not enough unused pixels to place all placeholder stops.")

    placeholder_data = {}

    for idx, (stop_id, stop_name) in enumerate(stop_items):
        pixel = available_pixels[idx]
        used_pixels.add(pixel)

        placeholder_data[stop_id] = {
            "name": stop_name,
            "pixel": pixel,
        }

    return placeholder_data


def build_global_stop_maps(route_stop_data_by_route):
    stop_name_map = {}
    stop_to_pixel = {}

    for route_id, route_stop_data in route_stop_data_by_route.items():
        for stop_id, data in route_stop_data.items():
            key = (route_id, stop_id)

            stop_name_map[key] = data["name"]
            stop_to_pixel[key] = data["pixel"]

    return stop_name_map, stop_to_pixel


def update_route_gui_data(buses, trip_direction_map, stop_name_map):
    latest = {
        "30": {},
        "81": {},
        "92": {},
    }

    for bus in buses:
        route_id = bus["route_id"]

        if route_id not in latest:
            continue

        trip_info = trip_direction_map.get(bus["trip_id"], {})
        stop_id = bus["stop_id"]

        # use the recorded stop name if using replayed data
        if bus.get("recorded_last_stop"):
            stop_name = bus["recorded_last_stop"]
        elif stop_id:
            stop_name = stop_name_map.get((route_id, stop_id), f"Stop {stop_id}")
        else:
            stop_name = "Unknown"

        # use the recorded destination/direction if using replayed data
        destination = (
            bus.get("recorded_destination")
            or trip_info.get("direction", "Unknown")
        )

        direction = (
            bus.get("recorded_direction")
            or destination
        )

        latest[route_id][bus["vehicle_id"]] = {
            "status": bus.get("current_status", "Unknown"),
            "last_stop": stop_name,
            "destination": destination,
            "direction": direction,
            "occupancy": bus.get("occupancy_status", "Unknown"),
        }

    with route_gui_lock:
        route_gui_data["30"].clear()
        route_gui_data["81"].clear()
        route_gui_data["92"].clear()

        route_gui_data["30"].update(latest["30"])
        route_gui_data["81"].update(latest["81"])
        route_gui_data["92"].update(latest["92"])


def get_route_gui_snapshot(route_id):
    with route_gui_lock:
        return {
            bus_id: dict(info)
            for bus_id, info in route_gui_data.get(route_id, {}).items()
        }


# clears matrix and redraws selected route
def draw_selected_route_leds(led_matrix, bus_states, stop_to_pixel, selected_route_id):
    led_matrix.clear()

    if selected_route_id is None:
        return

    for bus_id, state in bus_states.items():
        route_id = state["route_id"]

        if selected_route_id != "ALL" and route_id != selected_route_id:
            continue

        stop_id = state["stop_id"]
        stop_key = (route_id, stop_id)

        if stop_key not in stop_to_pixel:
            continue

        pixel = stop_to_pixel[stop_key]
        direction_type = state.get("direction_type", "unknown")

        if direction_type == "outbound":
            color = GREEN
        else:
            color = RED

        led_matrix.set_pixel(pixel[0], pixel[1], color)


def draw_single_stop_led(led_matrix, stop_to_pixel, route_id, stop_id, direction_mode):
    led_matrix.clear()

    stop_key = (str(route_id), str(stop_id))
    pixel = stop_to_pixel.get(stop_key)

    if pixel is None:
        return

    color = GREEN if direction_mode == "outbound" else RED
    led_matrix.set_pixel(pixel[0], pixel[1], color)


def draw_trip_picker_leds(led_matrix, stop_to_pixel, locked_stops, highlighted_stop):
    led_matrix.clear()

    for stop_info in locked_stops:
        stop_key = (str(stop_info.get("route")), str(stop_info.get("stop_id")))
        pixel = stop_to_pixel.get(stop_key)
        if pixel is None:
            continue

        direction_mode = stop_info.get("direction")
        color = GREEN if direction_mode == "outbound" else RED
        led_matrix.set_pixel(pixel[0], pixel[1], color)

    if highlighted_stop is None:
        return

    stop_key = (
        str(highlighted_stop.get("route")),
        str(highlighted_stop.get("stop_id")),
    )
    pixel = stop_to_pixel.get(stop_key)
    if pixel is None:
        return

    direction_mode = highlighted_stop.get("direction")
    color = GREEN if direction_mode == "outbound" else RED
    led_matrix.set_pixel(pixel[0], pixel[1], color)


def draw_planned_trip_route_leds(led_matrix, planned_route):
    led_matrix.clear()

    if not isinstance(planned_route, dict):
        return

    for segment in planned_route.get("segments", []):
        route_id = str(segment.get("route"))
        color = ROUTE_COLORS.get(route_id, GREEN)
        for pixel in segment.get("pixels", []):
            if not isinstance(pixel, (list, tuple)) or len(pixel) != 2:
                continue
            led_matrix.set_pixel(int(pixel[0]), int(pixel[1]), color)


def bus_poll_loop(
    stop_event,
    trip_direction_map,
    stop_name_map,
    stop_to_pixel,
    led_matrix,
    led_route_queue,
):
    bus_states = {}
    selected_route_id = "ALL"
    trip_mode_active = False
    trip_locked_stops = []
    trip_highlighted_stop = None

    last_poll = 0

    # start audio announcer
    audio_announcer = AudioAnnouncer(
        enabled=True,
        voice="en-us+f3",
        speed=145,
        volume=140,
    )

    # load route 92 replay data
    route92_replay = Route92Replay(ROUTE_92_RECORDED_DATA_FILE)

    # clear matrix at startup
    led_matrix.clear()

    try:
        while not stop_event.is_set():

            # check if user selected a new route
            try:
                while True:
                    previous_route = selected_route_id
                    led_command = led_route_queue.get_nowait()

                    if isinstance(led_command, tuple):
                        command_type, command_value = led_command

                        if command_type == "trip_mode":
                            trip_mode_active = bool(command_value)
                            audio_announcer.set_enabled(not trip_mode_active, clear_queue=True)
                            trip_locked_stops = []
                            trip_highlighted_stop = None

                            if trip_mode_active:
                                led_matrix.clear()
                            else:
                                draw_selected_route_leds(
                                    led_matrix,
                                    bus_states,
                                    stop_to_pixel,
                                    selected_route_id,
                                )
                            continue

                        if command_type == "highlight_stop":
                            stop_info = command_value if isinstance(command_value, dict) else {}
                            trip_highlighted_stop = stop_info
                            draw_trip_picker_leds(
                                led_matrix,
                                stop_to_pixel,
                                trip_locked_stops,
                                trip_highlighted_stop,
                            )
                            continue

                        if command_type == "lock_stop":
                            stop_info = command_value if isinstance(command_value, dict) else {}
                            if stop_info:
                                stop_key = (
                                    str(stop_info.get("route")),
                                    str(stop_info.get("stop_id")),
                                )
                                if all(
                                    (
                                        str(existing.get("route")),
                                        str(existing.get("stop_id")),
                                    ) != stop_key
                                    for existing in trip_locked_stops
                                ):
                                    trip_locked_stops.append(stop_info)
                            draw_trip_picker_leds(
                                led_matrix,
                                stop_to_pixel,
                                trip_locked_stops,
                                trip_highlighted_stop,
                            )
                            continue

                        if command_type == "planned_trip_route":
                            draw_planned_trip_route_leds(led_matrix, command_value)
                            continue

                    selected_route_id = led_command

                    # when user changes route selection force an immediate poll
                    if selected_route_id != previous_route:
                        last_poll = 0

                    # immediately redraw using the current bus states
                    if selected_route_id != "ALL":
                        bus_states = {
                            bus_id: state
                            for bus_id, state in bus_states.items()
                            if state["route_id"] == selected_route_id
                        }

                    draw_selected_route_leds(
                        led_matrix,
                        bus_states,
                        stop_to_pixel,
                        selected_route_id,
                    )

            except queue.Empty:
                pass

            now_time = time.time()

            if trip_mode_active:
                time.sleep(0.1)
                continue

            if now_time - last_poll < POLL_SECONDS:
                time.sleep(0.2)
                continue

            last_poll = now_time

            try:
                if selected_route_id == "ALL":
                    active_routes = set(TARGET_ROUTES)
                else:
                    active_routes = {selected_route_id}

                live_buses = fetch_vehicle_feed(target_routes=active_routes)

                # check if 92 is currently running in live api
                live_route92_buses = []

                if "92" in active_routes:
                    live_route92_buses = [
                        bus for bus in live_buses
                        if bus["route_id"] == "92"
                    ]

                # start with real live buses
                buses = list(live_buses)

                # if 92 is not running live, use recorded data
                if "92" in active_routes and not live_route92_buses and route92_replay is not None:
                    replay_buses = route92_replay.next_buses()

                    if replay_buses:
                        buses.extend(replay_buses)

                active_vehicle_ids = {bus["vehicle_id"] for bus in buses}

                update_route_gui_data(
                    buses,
                    trip_direction_map,
                    stop_name_map,
                )

                latest_snapshot = build_bus_snapshot(
                    buses,
                    trip_direction_map,
                    stop_to_pixel,
                )

                for bus_id, state in latest_snapshot.items():
                    previous_stop = bus_states.get(bus_id, {}).get("stop_id")
                    bus_states[bus_id] = state

                    # bus was being tracked and stop changed
                    if previous_stop is not None and state["stop_id"] != previous_stop:
                        stop_key = (state["route_id"], state["stop_id"])
                        stop_name = stop_name_map.get(
                            stop_key,
                            f"Stop {state['stop_id']}",
                        )

                        pixel = stop_to_pixel.get(stop_key)
                        now_str = time.strftime("%H:%M:%S")

                        # only announce if the user selected the route
                        if selected_route_id == state["route_id"]:
                            audio_announcer.announce_bus_arrival(
                                route_id=state["route_id"],
                                bus_id=bus_id,
                                stop_name=stop_name,
                                direction=state.get("direction", "Unknown"),
                            )

                    # if this bus just appeared in the tracker for the first time
                    if previous_stop is None:
                        stop_key = (state["route_id"], state["stop_id"])
                        stop_name = stop_name_map.get(
                            stop_key,
                            f"Stop {state['stop_id']}",
                        )

                        pixel = stop_to_pixel.get(stop_key)
                        now_str = time.strftime("%H:%M:%S")

                # remove buses that disappeared from the live feed
                for old_bus_id in list(bus_states.keys()):
                    if (
                        old_bus_id not in latest_snapshot
                        and old_bus_id not in active_vehicle_ids
                    ):
                        del bus_states[old_bus_id]

                # redraw LEDs using the currently selected route setting
                draw_selected_route_leds(
                    led_matrix,
                    bus_states,
                    stop_to_pixel,
                    selected_route_id,
                )

            except Exception as e:
                print("Error in bus_poll_loop:", e)

    finally:
        audio_announcer.stop()