#!/usr/bin/env bash
# ======================================================================
# dump_restore.sh — Restore from text dump (backups/dump_*.txt)
#
# PURPOSE
#   • Restore the working tree (or specific files) from a text dump created
#     by dump_for_chat.sh.
#   • Designed to work with dumps in this format:
#       === BEGIN FILE DUMP ===
#       ----- FILE: relative/path -----
#       <contents>
#       ...
#       === END FILE DUMP ===
#
# USAGE (examples)
#   # DRY RUN — show what would be restored
#   tools/dump_restore.sh --dump backups/dump_20251115_080321.txt
#
#   # Restore everything from a snapshot
#   tools/dump_restore.sh --dump backups/dump_20251115_080321.txt --apply --yes
#
#   # Restore only one file matching regex
#   tools/dump_restore.sh \
#     --dump backups/dump_20251115_080321.txt \
#     --filter '^main/app_main\.c$' \
#     --apply --yes
#
#   # Restore with per-file overwrite backup
#   tools/dump_restore.sh \
#     --dump backups/dump_20251115_080321.txt \
#     --filter '^components/ui/ui\.c$' \
#     --apply --yes --backup-overwrites
#
# NOTES
#   • Default is DRY RUN (no changes) unless --apply is given.
#   • Excludes are applied to paths found in the dump, so even if old dumps
#     contain tools/ or other paths, they will not be restored if excluded.
#   • This script is designed to be compatible with _quick_patch.sh calls:
#       dump_for_chat.sh --mode backup --label ...
#       dump_restore.sh --dump backups/dump_*.txt --apply --yes
# ======================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

DUMP_PATH=""
FILTER_RE=""
APPLY=0
ASSUME_YES=0
BACKUP_OVERWRITES=0
USER_ROOT=""

usage() {
  cat <<'EOF'
Usage:
  dump_restore.sh --dump <path/to/dump.txt> [options]

Options:
  --dump <file>          Text dump file created by dump_for_chat.sh
  --filter <regex>       Only restore files whose relative path matches regex
  --root <dir>           Override repo root (default: parent of tools/)
  --apply                Actually restore files (default is DRY RUN)
  --yes, -y              Skip confirmation prompt (use with --apply)
  --backup-overwrites    Before overwriting, back up existing files to
                         backups/overwrites_YYYYmmdd_HHMMSS/
  --help, -h             Show this help
EOF
}

# -------- arg parse --------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dump)
      DUMP_PATH="${2:-}"; shift 2;;
    --filter)
      FILTER_RE="${2:-}"; shift 2;;
    --root)
      USER_ROOT="${2:-}"; shift 2;;
    --apply)
      APPLY=1; shift;;
    --yes|-y)
      ASSUME_YES=1; shift;;
    --backup-overwrites)
      BACKUP_OVERWRITES=1; shift;;
    --help|-h)
      usage; exit 0;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      usage
      exit 1;;
  esac
done

if [[ -z "$DUMP_PATH" ]]; then
  echo "ERROR: --dump <file> is required" >&2
  usage
  exit 1
fi

if [[ ! -f "$DUMP_PATH" ]]; then
  echo "ERROR: dump file not found: $DUMP_PATH" >&2
  exit 1
fi

ROOT="${USER_ROOT:-$DEFAULT_ROOT}"
cd "$ROOT"

# ========= CONFIG (mirrored from dump_for_chat.sh, but used as restore *excludes*) =========
EXCLUDE_DIRS=(
  "build"
  ".git"
  ".idea"
  "backups"
  "obsolete"
  "Patchlets"
  "misc"
  "tools"     # <-- do NOT restore tools/ even if present in old dumps
)

EXCLUDE_FILE_GLOBS=(
  "*.ods"
  "*odt"
  "sdkconfig"
  "*.bin"
  "*.elf"
  "*.map"
  "*.o"
  "*.a"
  "*.pyc"
  "*.swp"
  "*.tmp"
  "*~"
)

EXCLUDE_PATHS=(
  "_dump_for_chat.txt"
)

TS="$(date +%Y%m%d_%H%M%S)"
OVERWRITE_DIR=""

if [[ "$BACKUP_OVERWRITES" -eq 1 && "$APPLY" -eq 1 ]]; then
  OVERWRITE_DIR="${ROOT}/backups/overwrites_${TS}"
  mkdir -p "$OVERWRITE_DIR"
fi

# -------- helpers: path filtering --------
should_skip_path() {
  local rel="$1"

  # Exclude dirs
  for d in "${EXCLUDE_DIRS[@]}"; do
    if [[ "$rel" == "$d" || "$rel" == "$d/"* ]]; then
      return 0   # skip
    fi
  done

  # Exclude exact paths
  for p in "${EXCLUDE_PATHS[@]}"; do
    if [[ "$rel" == "$p" ]]; then
      return 0   # skip
    fi
  done

  # Exclude by filename glob
  local base="${rel##*/}"
  for g in "${EXCLUDE_FILE_GLOBS[@]}"; do
    if [[ "$base" == $g ]]; then
      return 0   # skip
    fi
  done

  return 1       # do NOT skip
}

