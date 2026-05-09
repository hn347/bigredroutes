import time
import RPi.GPIO as GPIO
from route_data import (
    INBOUND_PICKER_STOP_ORDER,
    OUTBOUND_PICKER_STOP_ORDER,
    ROUTE_30_INBOUND_STOPS,
    ROUTE_30_OUTBOUND_STOPS,
    ROUTE_81_INBOUND_STOPS,
    ROUTE_81_OUTBOUND_STOPS,
    ROUTE_92_INBOUND_STOPS,
    ROUTE_92_OUTBOUND_STOPS,
)
from find_a_route import quick_find_from_entries


# GPIO pin assignments
WHITE_BUTTON_PIN = 18   # white button = select/back button
GREEN_BUTTON_PIN = 14   # green button = cycle mode on home screen OR Route 30 on route screen
BLUE_BUTTON_PIN = 19    # blue button = Route 81
RED_BUTTON_PIN = 15     # red button = Route 92


MODES = [
    "Select a Route to Display",
    "Find a Route for Your Trip",
]


def setup_gpio():
    GPIO.setmode(GPIO.BCM)

    GPIO.setup(WHITE_BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(GREEN_BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(BLUE_BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(RED_BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)


# handling buttons on map
def gpio_button_loop(stop_event, screen_command_queue, led_route_queue):

    current_screen = "home"
    selected_mode_index = 0
    trip_direction = None
    trip_start_entries = []
    trip_start_index = 0
    trip_start_selected_entry = None
    trip_end_entries = []
    trip_end_index = 0

    # show the home screen at startup
    screen_command_queue.put(("show_home", selected_mode_index))

    # show all routes on led matrix at startup
    led_route_queue.put("ALL")

    # build stop picking list from selected direction
    def build_trip_entries(direction):
        route_lists = (
            [ROUTE_30_OUTBOUND_STOPS, ROUTE_81_OUTBOUND_STOPS, ROUTE_92_OUTBOUND_STOPS]
            if direction == "outbound"
            else [ROUTE_30_INBOUND_STOPS, ROUTE_81_INBOUND_STOPS, ROUTE_92_INBOUND_STOPS]
        )
        preferred_stop_order = (
            OUTBOUND_PICKER_STOP_ORDER
            if direction == "outbound"
            else INBOUND_PICKER_STOP_ORDER
        )
        entries = []
        grouped_by_stop = {}

        # group all route entires by stop name
        for route_stops in route_lists:
            for route_item in route_stops:
                stop_name = str(route_item["name"])
                grouped_by_stop.setdefault(stop_name, []).append(
                    (
                        str(route_item["route"]),
                        stop_name,
                        str(route_item["stop_id"]),
                    )
                )

        # adds stops in preferred order first
        for stop_name in preferred_stop_order:
            entries.extend(grouped_by_stop.pop(stop_name, []))
        # add remaining stops
        for stop_name in sorted(grouped_by_stop.keys()):
            entries.extend(grouped_by_stop[stop_name])

        return entries

    # display trip stop picker on pitft
    def send_trip_picker_screen(direction, phase, entries, selected_index):
        screen_command_queue.put(
            (
                "show_trip_stop_picker",
                {
                    "direction": direction,
                    "phase": phase,
                    "stop_entries": entries,
                    "selected_index": selected_index,
                },
            )
        )

    # cycling through the stop selection options
    def cycle_trip_picker(direction, phase, step):

        nonlocal trip_start_index
        nonlocal trip_end_index

        # whether we are moving through start or end stops
        entries = trip_start_entries if phase == "start" else trip_end_entries

        if not entries:
            return

        current_index = trip_start_index if phase == "start" else trip_end_index
        n = len(entries)

        # green to move forward and blue for backward
        button_pin = GREEN_BUTTON_PIN if step > 0 else BLUE_BUTTON_PIN

        hold_start = time.time()
        next_step_time = 0.0

        # scrolling while button is held
        while GPIO.input(button_pin) == GPIO.LOW and not stop_event.is_set():
            now = time.time()

            if now >= next_step_time:
                current_index = (current_index + step) % n

                if phase == "start":
                    trip_start_index = current_index
                else:
                    trip_end_index = current_index

                # update pitft picker screen
                send_trip_picker_screen(direction, phase, entries, current_index)
                # light currently selected stop on matrix
                highlight_entry(entries[current_index], direction)

                # scrolling speeds up as button held longer
                held_for = now - hold_start
                if held_for < 0.8:
                    step_delay = 0.27
                elif held_for < 1.8:
                    step_delay = 0.16
                else:
                    step_delay = 0.08

                next_step_time = now + step_delay

            # add delay
            time.sleep(0.01)

    # lights corresponding stop on led matrix while scrollig
    def highlight_entry(entry, direction):
        if entry is None:
            return

        route_id, _stop_name, stop_id = entry
        led_route_queue.put(
            (
                "highlight_stop",
                {
                    "route": route_id,
                    "stop_id": stop_id,
                    "direction": direction,
                },
            )
        )

    # locks stop on matrix when user selects start/end stop
    def lock_entry(entry, direction):
        if entry is None:
            return

        route_id, _stop_name, stop_id = entry
        led_route_queue.put(
            (
                "lock_stop",
                {
                    "route": route_id,
                    "stop_id": stop_id,
                    "direction": direction,
                },
            )
        )

    # start find a route mode
    def enter_trip_selection_mode(direction):
        nonlocal trip_direction
        nonlocal trip_start_entries
        nonlocal trip_start_index
        nonlocal trip_start_selected_entry
        nonlocal trip_end_entries
        nonlocal trip_end_index
        nonlocal current_screen

        trip_direction = direction
        trip_start_entries = build_trip_entries(trip_direction)
        trip_start_index = 0
        trip_start_selected_entry = None
        trip_end_entries = []
        trip_end_index = 0
        current_screen = "trip_stop_picker_start"

        led_route_queue.put(("trip_mode", True))

        # show picking screen
        send_trip_picker_screen(
            trip_direction,
            "start",
            trip_start_entries,
            trip_start_index,
        )

        # light first stop
        if trip_start_entries:
            highlight_entry(trip_start_entries[trip_start_index], trip_direction)

    # leaves trip selection mode and show all routes
    def exit_trip_selection_mode():
        led_route_queue.put(("trip_mode", False))
        led_route_queue.put("ALL")

    while not stop_event.is_set():

        # WHITE BUTTON
        if GPIO.input(WHITE_BUTTON_PIN) == GPIO.LOW:

            if current_screen == "home":
                selected_mode = MODES[selected_mode_index]

                if selected_mode == "Select a Route to Display":
                    current_screen = "route_selection"
                    screen_command_queue.put(("show_route_selection", None))

                elif selected_mode == "Find a Route for Your Trip":
                    current_screen = "trip_finder"
                    screen_command_queue.put(("show_trip_finder", None))

            elif current_screen == "trip_stop_picker_start":
                if trip_start_entries:
                    trip_start_selected_entry = trip_start_entries[trip_start_index]
                    lock_entry(trip_start_selected_entry, trip_direction)
                    trip_end_entries = trip_start_entries[trip_start_index + 1:]
                    trip_end_index = 0
                    current_screen = "trip_stop_picker_end"

                    send_trip_picker_screen(
                        trip_direction,
                        "end",
                        trip_end_entries,
                        trip_end_index,
                    )
                    if trip_end_entries:
                        highlight_entry(trip_end_entries[trip_end_index], trip_direction)

            elif current_screen == "trip_stop_picker_end":
                if trip_end_entries:
                    selected_end_entry = trip_end_entries[trip_end_index]
                    lock_entry(selected_end_entry, trip_direction)
                    planned_route = quick_find_from_entries(
                        trip_start_selected_entry,
                        selected_end_entry,
                        trip_direction,
                    )
                    led_route_queue.put(("planned_trip_route", planned_route))
                    current_screen = "trip_summary"
                    screen_command_queue.put(
                        (
                            "show_trip_summary",
                            {
                                "direction": trip_direction,
                                "start_entry": trip_start_selected_entry,
                                "end_entry": selected_end_entry,
                            },
                        )
                    )

            elif current_screen != "home":
                current_screen = "home"
                screen_command_queue.put(("show_home", selected_mode_index))
                if trip_direction is not None:
                    exit_trip_selection_mode()
                    trip_direction = None

            time.sleep(0.3)

        # GREEN BUTTON
        elif GPIO.input(GREEN_BUTTON_PIN) == GPIO.LOW:

            if current_screen == "home":
                selected_mode_index = (selected_mode_index + 1) % len(MODES)
                screen_command_queue.put(("show_home", selected_mode_index))

            elif current_screen == "route_selection":
                current_screen = "route"
                screen_command_queue.put(("next_bus", "30"))
                led_route_queue.put("30")

            elif current_screen == "route":
                screen_command_queue.put(("next_bus", "30"))
                led_route_queue.put("30")

            elif current_screen == "trip_finder":
                enter_trip_selection_mode("outbound")

            elif current_screen in ["trip_stop_picker_start", "trip_stop_picker_end"] and trip_direction in (
                "outbound",
                "inbound",
            ):
                picker_phase = "start" if current_screen == "trip_stop_picker_start" else "end"
                cycle_trip_picker(trip_direction, picker_phase, 1)
                time.sleep(0.1)
                continue

            time.sleep(0.3)

        # BLUE BUTTON
        elif GPIO.input(BLUE_BUTTON_PIN) == GPIO.LOW:

            if current_screen in ["trip_stop_picker_start", "trip_stop_picker_end"] and trip_direction in (
                "outbound",
                "inbound",
            ):
                picker_phase = "start" if current_screen == "trip_stop_picker_start" else "end"
                cycle_trip_picker(trip_direction, picker_phase, -1)
                time.sleep(0.1)
                continue

            if current_screen in ["route_selection", "route"]:
                current_screen = "route"
                screen_command_queue.put(("next_bus", "81"))
                led_route_queue.put("81")

            time.sleep(0.3)

        # RED BUTTON
        elif GPIO.input(RED_BUTTON_PIN) == GPIO.LOW:

            if current_screen in ["route_selection", "route"]:
                current_screen = "route"
                screen_command_queue.put(("next_bus", "92"))
                led_route_queue.put("92")

            elif current_screen == "trip_finder":
                enter_trip_selection_mode("inbound")

            time.sleep(0.3) # debouncing

        else:
            time.sleep(0.01) # delay if no button is pressed