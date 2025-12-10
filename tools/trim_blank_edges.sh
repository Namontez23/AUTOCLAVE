#!/usr/bin/env bash
# Trim leading/trailing blank lines, ensure exactly one trailing newline.
# Optional:
#   - Collapse interior blank-line runs to a single blank (threshold >= N)
#   - Normalize CRLF -> LF
#
# Usage:
#   tools/trim_blank_edges.sh [--dry-run] [--collapse[=N] | --min-run=N] [--eol=lf]
# Examples:
#   tools/trim_blank_edges.sh --dry-run --collapse          # collapse runs >=3
#   tools/trim_blank_edges.sh --collapse=2                  # collapse runs >=2
#   tools/trim_blank_edges.sh --collapse --eol=lf           # also normalize EOLs
#   MIN_RUN=2 tools/trim_blank_edges.sh --collapse          # env override
set -euo pipefail
LC_ALL=C

DRY=0
EOL_MODE="keep"    # keep|lf
# Collapse control: disabled unless COLLAPSE=1; threshold MIN_RUN (>=2 recommended)
COLLAPSE=0
MIN_RUN="${MIN_RUN:-3}"

# ---- Args ----
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY=1;;
    --eol=lf)  EOL_MODE="lf";;
    --collapse)
      COLLAPSE=1
      # MIN_RUN stays whatever env set or default=3
      ;;
    --collapse=*)
      COLLAPSE=1
      MIN_RUN="${1#*=}"
      if ! [[ "$MIN_RUN" =~ ^[0-9]+$ ]]; then
        echo "Invalid --collapse value: ${MIN_RUN}" >&2; exit 2
      fi
      ;;
    --min-run=*)
      MIN_RUN="${1#*=}"
      if ! [[ "$MIN_RUN" =~ ^[0-9]+$ ]]; then
        echo "Invalid --min-run value: ${MIN_RUN}" >&2; exit 2
      fi
      ;;
    -h|--help)
      cat <<'HLP'
Usage: tools/trim_blank_edges.sh [--dry-run] [--collapse[=N] | --min-run=N] [--eol=lf]
  --dry-run      : Show what would change, without writing files
  --collapse     : Collapse interior blank-line runs (default threshold N=3)
  --collapse=N   : Collapse runs of >= N blank lines (N >= 2 recommended)
  --min-run=N    : Alias to set threshold N (works with --collapse)
  --eol=lf       : Normalize CRLF to LF during processing
Environment:
  MIN_RUN        : Threshold if --collapse is set (default 3)
Notes:
  * Only blank lines are modified (plus optional CR removal when --eol=lf).
  * Leading/trailing blank regions are removed, and exactly one newline is ensured at EOF.
  * Only safe, text-like files are included using the policy below.
HLP
      exit 0;;
    *) echo "Unknown arg: $1" >&2; exit 2;;
  esac
  shift
done

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

# ==== File selection: mirror dump_for_chat include policy (safe text/code only) ====
INCLUDE_GLOBS=(
  "*.c" "*.h" "CMakeLists.txt" "*.cmake" "*.txt" "*.md" "sdkconfig.defaults" "Kconfig*"
)
ALWAYS_INCLUDE_FILES=(
  ".vscode/settings.json"
)

EXCLUDE_DIRS=( "build" ".git" ".idea" "backups" )
EXCLUDE_FILE_GLOBS=( "sdkconfig" "*.bin" "*.elf" "*.map" "*.o" "*.a" "*.pyc" "*.swp" "*.tmp" "*~" )
EXCLUDE_PATHS=( "_dump_for_chat.txt" )

FIND_ARGS=()
for d in "${EXCLUDE_DIRS[@]}"; do FIND_ARGS+=( -path "./$d" -prune -o ); done
FIND_ARGS+=( -type f \( )
for i in "${!INCLUDE_GLOBS[@]}"; do
  (( i > 0 )) && FIND_ARGS+=( -o )
  FIND_ARGS+=( -name "${INCLUDE_GLOBS[$i]}" )
done
FIND_ARGS+=( \) )
for g in "${EXCLUDE_FILE_GLOBS[@]}"; do FIND_ARGS+=( ! -name "$g" ); done
for p in "${EXCLUDE_PATHS[@]}";    do FIND_ARGS+=( ! -path "./$p" ); done

