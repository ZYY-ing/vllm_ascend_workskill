#!/usr/bin/env python3
"""Distribute TCP connections over loopback SSH proxy forwards (Python 3.10+)."""

import argparse
import asyncio
import itertools
import json
import time
from pathlib import Path


def port(value):
    number = int(value)
    if not 1 <= number <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return number


class ProxyPool:
    def __init__(self, ports, status_file=None):
        self.ports = ports
        self.cycle = itertools.cycle(range(len(ports)))
        self.status_file = Path(status_file) if status_file else None
        self.state = dict(
            started=time.time(), download_bytes=0, upload_bytes=0,
            connections=0, active=0, errors=0, upstream_ports=ports,
        )

    async def connect(self):
        first = next(self.cycle)
        for offset in range(len(self.ports)):
            try:
                return await asyncio.wait_for(
                    asyncio.open_connection(
                        "127.0.0.1", self.ports[(first + offset) % len(self.ports)],
                        limit=524288,
                    ), timeout=5,
                )
            except (OSError, asyncio.TimeoutError):
                continue
        raise ConnectionError("No reachable SSH forward")

    async def handle(self, reader, writer):
        remote_writer = None
        tasks = []
        counted = False
        try:
            remote_reader, remote_writer = await self.connect()
            self.state["connections"] += 1
            self.state["active"] += 1
            counted = True

            async def pipe(source, destination, counter):
                while data := await source.read(262144):
                    destination.write(data)
                    await destination.drain()
                    self.state[counter] += len(data)

            tasks = [
                asyncio.create_task(pipe(reader, remote_writer, "upload_bytes")),
                asyncio.create_task(pipe(remote_reader, writer, "download_bytes")),
            ]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except (OSError, asyncio.TimeoutError):
            self.state["errors"] += 1
        finally:
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            if counted:
                self.state["active"] -= 1
            writer.close()
            if remote_writer:
                remote_writer.close()
            await asyncio.gather(
                writer.wait_closed(),
                *([remote_writer.wait_closed()] if remote_writer else []),
                return_exceptions=True,
            )

    async def report(self):
        last_bytes = 0
        last_time = time.monotonic()
        if self.status_file:
            self.status_file.parent.mkdir(parents=True, exist_ok=True)
        while True:
            now = time.monotonic()
            count = self.state["download_bytes"]
            self.state.update(
                updated=time.time(),
                MBps=round((count - last_bytes) / max(0.001, now - last_time) / 1e6, 3),
            )
            last_bytes, last_time = count, now
            payload = json.dumps(self.state, indent=2)
            if self.status_file:
                temporary = self.status_file.with_name(self.status_file.name + ".tmp")
                temporary.write_text(payload, encoding="utf-8")
                temporary.replace(self.status_file)
            else:
                print(payload, flush=True)
            await asyncio.sleep(10)


async def run(args):
    if args.listen_port in args.upstream_ports:
        raise ValueError("listen port cannot also be an upstream port")
    pool = ProxyPool(args.upstream_ports, args.status_file)
    server = await asyncio.start_server(
        pool.handle, "127.0.0.1", args.listen_port, limit=524288,
    )
    async with server:
        await asyncio.gather(server.serve_forever(), pool.report())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen-port", type=port, required=True)
    parser.add_argument("--upstream-ports", type=port, nargs="+", required=True)
    parser.add_argument("--status-file")
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
