#!/usr/bin/env bash
# ======================================================================
# _quick_patch.sh — Transactional patch runner (Option B: patchlets)
# Repo:  /home/nick/esp/Projects/ESP32_PID_PCOOK_V1
#
# PURPOSE:
#   • Take a pre-patch snapshot to /backups/… (undo point).
#   • Execute external patchlets (one or many).
#   • Verify via asserts inside each patchlet.
#   • On failure AFTER snapshot: auto-restore from the undo point (all-or-nothing).
#   • On success: refresh _dump_for_chat.txt.
#   • In --dry-verify mode: run patchlets in "asserts only" mode with
#     NO snapshot, NO restore, and NO _dump_for_chat refresh.
#
# USAGE (examples):
#   tools/_quick_patch.sh --patch Patchlets/007_LCD_BACKLIGHT_FLICKER_FIX.sh
#   tools/_quick_patch.sh --dir Patchlets --label pre_patch_ui
#   # You can include "restore patchlets" (e.g., 000_restore_ui.sh) that call
#   # tools/dump_restore.sh --latest --apply --yes to reset the tree
#   # before applying fixes.
#
# FLAGS:
#   --patch PATH       Run exactly this patchlet file
#   --dir PATH         Run all *.sh patchlets under PATH (sorted)
#   --label STR        Tag used in the snapshot file name (e.g., pre_patch_xyz)
#   --verbose          Echo each step + asserts
#   --dry-verify       Do not edit; patchlets should run asserts only
#                     (NO snapshot, NO restore, NO dump refresh)
#   --lint             Run optional lint after all patchlets (see $LINT_CMD)
#   -h|--help          Show this help
#
# ENV (optional):
#   PROJ=/path/to/repo             (default: /home/nick/esp/Projects/ESP32_PID_PCOOK_V1)
#   TOOLS_DIR=/path/to/tools       (default: $PROJ/tools)
#   PATCHLETS_DIR=/path/to/patches (default: $PROJ/Patchlets)
#   LINT_CMD="make -j lint"        (used only if --lint is set; else skipped)
#
# EXIT CODES:
#   0  success (all patchlets applied & verified)
#   2  usage/config errors (no snapshot created; repo unchanged)
#   3  snapshot creation/lookup failure (no patchlets run; repo unchanged)
#   4  patchlet failure or restore failure
#      (if snapshot existed, restore was attempted)
#   5  lint failure
#      (if snapshot existed, restore was attempted)
#   6  post-patch _dump_for_chat refresh failure
#      (patches applied; snapshot still exists as an undo point)
# ======================================================================

set -euo pipefail

# ---------- Config ----------
PROJ_DEFAULT="/home/nick/esp/Projects/ESP32_PID_PCOOK_V1"
TOOLS_DIR_DEFAULT="${PROJ_DEFAULT}/tools"
PATCHLETS_DIR_DEFAULT="${PROJ_DEFAULT}/Patchlets"

# Colors
BLD="$(printf '\033[1m')" ; RST="$(printf '\033[0m')"
RED="$(printf '\033[31m')" ; GRN="$(printf '\033[32m')" ; YEL="$(printf '\033[33m')"
CYA="$(printf '\033[36m')"

# ---------- CLI ----------
VERBOSE=0
DRY_VERIFY=0
DO_LINT=0   # lint is opt-in via --lint
LABEL=""
PATCH_FILE=""
PATCH_DIR=""

usage() {
  sed -n '1,80p' "$0" | sed 's/^# \{0,1\}//' | sed '1,3d; s/^$//'
}

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --patch)      PATCH_FILE="${2:-}"; shift 2;;
    --dir)        PATCH_DIR="${2:-}";  shift 2;;
    --label)      LABEL="${2:-}";      shift 2;;
    --verbose)    VERBOSE=1;           shift;;
    --dry-verify) DRY_VERIFY=1;        shift;;
    --lint)       DO_LINT=1;           shift;;
    -h|--help)    usage; exit 0;;
    *) echo "Unknown arg: $1"; usage; exit 2;;
  esac
done

# ---------- Paths ----------
PROJ="${PROJ:-$PROJ_DEFAULT}"
TOOLS_DIR="${TOOLS_DIR:-$TOOLS_DIR_DEFAULT}"
PATCHLETS_DIR="${PATCHLETS_DIR:-$PATCHLETS_DIR_DEFAULT}"

DUMPER="${TOOLS_DIR}/dump_for_chat.sh"
RESTORER="${TOOLS_DIR}/dump_restore.sh"

# Ensure we’re in repo root
cd "$PROJ"

