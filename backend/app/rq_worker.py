from __future__ import annotations

from rq import Connection, Worker

from .automation_runner import get_queue, run_automation_job


def main() -> None:
    queue = get_queue()
    with Connection(queue.connection):
        worker = Worker([queue])
        worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
