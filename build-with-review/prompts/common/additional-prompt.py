#!/usr/bin/env python3
"""Read and mutate one workspace-owned additional prompt without following aliases."""

import os
import secrets
import stat
import sys


NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
DIRECTORY = getattr(os, "O_DIRECTORY", 0)


def fail(message):
    print(f"**additional-prompt ERROR** · {message}", file=sys.stderr)
    raise SystemExit(1)


def exact_absolute_path(value, subject):
    if not os.path.isabs(value) or os.path.normpath(value) != value:
        fail(f"{subject} must be one exact absolute path: {value}")


def open_real_directory(parent_fd, name, subject):
    try:
        state = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(state.st_mode):
        fail(f"{subject} is a symlink: {name}")
    if not stat.S_ISDIR(state.st_mode):
        fail(f"{subject} is not one real directory: {name}")
    try:
        descriptor = os.open(name, os.O_RDONLY | DIRECTORY | NOFOLLOW, dir_fd=parent_fd)
    except OSError as error:
        fail(f"{subject} changed identity before use: {name}: {error}")
    if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        fail(f"{subject} is not one real directory: {name}")
    return descriptor


def open_directory_path(root_fd, parts, subject, *, create, absent_ok):
    descriptor = os.dup(root_fd)
    try:
        for part in parts:
            child = open_real_directory(descriptor, part, subject)
            if child is None:
                if absent_ok:
                    os.close(descriptor)
                    return None
                if not create:
                    fail(f"{subject} is absent: {part}")
                try:
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
                except OSError as error:
                    fail(f"could not create {subject}: {part}: {error}")
                child = open_real_directory(descriptor, part, subject)
                if child is None:
                    fail(f"{subject} disappeared after creation: {part}")
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def regular_leaf_state(parent_fd, leaf, subject):
    try:
        state = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(state.st_mode):
        fail(f"{subject} is a symlink: {leaf}")
    if not stat.S_ISREG(state.st_mode):
        fail(f"{subject} is not one real regular file: {leaf}")
    return state


def copy_bytes(source_fd, destination_fd):
    while True:
        payload = os.read(source_fd, 65536)
        if not payload:
            return
        offset = 0
        while offset < len(payload):
            written = os.write(destination_fd, payload[offset:])
            if written <= 0:
                fail("the additional-prompt temporary received a short write")
            offset += written


def open_workspace(workspace):
    exact_absolute_path(workspace, "workspace")
    if os.path.realpath(workspace) != workspace:
        fail(f"workspace resolves through an alias: {workspace}")
    try:
        workspace_state = os.stat(workspace, follow_symlinks=False)
    except FileNotFoundError:
        fail(f"workspace is absent: {workspace}")
    if stat.S_ISLNK(workspace_state.st_mode) or not stat.S_ISDIR(workspace_state.st_mode):
        fail(f"workspace is not one real directory: {workspace}")

    helper = os.path.abspath(__file__)
    expected_helper = os.path.join(workspace, "prompts", "common", "additional-prompt.py")
    if helper != expected_helper:
        fail(f"helper is not the frozen workspace copy: {helper}")
    return os.open(workspace, os.O_RDONLY | DIRECTORY | NOFOLLOW)


def establish_inputs(workspace, role_prompt, additional_prompt):
    exact_absolute_path(role_prompt, "role prompt")
    exact_absolute_path(additional_prompt, "additional prompt")

    prompts = os.path.join(workspace, "prompts")
    try:
        common = os.path.commonpath((prompts, role_prompt))
    except ValueError:
        fail(f"role prompt is outside the workspace prompts: {role_prompt}")
    if common != prompts or role_prompt == prompts:
        fail(f"role prompt is outside the workspace prompts: {role_prompt}")
    relative = os.path.relpath(role_prompt, prompts)
    parts = relative.split(os.sep)
    if any(part in ("", ".", "..") for part in parts):
        fail(f"role prompt has a forbidden path component: {role_prompt}")

    expected_additional = os.path.join(workspace, "additional-prompts", relative)
    if additional_prompt != expected_additional:
        fail(
            "additional prompt does not mirror the exact role prompt: "
            f"expected {expected_additional}, got {additional_prompt}"
        )

    workspace_fd = open_workspace(workspace)
    prompts_fd = open_directory_path(
        workspace_fd, ["prompts"], "workspace prompts root", create=False, absent_ok=False
    )
    role_parent_fd = open_directory_path(
        prompts_fd,
        parts[:-1],
        "role-prompt parent",
        create=False,
        absent_ok=False,
    )
    try:
        if regular_leaf_state(role_parent_fd, parts[-1], "role prompt") is None:
            fail(f"role prompt is absent: {role_prompt}")
    finally:
        os.close(role_parent_fd)
        os.close(prompts_fd)

    additional_root_fd = open_directory_path(
        workspace_fd,
        ["additional-prompts"],
        "additional-prompts root",
        create=False,
        absent_ok=False,
    )
    os.close(workspace_fd)
    return additional_root_fd, parts