# ---------- Helpers (orchestrator) ----------
say()  { printf "%b\n" "$*"; }
note() { printf "%b\n" "${CYA}$*${RST}"; }
ok()   { printf "%b\n" "${GRN}$*${RST}"; }
warn() { printf "%b\n" "${YEL}$*${RST}"; }
err()  { printf "%b\n" "${RED}$*${RST}"; }

fail() {
  local code="${1:-1}"; shift || true
  echo
  err "${BLD}==== FAIL (exit ${code}) ==== ${RST}$*"
  exit "$code"
}

need_exec() {
  local p="$1"
  [[ -x "$p" ]] || fail 2 "Required tool not executable: $p"
}

latest_backup_path() {
  # Return newest backups/dump_*.txt (absolute path)
  local latest
  latest="$(ls -1t backups/dump_*.txt 2>/dev/null | head -n1 || true)"
  [[ -n "$latest" ]] && { readlink -f "$latest"; return 0; }
  return 1
}

# ======================================================================
# Patchlet helper library (for use INSIDE patchlets)
# ======================================================================

patchlet_helpers() {
  cat <<'HLP'
say()  { printf "%b\n" "$*"; }
ok()   { printf '\033[32m%b\033[0m\n' "$*"; }
warn() { printf '\033[33m%b\033[0m\n' "$*"; }
err()  { printf '\033[31m%b\033[0m\n' "$*"; }

# Abort current patchlet only; orchestrator will catch and restore.
fail() { local code="${1:-1}"; shift || true; err "PATCHLET FAIL: $*"; exit "$code"; }

# Guarded regex replace (Perl).
# Usage: regex_replace FILE 's/old/new/g'
#   - You provide a full Perl s/// expression (including any flags like g, i, m).
#   - In DRY VERIFY (QUICKPATCH_DRY_VERIFY=1) this is NOT allowed and will fail loudly.
regex_replace() {
  local f="$1"; local expr="$2"
  if [[ "${QUICKPATCH_DRY_VERIFY:-0}" -eq 1 ]]; then
    fail 1 "regex_replace called during DRY VERIFY (QUICKPATCH_DRY_VERIFY=1). Patchlet must skip edits in dry runs."
  fi
  [[ -f "$f" ]] || fail 1 "regex_replace: file not found: $f"
  perl -0777 -i -pe "$expr" "$f"
}

# Insert a block after an anchor, only if missing a guard token.
# Usage: guard_insert FILE 'anchor regex' 'GUARD_TOKEN' 'block text'
#   - In DRY VERIFY (QUICKPATCH_DRY_VERIFY=1) this is NOT allowed and will fail loudly.
guard_insert() {
  local f="$1"; local anchor="$2"; local guard="$3"; local block="$4"
  if [[ "${QUICKPATCH_DRY_VERIFY:-0}" -eq 1 ]]; then
    fail 1 "guard_insert called during DRY VERIFY (QUICKPATCH_DRY_VERIFY=1). Patchlet must skip edits in dry runs."
  fi
  [[ -f "$f" ]] || fail 1 "guard_insert: file not found: $f"
  if grep -qE "$guard" "$f"; then
    say "guard_insert: guard already present in $f (ok)"
    return 0
  fi
  local tmp
  tmp="$(mktemp)"
  awk -v anchor="$anchor" -v block="$block" '
    BEGIN{done=0}
    {
      print
      if (!done && $0 ~ anchor) {
        print block
        done=1
      }
    }
    END{}' "$f" >"$tmp"
  mv "$tmp" "$f"
}

# Assertions (must match / must not match)
assert_grep() {
  local f="$1"; local re="$2"; local why="${3:-must match}"
  [[ -f "$f" ]] || fail 1 "assert_grep: file not found: $f"
  if grep -qE "$re" "$f"; then
    ASSERT_COUNT=$((ASSERT_COUNT+1))
    say "assert_grep OK: $f :: $why"
  else
    fail 1 "assert_grep FAIL: $f :: $why :: regex=/$re/"
  fi
}

assert_notgrep() {
  local f="$1"; local re="$2"; local why="${3:-must NOT match}"
  [[ -f "$f" ]] || fail 1 "assert_notgrep: file not found: $f"
  if grep -qE "$re" "$f"; then
    fail 1 "assert_notgrep FAIL: $f :: $why :: regex=/$re/"
  else
    ASSERT_COUNT=$((ASSERT_COUNT+1))
    say "assert_notgrep OK: $f :: $why"
  fi
}

# Optional forensic backup of files before this patchlet edits them.
# In DRY VERIFY:
#   - backup_paths is effectively a no-op because QUICKPATCH_BKDIR will usually be empty.
backup_paths() {
  local dest="$QUICKPATCH_BKDIR"
  [[ -n "$dest" ]] || return 0
  mkdir -p "$dest"
  for f in "$@"; do
    [[ -f "$f" ]] || continue
    mkdir -p "$dest/$(dirname "$f")"
    cp -f -- "$f" "$dest/$f"
  done
  say "Backed up $(($#)) file(s) for forensic diff to $dest"
}
HLP
}

