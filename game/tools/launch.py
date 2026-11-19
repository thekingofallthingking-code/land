"""Project-local setup and bounded launch commands used by the Windows scripts."""

from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
from time import monotonic


PROJECT = Path(__file__).resolve().parents[2]
INTERACTIVE_TIMEOUT = 4 * 60 * 60
TEST_TIMEOUT = 90
PYPI = "https://pypi.org/simple"
PYTHON_CHECK = (
    "import os, sys, sysconfig; raise SystemExit(sys.version_info[:2] not in "
    "((3, 12), (3, 11)) or sys.maxsize <= 2**32 or "
    "(os.name == 'nt' and sysconfig.get_platform() != 'win-amd64'))"
)


def project_path(*parts):
    path = PROJECT.joinpath(*parts)
    if not path.resolve().is_relative_to(PROJECT):
        raise ValueError(f"Path resolves outside the Harbor City project: {path}")
    return path


def run_setup_step(label, command, deadline, environment, log):
    print(f"{label} ...", flush=True)
    log.write(f"\n{label}\n")
    log.flush()
    result = subprocess.run(
        command, cwd=PROJECT, env=environment, stdout=log, stderr=subprocess.STDOUT,
        timeout=deadline, check=False,
    )
    if result.returncode:
        raise RuntimeError(f"{label} failed with exit code {result.returncode}")


def setup():
    logs = project_path("logs")
    logs.mkdir(exist_ok=True)
    log_file = project_path("logs", "setup.log")
    with log_file.open("a", encoding="utf-8") as log:
        log.write(f"\nHarbor City setup started at {datetime.now().astimezone().isoformat()}\n")
        try:
            if (
                sys.version_info[:2] not in ((3, 12), (3, 11)) or sys.maxsize <= 2**32
                or (os.name == "nt" and sysconfig.get_platform() != "win-amd64")
            ):
                raise RuntimeError("Setup requires 64-bit Python 3.12 or 3.11")
            environment = os.environ.copy()
            environment.pop("PYTHONHOME", None)
            environment.pop("PYTHONPATH", None)
            environment["PYTHONNOUSERSITE"] = "1"
            environment["PIP_CONFIG_FILE"] = os.devnull
            scratch = project_path("logs", "setup-tmp")
            scratch.mkdir(exist_ok=True)
            for name in ("TMPDIR", "TEMP", "TMP"):
                environment[name] = str(scratch)

            venv = project_path(".venv")
            if os.name == "nt":
                python_path = project_path(".venv", "Scripts", "python.exe")
            else:
                # A standard POSIX venv can link its Python executable to the base interpreter.
                python_path = project_path(".venv", "bin") / "python"
            python = str(python_path)
            if python_path.is_file():
                try:
                    run_setup_step("Checking Python", [python, "-c", PYTHON_CHECK], 15, environment, log)
                except (OSError, RuntimeError):
                    run_setup_step(
                        "Repairing project environment", [sys.executable, "-m", "venv", "--upgrade", str(venv)],
                        120, environment, log,
                    )
                    run_setup_step("Rechecking Python", [python, "-c", PYTHON_CHECK], 15, environment, log)
            else:
                run_setup_step(
                    "Creating project environment", [sys.executable, "-m", "venv", str(venv)],
                    120, environment, log,
                )

            pip = [
                python, "-m", "pip", "--isolated", "--disable-pip-version-check", "--retries", "2",
                "--timeout", "20", "--cache-dir", str(project_path("logs", "pip-cache")),
            ]
            install = ["install", "--index-url", PYPI, "--only-binary=:all:"]
            run_setup_step("Updating pip", pip + install + ["--upgrade", "pip"], 180, environment, log)
            run_setup_step(
                "Installing pinned dependencies", pip + install + ["-r", str(project_path("requirements.txt"))],
                300, environment, log,
            )
            run_setup_step("Checking dependencies", pip + ["check"], 45, environment, log)
            run_setup_step(
                "Verifying imports",
                [python, "-c", "from panda3d.bullet import BulletWorld; import simplepbr, numpy, PIL; BulletWorld()"],
                30, environment, log,
            )
            project_path("assets_generated").mkdir(exist_ok=True)
            run_setup_step(
                "Generating procedural assets", [python, "-m", "game.tools.assets"], 60, environment, log,
            )
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
            message = f"FAIL - {error}"
            print(message, file=sys.stderr)
            log.write(message + "\n")
            return 1
        message = "PASS - Harbor City is ready. Open run.bat to play."
        print(message)
        log.write(message + "\n")
        return 0


def run_python(arguments, timeout):
    if timeout <= 0:
        print("FAIL - Harbor City exceeded its allotted time.", file=sys.stderr)
        return 124
    try:
        with subprocess.Popen([sys.executable, *arguments], cwd=PROJECT) as child:
            try:
                return child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                print(f"FAIL - Harbor City exceeded its {timeout:.1f}-second timeout.", file=sys.stderr)
                return 124
            except KeyboardInterrupt:
                return 130
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait()
    except OSError as error:
        print(f"FAIL - Launch failed: {error}", file=sys.stderr)
        return 1


def main(arguments):
    if arguments == ["setup"]:
        try:
            return setup()
        except (OSError, ValueError) as error:
            print(f"FAIL - Setup could not open its project log: {error}", file=sys.stderr)
            return 1
    if arguments and arguments[0] == "run":
        return run_python(["-m", "game", *arguments[1:]], INTERACTIVE_TIMEOUT)
    if arguments and arguments[0] == "test":
        deadline = monotonic() + TEST_TIMEOUT
        unit_status = run_python(["-m", "unittest", "discover", "-s", "tests"], 10)
        if unit_status:
            return unit_status
        return run_python(["-m", "game", "--self-test", *arguments[1:]], deadline - monotonic())
    print("Usage: launch.py {setup|run|test}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
