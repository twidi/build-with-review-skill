#!/usr/bin/env bash
# Durable binding for the owner of an attempt's closing tail.
#
# Sourced by the owning closers and their direct consumers. attempt-in-flight
# starts with two lines: the attempt identity, then its frozen plan manifest.
# A failure or stop appends
# two more lines atomically before its first preserve/reset gesture:
#
#   closer <failure|stop> <SHA-256 of the exact normalized call>
#   call <lossless shell spelling of that call>
#
# The hash is the mechanical identity. The call line is the durable recovery
# instruction a takeover can read after compaction. No eval ever consumes it.

controller_physical_test_barrier() {
    local name=$1 directory ready release count=0
    [ "${BWR_TEST_CONTROLLER_PHYSICAL_BARRIER:-}" = "$name" ] || return 0
    directory=${BWR_TEST_CONTROLLER_PHYSICAL_BARRIER_DIR:?missing test barrier directory}
    ready="$directory/$name.ready"
    release="$directory/$name.release"
    printf 'ready\n' > "$ready"
    while [ ! -e "$release" ]; do
        count=$((count + 1))
        [ "$count" -lt 3000 ] || return 75
        sleep 0.01
    done
}

controller_physical_admission_acquire() {
    local workspace=$1 inherited_error
    CONTROLLER_PHYSICAL_ADMISSION_ERROR=
    if [ -n "${CONTROLLER_PHYSICAL_ADMISSION_FD:-}" ]; then
        if [ "${CONTROLLER_PHYSICAL_ADMISSION_ACQUIRED_HERE:-}" = 1 ]; then
            CONTROLLER_PHYSICAL_ADMISSION_ERROR="the controller physical admission is already retained"
            return 2
        fi
        if ! inherited_error=$(python3 - "$CONTROLLER_PHYSICAL_ADMISSION_FD" \
                "$workspace/controller-physical-admission.lock" <<'PY'
import fcntl
import os
import stat
import sys


def refuse(message):
    print(message)
    raise SystemExit(2)


try:
    descriptor = int(sys.argv[1])
except (TypeError, ValueError):
    refuse("the inherited controller physical admission descriptor is not an integer")
if descriptor < 0:
    refuse("the inherited controller physical admission descriptor is negative")

path = sys.argv[2]
try:
    descriptor_state = os.fstat(descriptor)
except OSError:
    refuse("the inherited controller physical admission descriptor is not open")
try:
    path_state = os.lstat(path)
except OSError:
    refuse("the canonical controller physical admission lock is absent")
if not stat.S_ISREG(path_state.st_mode):
    refuse("the canonical controller physical admission lock is not one real regular file")
if not stat.S_ISREG(descriptor_state.st_mode) or (
    descriptor_state.st_dev,
    descriptor_state.st_ino,
) != (path_state.st_dev, path_state.st_ino):
    refuse("the inherited descriptor does not name the canonical controller physical admission lock generation")

flags = os.O_WRONLY | os.O_APPEND
if hasattr(os, "O_NOFOLLOW"):
    flags |= os.O_NOFOLLOW
try:
    probe = os.open(path, flags)
except OSError:
    refuse("the canonical controller physical admission lock cannot be reopened safely")
try:
    probe_state = os.fstat(probe)
    if (probe_state.st_dev, probe_state.st_ino) != (
        descriptor_state.st_dev,
        descriptor_state.st_ino,
    ):
        refuse("the canonical controller physical admission lock generation changed")
    try:
        fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        pass
    else:
        fcntl.flock(probe, fcntl.LOCK_UN)
        refuse("the inherited controller physical admission descriptor does not retain the lock")
finally:
    os.close(probe)

try:
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    refuse("the canonical controller physical admission is retained by another descriptor")
try:
    final_state = os.lstat(path)
except OSError:
    refuse("the canonical controller physical admission lock disappeared")
if (final_state.st_dev, final_state.st_ino) != (
    descriptor_state.st_dev,
    descriptor_state.st_ino,
):
    refuse("the canonical controller physical admission lock generation changed")
PY
        ); then
            CONTROLLER_PHYSICAL_ADMISSION_ERROR=${inherited_error:-the inherited controller physical admission is invalid}
            return 2
        fi
        CONTROLLER_PHYSICAL_ADMISSION_ACQUIRED_HERE=
        return 0
    fi
    exec {CONTROLLER_PHYSICAL_ADMISSION_FD}>> "$workspace/controller-physical-admission.lock" \
        || { CONTROLLER_PHYSICAL_ADMISSION_ERROR="cannot open the controller physical admission lock"; return 2; }
    flock -x "$CONTROLLER_PHYSICAL_ADMISSION_FD" \
        || { CONTROLLER_PHYSICAL_ADMISSION_ERROR="cannot retain the controller physical admission lock"; return 2; }
    CONTROLLER_PHYSICAL_ADMISSION_ACQUIRED_HERE=1
    export CONTROLLER_PHYSICAL_ADMISSION_FD
}