matches_filter() {
  local rel="$1"
  if [[ -z "$FILTER_RE" ]]; then
    return 0   # no filter → always match
  fi
  if [[ "$rel" =~ $FILTER_RE ]]; then
    return 0
  fi
  return 1
}

apply_block() {
  local rel="$1"
  local tmpfile="$2"

  # Skip by EXCLUDE rules
  if should_skip_path "$rel"; then
    printf '[SKIP excl] %s\n' "$rel"
    return
  fi

  # Skip if not matching filter (if any)
  if ! matches_filter "$rel"; then
    printf '[SKIP filt] %s\n' "$rel"
    return
  fi

  local target="${ROOT}/${rel}"
  if [[ "$APPLY" -eq 0 ]]; then
    printf '[DRY] would restore %s -> %s\n' "$rel" "$target"
    return
  fi

  # Backup existing file if requested
  if [[ "$BACKUP_OVERWRITES" -eq 1 && -n "$OVERWRITE_DIR" && -f "$target" ]]; then
    local backup_path="${OVERWRITE_DIR}/${rel}"
    mkdir -p "$(dirname "$backup_path")"
    cp -p -- "$target" "$backup_path"
    printf '[BKUP] %s -> %s\n' "$target" "$backup_path"
  fi

  mkdir -p "$(dirname "$target")"
  cp -f -- "$tmpfile" "$target"
  printf '[RESTORE] %s -> %s\n' "$rel" "$target"
}

# -------- pre-flight summary & confirmation --------
echo "Repo root:      ${ROOT}"
echo "Dump file:      ${DUMP_PATH}"
echo "Filter regex:   ${FILTER_RE:-(none)}"
echo "Mode:           $([[ "$APPLY" -eq 1 ]] && echo APPLY || echo DRY-RUN)"
echo "Backup overwrites: $([[ "$BACKUP_OVERWRITES" -eq 1 ]] && echo yes || echo no)"
echo

if [[ "$APPLY" -eq 1 && "$ASSUME_YES" -eq 0 ]]; then
  read -r -p "This will overwrite files under ${ROOT} from ${DUMP_PATH}. Continue? [y/N] " ans
  case "$ans" in
    y|Y|yes|YES) ;;
    *) echo "Aborted."; exit 1;;
  esac
fi

# -------- parse and apply from dump --------
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

in_dump=0
current_rel=""
current_tmp=""
file_index=0

while IFS= read -r line; do
  # Start of dump: match any line that *contains* "BEGIN FILE DUMP"
  if [[ "$line" == *"BEGIN FILE DUMP"* ]]; then
    in_dump=1
    continue
  fi

  # Ignore everything before the dump section
  if [[ "$in_dump" -eq 0 ]]; then
    continue
  fi

  # End of dump: match any line that *contains* "END FILE DUMP"
  if [[ "$line" == *"END FILE DUMP"* ]]; then
    if [[ -n "$current_rel" && -n "$current_tmp" ]]; then
      apply_block "$current_rel" "$current_tmp"
    fi
    current_rel=""
    current_tmp=""
    break
  fi

  # Skip structural group headers from dump_for_chat.sh
  # e.g. "=== COMPONENTS ===", "=== (root) ===", "--- components/brain ---"
  if [[ "$line" =~ ^===\ .*\ ===$ ]]; then
    continue
  fi
  if [[ "$line" =~ ^---\ .*\ ---$ ]]; then
    continue
  fi

  if [[ "$line" == "----- FILE: "* ]]; then
    # flush previous
    if [[ -n "$current_rel" && -n "$current_tmp" ]]; then
      apply_block "$current_rel" "$current_tmp"
    fi

    current_rel="${line#----- FILE: }"
    current_rel="${current_rel% -----}"
    file_index=$((file_index + 1))
    current_tmp="${TMPDIR}/file_${file_index}"
    : > "$current_tmp"
    continue
  fi

  if [[ -n "$current_rel" && -n "$current_tmp" ]]; then
    printf '%s\n' "$line" >> "$current_tmp"
  fi
done < "$DUMP_PATH"



# If file ended without explicit END marker, flush last block
if [[ -n "$current_rel" && -n "$current_tmp" ]]; then
  apply_block "$current_rel" "$current_tmp"
fi

if [[ "$APPLY" -eq 0 ]]; then
  echo
  echo "Dry run completed. Re-run with --apply (and optionally --yes) to perform restore."
fi
