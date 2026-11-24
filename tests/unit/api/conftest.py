"""What the API tests share."""

from jev_trader.jobs import JobNotKilled


class StandInBuilds:
    """Dataset build jobs that exist only as notes: started ones run until stopped."""

    def __init__(self):
        self.started: list[tuple[int, str, bool]] = []
        self.running: set[int] = set()
        self.stopped: list[int] = []
        self.will_not_die = False

    def start(self, dataset_id, settings_text, check):
        self.started.append((dataset_id, settings_text, check))
        self.running.add(dataset_id)

    def is_running(self, dataset_id):
        return dataset_id in self.running

    def stop(self, dataset_id):
        if dataset_id not in self.running:
            return False
        if self.will_not_die:
            raise JobNotKilled(f"the build of dataset {dataset_id} would not die")
        self.running.remove(dataset_id)
        self.stopped.append(dataset_id)
        return True

    def settings_text(self, dataset_id):
        for started, text, _ in self.started:
            if started == dataset_id:
                return text
        return None


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