controller_physical_admission_release() {
    [ "${CONTROLLER_PHYSICAL_ADMISSION_ACQUIRED_HERE:-}" = 1 ] || return 0
    [ -n "${CONTROLLER_PHYSICAL_ADMISSION_FD:-}" ] || return 0
    flock -u "$CONTROLLER_PHYSICAL_ADMISSION_FD"
    exec {CONTROLLER_PHYSICAL_ADMISSION_FD}>&-
    unset CONTROLLER_PHYSICAL_ADMISSION_FD
    unset CONTROLLER_PHYSICAL_ADMISSION_ACQUIRED_HERE
}

attempt_closer_read() {
    local inflight=$1 tag extra
    ATTEMPT_CLOSER_KIND=
    ATTEMPT_CLOSER_HASH=
    ATTEMPT_CLOSER_CALL=
    ATTEMPT_CLOSER_ERROR=
    mapfile -t ATTEMPT_CLOSER_LINES < "$inflight"
    case ${#ATTEMPT_CLOSER_LINES[@]} in
        2) return 1 ;;
        4) ;;
        *)
            ATTEMPT_CLOSER_ERROR="attempt-in-flight has ${#ATTEMPT_CLOSER_LINES[@]} lines; expected 2 before a closer binds or 4 afterwards"
            return 2
            ;;
    esac
    read -r tag ATTEMPT_CLOSER_KIND ATTEMPT_CLOSER_HASH extra \
        <<< "${ATTEMPT_CLOSER_LINES[2]}"
    if [ "$tag" != closer ] || [[ ! $ATTEMPT_CLOSER_KIND =~ ^(failure|stop)$ ]] \
       || [[ ! $ATTEMPT_CLOSER_HASH =~ ^[0-9a-f]{64}$ ]] || [ -n "$extra" ]; then
        ATTEMPT_CLOSER_ERROR="attempt-in-flight has an invalid closer identity on line 3"
        return 2
    fi
    case ${ATTEMPT_CLOSER_LINES[3]} in
        'call '*) ATTEMPT_CLOSER_CALL=${ATTEMPT_CLOSER_LINES[3]#call } ;;
        *)
            ATTEMPT_CLOSER_ERROR="attempt-in-flight has no lossless closer call on line 4"
            return 2
            ;;
    esac
    [ -n "$ATTEMPT_CLOSER_CALL" ] || {
        ATTEMPT_CLOSER_ERROR="attempt-in-flight has an empty closer call on line 4"
        return 2
    }
    return 0
}

attempt_closer_bind() {
    local inflight=$1 kind=$2 program=$3 hash call status
    shift 3
    hash=$(
        {
            printf '%s\0' "$kind" "$program"
            for argument in "$@"; do printf '%s\0' "$argument"; done
        } | sha256sum | cut -d' ' -f1
    )
    printf -v call '%q ' "$program" "$@"
    call=${call% }

    if attempt_closer_read "$inflight"; then
        if [ "$ATTEMPT_CLOSER_KIND" != "$kind" ] \
           || [ "$ATTEMPT_CLOSER_HASH" != "$hash" ] \
           || [ "$ATTEMPT_CLOSER_CALL" != "$call" ]; then
            ATTEMPT_CLOSER_ERROR="attempt closer is already bound to: $ATTEMPT_CLOSER_CALL"
            return 2
        fi
        return 0
    else
        status=$?
        [ "$status" -eq 1 ] || return "$status"
    fi

    {
        printf '%s\n' "${ATTEMPT_CLOSER_LINES[0]}" "${ATTEMPT_CLOSER_LINES[1]}"
        printf 'closer %s %s\n' "$kind" "$hash"
        printf 'call %s\n' "$call"
    } > "$inflight.closer.tmp"
    mv "$inflight.closer.tmp" "$inflight"
    ATTEMPT_CLOSER_KIND=$kind
    ATTEMPT_CLOSER_HASH=$hash
    ATTEMPT_CLOSER_CALL=$call
    return 0
}