extract_title_from_patchlet() {
  # Reads a TITLE from the top-of-file comment: e.g., "# TITLE: XYZ"
  local p="$1"
  local t
  t="$(sed -n '1,15s/^\s*#\s*TITLE:\s*//p' "$p" | head -n1 | sed 's/[[:cntrl:]]//g')"
  [[ -n "$t" ]] && echo "$t" || basename "$p"
}

run_patchlet() {
  local p="$1"; local idx="$2"
  local title; title="$(extract_title_from_patchlet "$p")"

  echo
  note "${BLD}PATCHLET ${idx} — ${title}${RST}"
  [[ $VERBOSE -eq 1 ]] && say "File: $p"

  # Subshell: define helpers, env flags, then source patchlet
  (
    set -euo pipefail
    # Helpers
    eval "$(patchlet_helpers)"

    # Env visible to patchlet
    export PROJ DRY_VERIFY VERBOSE
    export QUICKPATCH_BKDIR="$RUN_BKDIR"

    # If dry-verify: patchlet is expected to run only asserts (no edits via helpers)
    if [[ "${DRY_VERIFY}" -eq 1 ]]; then
      export QUICKPATCH_DRY_VERIFY=1
    else
      export QUICKPATCH_DRY_VERIFY=0
    fi

    # Track how many assertions were run
    ASSERT_COUNT=0

    # Source the patchlet in this subshell so helpers are available
    [[ -r "$p" ]] || fail 1 "patchlet not readable: $p"
    # shellcheck source=/dev/null
    source "$p"

    # In dry-verify mode, require at least one assert_* call
    if [[ "${DRY_VERIFY}" -eq 1 ]]; then
      if [[ "${ASSERT_COUNT:-0}" -le 0 ]]; then
        fail 1 "Dry-verify: patchlet executed without any assert_grep/assert_notgrep calls."
      fi
    fi
  )
}

# ---------- Pre-flight ----------
need_exec "$DUMPER"
if [[ "$DRY_VERIFY" -eq 0 ]]; then
  need_exec "$RESTORER"
fi

# Patch selection
PATCH_LIST=()
if [[ -n "$PATCH_FILE" && -n "$PATCH_DIR" ]]; then
  fail 2 "Use either --patch or --dir, not both."
elif [[ -n "$PATCH_FILE" ]]; then
  [[ -f "$PATCH_FILE" ]] || fail 2 "Patchlet not found: $PATCH_FILE"
  PATCH_LIST+=("$PATCH_FILE")
