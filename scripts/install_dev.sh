#!/usr/bin/env bash
# Developer install for the current checkout.
# Usage:
#   bash scripts/install_dev.sh
#   bash scripts/install_dev.sh --global-venv
#   bash scripts/install_dev.sh --with-channels

set -euo pipefail

if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    RESET='\033[0m'
else
    RED='' GREEN='' YELLOW='' BLUE='' CYAN='' BOLD='' RESET=''
fi

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
step()    { echo -e "\n${BOLD}${BLUE}==>${RESET}${BOLD} $*${RESET}"; }

WITH_CHANNELS=false
GLOBAL_VENV=false

for arg in "$@"; do
    case "$arg" in
        --with-channels) WITH_CHANNELS=true ;;
        --global-venv) GLOBAL_VENV=true ;;
        --help|-h)
            echo "Usage: $0 [--with-channels] [--global-venv]"
            echo ""
            echo "Installs the current checkout in editable mode and"
            echo "registers oh/ohmo in ~/.local/bin."
            echo ""
            echo "  default         use ./ .openharness-venv inside the current repo"
            echo "  --global-venv   use ~/.openharness-venv but still install the current repo"
            echo "  --with-channels deprecated compatibility flag; common IM deps install by default"
            exit 0
            ;;
        *)
            error "Unknown argument: $arg"
            exit 1
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
if [ "$GLOBAL_VENV" = true ]; then
    VENV_DIR="$HOME/.openharness-venv"
else
    VENV_DIR="$REPO_ROOT/.openharness-venv"
fi
BIN_DIR="$HOME/.local/bin"

step "Checking Python version (>= 3.10 required)"

PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
        PY_VER=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
        PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
        PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
        if [ "${PY_MAJOR}" -ge 3 ] && [ "${PY_MINOR}" -ge 10 ]; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    error "Python 3.10+ not found."
    exit 1
fi

success "Found $("$PYTHON_CMD" --version 2>&1) (${PYTHON_CMD})"

step "Preparing developer virtual environment"

if [ ! -d "$VENV_DIR" ]; then
    info "Creating virtual environment at ${VENV_DIR}"
    "$PYTHON_CMD" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip setuptools wheel --quiet
success "Virtual environment ready: ${VENV_DIR}"

step "Installing current checkout in editable mode"
python -m pip install -e "$REPO_ROOT" --quiet
success "Installed OpenHarness from ${REPO_ROOT}"

if [ "$WITH_CHANNELS" = true ]; then
    step "Channel dependencies"
    info "--with-channels is no longer required; common IM channel dependencies are installed by default."
fi

step "Installing React terminal dependencies (optional)"
if command -v node >/dev/null 2>&1; then
    NODE_MAJOR=$(node --version 2>&1 | grep -oE '[0-9]+' | head -1)
    FRONTEND_DIR="$REPO_ROOT/frontend/terminal"
    if [ "${NODE_MAJOR}" -ge 18 ] 2>/dev/null && [ -f "$FRONTEND_DIR/package.json" ]; then
        info "Running npm install in ${FRONTEND_DIR}"
        (cd "$FRONTEND_DIR" && npm install --no-fund --no-audit --silent)
        success "React terminal dependencies installed"
    else
        warn "Node.js too old or frontend directory missing; skipping npm install"
    fi
else
    warn "Node.js not found; skipping npm install"
fi

step "Registering global commands"

mkdir -p "$BIN_DIR"
ln -snf "$VENV_DIR/bin/oh" "$BIN_DIR/oh"
ln -snf "$VENV_DIR/bin/ohmo" "$BIN_DIR/ohmo"
ln -snf "$VENV_DIR/bin/openharness" "$BIN_DIR/openharness"
success "Linked oh/ohmo into ${BIN_DIR}"

ensure_path_in_file() {
    local rc_file="$1"
    local line="$2"
    [ -f "$rc_file" ] || return 0
    if ! grep -qF "$line" "$rc_file" 2>/dev/null; then
        echo "" >> "$rc_file"
        echo "# OpenHarness dev" >> "$rc_file"
        echo "$line" >> "$rc_file"
        success "Added ${BIN_DIR} to PATH in $(basename "$rc_file")"
    fi
}

step "Ensuring ~/.local/bin is on PATH"
mkdir -p "$HOME/.config/fish"
ensure_path_in_file "$HOME/.bashrc" "export PATH=\"$BIN_DIR:\$PATH\""
ensure_path_in_file "$HOME/.bash_profile" "export PATH=\"$BIN_DIR:\$PATH\""
ensure_path_in_file "$HOME/.zshrc" "export PATH=\"$BIN_DIR:\$PATH\""

if [ -f "$HOME/.config/fish/config.fish" ]; then
    if ! grep -qF "$BIN_DIR" "$HOME/.config/fish/config.fish" 2>/dev/null; then
        {
            echo ""
            echo "# OpenHarness dev"
            echo "if not contains -- \"$BIN_DIR\" \$PATH"
            echo "    set -gx PATH \"$BIN_DIR\" \$PATH"
            echo "end"
        } >> "$HOME/.config/fish/config.fish"
        success "Added ${BIN_DIR} to PATH in config.fish"
    fi
else
    cat > "$HOME/.config/fish/config.fish" <<EOF
# OpenHarness dev
if not contains -- "$BIN_DIR" \$PATH
    set -gx PATH "$BIN_DIR" \$PATH
end
EOF
    success "Created config.fish with ${BIN_DIR} on PATH"
fi

echo ""
echo -e "${BOLD}${GREEN}Developer install complete.${RESET}"
echo ""
echo "  Repo root:           $REPO_ROOT"
echo "  Virtual environment: $VENV_DIR"
echo "  Command links:       $BIN_DIR/oh , $BIN_DIR/ohmo"
echo ""
echo "  If this shell does not see the commands yet, run one of:"
echo "    bash: source ~/.bashrc"
echo "    zsh:  source ~/.zshrc"
echo "    fish: source ~/.config/fish/config.fish"
echo ""
echo "  Or use immediately in this shell:"
echo "    export PATH=\"$BIN_DIR:\$PATH\""
echo "    hash -r"
echo ""