attempt_closer_route() {
    local inflight=$1 status
    if attempt_closer_read "$inflight"; then
        printf 'Rerun from the workspace: %s' "$ATTEMPT_CLOSER_CALL"
        return 0
    else
        status=$?
    fi
    if [ "$status" -eq 1 ]; then
        printf '%s' "This legacy identity has no durable closer binding. Do not guess between failure, pause and abort. Take it to the human."
    else
        printf 'The closer binding is invalid: %s. Take it to the human.' "$ATTEMPT_CLOSER_ERROR"
    fi
    return 1
}

# A controller-owned document, commit or rewind operation owns the repository until
# its exact caller consumes its marker. An attempt closer cannot distinguish
# that payload or history tail from implementer work. This read-only guard is
# shared with triplet stop; it never removes, follows or repairs a marker.
attempt_success_refuse_pending() {
    local workspace=$1 marker
    CONTROLLER_OPERATION_ERROR=
    marker="$workspace/attempt-success-in-progress.json"
    if [ -e "$marker" ] || [ -L "$marker" ]; then
        if [ -L "$marker" ] || [ ! -f "$marker" ]; then
            CONTROLLER_OPERATION_ERROR="the attempt-success marker is not one real regular file: $marker. It remains untouched. Take this state to the human"
            return 2
        fi
        CONTROLLER_OPERATION_ERROR="an attempt success owns the workspace through $marker. Rerun the exact same attempt-succeeded.sh call. That call alone finishes its stable ref, journal terminal and marker cleanup"
        return 2
    fi
    return 0
}

controller_operation_refuse_pending() {
    local workspace=$1 name marker route
    shift
    attempt_success_refuse_pending "$workspace" || return $?
    if [ $# -eq 0 ]; then
        set -- document-copy spec-commit amendment-commit spec-breach-recovery \
            amendment-attempt-settle gate-check
    fi
    for name in "$@"; do
        case "$name" in
            document-copy)
                marker="$workspace/document-copy-in-progress"
                route="Rerun the exact owning plan-commit.sh, plan-publish.sh or amendment-commit.sh call. That call alone consumes this marker through document-copy.sh finish. Never remove it by hand"
                ;;
            plan-commit)
                marker="$workspace/plan-commit-in-progress"
                route="Rerun the exact same plan-commit.sh call. It owns its prepared plan commit, task-0 ref, journal tail and marker removal"
                ;;
            spec-commit)
                marker="$workspace/spec-commit-in-progress"
                route="Rerun the exact same spec-commit.sh call. It owns its prepared payload, commit, mark move, journal tail and marker removal"
                ;;
            amendment-commit)
                marker="$workspace/amendment-commit-in-progress"
                route="Rerun the exact same amendment-commit.sh call. It owns its prepared payload, commit, mark move, journal tail and marker removal"
                ;;
            spec-breach-recovery)
                marker="$workspace/spec-breach-recovery-in-progress"
                route="Rerun the exact same spec-breach-recover.sh call with the same breach number and subject. It alone validates and removes this marker; never remove it by hand"
                ;;
            amendment-attempt-settle)
                marker="$workspace/amendment-attempt-settle-in-progress.json"
                route="Rerun amendment-attempt-settle.sh with the exact amendment, lot, task and attempt. It alone preserves the consolidated Spec while the official failure closer resets the attempt"
                ;;
            rewind)
                marker="$workspace/rewind-in-progress"
                route="Rerun the exact same rewind.sh call with the same lot, task range and subject. It owns the reset, ref moves, optional re-land, journal tail and state removal"
                ;;
            gate-check)
                marker="$workspace/gate-check-in-progress"
                route="Stop the physical runner. If its whole reports/gate/<op>.json exists, rerun gate-check.sh close <op>; otherwise rerun gate-check.sh open with the exact owner to regenerate it, or use gate-check.sh abandon <op> before returning to the owning checker. Never let another operation consume its frozen candidate"
                ;;
            *)
                CONTROLLER_OPERATION_ERROR="internal error: unknown controller operation marker $name"
                return 2
                ;;
        esac
        if [ ! -e "$marker" ] && [ ! -L "$marker" ]; then
            continue
        fi
        if [ -L "$marker" ] || [ ! -f "$marker" ]; then
            CONTROLLER_OPERATION_ERROR="the $name marker is not one real regular file: $marker. It remains untouched. Take this state to the human"
            return 2
        fi
        CONTROLLER_OPERATION_ERROR="a $name operation owns the workspace through $marker. $route"
        return 2
    done
    return 0
}
