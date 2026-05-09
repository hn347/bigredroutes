import queue
import threading

import RPi.GPIO as GPIO

from config import *
from route_data import ROUTE_STOP_DATA_BY_ROUTE
from tcat_api import load_gtfs_static_data
from bus_tracker import (
    build_global_stop_maps,
    bus_poll_loop,
)
from led_matrix import BusLEDMatrix
from gui import pitft_screen_loop
from gpio_buttons import setup_gpio, gpio_button_loop


def main():
    # load GTFS data
    trip_direction_map = load_gtfs_static_data()

    # build stop name and pixel lookup tables using pixels assigned in route_data.py
    stop_name_map, stop_to_pixel = build_global_stop_maps(
        ROUTE_STOP_DATA_BY_ROUTE
    )

    # setup gpio pins for buttons
    setup_gpio()

    stop_event = threading.Event()
    screen_command_queue = queue.Queue() # queue to send button commands to pitft
    led_route_queue = queue.Queue() # queue to send route selection commands to LED
    
    # create a led matrix object
    led_matrix = BusLEDMatrix(
        rows=HEIGHT,
        cols=WIDTH,
        brightness=80,
        gpio_slowdown=4,
    )
    led_matrix.clear()

    # thread 1 - polls TCAT data continuously
    poll_thread = threading.Thread(
        name="TCAT API polling",
        target=bus_poll_loop,
        args=(
            stop_event,
            trip_direction_map,
            stop_name_map,
            stop_to_pixel,
            led_matrix,
            led_route_queue,
        ),
        daemon=True,
    )

    # thread 2 - continuously checks if button is pressed
    button_thread = threading.Thread(
        name="GPIO button loop",
        target=gpio_button_loop,
        args=(stop_event, screen_command_queue, led_route_queue),
        daemon=True,
    )

    try:
        poll_thread.start()
        button_thread.start()
        pitft_screen_loop(stop_event, screen_command_queue)

    except KeyboardInterrupt:
        pass

    finally:
        stop_event.set() # stop all threads
        poll_thread.join(timeout=1.0)
        button_thread.join(timeout=1.0)
        GPIO.cleanup()


if __name__ == "__main__":
    main()