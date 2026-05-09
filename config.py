import os

# ------------------------
# tcat urls
# ------------------------

# gives live bus positions
VEHICLES_URL = "https://realtimetcatbus.availtec.com/InfoPoint/GTFS-Realtime.ashx?&Type=VehiclePosition&serverid=0"

# gives route + direction info
GTFS_STATIC_ZIP_URL = "https://s3.amazonaws.com/tcat-gtfs/tcat-ny-us.zip"

# stop list for each bus route
ROUTE_30_STOPS_URL = "https://realtimetcatbus.availtec.com/InfoPoint/Minimal/Stops/ForRoute?routeId=30"
ROUTE_81_STOPS_URL = "https://realtimetcatbus.availtec.com/InfoPoint/Minimal/Stops/ForRoute?routeId=81"
ROUTE_92_STOPS_URL = "https://realtimetcatbus.availtec.com/InfoPoint/Minimal/Stops/ForRoute?routeId=92"

# how often we scrape the TCAT API for bus data
POLL_SECONDS = 10
# routes we are tracking
TARGET_ROUTES = ("30", "81", "92")

# route 92 recorded data
ROUTE_92_RECORDED_DATA = True

ROUTE_92_RECORDED_DATA_FILE = os.path.join(
    os.path.dirname(__file__),
    "route92_recorded_data.jsonl",
)
# ------------------------
# led matrix settings
# ------------------------

WIDTH = 32
HEIGHT = 16

OFF = 0
RED = 1
GREEN = 2
YELLOW = 3
BLUE = 4
MAGENTA = 5
CYAN = 6
WHITE = 7

# ------------------------
# PiTFT settings
# ------------------------

SCREEN_WIDTH = 320
SCREEN_HEIGHT = 240

BLACK = (0, 0, 0)
WHITE_RGB = (255, 255, 255)
GRAY = (80, 80, 80)
LIGHT_GRAY = (160, 160, 160)
GREEN_RGB = (0, 200, 0)
RED_RGB = (200, 0, 0)
YELLOW_RGB = (220, 220, 0)