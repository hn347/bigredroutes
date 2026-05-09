import queue
import subprocess
import threading
import time

# handle audio announcements in separate thread
class AudioAnnouncer:

    def __init__(self, enabled=True, voice="en-us+f3", speed=100, volume=140):
        self.enabled = enabled 
        self.voice = voice
        self.speed = speed
        self.volume = volume

        self.stop_event = threading.Event()
        self.message_queue = queue.Queue()

        # create background audio thread
        self.thread = threading.Thread(
            target=self._audio_loop,
            daemon=True,
        )

        self.thread.start()

    # add message to audio queue
    def announce(self, message):
        if not self.enabled:
            return

        if not message:
            return

        self.message_queue.put(message)

    # creates a bus arrival message
    def announce_bus_arrival(self, route_id, bus_id, stop_name, direction):
        message = (
            f"Route {route_id}, bus {bus_id}. "
            f"Arrived at {stop_name}. "
            f"Going in the {direction} direction."
        )

        self.announce(message)

    # speak messages one at a time
    def _audio_loop(self):
        while not self.stop_event.is_set():
            try:
                # wait for next message in queue
                message = self.message_queue.get(timeout=0.2)
            except queue.Empty:
                # continue to check queue if no message available
                continue

            try:
                espeak_voice = self.voice if self.voice else "en-us+f3"
                espeak_speed = str(int(self.speed))
                # keep volume between 0 and 200 and convert to str
                espeak_volume = str(int(max(0.0, min(200.0, float(self.volume)))))

                subprocess.run(
                    [
                        "espeak",
                        "-v", espeak_voice,
                        "-s", espeak_speed,
                        "-a", espeak_volume,
                        message,
                    ],
                    check=False,
                )
            except Exception:
                pass

            # for time between announcements
            time.sleep(0.1)


    # stops audio thread
    def stop(self):
        self.stop_event.set()
        self.message_queue.put("")
        self.thread.join(timeout=1.0)


    # enable or disable future announcements
    def set_enabled(self, enabled, clear_queue=False):
        self.enabled = bool(enabled)

        if clear_queue and not self.enabled:
            while True:
                try:
                    self.message_queue.get_nowait()
                except queue.Empty:
                    break


# main function to test file
if __name__ == "__main__":
    announcer = AudioAnnouncer(enabled=True)

    announcer.announce_bus_arrival(
        route_id="30",
        bus_id="1234",
        stop_name="Carpenter Hall",
        direction="Ithaca Mall",
    )

    time.sleep(5)
    announcer.stop()