elif [[ -n "$PATCH_DIR" ]]; then
  [[ -d "$PATCH_DIR" ]] || fail 2 "Directory not found: $PATCH_DIR"
  # Collect *.sh in sorted order
  mapfile -t PATCH_LIST < <(find "$PATCH_DIR" -maxdepth 1 -type f -name "*.sh" | sort)
  [[ ${#PATCH_LIST[@]} -gt 0 ]] || fail 2 "No patchlets (*.sh) found in: $PATCH_DIR"
else
  # Default to project Patchlets dir
  if [[ -d "$PATCHLETS_DIR_DEFAULT" ]]; then
    mapfile -t PATCH_LIST < <(find "$PATCHLETS_DIR_DEFAULT" -maxdepth 1 -type f -name "*.sh" | sort)
    [[ ${#PATCH_LIST[@]} -gt 0 ]] || fail 2 "No patchlets found in default: $PATCHLETS_DIR_DEFAULT. Use --patch or --dir."
  else
    fail 2 "No patchlet specified and default Patchlets directory not found. Use --patch PATH or --dir PATH."
  fi
fi

# Label
if [[ -z "$LABEL" ]]; then
  LABEL="pre_patch_auto"
fi

# Human-friendly patch mode description
PATCH_MODE_DESC=""
if [[ -n "$PATCH_FILE" ]]; then
  PATCH_MODE_DESC="single file: ${PATCH_FILE}"
elif [[ -n "$PATCH_DIR" ]]; then
  PATCH_MODE_DESC="directory: ${PATCH_DIR}"
else
  PATCH_MODE_DESC="directory: ${PATCHLETS_DIR_DEFAULT}"
fi

echo
note "${BLD}== QUICK PATCH (Option B) ==${RST}"
say  "Repo:        $PROJ"
say  "Tools dir:   $TOOLS_DIR"
say  "Patch mode:  ${PATCH_MODE_DESC}"
say  "Patchlets:   ${#PATCH_LIST[@]}"
say  "Flags:       verbose=$VERBOSE dry-verify=$DRY_VERIFY lint=$DO_LINT"
say  "Label:       $LABEL"
echo

# ---------- Pre-patch snapshot (undo point) ----------
PRE_DUMP=""
RUN_BKDIR=""

if [[ "$DRY_VERIFY" -eq 0 ]]; then
  say "Creating pre-patch snapshot (undo point)…"
  if ! "$DUMPER" --mode backup --label "$LABEL"; then
    fail 3 "Snapshot creation failed via dump_for_chat.sh"
  fi

  PRE_DUMP="$(latest_backup_path)" || fail 3 "Could not locate created backup in ./backups"
  ok  "Pre-patch backup: ${PRE_DUMP}"

  # Forensic backup bin for this run (optional per-patchlet)
  RUN_TAG="$(basename "${PRE_DUMP%.txt}")" # dump_YYYYmmdd_HHMMSS_label
  RUN_BKDIR="backups/${RUN_TAG}.forensic"
  mkdir -p "$RUN_BKDIR"
else
  warn "DRY-VERIFY mode: skipping snapshot/restore and forensic backups."
fi

# ---------- Apply patchlets ----------
idx=0
for p in "${PATCH_LIST[@]}"; do
  idx=$((idx+1))
  if ! run_patchlet "$p" "$idx"; then
    echo
    if [[ "$DRY_VERIFY" -eq 0 && -n "$PRE_DUMP" ]]; then
      err "${BLD}Patchlet ${idx} FAILED (${p}).${RST} Restoring from pre-patch snapshot…"
      if ! "$RESTORER" --dump "$PRE_DUMP" --apply --yes; then
        fail 4 "Restore failed; manual intervention required"
      fi
      fail 4 "Restored from ${PRE_DUMP}. See messages above for the failing patchlet/assert."
    else
      err "${BLD}Patchlet ${idx} FAILED in dry-verify mode (${p}).${RST} No restore performed."
      fail 4 "Dry-verify failure. See messages above for the failing patchlet/assert."
    fi
  fi
  ok "PATCHLET ${idx} — OK (${p})"
done

# ---------- Optional lint ----------
if [[ "$DO_LINT" -eq 1 && "$DRY_VERIFY" -eq 0 ]]; then
  echo
  if [[ -n "${LINT_CMD:-}" ]]; then
    say "Running lint: $LINT_CMD"
    if ! bash -lc "$LINT_CMD"; then
      err "Lint failed."
      if [[ -n "$PRE_DUMP" ]]; then
        err "Restoring from ${PRE_DUMP}…"
        if ! "$RESTORER" --dump "$PRE_DUMP" --apply --yes; then
          fail 5 "Restore failed after lint"
        fi
        fail 5 "Restored from ${PRE_DUMP} due to lint failure."
      else
        fail 5 "Lint failed (no snapshot available to restore)."
      fi
    fi
    ok "Lint OK"
  else
    warn "No LINT_CMD defined; skipping lint."
  fi
elif [[ "$DO_LINT" -eq 1 && "$DRY_VERIFY" -eq 1 ]]; then
  warn "Lint requested but DRY-VERIFY is enabled; skipping lint."
fi

# ---------- Post-patch refresh ----------
if [[ "$DRY_VERIFY" -eq 0 ]]; then
  echo
  say "Refreshing main dump (_dump_for_chat.txt)…"
  if ! "$DUMPER" --mode main; then
    fail 6 "Post-patch _dump_for_chat update failed"
  fi

  echo
  ok "${BLD}==== OK ==== ${RST}Patches applied and verified successfully."
  if [[ -n "$PRE_DUMP" ]]; then
    say "Undo point: ${PRE_DUMP}"
  fi
  if [[ $VERBOSE -eq 1 && -n "$RUN_BKDIR" ]]; then
    say "Forensic backups (original touched files): ${RUN_BKDIR}"
  fi
else
  echo
  ok "${BLD}==== OK (dry-verify) ==== ${RST}Patchlets executed; no snapshot, restore, or dump refresh."
fi
