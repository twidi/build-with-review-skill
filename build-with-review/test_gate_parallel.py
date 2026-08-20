#!/usr/bin/env python3
"""Focused tests for frozen gate-command parallel execution."""
import base64
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import traceback


HERE = pathlib.Path(__file__).resolve().parent
TESTS = []


def test(function):
    TESTS.append(function)
    return function


def check(condition, message):
    if not condition:
        raise AssertionError(message)


class Fixture:
    def __init__(self):
        self.temp = pathlib.Path(tempfile.mkdtemp(prefix="bwr-gate-parallel-"))
        self.repo = self.temp / "repo"
        self.workspace = self.repo / ".superpowers" / "bwr" / "run"
        self.prompts = self.workspace / "prompts" / "construction"
        self.prompts.mkdir(parents=True)
        for name in ("gate_file.py", "gate_execution.py", "gate_report.py", "ordinary_gate.py"):
            shutil.copy2(HERE / "prompts" / "construction" / name, self.prompts / name)
        self.run("git", "init", "-q", cwd=self.repo)
        self.run("git", "config", "user.email", "test@example.invalid", cwd=self.repo)
        self.run("git", "config", "user.name", "Gate Parallel Test", cwd=self.repo)
        (self.repo / ".gitignore").write_text(".superpowers/\n", encoding="utf-8")
        (self.repo / "tracked.txt").write_text("base\n", encoding="utf-8")
        self.run("git", "add", ".gitignore", "tracked.txt", cwd=self.repo)
        self.run("git", "commit", "-q", "-m", "base", cwd=self.repo)
        self.gate = self.repo / ".superpowers" / "bwr" / "gate.md"

    def close(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def run(self, *args, cwd=None, ok=True):
        result = subprocess.run(
            list(map(str, args)), cwd=cwd or self.repo, capture_output=True, text=True,
            timeout=15,
        )
        if ok and result.returncode:
            raise AssertionError(f"command failed: {args}\n{result.stdout}\n{result.stderr}")
        if ok is False and result.returncode == 0:
            raise AssertionError(f"command unexpectedly succeeded: {args}\n{result.stdout}")
        return result

    def helper(self, *args, ok=True):
        return self.run(sys.executable, self.prompts / "gate_execution.py", *args, ok=ok)

    def gate_hash(self):
        return self.run("git", "hash-object", self.gate).stdout.strip()

    def tree(self):
        return self.run("git", "write-tree").stdout.strip()

    def publish(self, maximum, groups, evidence_paths=(".",)):
        draft = self.temp / "execution-draft.json"
        evidence = json.loads(self.helper("evidence", *evidence_paths).stdout) \
            if any(len(group) > 1 for group in groups) else []
        draft.write_text(json.dumps({
            "schema": 1,
            "gate": self.gate_hash(),
            "max_parallel": maximum,
            "compatibility_evidence": evidence,
            "compatible_groups": groups,
        }), encoding="utf-8")
        self.helper("publish", draft)

    def open_marker(self, op, scope="baseline"):
        token = json.loads(self.helper("token").stdout)
        values = {
            "op": op,
            "scope": scope,
            "owner": "parallel-test",
            "lot": "-",
            "task": "0",
            "attempt": "0",
            "head": self.run("git", "rev-parse", "HEAD").stdout.strip(),
            "base": self.run("git", "rev-parse", "HEAD").stdout.strip(),
            "tree": self.tree(),
            "gate": self.gate_hash(),
            "code": "-",
            "execution": token["token"],
        }
        marker = self.workspace / "gate-check-in-progress"
        marker.write_text("".join(f"{key} {value}\n" for key, value in values.items()), encoding="utf-8")
        return token

    def account(self, op):
        path = self.workspace / "reports" / "gate" / f"{op}.commands" / "account.json"
        return json.loads(path.read_text(encoding="utf-8"))


def py_command(path, body):
    path.write_text(body, encoding="utf-8")
    return f"{sys.executable} {path}"


@test
def absent_configuration_preserves_sequential_execution():
    fixture = Fixture()
    try:
        first_done = fixture.temp / "first-done"
        first = py_command(fixture.temp / "first.py", f"""
import pathlib, time
time.sleep(0.2)
pathlib.Path({str(first_done)!r}).write_text("done")
""")
        second = py_command(fixture.temp / "second.py", f"""
import pathlib, sys
print("exact output after sequential dependency")
raise SystemExit(0 if pathlib.Path({str(first_done)!r}).exists() else 9)
""")
        fixture.gate.write_text(f"{first}\n{second}\n", encoding="utf-8")
        token = fixture.open_marker("a" * 64)
        execution = token["execution"]
        check(execution["max_parallel"] == 1, execution)
        check(execution["compatible_groups"] == [[first], [second]], execution)
        first_run = fixture.helper("run", "a" * 64)
        repeated = fixture.helper("run", "a" * 64)
        account = fixture.account("a" * 64)
        check([item["returncode"] for item in account["commands"]] == [0, 0], account)
        expected = "exact output after sequential dependency"
        check("COMMAND 2 exit=0" in first_run.stdout and "COMMAND 2 exit=0" in repeated.stdout,
              "a lost final message did not recover the durable command result")
        output = json.loads(fixture.helper("output", "a" * 64, "2", "0", "65536").stdout)
        check(base64.b64decode(output["data"]).decode().strip() == expected and output["done"],
              "the executor did not preserve the exact independently readable output")
    finally:
        fixture.close()


@test
def compatible_group_waits_for_all_commands_and_keeps_gate_order_after_red():
    fixture = Fixture()
    try:
        ready_one = fixture.temp / "ready-one"
        ready_two = fixture.temp / "ready-two"
        second_done = fixture.temp / "second-done"
        third_done = fixture.temp / "third-done"
        first = py_command(fixture.temp / "first.py", f"""
import pathlib, time
mine = pathlib.Path({str(ready_one)!r}); other = pathlib.Path({str(ready_two)!r})
mine.write_text("ready")
for _ in range(100):
    if other.exists(): break
    time.sleep(0.01)
raise SystemExit(7 if other.exists() else 8)
""")
        second = py_command(fixture.temp / "second.py", f"""
import pathlib, time
mine = pathlib.Path({str(ready_two)!r}); other = pathlib.Path({str(ready_one)!r})
mine.write_text("ready")
for _ in range(100):
    if other.exists(): break
    time.sleep(0.01)
time.sleep(0.1)
pathlib.Path({str(second_done)!r}).write_text("done")
raise SystemExit(0 if other.exists() else 9)
""")
        third = py_command(fixture.temp / "third.py", f"""
import pathlib
pathlib.Path({str(third_done)!r}).write_text("done")
""")
        commands = [first, second, third]
        fixture.gate.write_text("\n".join(commands) + "\n", encoding="utf-8")
        fixture.publish(2, [[first, second], [third]])
        fixture.open_marker("b" * 64)
        result = fixture.helper("run", "b" * 64)
        account = fixture.account("b" * 64)
        check(second_done.exists(), "the executor returned before the active group completed")
        check(third_done.exists(), "a RED command prevented a later compatible group")
        check([item["command"] for item in account["commands"]] == commands, account)
        check([item["returncode"] for item in account["commands"]] == [7, 0, 0], account)
        check(result.stdout.index("COMMAND 1 exit=") < result.stdout.index("COMMAND 2 exit=")
              < result.stdout.index("COMMAND 3 exit="), result.stdout)
    finally:
        fixture.close()


@test
def repository_mutation_waits_for_the_active_group_then_invalidates_the_operation():
    fixture = Fixture()
    try:
        peer_done = fixture.temp / "peer-done"
        mutate = py_command(
            fixture.temp / "mutate.py",
            "import pathlib\n"
            f"pathlib.Path({str(fixture.repo / 'tracked.txt')!r}).write_text('gate side effect\\n')\n",
        )
        peer = py_command(
            fixture.temp / "peer.py",
            "import pathlib, time\n"
            "time.sleep(0.2)\n"
            f"pathlib.Path({str(peer_done)!r}).write_text('done')\n",
        )
        fixture.gate.write_text(f"{mutate}\n{peer}\n", encoding="utf-8")
        fixture.publish(2, [[mutate, peer]])
        fixture.open_marker("e" * 64)
        fixture.helper("run", "e" * 64, ok=False)
        check(peer_done.exists(), "candidate mutation hid another active command result")
        account = fixture.workspace / "reports" / "gate" / f"{'e' * 64}.commands"
        check(not account.exists(), "a mutated candidate received a complete command account")
    finally:
        fixture.close()


def wait_for(path, message):
    for _ in range(200):
        if path.exists():
            return
        time.sleep(0.01)
    raise AssertionError(message)


@test
def concurrent_same_op_callers_join_one_executor_owner():
    fixture = Fixture()
    first = second = None
    try:
        ready = fixture.temp / "owner-ready"
        release = fixture.temp / "owner-release"
        log = fixture.temp / "owner-log"
        command = py_command(
            fixture.temp / "owner.py",
            "import pathlib, time\n"
            f"ready=pathlib.Path({str(ready)!r}); release=pathlib.Path({str(release)!r})\n"
            f"log=pathlib.Path({str(log)!r})\n"
            "with log.open('a') as handle: handle.write('start\\n')\n"
            "ready.write_text('ready')\n"
            "while not release.exists(): time.sleep(0.01)\n"
            "with log.open('a') as handle: handle.write('end\\n')\n",
        )
        fixture.gate.write_text(f"{command}\n", encoding="utf-8")
        fixture.publish(1, [[command]])
        fixture.open_marker("f" * 64)
        arguments = [sys.executable, fixture.prompts / "gate_execution.py", "run", "f" * 64]
        first = subprocess.Popen(arguments, cwd=fixture.repo, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
        wait_for(ready, "executor A never entered its command")
        second = subprocess.Popen(arguments, cwd=fixture.repo, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True)
        time.sleep(0.2)
        check(log.read_text(encoding="utf-8").splitlines() == ["start"],
              "executor B overlapped the same singleton command")
        release.write_text("release", encoding="utf-8")
        first_output = first.communicate(timeout=10)
        second_output = second.communicate(timeout=10)
        check(first.returncode == 0 and second.returncode == 0,
              {"first": first_output, "second": second_output})
        check(log.read_text(encoding="utf-8").splitlines() == ["start", "end"],
              "the joined caller physically reran an accounted command")
        check(fixture.account("f" * 64)["commands"][0]["returncode"] == 0,
              "the unique owner did not publish one account")
    finally:
        for process in (first, second):
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
        fixture.close()


@test
def orphaned_wave_holds_ownership_until_its_command_exits():
    fixture = Fixture()
    first = replacement = None
    try:
        ready = fixture.temp / "orphan-ready"
        release = fixture.temp / "orphan-release"
        log = fixture.temp / "orphan-log"
        command = py_command(
            fixture.temp / "orphan.py",
            "import os, pathlib, time\n"
            f"ready=pathlib.Path({str(ready)!r}); release=pathlib.Path({str(release)!r})\n"
            f"log=pathlib.Path({str(log)!r})\n"
            "with log.open('a') as handle: handle.write(f'start {os.getpid()}\\n')\n"
            "ready.write_text('ready')\n"
            "while not release.exists(): time.sleep(0.01)\n"
            "with log.open('a') as handle: handle.write(f'end {os.getpid()}\\n')\n",
        )
        fixture.gate.write_text(f"{command}\n", encoding="utf-8")
        fixture.publish(1, [[command]])
        fixture.open_marker("1" * 64)
        arguments = [sys.executable, fixture.prompts / "gate_execution.py", "run", "1" * 64]
        first = subprocess.Popen(arguments, cwd=fixture.repo, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
        wait_for(ready, "the original executor never entered its active wave")
        first.terminate()
        first.communicate(timeout=10)
        replacement = subprocess.Popen(arguments, cwd=fixture.repo, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True)
        time.sleep(0.2)
        check(len(log.read_text(encoding="utf-8").splitlines()) == 1,
              "replacement execution overlapped the orphaned command")
        fixture.helper("idle", "1" * 64, ok=False)
        release.write_text("release", encoding="utf-8")
        replacement_output = replacement.communicate(timeout=10)
        check(replacement.returncode == 0, replacement_output)
        lines = log.read_text(encoding="utf-8").splitlines()
        check([line.split()[0] for line in lines] == ["start", "end", "start", "end"], lines)
        check(lines[0].split()[1] == lines[1].split()[1]
              and lines[2].split()[1] == lines[3].split()[1]
              and lines[0].split()[1] != lines[2].split()[1], lines)
        fixture.helper("idle", "1" * 64)
    finally:
        release = fixture.temp / "orphan-release"
        release.write_text("release", encoding="utf-8")
        for process in (first, replacement):
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
        fixture.close()


@test
def partial_wave_launch_failure_keeps_ownership_until_started_command_exits():
    fixture = Fixture()
    failed_owner = replacement = None
    try:
        ready = fixture.temp / "partial-ready"
        release = fixture.temp / "partial-release"
        log = fixture.temp / "partial-log"
        first = py_command(
            fixture.temp / "partial-first.py",
            "import pathlib, time\n"
            f"ready=pathlib.Path({str(ready)!r}); release=pathlib.Path({str(release)!r})\n"
            f"log=pathlib.Path({str(log)!r})\n"
            "with log.open('a') as handle: handle.write('start\\n')\n"
            "ready.write_text('ready')\n"
            "while not release.exists(): time.sleep(0.01)\n"
            "with log.open('a') as handle: handle.write('end\\n')\n",
        )
        second = py_command(fixture.temp / "partial-second.py", "print('second')\n")
        fixture.gate.write_text(f"{first}\n{second}\n", encoding="utf-8")
        fixture.publish(2, [[first, second]])
        fixture.open_marker("2" * 64)

        driver = fixture.temp / "partial-driver.py"
        driver.write_text(
            "import pathlib, sys\n"
            f"sys.path.insert(0, {str(fixture.prompts)!r})\n"
            "import gate_execution\n"
            "original = gate_execution.subprocess.Popen\n"
            "started = 0\n"
            "def fail_second_bash(*args, **kwargs):\n"
            "    global started\n"
            "    command = args[0] if args else kwargs.get('args')\n"
            "    if command and command[0] == 'bash':\n"
            "        started += 1\n"
            "        if started == 2:\n"
            "            raise OSError('forced second Popen failure')\n"
            "    return original(*args, **kwargs)\n"
            "gate_execution.subprocess.Popen = fail_second_bash\n"
            f"gate_execution.run_commands({'2' * 64!r})\n",
            encoding="utf-8",
        )
        failed_owner = subprocess.Popen(
            [sys.executable, driver], cwd=fixture.repo,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        wait_for(ready, "the first command never entered before the forced launch failure")
        failed_output = failed_owner.communicate(timeout=10)
        check(failed_owner.returncode != 0 and "forced second Popen failure" in failed_output[1],
              failed_output)

        arguments = [sys.executable, fixture.prompts / "gate_execution.py", "run", "2" * 64]
        replacement = subprocess.Popen(
            arguments, cwd=fixture.repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        time.sleep(0.2)
        check(log.read_text(encoding="utf-8").splitlines() == ["start"],
              "replacement execution overlapped the command from a partial wave")
        fixture.helper("idle", "2" * 64, ok=False)

        release.write_text("release", encoding="utf-8")
        replacement_output = replacement.communicate(timeout=10)
        check(replacement.returncode == 0, replacement_output)
        check(log.read_text(encoding="utf-8").splitlines() == ["start", "end", "start", "end"],
              "replacement did not wait for the inherited owner before rerunning the wave")
        check(len(fixture.account("2" * 64)["commands"]) == 2,
              "replacement did not publish one complete canonical account")
    finally:
        release = fixture.temp / "partial-release"
        release.write_text("release", encoding="utf-8")
        for process in (failed_owner, replacement):
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
        fixture.close()


@test
def frozen_marker_does_not_adopt_a_later_configuration():
    fixture = Fixture()
    try:
        ready_one = fixture.temp / "frozen-one"
        ready_two = fixture.temp / "frozen-two"
        first = py_command(fixture.temp / "frozen-first.py", f"""
import pathlib, time
mine = pathlib.Path({str(ready_one)!r}); other = pathlib.Path({str(ready_two)!r})
mine.write_text("ready")
for _ in range(100):
    if other.exists(): break
    time.sleep(0.01)
raise SystemExit(0 if other.exists() else 8)
""")
        second = py_command(fixture.temp / "frozen-second.py", f"""
import pathlib, time
mine = pathlib.Path({str(ready_two)!r}); other = pathlib.Path({str(ready_one)!r})
mine.write_text("ready")
for _ in range(100):
    if other.exists(): break
    time.sleep(0.01)
raise SystemExit(0 if other.exists() else 9)
""")
        fixture.gate.write_text(f"{first}\n{second}\n", encoding="utf-8")
        fixture.publish(2, [[first, second]])
        frozen = fixture.open_marker("c" * 64)
        replacement = fixture.temp / "replacement.json"
        replacement.write_text(json.dumps({
            "schema": 1, "gate": fixture.gate_hash(), "max_parallel": 1,
            "compatible_groups": [[first], [second]],
        }), encoding="utf-8")
        fixture.helper("publish", replacement, ok=False)
        (fixture.workspace / "gate-execution.json").write_text(
            replacement.read_text(encoding="utf-8"), encoding="utf-8",
        )
        fixture.helper("run", "c" * 64)
        account = fixture.account("c" * 64)
        check(account["execution"] == frozen["sha256"], account)
        check([item["returncode"] for item in account["commands"]] == [0, 0], account)
    finally:
        fixture.close()


@test
def publication_rejects_stale_or_incomplete_command_partitions():
    fixture = Fixture()
    try:
        commands = ["true", "false"]
        fixture.gate.write_text("\n".join(commands) + "\n", encoding="utf-8")
        stale = fixture.temp / "stale.json"
        stale.write_text(json.dumps({
            "schema": 1, "gate": "0" * 40, "max_parallel": 2,
            "compatible_groups": [commands],
        }), encoding="utf-8")
        fixture.helper("publish", stale, ok=False)
        incomplete = fixture.temp / "incomplete.json"
        incomplete.write_text(json.dumps({
            "schema": 1, "gate": fixture.gate_hash(), "max_parallel": 2,
            "compatible_groups": [[commands[0]]],
        }), encoding="utf-8")
        fixture.helper("publish", incomplete, ok=False)
        check(not (fixture.workspace / "gate-execution.json").exists(),
              "an invalid schedule became workspace authority")
    finally:
        fixture.close()


@test
def changed_gate_requires_a_replacement_schedule_or_explicit_sequential_default():
    fixture = Fixture()
    try:
        original = ["true", "printf original"]
        replacement = ["true", "printf replacement"]
        fixture.gate.write_text("\n".join(original) + "\n", encoding="utf-8")
        fixture.publish(2, [original])

        fixture.gate.write_text("\n".join(replacement) + "\n", encoding="utf-8")
        fixture.helper("token", ok=False)
        fixture.helper("remove")
        settled = json.loads(fixture.helper("token").stdout)["execution"]
        check(settled["max_parallel"] == 1, settled)
        check(settled["compatible_groups"] == [[command] for command in replacement], settled)
        check(settled["compatibility_evidence"] == [], settled)
    finally:
        fixture.close()


@test
def changed_compatibility_evidence_refuses_before_any_gate_command():
    fixture = Fixture()
    try:
        definition = fixture.repo / "gate-definition.txt"
        definition.write_text("separate resources\n", encoding="utf-8")
        fixture.run("git", "add", "gate-definition.txt")
        fixture.run("git", "commit", "-q", "-m", "add gate definition")
        started = fixture.temp / "evidence-started"
        commands = [
            f"printf first >> {started}",
            f"printf second >> {started}",
        ]
        fixture.gate.write_text("\n".join(commands) + "\n", encoding="utf-8")
        fixture.publish(2, [commands], evidence_paths=("gate-definition.txt",))

        definition.write_text("shared cache\n", encoding="utf-8")
        fixture.run("git", "add", "gate-definition.txt")
        refusal = fixture.helper("token", ok=False)
        check("project evidence for parallel gate compatibility changed: gate-definition.txt"
              in refusal.stderr,
              refusal.stderr)
        check(not started.exists(), "a stale parallel schedule ran before revalidation")

        fixture.helper("remove")
        settled = json.loads(fixture.helper("token").stdout)["execution"]
        check(settled["max_parallel"] == 1
              and settled["compatible_groups"] == [[command] for command in commands], settled)
    finally:
        fixture.close()


@test
def large_outputs_have_bounded_independent_chunk_and_metadata_reads():
    fixture = Fixture()
    try:
        size = 8 * 1024 * 1024
        commands = [
            py_command(fixture.temp / "large-one.py", f"import sys\nsys.stdout.buffer.write(b'A' * {size})\n"),
            py_command(fixture.temp / "large-two.py", f"import sys\nsys.stdout.buffer.write(b'B' * {size})\n"),
        ]
        fixture.gate.write_text("\n".join(commands) + "\n", encoding="utf-8")
        fixture.publish(2, [commands])
        op = "3" * 64
        fixture.open_marker(op)
        fixture.helper("run", op)

        account_dir = fixture.workspace / "reports" / "gate" / f"{op}.commands"
        manifest = account_dir / "account.json"
        check(manifest.stat().st_size < 32_768,
              "the canonical manifest still materializes complete raw outputs")
        check((account_dir / "1.output").stat().st_size == size
              and (account_dir / "2.output").stat().st_size == size,
              "the two exact raw outputs are not independently durable")

        driver = fixture.temp / "bounded-reader.py"
        driver.write_text(
            "import contextlib, io, json, os, sys\n"
            f"sys.path.insert(0, {str(fixture.prompts)!r})\n"
            "import gate_execution\n"
            "original_open = gate_execution.os.open\n"
            "original_pread = gate_execution.os.pread\n"
            "opened = []\n"
            "read_bytes = 0\n"
            "def measured_open(path, *args, **kwargs):\n"
            "    if str(path).endswith('.output'): opened.append(str(path))\n"
            "    return original_open(path, *args, **kwargs)\n"
            "def measured_pread(descriptor, length, offset):\n"
            "    global read_bytes\n"
            "    read_bytes += length\n"
            "    return original_pread(descriptor, length, offset)\n"
            "gate_execution.os.open = measured_open\n"
            "gate_execution.os.pread = measured_pread\n"
            "sink = io.StringIO()\n"
            "with contextlib.redirect_stdout(sink):\n"
            f"    gate_execution.output_chunk({op!r}, '1', '0', '1')\n"
            "chunk_reads = read_bytes\n"
            "chunk_opened = list(opened)\n"
            "opened.clear(); read_bytes = 0\n"
            "with contextlib.redirect_stdout(sink):\n"
            f"    gate_execution.result_item({op!r}, '2')\n"
            "print(json.dumps({'chunk_reads': chunk_reads, 'chunk_opened': chunk_opened, "
            "'result_reads': read_bytes, 'result_opened': opened}))\n",
            encoding="utf-8",
        )
        measured = json.loads(fixture.run(sys.executable, driver).stdout)
        check(measured["chunk_reads"] <= 65_536, measured)
        check(len(measured["chunk_opened"]) == 1
              and measured["chunk_opened"][0].endswith("/1.output"), measured)
        check(measured["result_reads"] == 0 and measured["result_opened"] == [], measured)

        first_output = account_dir / "1.output"
        with first_output.open("r+b") as handle:
            handle.seek(0)
            handle.write(b"Z")
        fixture.helper("output", op, "1", "0", "1", ok=False)
        first_output.write_bytes(b"A" * size)

        second_output = account_dir / "2.output"
        swap = account_dir / "swap.output"
        first_output.rename(swap)
        second_output.rename(first_output)
        swap.rename(second_output)
        fixture.helper("output", op, "1", "0", "1", ok=False)
        first_output.rename(swap)
        second_output.rename(first_output)
        swap.rename(second_output)

        with first_output.open("r+b") as handle:
            handle.truncate(size - 1)
        fixture.helper("result", op, "1", ok=False)
        first_output.write_bytes(b"A" * size)

        second_output.unlink()
        fixture.helper("result", op, "2", ok=False)
        second_output.write_bytes(b"B" * size)

        foreign = account_dir / "foreign.output"
        foreign.write_bytes(b"foreign")
        fixture.helper("inspect", op, ok=False)
        foreign.unlink()

        second_output.unlink()
        external = fixture.temp / "external-output"
        external.write_bytes(b"B" * size)
        second_output.symlink_to(external)
        fixture.helper("result", op, "2", ok=False)
        check(external.read_bytes()[:1] == b"B", "an aliased output target was changed")
    finally:
        fixture.close()


@test
def ordinary_gate_and_report_auditor_consume_the_same_frozen_account():
    fixture = Fixture()
    try:
        ready_one = fixture.temp / "ordinary-one"
        ready_two = fixture.temp / "ordinary-two"
        first = py_command(fixture.temp / "ordinary-first.py", f"""
import pathlib, time
mine = pathlib.Path({str(ready_one)!r}); other = pathlib.Path({str(ready_two)!r})
mine.write_text("ready")
for _ in range(100):
    if other.exists(): break
    time.sleep(0.01)
raise SystemExit(0 if other.exists() else 8)
""")
        second = py_command(fixture.temp / "ordinary-second.py", f"""
import pathlib, time
mine = pathlib.Path({str(ready_two)!r}); other = pathlib.Path({str(ready_one)!r})
mine.write_text("ready")
for _ in range(100):
    if other.exists(): break
    time.sleep(0.01)
raise SystemExit(0 if other.exists() else 9)
""")
        fixture.gate.write_text(f"{first}\n{second}\n", encoding="utf-8")
        fixture.publish(2, [[first, second]])
        token = fixture.open_marker("d" * 64, scope="review")
        ordinary = fixture.run(
            sys.executable, fixture.prompts / "ordinary_gate.py", "d" * 64,
        )
        check("ORDINARY GATE REPORT" in ordinary.stdout, ordinary.stdout)
        report_path = fixture.workspace / "reports" / "gate" / f"{'d' * 64}.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        check(report["execution"] == token["execution"], report)
        check(report["command_account_sha256"], report)
        audited = fixture.run(
            sys.executable, fixture.prompts / "gate_report.py", "d" * 64,
            fixture.gate_hash(), fixture.tree(), token["sha256"],
        )
        outcome = json.loads(audited.stdout)
        check(outcome["green"] is True and outcome["commands"] == 2, outcome)

        report["commands"][0]["status"] = "red"
        report_path.write_text(json.dumps(report), encoding="utf-8")
        fixture.run(
            sys.executable, fixture.prompts / "gate_report.py", "d" * 64,
            fixture.gate_hash(), fixture.tree(), token["sha256"], ok=False,
        )
    finally:
        fixture.close()


@test
def controller_and_runner_contracts_share_one_bounded_schedule():
    def contract(path):
        return " ".join(path.read_text(encoding="utf-8").split())

    mode = contract(HERE / "prompts" / "construction" / "MODE.md")
    runner = contract(HERE / "prompts" / "construction" / "gate-runner.md")
    implementer = contract(HERE / "prompts" / "construction" / "implementer.md")
    skill = contract(HERE / "SKILL.md")
    for required in (
        "Maximum parallel gate commands?",
        "2 (recommended)",
        "proven-absent config means strict sequential execution",
        "project evidence establishes",
        "gate_execution.py evidence",
        "Gate execution drift",
        "Before you release the implementer",
        "remove the stale config",
        "An existing run whose C0 already finished adopts this feature between logical gate",
    ):
        check(required in mode, f"construction mode lost gate scheduling rule: {required}")
    for required in (
        "gate_execution.py run <op>",
        "Never accept a copied command list or improvise an execution schedule",
        "continues after a RED command",
        "Before it starts any gate command",
        "compatibility evidence against the exact candidate tree",
        "One op has one executor owner",
        "active commands retain ownership until all of them exit",
        "gate_execution.py inspect <op>",
        "gate_execution.py result <op> <item-number>",
        "gate_execution.py output",
        "length-at-most-65536",
        "inspect` and `result` read no raw output bytes",
        "never materializes that complete output or another command's output",
        "command_account_sha256",
    ):
        check(required in runner, f"gate runner lost frozen execution rule: {required}")
    check("same executor used by the ordinary gate" in implementer,
          "the final gate no longer shares the ordinary-gate executor")
    check("replacement schedule or the explicit sequential default" in implementer,
          "task gate drift can release the implementer with a stale schedule")
    check("no gate command has run" in implementer and "Gate execution drift" in implementer,
          "the implementer can misclassify stale compatibility before execution")
    check("orphaned active command retains that lock" in mode,
          "construction resume can overlap an orphaned active wave")
    check("human-approved ordered compatibility partition" in skill,
          "the root skill lost the workspace gate-execution contract")


def main():
    failures = 0
    for function in TESTS:
        try:
            function()
        except Exception:
            failures += 1
            print(f"FAIL {function.__name__}", file=sys.stderr)
            traceback.print_exc()
    if failures:
        raise SystemExit(1)
    print(f"all {len(TESTS)} gate-parallel tests passed")


if __name__ == "__main__":
    main()
