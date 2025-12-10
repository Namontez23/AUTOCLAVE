#!/usr/bin/env bash
# ======================================================================
# dump_for_chat.sh — Create human-readable project snapshots
#
# PURPOSE
#   • Produce a restore-friendly text dump of source/config files.
#   • Modes:
#       manual → write BOTH a timestamped backup in /backups/ AND the root _dump_for_chat.txt
#       backup → write ONLY a timestamped backup in /backups/
#       main   → write ONLY the root _dump_for_chat.txt
#       subset → write ONLY a subset dump (e.g., just TOOLS) to /backups/
#
# USAGE
#   tools/dump_for_chat.sh --mode manual  --label pre_patch_xyz
#   tools/dump_for_chat.sh --mode backup  --label pre_patch_xyz
#   tools/dump_for_chat.sh --mode main
#   tools/dump_for_chat.sh --mode subset --subset src
#
# FLAGS
#   --mode   manual|backup|main|subset   (default: manual)
#   --label  STR                         (optional; appended to backup filename)
#   --root   PATH                        (override auto-detected repo root)
#   --subset NAME                        (for --mode subset: top-level dir, e.g. src, tools)
#   -h|--help
#
# OUTPUTS
#   • backups/dump_YYYYmmdd_HHMMSS[_label].txt          (for manual/backup)
#   • _dump_for_chat.txt                                (for manual/main)
#   • backups/dump_YYYYmmdd_HHMMSS_SUBSET[_label].txt   (for subset)
#
# FORMAT (stable; used by dump_restore.sh or manual inspection)
#   === Project dump generated: ...
#   === File summary (included) ===
#   === (root) ===
#    - main.py
#   === SRC ===
#   --- src/core ---
#    - src/core/pid_core.py
#   ...
#   ===================== BEGIN / END FILE DUMP =========================
# ======================================================================

set -euo pipefail

# ---------- Defaults & CLI ----------
MODE="manual"
LABEL=""
USER_ROOT=""
SUBSET_NAME=""

usage() {
  sed -n '1,80p' "$0" | sed 's/^# \{0,1\}//' | sed '1,3d'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)   MODE="${2:-}"; shift 2;;
    --label)  LABEL="${2:-}"; shift 2;;
    --root)   USER_ROOT="${2:-}"; shift 2;;
    --subset) SUBSET_NAME="${2:-}"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1"; usage; exit 2;;
  esac
done

# ---------- Resolve ROOT ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ROOT="${USER_ROOT:-$DEFAULT_ROOT}"

cd "$ROOT"

# ---------- Paths ----------
MAIN_OUT="${ROOT}/_dump_for_chat.txt"
BACKUPS_DIR="${ROOT}/backups"
TS="$(date +%Y%m%d_%H%M%S)"

LABEL_SAFE=""
if [[ -n "$LABEL" ]]; then
  LABEL_SAFE="$(echo "$LABEL" | tr -cs 'A-Za-z0-9._+-' '_' | sed 's/^_//; s/_$//')"
fi

# ======================================================================
# DEFAULT INCLUDE / EXCLUDE RULES (generic across projects)
# You can override/extend these in tools/dump_for_chat.conf if needed.
# ======================================================================

# Directories we usually do NOT want in dumps
EXCLUDE_DIRS=(
  "build"
  "dist"
  ".git"
  ".idea"
  ".vscode"
  ".venv"
  "__pycache__"
  ".mypy_cache"
  ".pytest_cache"
  "backups"
  "obsolete"
  "tools"
)

# File globs we usually do NOT want
EXCLUDE_FILE_GLOBS=(
  "*.ods"
  "*.odt"
  "*.xlsx"
  "*.xls"
  "*.bin"
  "*.elf"
  "*.map"
  "*.o"
  "*.a"
  "*.pyc"
  "*.pyo"
  "*.swp"
  "*.tmp"
  "*~"
  "*.log"
)

# Specific paths we never want to include
EXCLUDE_PATHS=(
  "_dump_for_chat.txt"   # DO NOT SELF INCLUDE OUTPUT FILE
)

# File patterns we DO want to include
INCLUDE_GLOBS=(
  # Shell / scripts
  "*.sh"
  "*.bash"
  "Makefile"

  # C / C++
  "*.c"
  "*.h"
  "*.cpp"
  "*.hpp"

  # Python / MicroPython
  "*.py"
  "requirements.txt"
  "requirements-*.txt"
  "pyproject.toml"
  "setup.cfg"

  # Build / project config
  "CMakeLists.txt"
  "*.cmake"
  "Kconfig*"
  "sdkconfig.defaults"

  # Text / docs
  "*.txt"
  "*.md"
  "*.rst"
)

