"""What the API tests share."""


class StandInLauncher:
    """Jobs that exist only as marks: started ones run until stopped, or until `hang` is cleared."""

    def __init__(self):
        self.started: list[int] = []
        self.running: set[str] = set()
        self.killed: list[str] = []

    def start(self, sim_id):
        self.started.append(sim_id)
        mark = f"pid {1000 + len(self.started)} started {len(self.started)}.0"
        self.running.add(mark)
        return mark

    def is_running(self, running_on):
        return running_on in self.running

    def stop(self, running_on):
        if running_on not in self.running:
            return False
        self.running.remove(running_on)
        self.killed.append(running_on)
        return True
