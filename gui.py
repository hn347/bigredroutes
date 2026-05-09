import os
import time
import queue

import pygame
from pygame.locals import *

from config import *
from bus_tracker import get_route_gui_snapshot


# Route colors on the PiTFT screen
# Route 30 = green
# Route 81 = blue
# Route 92 = red
ROUTE_DISPLAY_COLORS = {
    "30": GREEN_RGB,
    "81": (0, 120, 255),
    "92": (220, 0, 0),
}

MODES = [
    "Select a Route to Display",
    "Find a Route for Your Trip",
]

def draw_text(lcd, text, font, color, x, y, max_chars=None):
    if max_chars is not None and len(text) > max_chars:
        text = text[:max_chars - 3] + "..."

    surface = font.render(text, True, color)
    lcd.blit(surface, (x, y))


# start screen
def draw_home_screen(lcd, title_font, small_font, selected_mode_index):

    lcd.fill(BLACK)

    title_surface = title_font.render("Big Red Routes", True, WHITE_RGB)
    title_rect = title_surface.get_rect(center=(SCREEN_WIDTH // 2, 35))
    lcd.blit(title_surface, title_rect)

    draw_text(
        lcd,
        "Green button: Choose a mode",
        small_font,
        GREEN_RGB,
        65,
        70,
    )

    draw_text(
        lcd,
        "White Button: Select",
        small_font,
        WHITE_RGB,
        92,
        100,
    )

    y = 140

    for i, mode in enumerate(MODES):
        if i == selected_mode_index:
            text = f"> {mode}"
            color = YELLOW_RGB
        else:
            text = f"  {mode}"
            color = WHITE_RGB

        draw_text(
            lcd,
            text,
            small_font,
            color,
            65,
            y,
            max_chars=34,
        )

        y += 25

    pygame.display.flip()

# screen when user chooses 'Select a Route to Display'
def draw_route_selection_screen(lcd, title_font, small_font):

    lcd.fill(BLACK)

    title_surface = title_font.render("Select a Route to Display", True, WHITE_RGB)
    title_rect = title_surface.get_rect(center=(SCREEN_WIDTH // 2, 40))
    lcd.blit(title_surface, title_rect)

    draw_text(
        lcd,
        "Choose a route to show LEDs",
        small_font,
        WHITE_RGB,
        60,
        75,
    )

    draw_text(
        lcd,
        "Green Button: Route 30",
        small_font,
        ROUTE_DISPLAY_COLORS["30"],
        80,
        115,
    )

    draw_text(
        lcd,
        "Blue Button: Route 81",
        small_font,
        ROUTE_DISPLAY_COLORS["81"],
        83,
        140,
    )

    draw_text(
        lcd,
        "Red Button: Route 92",
        small_font,
        ROUTE_DISPLAY_COLORS["92"],
        87,
        165,
    )

    pygame.display.flip()


# screen for second mode
def draw_trip_finder_screen(lcd, title_font, small_font):

    lcd.fill(BLACK)

    title_surface = title_font.render("Find a Route", True, WHITE_RGB)
    title_rect = title_surface.get_rect(center=(SCREEN_WIDTH // 2, 45))
    lcd.blit(title_surface, title_rect)

    draw_text(
        lcd,
        "Select the Direction You Want To Go",
        small_font,
        WHITE_RGB,
        45,
        70,
    )

    draw_text(
        lcd,
        "Green Button: Outbound (North to South)",
        small_font,
        GREEN_RGB,
        30,
        120,
    )

    draw_text(
        lcd,
        "Red Button: Inbound (South to North)",
        small_font,
        RED_RGB,
        42,
        155,
    )

    pygame.display.flip()


# screen for picking start and end stops
def draw_trip_stop_picker_screen(
    lcd,
    title_font,
    small_font,
    direction_mode,
    picker_phase,
    stop_entries,
    selected_index,
):
    lcd.fill(BLACK)

    is_outbound = direction_mode == "outbound"
    mode = "Outbound" if is_outbound else "Inbound"
    mode_color = GREEN_RGB if is_outbound else RED_RGB

    title_surface = title_font.render(f"Find a Route: {mode}", True, WHITE_RGB)
    title_rect = title_surface.get_rect(center=(SCREEN_WIDTH // 2, 24))
    lcd.blit(title_surface, title_rect)

    prompt = "Select a starting stop" if picker_phase == "start" else "Select an end stop"
    prompt_surface = small_font.render(prompt, True, WHITE_RGB)
    prompt_rect = prompt_surface.get_rect(center=(SCREEN_WIDTH // 2, 54))
    lcd.blit(prompt_surface, prompt_rect)

    mode_hint_surface = small_font.render(
        "Green: Next stop (hold to speed up)", True, GREEN_RGB
    )
    mode_hint_rect = mode_hint_surface.get_rect(center=(SCREEN_WIDTH // 2, 72))
    lcd.blit(mode_hint_surface, mode_hint_rect)

    up_hint_surface = small_font.render(
        "Blue: Previous stop (hold to speed up)", True, ROUTE_DISPLAY_COLORS["81"]
    )
    up_hint_rect = up_hint_surface.get_rect(center=(SCREEN_WIDTH // 2, 90))
    lcd.blit(up_hint_surface, up_hint_rect)

    select_hint_surface = small_font.render("White: Select", True, WHITE_RGB)
    select_hint_rect = select_hint_surface.get_rect(center=(SCREEN_WIDTH // 2, 108))
    lcd.blit(select_hint_surface, select_hint_rect)

    if not stop_entries:
        draw_text(lcd, "No stops available.", small_font, YELLOW_RGB, 28, 150)
        pygame.display.flip()
        return

    visible_count = 5
    start_view = max(0, selected_index - 2)

    if start_view + visible_count > len(stop_entries):
        start_view = max(0, len(stop_entries) - visible_count)

    y = 132

    for i in range(start_view, min(start_view + visible_count, len(stop_entries))):
        route_id = stop_entries[i][0]
        stop_name = stop_entries[i][1]

        if i == selected_index:
            text = f"> Route {route_id}: {stop_name}"
            color = mode_color
        else:
            text = f"  Route {route_id}: {stop_name}"
            color = WHITE_RGB

        draw_text(lcd, text, small_font, color, 22, y, max_chars=44)
        y += 19

    pygame.display.flip()


# screen after start and end stops were selected
def draw_trip_selection_summary_screen(
    lcd,
    title_font,
    small_font,
    direction_mode,
    start_entry,
    end_entry,
):
    lcd.fill(BLACK)

    is_outbound = direction_mode == "outbound"
    mode = "Outbound (North to South)" if is_outbound else "Inbound (South to North)"
    mode_color = GREEN_RGB if is_outbound else RED_RGB

    title_surface = title_font.render("Trip Selected", True, WHITE_RGB)
    title_rect = title_surface.get_rect(center=(SCREEN_WIDTH // 2, 28))
    lcd.blit(title_surface, title_rect)

    mode_surface = small_font.render(f"> {mode}", True, mode_color)
    mode_rect = mode_surface.get_rect(center=(SCREEN_WIDTH // 2, 58))
    lcd.blit(mode_surface, mode_rect)

    selected_trip_surface = small_font.render(
        "Showing route for your selected trip:",
        True,
        WHITE_RGB,
    )
    selected_trip_rect = selected_trip_surface.get_rect(center=(SCREEN_WIDTH // 2, 78))
    lcd.blit(selected_trip_surface, selected_trip_rect)

    if start_entry is not None:
        draw_text(
            lcd,
            f"Start: Route {start_entry[0]}: {start_entry[1]}",
            small_font,
            WHITE_RGB,
            24,
            104,
            max_chars=46,
        )

    if end_entry is not None:
        draw_text(
            lcd,
            f"End: Route {end_entry[0]}: {end_entry[1]}",
            small_font,
            WHITE_RGB,
            24,
            133,
            max_chars=46,
        )

    home_hint_surface = small_font.render("White button: Back to home", True, WHITE_RGB)
    home_hint_rect = home_hint_surface.get_rect(center=(SCREEN_WIDTH // 2, 178))
    lcd.blit(home_hint_surface, home_hint_rect)

    pygame.display.flip()


def draw_route_bus_screen(
    lcd,
    title_font,
    small_font,
    route_id,
    route_snapshot,
    selected_bus_id,
):
    lcd.fill(BLACK)

    route_color = ROUTE_DISPLAY_COLORS.get(route_id, GREEN_RGB)

    title_surface = title_font.render(f"Route {route_id}", True, WHITE_RGB)
    title_rect = title_surface.get_rect(center=(SCREEN_WIDTH // 2, 18))
    lcd.blit(title_surface, title_rect)

    bus_ids = sorted(route_snapshot.keys())

    # Left side bus list
    draw_text(lcd, "Buses", small_font, route_color, 8, 42)

    if not bus_ids:
        draw_text(lcd, "None", small_font, YELLOW_RGB, 8, 70)

        draw_text(
            lcd,
            f"No Route {route_id} buses",
            small_font,
            YELLOW_RGB,
            95,
            100,
        )

        draw_text(
            lcd,
            "available",
            small_font,
            YELLOW_RGB,
            125,
            125,
        )

        pygame.display.flip()
        return

    y = 65

    for bus_id in bus_ids[:7]:
        if bus_id == selected_bus_id:
            draw_text(lcd, f"> {bus_id}", small_font, route_color, 8, y)
        else:
            draw_text(lcd, f"  {bus_id}", small_font, WHITE_RGB, 8, y)

        y += 22

    # Divider line
    pygame.draw.line(lcd, GRAY, (75, 40), (75, 230), 2)

    # Right side selected bus info
    details = route_snapshot.get(selected_bus_id)

    if details is None:
        draw_text(
            lcd,
            "Selected bus unavailable",
            small_font,
            YELLOW_RGB,
            90,
            90,
            28,
        )
        pygame.display.flip()
        return

    draw_text(
        lcd,
        f"Bus {selected_bus_id}",
        small_font,
        route_color,
        90,
        45,
    )

    y = 75
    line_gap = 27

    draw_text(
        lcd,
        f"Status: {details['status']}",
        small_font,
        WHITE_RGB,
        90,
        y,
        29,
    )
    y += line_gap

    draw_text(
        lcd,
        f"Last Stop: {details['last_stop']}",
        small_font,
        WHITE_RGB,
        90,
        y,
        29,
    )
    y += line_gap

    draw_text(
        lcd,
        f"Destination: {details['destination']}",
        small_font,
        WHITE_RGB,
        90,
        y,
        29,
    )
    y += line_gap

    draw_text(
        lcd,
        f"Direction: {details['direction']}",
        small_font,
        WHITE_RGB,
        90,
        y,
        29,
    )
    y += line_gap

    draw_text(
        lcd,
        f"Occupancy: {details['occupancy']}",
        small_font,
        WHITE_RGB,
        90,
        y,
        29,
    )

    pygame.display.flip()


def choose_next_bus_id(bus_ids, selected_bus_id):
    if not bus_ids:
        return None

    if selected_bus_id not in bus_ids:
        return bus_ids[0]

    current_index = bus_ids.index(selected_bus_id)
    next_index = (current_index + 1) % len(bus_ids)

    return bus_ids[next_index]


def keep_selected_bus_valid(bus_ids, selected_bus_id):
    if not bus_ids:
        return None

    if selected_bus_id not in bus_ids:
        return bus_ids[0]

    return selected_bus_id


def pitft_screen_loop(stop_event, screen_command_queue):
    os.putenv("SDL_VIDEODRIVER", "fbcon")
    os.putenv("SDL_FBDEV", "/dev/fb0")
    os.putenv("SDL_MOUSEDRV", "TSLIB")
    os.putenv("SDL_MOUSEDEV", "/dev/input/touchscreen")
    os.putenv("DISPLAY", "")

    pygame.init()

    lcd = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.mouse.set_visible(False)
    pygame.display.set_caption("Ithaca TCAT Tracker")

    title_font = pygame.font.Font(None, 30)
    small_font = pygame.font.Font(None, 19)

    current_screen = "home"
    current_route_id = None
    selected_mode_index = 0
    current_trip_direction = None
    current_trip_picker_phase = None
    current_trip_stop_entries = []
    current_trip_selected_index = 0
    current_trip_start_entry = None
    current_trip_end_entry = None

    selected_bus_by_route = {
        "30": None,
        "81": None,
        "92": None,
    }

    last_snapshot_string = ""
    last_selected_bus_id = None
    last_screen = None
    last_route_id = None
    last_mode_index = None
    last_trip_direction = None
    last_trip_picker_phase = None
    last_trip_stop_entries = None
    last_trip_selected_index = None
    last_trip_start_entry = None
    last_trip_end_entry = None
    last_redraw_time = 0

    pitft_clock = pygame.time.Clock()

    # draw start screen immediately
    draw_home_screen(lcd, title_font, small_font, selected_mode_index)

    try:
        while not stop_event.is_set():

            # keep selected bus valid if we are currently viewing a route
            if current_route_id is not None:
                current_snapshot = get_route_gui_snapshot(current_route_id)
                current_bus_ids = sorted(current_snapshot.keys())

                selected_bus_by_route[current_route_id] = keep_selected_bus_valid(
                    current_bus_ids,
                    selected_bus_by_route[current_route_id],
                )
            else:
                current_snapshot = {}
                current_bus_ids = []

            # check button commands
            try:
                command = screen_command_queue.get_nowait()

                if isinstance(command, tuple):
                    command_type, value = command

                    if command_type == "show_home":
                        current_screen = "home"
                        current_route_id = None
                        selected_mode_index = value

                        draw_home_screen(
                            lcd,
                            title_font,
                            small_font,
                            selected_mode_index,
                        )

                    elif command_type == "show_route_selection":
                        current_screen = "route_selection"
                        current_route_id = None

                        draw_route_selection_screen(
                            lcd,
                            title_font,
                            small_font,
                        )

                    elif command_type == "show_trip_finder":
                        current_screen = "trip_finder"
                        current_route_id = None
                        current_trip_direction = None
                        current_trip_picker_phase = None
                        current_trip_stop_entries = []
                        current_trip_selected_index = 0
                        current_trip_start_entry = None
                        current_trip_end_entry = None

                        draw_trip_finder_screen(
                            lcd,
                            title_font,
                            small_font,
                        )

                    elif command_type == "next_bus":
                        route_id = value

                        route_snapshot = get_route_gui_snapshot(route_id)
                        bus_ids = sorted(route_snapshot.keys())

                        # if switching to a different route, open that route
                        # and select the first bus
                        if current_route_id != route_id:
                            current_screen = "route"
                            current_route_id = route_id

                            if bus_ids:
                                selected_bus_by_route[route_id] = bus_ids[0]
                            else:
                                selected_bus_by_route[route_id] = None

                        # if already on that route, move to the next bus
                        else:
                            selected_bus_by_route[route_id] = choose_next_bus_id(
                                bus_ids,
                                selected_bus_by_route[route_id],
                            )

                        draw_route_bus_screen(
                            lcd,
                            title_font,
                            small_font,
                            route_id,
                            route_snapshot,
                            selected_bus_by_route[route_id],
                        )

                    elif command_type == "show_trip_stop_picker":
                        current_screen = "trip_stop_picker"
                        current_route_id = None

                        trip_data = value if isinstance(value, dict) else {}
                        current_trip_direction = trip_data.get("direction")
                        current_trip_picker_phase = trip_data.get("phase")
                        current_trip_stop_entries = trip_data.get("stop_entries", [])
                        current_trip_selected_index = trip_data.get("selected_index", 0)

                        draw_trip_stop_picker_screen(
                            lcd,
                            title_font,
                            small_font,
                            current_trip_direction,
                            current_trip_picker_phase,
                            current_trip_stop_entries,
                            current_trip_selected_index,
                        )

                    elif command_type == "show_trip_summary":
                        current_screen = "trip_summary"
                        current_route_id = None

                        trip_data = value if isinstance(value, dict) else {}
                        current_trip_direction = trip_data.get("direction")
                        current_trip_start_entry = trip_data.get("start_entry")
                        current_trip_end_entry = trip_data.get("end_entry")

                        draw_trip_selection_summary_screen(
                            lcd,
                            title_font,
                            small_font,
                            current_trip_direction,
                            current_trip_start_entry,
                            current_trip_end_entry,
                        )

            except queue.Empty:
                pass

            # redraw current screen periodically
            now = time.time()

            if current_route_id is not None:
                current_snapshot = get_route_gui_snapshot(current_route_id)
                current_selected_bus_id = selected_bus_by_route[current_route_id]
            else:
                current_snapshot = {}
                current_selected_bus_id = None

            snapshot_string = str(current_snapshot)

            should_redraw = (
                snapshot_string != last_snapshot_string
                or current_selected_bus_id != last_selected_bus_id
                or current_screen != last_screen
                or current_route_id != last_route_id
                or selected_mode_index != last_mode_index
                or current_trip_direction != last_trip_direction
                or current_trip_picker_phase != last_trip_picker_phase
                or current_trip_stop_entries != last_trip_stop_entries
                or current_trip_selected_index != last_trip_selected_index
                or current_trip_start_entry != last_trip_start_entry
                or current_trip_end_entry != last_trip_end_entry
                or now - last_redraw_time > 1.0
            )

            if should_redraw:
                if current_screen == "home":
                    draw_home_screen(
                        lcd,
                        title_font,
                        small_font,
                        selected_mode_index,
                    )

                elif current_screen == "route_selection":
                    draw_route_selection_screen(
                        lcd,
                        title_font,
                        small_font,
                    )

                elif current_screen == "trip_finder":
                    draw_trip_finder_screen(
                        lcd,
                        title_font,
                        small_font,
                    )

                elif current_screen == "trip_stop_picker":
                    draw_trip_stop_picker_screen(
                        lcd,
                        title_font,
                        small_font,
                        current_trip_direction,
                        current_trip_picker_phase,
                        current_trip_stop_entries,
                        current_trip_selected_index,
                    )

                elif current_screen == "trip_summary":
                    draw_trip_selection_summary_screen(
                        lcd,
                        title_font,
                        small_font,
                        current_trip_direction,
                        current_trip_start_entry,
                        current_trip_end_entry,
                    )

                elif current_screen == "route" and current_route_id is not None:
                    draw_route_bus_screen(
                        lcd,
                        title_font,
                        small_font,
                        current_route_id,
                        current_snapshot,
                        current_selected_bus_id,
                    )

                last_snapshot_string = snapshot_string
                last_selected_bus_id = current_selected_bus_id
                last_screen = current_screen
                last_route_id = current_route_id
                last_mode_index = selected_mode_index
                last_trip_direction = current_trip_direction
                last_trip_picker_phase = current_trip_picker_phase
                last_trip_stop_entries = list(current_trip_stop_entries)
                last_trip_selected_index = current_trip_selected_index
                last_trip_start_entry = current_trip_start_entry
                last_trip_end_entry = current_trip_end_entry
                last_redraw_time = now

            # keep pygame responsive
            for event in pygame.event.get():
                if event.type == QUIT:
                    stop_event.set()

            pitft_clock.tick(20)

    except KeyboardInterrupt:
        print("Exiting PiTFT screen.")

    finally:
        pygame.quit()