import sys
import types
import threading

# Here be the shared variables and pub/sub for the telemetry stream
class SharedVarsModule(types.ModuleType):
    def __init__(self, name):
        super().__init__(name)
        super().__setattr__("_lock", threading.Lock())
        super().__setattr__("_listeners", [])
        super().__setattr__("latest_car_id", "blue_445")
        super().__setattr__("DBPATH", "BaseStation/EVGPTelemetry.sqlite")
        super().__setattr__("data_blue_445", [None] * 21)
        super().__setattr__("data_red_111", [None] * 21)
        super().__setattr__("data", [None] * 21)

    def add_listener(self, listener):
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def remove_listener(self, listener):
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def notify_listeners(self, car_id, data):
        with self._lock:
            listeners = list(self._listeners)
        for fn in listeners:
            try:
                fn(car_id, data)
            except Exception as e:
                print("Telemetry listener error:", e)

    def broadcast_data(self, car_id, data):
        if car_id == "blue_445":
            self.data_blue_445 = data
        elif car_id == "red_111":
            self.data_red_111 = data
        else:
            self.data = data

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if hasattr(self, "_lock") and name in ("data_blue_445", "data_red_111", "data"):
            car_id = "blue_445" if name == "data_blue_445" else ("red_111" if name == "data_red_111" else getattr(self, "latest_car_id", "blue_445"))
            super().__setattr__("latest_car_id", car_id)
            if name != "data":
                super().__setattr__("data", value)
            self.notify_listeners(car_id, value)

sys.modules[__name__] = SharedVarsModule(__name__)