mapfile -t FILES < <(
  {
    find . "${FIND_ARGS[@]}" -print
    for f in "${ALWAYS_INCLUDE_FILES[@]}"; do [[ -f "$f" ]] && echo "./$f"; done
  } | sed 's|^\./||' | sort -u
)

# Treat as text if grep sees any bytes as text (exclude binary)
is_text_file(){ grep -Iq . -- "$1"; }

process_file(){
  local file="$1"
  # We normalize CR only if EOL_MODE=lf; otherwise we keep original CRs in output.
  # Implementation detail: we always strip CR when reading (so awk logic is simple),
  # then optionally re-add CR if original file had CRLF and EOL_MODE=keep.
  local had_crlf=0
  if [[ "$EOL_MODE" == "keep" ]]; then
    if grep -q $'\r$' "$file"; then had_crlf=1; fi
  fi

  awk -v collapse="$COLLAPSE" -v minrun="$MIN_RUN" -v eol_mode="$EOL_MODE" -v had_crlf="$had_crlf" '
    function outln(s){
      # Output with LF during processing; CR handling is done after
      print s
    }
    BEGIN{ run=0; ln=0; }
    {
      gsub(/\r/, "");      # view as LF in-memory
      lines[NR]=$0
    }
    END{
      N=NR
      # Locate first/last non-blank
      first=1
      while (first<=N && lines[first] ~ /^[[:space:]]*$/) first++
      last=N
      while (last>=first && lines[last] ~ /^[[:space:]]*$/) last--

      if (first>last){
        # All blank -> single newline
        outln(""); exit
      }

      prev_blank=0; run=0
      for(i=first;i<=last;i++){
        is_blank = (lines[i] ~ /^[[:space:]]*$/)
        if (is_blank){
          run++
          if (collapse==1){
            # Only emit a single blank for a run >=1, but gate on threshold
            # Implement threshold logic by not emitting until we know run size:
            # Instead, we buffer run and only emit if needed when next non-blank arrives.
            # To keep memory light, just track count; defer emission.
            if (i==last){
              # End-of-file run -> drop (no trailing blanks)
              # do nothing
            }
          } else {
            # Preserve raw blanks when not collapsing
            outln("")
          }
          prev_blank=1
        } else {
          # Before printing non-blank, handle any pending run:
          if (collapse==1 && run>0){
            if (run >= minrun){
              # collapse to exactly one blank (but not before first content)
              if (ln>0) outln("")
            } else {
              # Keep short runs verbatim
              for (k=0; k<run; k++) outln("")
            }
            run=0
          }
          outln(lines[i]); ln++
          prev_blank=0
        }
      }
      # Exactly one trailing newline already ensured by print semantics
    }
  ' "$file"
}

changed=0 checked=0
for f in "${FILES[@]}"; do
  [[ -f "$f" ]] || continue
  is_text_file "$f" || continue

  checked=$((checked+1))
  tmp="${f}.trim.$$"

  process_file "$f" > "$tmp"

  # Re-add CRLF if we preserved EOLs and the original had CRLFs
  if [[ "$EOL_MODE" == "keep" ]] && grep -q $'\r$' "$f"; then
    # Convert LF->CRLF in tmp
    awk '{ sub(/\r$/,""); printf "%s\r\n", $0 }' RS='\n' ORS='' "$tmp" > "${tmp}.crlf"
    mv -f "${tmp}.crlf" "$tmp"
  fi

  if ! cmp -s "$f" "$tmp"; then
    if (( DRY )); then
      echo "[DRY] would fix: $f"
      rm -f -- "$tmp"
    else
      mv -- "$tmp" "$f"
      echo "fixed: $f"
    fi
    changed=$((changed+1))
  else
    rm -f -- "$tmp"
  fi
done

if (( DRY )); then
  echo "== DRY-RUN COMPLETE =="; echo "Checked: $checked"; echo "Would change: $changed"
else
  echo "== DONE =="; echo "Checked: $checked"; echo "Changed: $changed"
fi
