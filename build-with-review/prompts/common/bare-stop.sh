#!/usr/bin/env bash
# Durable identity and recovery state for stop.sh calls with no attempt triplet.
# Sourced by stop.sh and by direct consumers that must not pass a current bare
# stop. Callers define die(); no function evaluates the stored call.

bare_stop_marker_read() {
    local marker=$1 tag value extra phase sha encoded decoded
    BARE_STOP_ERROR=
    BARE_STOP_OP=
    BARE_STOP_MODE=
    BARE_STOP_HASH=
    BARE_STOP_CALL=
    BARE_STOP_PHASE=
    BARE_STOP_SHA=
    BARE_STOP_REPORT=
    [ ! -L "$marker" ] && [ -f "$marker" ] || {
        BARE_STOP_ERROR="the bare-stop marker is not one real regular file: $marker"
        return 2
    }
    mapfile -t BARE_STOP_LINES < "$marker"
    [ ${#BARE_STOP_LINES[@]} -eq 6 ] || {
        BARE_STOP_ERROR="the bare-stop marker has ${#BARE_STOP_LINES[@]} lines; expected 6"
        return 2
    }

    read -r tag value extra <<< "${BARE_STOP_LINES[0]}"
    [ "$tag" = op ] && [[ $value =~ ^[0-9a-f]{64}$ ]] && [ -z "$extra" ] || {
        BARE_STOP_ERROR="the bare-stop marker has an invalid operation identity"
        return 2
    }
    BARE_STOP_OP=$value
    read -r tag value extra <<< "${BARE_STOP_LINES[1]}"
    [ "$tag" = mode ] && [[ $value =~ ^(pause|abort)$ ]] && [ -z "$extra" ] || {
        BARE_STOP_ERROR="the bare-stop marker has an invalid mode"
        return 2
    }
    BARE_STOP_MODE=$value
    read -r tag value extra <<< "${BARE_STOP_LINES[2]}"
    [ "$tag" = hash ] && [[ $value =~ ^[0-9a-f]{64}$ ]] && [ -z "$extra" ] || {
        BARE_STOP_ERROR="the bare-stop marker has an invalid call hash"
        return 2
    }
    BARE_STOP_HASH=$value
    case ${BARE_STOP_LINES[3]} in
        'call '*) BARE_STOP_CALL=${BARE_STOP_LINES[3]#call } ;;
        *)
            BARE_STOP_ERROR="the bare-stop marker has no lossless call on line 4"
            return 2
            ;;
    esac
    [ -n "$BARE_STOP_CALL" ] || {
        BARE_STOP_ERROR="the bare-stop marker has an empty call"
        return 2
    }

    read -r tag phase sha extra <<< "${BARE_STOP_LINES[4]}"
    [ "$tag" = phase ] || {
        BARE_STOP_ERROR="the bare-stop marker has no phase on line 5"
        return 2
    }
    case "$phase" in
        prepared)
            [ -z "$sha$extra" ] || {
                BARE_STOP_ERROR="a prepared bare-stop marker carries an unexpected SHA"
                return 2
            }
            ;;
        tree-settled)
            [[ $sha =~ ^[0-9a-f]{40,64}$ ]] && [ -z "$extra" ] || {
                BARE_STOP_ERROR="a tree-settled bare-stop marker has an invalid SHA"
                return 2
            }
            BARE_STOP_SHA=$sha
            ;;
        *)
            BARE_STOP_ERROR="the bare-stop marker has an unknown phase: $phase"
            return 2
            ;;
    esac
    BARE_STOP_PHASE=$phase

    case ${BARE_STOP_LINES[5]} in
        'report '*) encoded=${BARE_STOP_LINES[5]#report } ;;
        *)
            BARE_STOP_ERROR="the bare-stop marker has no report payload on line 6"
            return 2
            ;;
    esac
    if [ "$phase" = prepared ]; then
        [ "$encoded" = - ] || {
            BARE_STOP_ERROR="a prepared bare-stop marker carries an unexpected report"
            return 2
        }
    else
        [ -n "$encoded" ] && [ "$encoded" != - ] || {
            BARE_STOP_ERROR="a tree-settled bare-stop marker has no report"
            return 2
        }
        if ! decoded=$(printf '%s' "$encoded" | base64 --decode 2>/dev/null); then
            BARE_STOP_ERROR="the bare-stop marker has an invalid report encoding"
            return 2
        fi
        BARE_STOP_REPORT=$decoded
    fi
    return 0
}

