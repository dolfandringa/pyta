import abc
import asyncio
import logging
import pyxhook
from pathlib import Path
import sys
from typing import Callable
import pandas as pd
from collections import deque


def get_data_file() -> Path:
    """Get the file to store the pandas dataframes."""
    home = Path.home()
    system_paths = {
        "win32": home / "AppData/Roaming",
        "linux": home / ".local/share",
        "darwin": home / "Library/Application Support",
    }

    if sys.platform not in system_paths:
        raise SystemError(
            f"Unknown System Platform: {sys.platform}. "
            f"Only supports {', '.join(list(system_paths.keys()))}"
        )
    data_dir = system_paths[sys.platform] / "pyta"
    return data_dir / "data_file.hdf"


def get_data(file: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Open the frequency map and distances data frames."""
    if not file.parent.exists():
        file.parent.mkdir()
    if not file.exists():
        frequency_map = pd.DataFrame(data={"key": ["a"], "count": [0]}).set_index("key")
        distances = pd.DataFrame(
            data={"key": ["a"], "previous": ["b"], "count": [0]}
        ).set_index(["key", "previous"])
        frequency_map.to_hdf(file, key="frequency_map")
        distances.to_hdf(file, key="distances")
    else:
        frequency_map: pd.DataFrame = pd.read_hdf(
            file, key="frequency_map"
        )  # type:ignore
        distances: pd.DataFrame = pd.read_hdf(file, key="distances")  # type: ignore
    return frequency_map, distances


def save_data(file: Path, frequency_map: pd.DataFrame, distances: pd.DataFrame):
    """Save the dataframes to files."""
    print("Saving file")
    distances.to_hdf(file, key="distances")
    frequency_map.to_hdf(file, key="frequency_map")


class BaseKeyLogger:
    def __init__(self):
        self.callbacks: list[Callable] = []

    def register_callback(self, callback: Callable):
        """Register a keypress event callback"""
        self.callbacks.append(callback)

    def handle_keypress(self, key):
        """Handle the keypress events."""
        for cb in self.callbacks:
            cb(key)

    @abc.abstractmethod
    def start(self):
        ...

    @abc.abstractmethod
    def stop(self):
        ...


class LinuxKeyLogger(BaseKeyLogger):
    def __init__(self):
        super().__init__()
        self.hm = pyxhook.HookManager()
        self.hm.KeyDown = self.handle_keypress  # type: ignore
        self.hm.HookKeyboard()
        self.log = logging.getLogger(__name__)
        self.log.setLevel(logging.DEBUG)

    def handle_keypress(self, event):
        """Handle pyxhook events."""
        self.log.debug("\nEvent handled:\n%s", event)
        super().handle_keypress(event.Key)

    def start(self):
        """Start handling the keypresses."""
        self.hm.start()

    def stop(self):
        """Stop handling keypresses."""
        self.hm.cancel()


class Pyta:
    """Main Pyta application which records and stores key stroke statistics."""

    def __init__(self):
        self.data_file = get_data_file()
        self.frequency_map, self.distances = get_data(self.data_file)
        self.key_buffer = deque(maxlen=2)
        self.log = logging.getLogger(__name__)
        main_logger = logging.getLogger("pyta")
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)
        main_logger.setLevel(logging.DEBUG)
        main_logger.addHandler(handler)
        self.key_logger = LinuxKeyLogger()
        self.key_logger.register_callback(self.log_keystroke)
        self.save_loop: asyncio.Task | None = None
        self.loop: asyncio.AbstractEventLoop | None = None

    async def start_save_loop(self):
        """Save files periodically."""
        try:
            await asyncio.sleep(10)
            save_data(self.data_file, self.distances, self.frequency_map)
            await self.start_save_loop()
        finally:
            save_data(self.data_file, self.frequency_map, self.distances)

    def start(self):
        """Start keylogging."""
        print("starting")
        self.loop = asyncio.get_event_loop()
        self.key_logger.start()
        self.save_loop = asyncio.ensure_future(self.start_save_loop())
        try:
            self.loop.run_forever()
        except KeyboardInterrupt:
            self.cancel()
            save_data(self.data_file, self.frequency_map, self.distances)

    def cancel(self):
        """Stop keylogging."""
        print("stopping")
        self.key_logger.stop()
        if self.save_loop is not None:
            self.save_loop.cancel()

    def log_keystroke(self, key):
        """Log a keystroke."""
        self.log.debug("Key pressed %s", key)
        if key not in self.frequency_map.index:
            self.frequency_map.loc[key] = {"count": 0}
        self.frequency_map.loc[key]["count"] += 1
        if len(self.key_buffer) > 0:
            previous = self.key_buffer[0]
            if (key, previous) not in self.distances.index:
                self.distances.loc[(key, previous), :] = {
                    "count": 1,
                }
            else:
                self.distances.loc[(key, previous), "count"] += 1

        self.key_buffer.appendleft(key)


def main():
    """Start the application"""
    app = Pyta()
    app.start()
