import threading
from rgbmatrix import RGBMatrix, RGBMatrixOptions

from config import *

# rgbmatrix for fast refreshing in the background
class BusLEDMatrix:

    def __init__(self, rows=HEIGHT, cols=WIDTH, brightness=80, gpio_slowdown=4):
        options = RGBMatrixOptions()
        options.rows = rows
        options.cols = cols
        options.chain_length = 1
        options.parallel = 1

        options.hardware_mapping = "adafruit-hat"

        options.brightness = brightness
        options.gpio_slowdown = gpio_slowdown
        options.pwm_bits = 11
        options.led_rgb_sequence = "RGB"

        options.drop_privileges = False

        self.matrix = RGBMatrix(options=options)
        self.canvas = self.matrix.CreateFrameCanvas()
        self.active_pixels = {}
        self.lock = threading.Lock()

    # converts color to rgb tuple
    def color_tuple(self, color):
        if color == RED:
            return (255, 0, 0)
        if color == GREEN:
            return (0, 255, 0)
        if color == YELLOW:
            return (255, 255, 0)
        if color == BLUE:
            return (0, 0, 255)
        if color == MAGENTA:
            return (255, 0, 255)
        if color == CYAN:
            return (0, 255, 255)
        if color == WHITE:
            return (255, 255, 255)
        return (0, 0, 0)

    # clears the matrix
    def clear(self):
        with self.lock:
            self.active_pixels.clear()
            self.canvas.Clear()
            self.canvas = self.matrix.SwapOnVSync(self.canvas)

    # sets a pixel to a color
    def set_pixel(self, x, y, color):
        if not (0 <= x < WIDTH and 0 <= y < HEIGHT):
            return

        with self.lock:
            if color == OFF:
                self.active_pixels.pop((x, y), None)
            else:
                self.active_pixels[(x, y)] = color

            self.redraw_locked()

    # redraws the matrix
    def redraw_locked(self):
        self.canvas.Clear()

        for (x, y), color in self.active_pixels.items():
            r, g, b = self.color_tuple(color)
            self.canvas.SetPixel(x, y, r, g, b)

        self.canvas = self.matrix.SwapOnVSync(self.canvas)