bare_stop_journal_state() {
    local journal=$1 kind state
    BARE_STOP_NOTE=
    BARE_STOP_RESUMED=
    [ "$BARE_STOP_MODE" = pause ] && kind=paused || kind=aborted
    [ -f "$journal" ] || return 0
    state=$(awk -v k="\"kind\":\"$kind\"" -v o="\"op\":\"$BARE_STOP_OP\"" '
        index($0,k) && index($0,o) {count++; seen=1; next}
        seen && index($0,"\"kind\":\"resumed\"") {resumed=1}
        END {printf "%d %d\n", count, resumed}' "$journal")
    read -r BARE_STOP_NOTE_COUNT BARE_STOP_RESUMED_FLAG <<< "$state"
    [ "$BARE_STOP_NOTE_COUNT" -le 1 ] || {
        BARE_STOP_ERROR="bare stop $BARE_STOP_OP has $BARE_STOP_NOTE_COUNT terminal notes"
        return 2
    }
    if [ "$BARE_STOP_NOTE_COUNT" -eq 1 ]; then
        [ "$BARE_STOP_PHASE" = tree-settled ] || {
            BARE_STOP_ERROR="bare stop $BARE_STOP_OP has a terminal note before its tree-settled phase"
            return 2
        }
        BARE_STOP_NOTE=1
    fi
    if [ "$BARE_STOP_RESUMED_FLAG" -eq 1 ]; then
        [ "$BARE_STOP_MODE" = pause ] || {
            BARE_STOP_ERROR="an aborted run has a later resumed boundary"
            return 2
        }
        BARE_STOP_RESUMED=1
    fi
    return 0
}

bare_stop_call_identity() {
    local mode=$1 program=$2 argument
    shift 2
    BARE_STOP_EXPECTED_HASH=$(
        {
            printf '%s\0' "$mode" "$program"
            for argument in "$@"; do printf '%s\0' "$argument"; done
        } | sha256sum | cut -d' ' -f1
    )
    printf -v BARE_STOP_EXPECTED_CALL '%q ' "$program" "$@"
    BARE_STOP_EXPECTED_CALL=${BARE_STOP_EXPECTED_CALL% }
}

bare_stop_owner_inspect() {
    local marker=$1 journal=$2 mode=$3 program=$4
    shift 4
    BARE_STOP_OWNER_STATE=fresh
    bare_stop_call_identity "$mode" "$program" "$@"
    if [ ! -e "$marker" ] && [ ! -L "$marker" ]; then
        return 0
    fi
    bare_stop_marker_read "$marker" || return $?
    bare_stop_journal_state "$journal" || return $?

    if [ -n "$BARE_STOP_NOTE" ] && [ -n "$BARE_STOP_RESUMED" ]; then
        BARE_STOP_OWNER_STATE=fresh
        return 0
    fi
    if [ "$BARE_STOP_MODE" != "$mode" ] \
       || [ "$BARE_STOP_HASH" != "$BARE_STOP_EXPECTED_HASH" ] \
       || [ "$BARE_STOP_CALL" != "$BARE_STOP_EXPECTED_CALL" ]; then
        if [ -n "$BARE_STOP_NOTE" ]; then
            BARE_STOP_ERROR="the run is already stopped by: $BARE_STOP_CALL. Resume it before a later stop"
        else
            BARE_STOP_ERROR="an unfinished bare stop owns the workspace. Rerun from the workspace: $BARE_STOP_CALL"
        fi
        return 2
    fi
    if [ -n "$BARE_STOP_NOTE" ]; then
        BARE_STOP_OWNER_STATE=completed
    else
        BARE_STOP_OWNER_STATE=retry
    fi
    return 0
}

bare_stop_allocate() {
    local marker=$1 mode=$2 program=$3 nonce
    shift 3
    bare_stop_call_identity "$mode" "$program" "$@"
    nonce=$(printf '%s\0' "$mode" "$BARE_STOP_EXPECTED_HASH" "$(date +%s%N)" "$$" "$RANDOM" \
        | sha256sum | cut -d' ' -f1)
    {
        printf 'op %s\n' "$nonce"
        printf 'mode %s\n' "$mode"
        printf 'hash %s\n' "$BARE_STOP_EXPECTED_HASH"
        printf 'call %s\n' "$BARE_STOP_EXPECTED_CALL"
        printf 'phase prepared\n'
        printf 'report -\n'
    } > "$marker.tmp"
    mv "$marker.tmp" "$marker"
    bare_stop_marker_read "$marker"
}

bare_stop_settle_tree() {
    local marker=$1 sha=$2 report=$3 encoded
    bare_stop_marker_read "$marker" || return $?
    [ "$BARE_STOP_PHASE" = prepared ] || {
        BARE_STOP_ERROR="bare stop $BARE_STOP_OP is already tree-settled"
        return 2
    }
    encoded=$(printf '%s' "$report" | base64 --wrap=0)
    [ -n "$encoded" ] || {
        BARE_STOP_ERROR="a bare stop cannot settle with an empty report"
        return 2
    }
    {
        printf '%s\n' "${BARE_STOP_LINES[0]}" "${BARE_STOP_LINES[1]}" \
            "${BARE_STOP_LINES[2]}" "${BARE_STOP_LINES[3]}"
        printf 'phase tree-settled %s\n' "$sha"
        printf 'report %s\n' "$encoded"
    } > "$marker.tmp"
    mv "$marker.tmp" "$marker"
    bare_stop_marker_read "$marker"
}

bare_stop_refuse_unfinished() {
    local workspace=$1 marker="$1/bare-stop-in-progress" journal="$1/progress.jsonl"
    BARE_STOP_ERROR=
    if [ ! -e "$marker" ] && [ ! -L "$marker" ]; then
        return 0
    fi
    bare_stop_marker_read "$marker" || return $?
    bare_stop_journal_state "$journal" || return $?
    if [ -z "$BARE_STOP_NOTE" ]; then
        BARE_STOP_ERROR="an unfinished bare stop owns the workspace. Rerun from the workspace: $BARE_STOP_CALL"
        return 2
    fi
    if [ "$BARE_STOP_MODE" = abort ]; then
        BARE_STOP_ERROR="bare stop $BARE_STOP_OP completed an abort. An aborted run has no resume or mutation route"
        return 2
    fi
    if [ -z "$BARE_STOP_RESUMED" ]; then
        BARE_STOP_ERROR="bare stop $BARE_STOP_OP completed a pause. Write progress.py note resumed before any normal mutation"
        return 2
    fi
    return 0
}
