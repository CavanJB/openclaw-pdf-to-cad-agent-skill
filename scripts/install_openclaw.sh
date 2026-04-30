#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_NAME="openclaw-pdf-to-cad"
DEFAULT_SKILLS_DIR="${OPENCLAW_SKILLS_DIR:-$HOME/.openclaw/workspace-cadbot/skills}"
DEST_DIR="$DEFAULT_SKILLS_DIR/$SKILL_NAME"
MODE="copy"

usage() {
  cat <<'EOF'
Install the OpenClaw PDF-to-CAD skill into an OpenClaw skills directory.

Usage:
  scripts/install_openclaw.sh [--skills-dir PATH] [--symlink]

Options:
  --skills-dir PATH  OpenClaw skills directory. Defaults to
                     ~/.openclaw/workspace-cadbot/skills
  --symlink          Symlink the skill directory instead of copying it.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --skills-dir)
      DEFAULT_SKILLS_DIR="${2:?missing path after --skills-dir}"
      DEST_DIR="$DEFAULT_SKILLS_DIR/$SKILL_NAME"
      shift 2
      ;;
    --symlink)
      MODE="symlink"
      shift
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

mkdir -p "$DEFAULT_SKILLS_DIR"

if [ -e "$DEST_DIR" ] || [ -L "$DEST_DIR" ]; then
  BACKUP_DIR="${DEST_DIR}.bak.$(date +%Y%m%d%H%M%S)"
  mv "$DEST_DIR" "$BACKUP_DIR"
  echo "Existing skill moved to: $BACKUP_DIR"
fi

if [ "$MODE" = "symlink" ]; then
  ln -s "$ROOT/skills/$SKILL_NAME" "$DEST_DIR"
else
  mkdir -p "$DEST_DIR"
  rsync -a --delete "$ROOT/skills/$SKILL_NAME/" "$DEST_DIR/"
fi

python3 -m venv "$DEST_DIR/.venv"
"$DEST_DIR/.venv/bin/python" -m pip install --upgrade pip >/dev/null
"$DEST_DIR/.venv/bin/python" -m pip install -r "$ROOT/requirements.txt" >/dev/null

cat > "$DEST_DIR/OPENCLAW_INSTALL.json" <<EOF
{
  "skill": "$SKILL_NAME",
  "installed_to": "$DEST_DIR",
  "source_repository": "$ROOT",
  "entrypoint": "$DEST_DIR/scripts/run_pdf_to_cad.sh",
  "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

echo "Installed OpenClaw skill: $DEST_DIR"
echo "Entrypoint: $DEST_DIR/scripts/run_pdf_to_cad.sh"