# Files to always include if present (even if they don't match the globs)
ALWAYS_INCLUDE_FILES=(
  ".vscode/settings.json"
  "pyrightconfig.json"
  "requirements-dev.txt"
  ".editorconfig"
  "settings.json"
)

# ======================================================================
# OPTIONAL PROJECT-LOCAL OVERRIDES
# If tools/dump_for_chat.conf exists, it can modify the arrays above.
# For example, inside that file you can:
#   EXCLUDE_DIRS+=("node_modules")
#   INCLUDE_GLOBS+=("*.js" "*.ts")
# ======================================================================
CONFIG_FILE="${SCRIPT_DIR}/dump_for_chat.conf"
if [[ -f "$CONFIG_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$CONFIG_FILE"
fi

# ---------- Build the find(1) expression ----------
# If we're in subset mode, allow that top-level dir even if normally excluded.
SUBSET_DIR_LOWER=""
if [[ "$MODE" == "subset" && -n "$SUBSET_NAME" ]]; then
  SUBSET_DIR_LOWER="$(echo "$SUBSET_NAME" | tr '[:upper:]' '[:lower:]')"
fi

FIND_ARGS=()
for d in "${EXCLUDE_DIRS[@]}"; do
  d_lower="$(echo "$d" | tr '[:upper:]' '[:lower:]')"
  if [[ -n "$SUBSET_DIR_LOWER" && "$d_lower" == "$SUBSET_DIR_LOWER" ]]; then
    continue
  fi
  FIND_ARGS+=( -path "./$d" -prune -o )
done

FIND_ARGS+=( -type f \( )
for i in "${!INCLUDE_GLOBS[@]}"; do
  (( i > 0 )) && FIND_ARGS+=( -o )
  FIND_ARGS+=( -name "${INCLUDE_GLOBS[$i]}" )
done
FIND_ARGS+=( \) )
for g in "${EXCLUDE_FILE_GLOBS[@]}"; do FIND_ARGS+=( ! -name "$g" ); done
for p in "${EXCLUDE_PATHS[@]}";    do FIND_ARGS+=( ! -path "./$p" ); done

# Collect files deterministically
mapfile -t FILES < <(
  {
    find . "${FIND_ARGS[@]}" -print
    for f in "${ALWAYS_INCLUDE_FILES[@]}"; do [[ -f "$f" ]] && echo "./$f"; done
  } | sed 's|^\./||' | sort -u
)

# ---------- Dump writer ----------
write_dump() {
  local out_path="$1"
  local tmp
  tmp="$(mktemp)"

  # Split into root-level files vs non-root
  local ROOT_FILES=()
  local NONROOT_FILES=()
  local f
  for f in "${FILES[@]}"; do
    if [[ "$f" == */* ]]; then
      NONROOT_FILES+=("$f")
    else
      ROOT_FILES+=("$f")
    fi
  done

  {
    printf '%s\n' "=== Project dump generated: $(date -Iseconds) ==="
    printf '%s\n' "Working directory: $ROOT"
    if [[ -n "$SUBSET_NAME" ]]; then
      printf '%s\n' "Subset: ${SUBSET_NAME}"
    fi
    printf '\n'

    printf '%s\n' "=== File summary (included) ==="

    # Root files
    if ((${#ROOT_FILES[@]} > 0)); then
      printf '%s\n' "=== (root) ==="
      for f in "${ROOT_FILES[@]}"; do
        printf '%s\n' " - ${f}"
      done
      printf '\n'
    fi

    # Group non-root files by top-level dir + first subdir
    local prev_root="" prev_sub=""

    for f in "${NONROOT_FILES[@]}"; do
      local root rest sub header

      root="${f%%/*}"
      rest="${f#*/}"

      sub=""
      if [[ -n "$rest" && "$rest" == */* ]]; then
        sub="${rest%%/*}"
      fi

      if [[ "$root" != "$prev_root" ]]; then
        [[ -n "$prev_root" ]] && printf '\n'
        header="${root^^}"
        printf '%s\n' "=== ${header} ==="
        prev_root="$root"
        prev_sub=""
      fi

      if [[ -n "$sub" && "$root/$sub" != "$prev_sub" ]]; then
        printf '%s\n' "--- ${root}/${sub} ---"
        prev_sub="$root/$sub"
      fi

      printf '%s\n' " - ${f}"
    done

    printf '\n'
    printf '%s\n' "===================== BEGIN FILE DUMP ========================="

    # ===== FILE DUMP: same grouping as summary, but "expanded" =====

    # Root group first
    if ((${#ROOT_FILES[@]} > 0)); then
      printf '\n%s\n' "=== (root) ==="
      for f in "${ROOT_FILES[@]}"; do
        printf '\n%s\n' "----- FILE: ${f} -----"
        cat -- "$f"
      done
    fi

    # Non-root groups: top-level dir + optional subdir headings
    prev_root=""
    prev_sub=""

    for f in "${NONROOT_FILES[@]}"; do
      local root rest sub header

      root="${f%%/*}"
      rest="${f#*/}"

      sub=""
      if [[ -n "$rest" && "$rest" == */* ]]; then
        sub="${rest%%/*}"
      fi

      if [[ "$root" != "$prev_root" ]]; then
        printf '\n%s\n' "=== ${root^^} ==="
        prev_root="$root"
        prev_sub=""
      fi

      if [[ -n "$sub" && "$root/$sub" != "$prev_sub" ]]; then
        printf '%s\n' "--- ${root}/${sub} ---"
        prev_sub="$root/$sub"
      fi

      printf '\n%s\n' "----- FILE: ${f} -----"
      cat -- "$f"
    done

    printf '\n'
    printf '%s\n' "===================== END FILE DUMP ========================="
  } > "$tmp"

  mkdir -p "$(dirname "$out_path")"
  mv -f "$tmp" "$out_path"
  printf '%s\n' "$out_path"
}

# ---------- Subset selection helper ----------
build_subset_files() {
  local name="$1"
  local name_up
  name_up="$(echo "$name" | tr '[:lower:]' '[:upper:]')"

  local subset=()
  local f root

  for f in "${FILES[@]}"; do
    if [[ "$f" == */* ]]; then
      root="${f%%/*}"
    else
      root="(root)"
    fi

    # Match "(root)" explicitly or top-level dir name case-insensitively
    if [[ "$name_up" == "(ROOT)" ]]; then
      if [[ "$root" == "(root)" ]]; then
        subset+=("$f")
      fi
    else
      if [[ "$(echo "$root" | tr '[:lower:]' '[:upper:]')" == "$name_up" ]]; then
        subset+=("$f")
      fi
    fi
  done

  FILES=("${subset[@]}")
}

# ---------- Mode execution ----------
case "$MODE" in
  manual)
    mkdir -p "$BACKUPS_DIR"
    if [[ -n "$LABEL_SAFE" ]]; then
      BPATH="${BACKUPS_DIR}/dump_${TS}_${LABEL_SAFE}.txt"
    else
      BPATH="${BACKUPS_DIR}/dump_${TS}.txt"
    fi
    BPATH_RET="$(write_dump "$BPATH")"
    printf '%s\n' "Backup: $BPATH_RET"

    MPATH_RET="$(write_dump "$MAIN_OUT")"
    printf '%s\n' "Main:   $MPATH_RET"
    ;;
  backup)
    mkdir -p "$BACKUPS_DIR"
    if [[ -n "$LABEL_SAFE" ]]; then
      BPATH="${BACKUPS_DIR}/dump_${TS}_${LABEL_SAFE}.txt"
    else
      BPATH="${BACKUPS_DIR}/dump_${TS}.txt"
    fi
    BPATH_RET="$(write_dump "$BPATH")"
    printf '%s\n' "Backup: $BPATH_RET"
    ;;
  main)
    MPATH_RET="$(write_dump "$MAIN_OUT")"
    printf '%s\n' "Main:   $MPATH_RET"
    ;;
  subset)
    if [[ -z "$SUBSET_NAME" ]]; then
      echo "ERROR: --mode subset requires --subset NAME (e.g. src, tools, (root))" >&2
      exit 2
    fi
    mkdir -p "$BACKUPS_DIR"

    build_subset_files "$SUBSET_NAME"

    if ((${#FILES[@]} == 0)); then
      echo "No files matched subset '${SUBSET_NAME}'" >&2
      exit 1
    fi

    SUBSET_SAFE="$(echo "$SUBSET_NAME" | tr -cs 'A-Za-z0-9._+-' '_' | sed 's/^_//; s/_$//')"
    if [[ -n "$LABEL_SAFE" ]]; then
      SUB_OUT="${BACKUPS_DIR}/dump_${TS}_${SUBSET_SAFE}_${LABEL_SAFE}.txt"
    else
      SUB_OUT="${BACKUPS_DIR}/dump_${TS}_${SUBSET_SAFE}.txt"
    fi

    SUBPATH_RET="$(write_dump "$SUB_OUT")"
    printf '%s\n' "Subset dump (${SUBSET_NAME}): $SUBPATH_RET"
    ;;
  *)
    echo "Invalid --mode: $MODE (expected manual|backup|main|subset)"; exit 2;;
esac
