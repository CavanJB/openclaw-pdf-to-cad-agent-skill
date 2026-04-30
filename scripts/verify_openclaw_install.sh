#!/usr/bin/env bash
set -euo pipefail

SKILL_NAME="openclaw-pdf-to-cad"
SKILLS_DIR="${OPENCLAW_SKILLS_DIR:-$HOME/.openclaw/workspace-cadbot/skills}"

usage() {
  cat <<'EOF'
Verify that openclaw-pdf-to-cad is installed as an OpenClaw skill.

Usage:
  scripts/verify_openclaw_install.sh [--skills-dir PATH]
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --skills-dir)
      SKILLS_DIR="${2:?missing path after --skills-dir}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

SKILL_DIR="$SKILLS_DIR/$SKILL_NAME"
ENTRYPOINT="$SKILL_DIR/scripts/run_pdf_to_cad.sh"
PY_SCRIPT="$SKILL_DIR/scripts/openclaw_pdf_to_cad.py"
MANIFEST="$SKILL_DIR/openclaw.skill.json"
INSTALL_RECORD="$SKILL_DIR/OPENCLAW_INSTALL.json"

missing=()
for path in "$SKILL_DIR/SKILL.md" "$MANIFEST" "$ENTRYPOINT" "$PY_SCRIPT" "$INSTALL_RECORD"; do
  if [ ! -e "$path" ]; then
    missing+=("$path")
  fi
done

if [ "${#missing[@]}" -gt 0 ]; then
  printf '{\n  "ok": false,\n  "skill": "%s",\n  "installed_to": "%s",\n  "missing": [\n' "$SKILL_NAME" "$SKILL_DIR"
  for i in "${!missing[@]}"; do
    comma=","
    [ "$i" -eq "$((${#missing[@]} - 1))" ] && comma=""
    printf '    "%s"%s\n' "${missing[$i]}" "$comma"
  done
  printf '  ]\n}\n'
  exit 1
fi

if [ ! -x "$ENTRYPOINT" ]; then
  echo "{\"ok\": false, \"skill\": \"$SKILL_NAME\", \"installed_to\": \"$SKILL_DIR\", \"error\": \"entrypoint is not executable\"}"
  exit 1
fi

if ! "$ENTRYPOINT" --help >/dev/null; then
  echo "{\"ok\": false, \"skill\": \"$SKILL_NAME\", \"installed_to\": \"$SKILL_DIR\", \"error\": \"entrypoint help check failed\"}"
  exit 1
fi

cat <<EOF
{
  "ok": true,
  "skill": "$SKILL_NAME",
  "target_runtime": "openclaw",
  "installed_to": "$SKILL_DIR",
  "entrypoint": "$ENTRYPOINT",
  "manifest": "$MANIFEST",
  "install_record": "$INSTALL_RECORD"
}
EOF