def establish_global_inputs(workspace, global_prompt):
    exact_absolute_path(global_prompt, "global additional prompt")
    expected = os.path.join(workspace, "additional-prompts", "global.md")
    if global_prompt != expected:
        fail(f"global additional prompt must be the exact workspace path: {expected}")

    workspace_fd = open_workspace(workspace)
    additional_root_fd = open_directory_path(
        workspace_fd,
        ["additional-prompts"],
        "additional-prompts root",
        create=False,
        absent_ok=False,
    )
    os.close(workspace_fd)
    return additional_root_fd, ["global.md"]


def read_prompt(root_fd, parts):
    parent_fd = open_directory_path(
        root_fd,
        parts[:-1],
        "additional-prompt parent",
        create=False,
        absent_ok=True,
    )
    if parent_fd is None:
        return
    try:
        state = regular_leaf_state(parent_fd, parts[-1], "additional prompt")
        if state is None:
            return
        try:
            prompt_fd = os.open(parts[-1], os.O_RDONLY | NOFOLLOW, dir_fd=parent_fd)
        except OSError as error:
            fail(f"additional prompt changed identity before read: {error}")
        try:
            if not stat.S_ISREG(os.fstat(prompt_fd).st_mode):
                fail("additional prompt is not one real regular file")
            while True:
                payload = os.read(prompt_fd, 65536)
                if not payload:
                    break
                sys.stdout.buffer.write(payload)
            sys.stdout.buffer.flush()
        finally:
            os.close(prompt_fd)
    finally:
        os.close(parent_fd)


def publish_prompt(root_fd, parts, source):
    exact_absolute_path(source, "additional-prompt source")
    try:
        source_fd = os.open(source, os.O_RDONLY | NOFOLLOW)
    except OSError as error:
        fail(f"additional-prompt source is not one readable non-symlink file: {source}: {error}")
    if not stat.S_ISREG(os.fstat(source_fd).st_mode):
        os.close(source_fd)
        fail(f"additional-prompt source is not one real regular file: {source}")

    parent_fd = open_directory_path(
        root_fd,
        parts[:-1],
        "additional-prompt parent",
        create=True,
        absent_ok=False,
    )
    temporary = f".bwr-additional-prompt-{secrets.token_hex(16)}"
    temporary_created = False
    try:
        initial = regular_leaf_state(parent_fd, parts[-1], "additional prompt")
        temporary_fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | NOFOLLOW,
            0o600,
            dir_fd=parent_fd,
        )
        temporary_created = True
        try:
            copy_bytes(source_fd, temporary_fd)
            os.fsync(temporary_fd)
        finally:
            os.close(temporary_fd)

        current = regular_leaf_state(parent_fd, parts[-1], "additional prompt")
        if initial is None:
            if current is not None:
                fail("additional prompt appeared during publication")
        elif current is None or (current.st_dev, current.st_ino) != (initial.st_dev, initial.st_ino):
            fail("additional prompt changed identity during publication")

        os.replace(temporary, parts[-1], src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        temporary_created = False
        final = regular_leaf_state(parent_fd, parts[-1], "published additional prompt")
        if final is None:
            fail("published additional prompt is absent after atomic rename")
        os.fsync(parent_fd)
    finally:
        if temporary_created:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        os.close(source_fd)
        os.close(parent_fd)


def remove_prompt(root_fd, parts):
    parent_fd = open_directory_path(
        root_fd,
        parts[:-1],
        "additional-prompt parent",
        create=False,
        absent_ok=True,
    )
    if parent_fd is None:
        return
    try:
        state = regular_leaf_state(parent_fd, parts[-1], "additional prompt")
        if state is None:
            return
        os.unlink(parts[-1], dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def main():
    if len(sys.argv) < 2:
        fail(
            "usage: additional-prompt.py <read|publish|remove> <workspace> "
            "<role-prompt> <additional-prompt> [source-file]; or "
            "<read-global|publish-global|remove-global> <workspace> "
            "<global-prompt> [source-file]"
        )
    command = sys.argv[1]
    if command in ("read", "publish", "remove"):
        expected = 6 if command == "publish" else 5
        if len(sys.argv) != expected:
            fail(f"{command} received the wrong number of arguments")
        root_fd, parts = establish_inputs(*sys.argv[2:5])
        source = sys.argv[5] if command == "publish" else None
    elif command in ("read-global", "publish-global", "remove-global"):
        action = command.removesuffix("-global")
        expected = 5 if action == "publish" else 4
        if len(sys.argv) != expected:
            fail(f"{command} received the wrong number of arguments")
        root_fd, parts = establish_global_inputs(*sys.argv[2:4])
        source = sys.argv[4] if action == "publish" else None
        command = action
    else:
        fail(f"unknown command: {command}")

    try:
        if command == "read":
            read_prompt(root_fd, parts)
        elif command == "publish":
            publish_prompt(root_fd, parts, source)
        elif command == "remove":
            remove_prompt(root_fd, parts)
    finally:
        os.close(root_fd)


if __name__ == "__main__":
    main()
