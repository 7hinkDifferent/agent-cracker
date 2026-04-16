from __future__ import annotations

"""Multi-backend terminal abstraction for the Hermes demo."""

import subprocess
from dataclasses import dataclass
from typing import Protocol


@dataclass
class CommandResult:
    backend: str
    command: str
    output: str


class TerminalBackend(Protocol):
    name: str

    def run(self, command: str) -> CommandResult:
        ...


class LocalBackend:
    name = "local"

    def run(self, command: str) -> CommandResult:
        proc = subprocess.run(command, shell=True, capture_output=True, text=True, check=False)
        output = proc.stdout.strip() or proc.stderr.strip() or f"exit={proc.returncode}"
        return CommandResult(self.name, command, output)


class MockRemoteBackend:
    def __init__(self, name: str, transport: str):
        self.name = name
        self.transport = transport

    def run(self, command: str) -> CommandResult:
        return CommandResult(
            self.name,
            command,
            f"[{self.transport}] executed `{command}` in an isolated workspace",
        )


class TerminalManager:
    """Expose multiple backends behind the same `run()` API."""

    def __init__(self):
        self.backends = {
            "local": LocalBackend(),
            "docker": MockRemoteBackend("docker", "container"),
            "ssh": MockRemoteBackend("ssh", "remote-host"),
            "modal": MockRemoteBackend("modal", "serverless-sandbox"),
            "daytona": MockRemoteBackend("daytona", "cloud-dev-environment"),
            "singularity": MockRemoteBackend("singularity", "hpc-container"),
        }

    def run(self, backend: str, command: str) -> CommandResult:
        runner = self.backends[backend]
        return runner.run(command)
