#!/usr/bin/env bash
# OpenHarness one-click installer
# Usage: curl -fsSL https://raw.githubusercontent.com/HKUDS/OpenHarness/main/scripts/install.sh | bash
#        bash scripts/install.sh [--from-source] [--with-channels]

set -euo pipefail

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
FROM_SOURCE=false
WITH_CHANNELS=false

for arg in "$@"; do
    case "$arg" in
        --from-source)  FROM_SOURCE=true ;;
        --with-channels) WITH_CHANNELS=true ;;
        --help|-h)
            echo "Usage: $0 [--from-source] [--with-channels]"
            echo ""
            echo "  --from-source    Clone from GitHub and install in editable mode"
            echo "  --with-channels  Deprecated compatibility flag."
            echo "                   Common IM channel dependencies are installed by default."
            exit 0
            ;;
        *)
            error "Unknown argument: $arg"
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}${CYAN}  ██████╗ ██╗  ██╗${RESET}"
echo -e "${BOLD}${CYAN} ██╔═══██╗██║  ██║${RESET}"
echo -e "${BOLD}${CYAN} ██║   ██║███████║${RESET}   OpenHarness Installer"
echo -e "${BOLD}${CYAN} ██║   ██║██╔══██║${RESET}   Open Agent Harness"
echo -e "${BOLD}${CYAN} ╚██████╔╝██║  ██║${RESET}"
echo -e "${BOLD}${CYAN}  ╚═════╝ ╚═╝  ╚═╝${RESET}"
echo ""

# ---------------------------------------------------------------------------
# Step 1: Detect OS
# ---------------------------------------------------------------------------
step "Detecting operating system"

OS_TYPE="unknown"
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Check for WSL
    if grep -qi microsoft /proc/version 2>/dev/null; then
        OS_TYPE="WSL"
    else
        OS_TYPE="Linux"
    fi
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS_TYPE="macOS"
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
    OS_TYPE="Windows (Git Bash)"
fi

info "OS detected: ${BOLD}${OS_TYPE}${RESET}"

# ---------------------------------------------------------------------------
# Step 2: Check Python >= 3.10
# ---------------------------------------------------------------------------
step "Checking Python version (>= 3.10 required)"

PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
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
    echo ""
    echo "  Please install Python 3.10 or newer:"
    case "$OS_TYPE" in
        macOS)
            echo "    brew install python@3.12"
            echo "  or download from: https://www.python.org/downloads/"
            ;;
        Linux|WSL)
            echo "    sudo apt update && sudo apt install -y python3 python3-pip  # Debian/Ubuntu"
            echo "    sudo dnf install -y python3                                 # Fedora/RHEL"
            echo "  or download from: https://www.python.org/downloads/"
            ;;
        *)
            echo "    Download from: https://www.python.org/downloads/"
            ;;
    esac
    echo ""
    exit 1
fi

PY_VERSION=$("$PYTHON_CMD" --version 2>&1)
success "Found ${PY_VERSION} (${PYTHON_CMD})"

# Determine pip command
PIP_CMD=""
for cmd in pip3 pip; do
    if command -v "$cmd" &>/dev/null; then
        PIP_CMD="$cmd"
        break
    fi
done

if [ -z "$PIP_CMD" ]; then
    # Try python -m pip
    if "$PYTHON_CMD" -m pip --version &>/dev/null 2>&1; then
        PIP_CMD="$PYTHON_CMD -m pip"
    else
        error "pip not found. Please install pip:"
        echo "    $PYTHON_CMD -m ensurepip --upgrade"
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
# Step 3: Check Node.js >= 18
# ---------------------------------------------------------------------------
step "Checking Node.js version (>= 18 required for React TUI)"

NODE_OK=false
if command -v node &>/dev/null; then
    NODE_VER=$(node --version 2>&1 | grep -oE '[0-9]+' | head -1)
    if [ "${NODE_VER}" -ge 18 ] 2>/dev/null; then
        NODE_OK=true
        success "Found Node.js $(node --version)"
    else
        warn "Node.js $(node --version) is too old (need >= 18). React TUI will be skipped."
    fi
else
    warn "Node.js not found. React TUI will be skipped."
    echo "  To enable the React terminal UI, install Node.js 18+:"
    case "$OS_TYPE" in
        macOS)
            echo "    brew install node"
            ;;
        Linux|WSL)
            echo "    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -"
            echo "    sudo apt install -y nodejs"
            ;;
        *)
            echo "    Download from: https://nodejs.org/"
            ;;
    esac
fi

# ---------------------------------------------------------------------------
# Step 4: Install OpenHarness
# ---------------------------------------------------------------------------
step "Installing OpenHarness"

REPO_URL="https://github.com/HKUDS/OpenHarness.git"
INSTALL_DIR="$HOME/.openharness-src"
VENV_DIR="$HOME/.openharness-venv"

# ---------------------------------------------------------------------------
# Create a virtual environment to avoid PEP 668 externally-managed errors
# ---------------------------------------------------------------------------
if [ -d "$VENV_DIR" ] && [ ! -f "$VENV_DIR/bin/activate" ]; then
    warn "Found incomplete virtual environment at ${VENV_DIR}; recreating it..."
    rm -rf "$VENV_DIR"
fi

if [ ! -f "$VENV_DIR/bin/activate" ]; then
    info "Creating virtual environment at ${VENV_DIR}..."
    "$PYTHON_CMD" -m venv "$VENV_DIR"
fi

# Activate the venv — all pip installs go here
source "$VENV_DIR/bin/activate"
PYTHON_CMD="python"
PIP_CMD="pip"
success "Virtual environment ready: ${VENV_DIR}"

if [ "$FROM_SOURCE" = true ]; then
    info "Mode: --from-source (git clone + pip install -e .)"

    if command -v git &>/dev/null; then
        if [ -d "$INSTALL_DIR/.git" ]; then
            info "Source directory exists, pulling latest changes..."
            git -C "$INSTALL_DIR" pull --ff-only
        else
            info "Cloning OpenHarness into ${INSTALL_DIR}..."
            git clone "$REPO_URL" "$INSTALL_DIR"
        fi
    else
        error "git is required for --from-source installation."
        echo "  Install git and retry:"
        case "$OS_TYPE" in
            macOS)   echo "    brew install git" ;;
            Linux|WSL) echo "    sudo apt install -y git" ;;
        esac
        exit 1
    fi

    info "Installing in editable mode (pip install -e .)..."
    $PIP_CMD install -e "$INSTALL_DIR" --quiet
else
    info "Mode: pip install openharness-ai"
    $PIP_CMD install openharness-ai --quiet --upgrade
fi

success "OpenHarness package installed"

# ---------------------------------------------------------------------------
# Step 5: Channel dependencies
# ---------------------------------------------------------------------------
if [ "$WITH_CHANNELS" = true ]; then
    step "Channel dependencies"
    info "--with-channels is no longer required; common IM channel dependencies are installed by default."
fi

# ---------------------------------------------------------------------------
# Step 6: Install frontend/terminal npm dependencies
# ---------------------------------------------------------------------------
if [ "$NODE_OK" = true ]; then
    # Determine the frontend/terminal path
    if [ "$FROM_SOURCE" = true ]; then
        FRONTEND_DIR="$INSTALL_DIR/frontend/terminal"
    else
        FRONTEND_DIR="$(pwd)/frontend/terminal"
    fi

    if [ -d "$FRONTEND_DIR" ] && [ -f "$FRONTEND_DIR/package.json" ]; then
        step "Installing React TUI dependencies"
        info "Running npm install in ${FRONTEND_DIR}..."
        (cd "$FRONTEND_DIR" && npm install --no-fund --no-audit --silent)
        success "React TUI dependencies installed"
    else
        info "No frontend/terminal directory found — skipping npm install"
    fi
fi

# ---------------------------------------------------------------------------
# Step 7: Create OpenHarness config directory
# ---------------------------------------------------------------------------
step "Setting up OpenHarness config directory"

mkdir -p "$HOME/.openharness"
mkdir -p "$HOME/.openharness/skills"
mkdir -p "$HOME/.openharness/plugins"

success "Config directory ready: ~/.openharness/"

# ---------------------------------------------------------------------------
# Step 8: Verify installation
# ---------------------------------------------------------------------------
step "Verifying installation"

if command -v oh &>/dev/null && command -v ohmo &>/dev/null; then
    OH_VERSION=$(oh --version 2>&1 || echo "(version check failed)")
    OHMO_VERSION=$(ohmo --help >/dev/null 2>&1 && echo "available" || echo "not available")
    success "Installation successful!"
    echo ""
    echo -e "  ${BOLD}oh${RESET} is ready: ${GREEN}${OH_VERSION}${RESET}"
    echo -e "  ${BOLD}ohmo${RESET} is ready: ${GREEN}${OHMO_VERSION}${RESET}"
elif "$PYTHON_CMD" -m openharness --version &>/dev/null 2>&1; then
    OH_VERSION=$("$PYTHON_CMD" -m openharness --version 2>&1)
    warn "'oh'/'ohmo' not in PATH. Run via: python -m openharness or python -m ohmo"
    echo "  Version: ${OH_VERSION}"
    echo "  To add them to PATH, ensure ${VENV_DIR}/bin is in PATH:"
    echo "    export PATH=\"${VENV_DIR}/bin:\$PATH\""
else
    warn "Could not verify 'oh'/'ohmo' commands. The package may need a PATH update."
    echo "  Try: $PYTHON_CMD -m openharness --version"
    echo "  Or add ${VENV_DIR}/bin to PATH and restart your shell."
fi

# ---------------------------------------------------------------------------
# Step 9: Add venv activation to shell profile
# ---------------------------------------------------------------------------
step "Setting up shell integration"

ACTIVATION_LINE="export PATH=\"$VENV_DIR/bin:\$PATH\""
FISH_CONFIG="$HOME/.config/fish/config.fish"
FISH_BLOCK=$(cat <<EOF
# OpenHarness
if not contains -- "$VENV_DIR/bin" \$PATH
    set -gx PATH "$VENV_DIR/bin" \$PATH
end
EOF
)

configured_any=false

append_shell_path() {
    local rc_file="$1"
    if [ ! -f "$rc_file" ]; then
        return
    fi
    if grep -q "$VENV_DIR/bin" "$rc_file" 2>/dev/null; then
        info "PATH already configured in $(basename "$rc_file")"
        configured_any=true
        return
    fi
    echo "" >> "$rc_file"
    echo "# OpenHarness" >> "$rc_file"
    echo "$ACTIVATION_LINE" >> "$rc_file"
    success "Added $VENV_DIR/bin to PATH in $(basename "$rc_file")"
    configured_any=true
}

append_shell_path "$HOME/.zshrc"
append_shell_path "$HOME/.bashrc"
append_shell_path "$HOME/.bash_profile"

mkdir -p "$(dirname "$FISH_CONFIG")"
if [ -f "$FISH_CONFIG" ] && grep -q "$VENV_DIR/bin" "$FISH_CONFIG" 2>/dev/null; then
    info "PATH already configured in $(basename "$FISH_CONFIG")"
    configured_any=true
else
    echo "" >> "$FISH_CONFIG"
    printf "%s\n" "$FISH_BLOCK" >> "$FISH_CONFIG"
    success "Added $VENV_DIR/bin to PATH in $(basename "$FISH_CONFIG")"
    configured_any=true
fi

if [ "$configured_any" = false ]; then
    warn "Could not find shell config file. Add this to your shell profile:"
    echo "    $ACTIVATION_LINE"
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}${GREEN}OpenHarness is installed!${RESET}"
echo ""
echo "  Next steps:"
echo "    1. Restart shell, or reload your shell config:"
echo "         bash/zsh: source ~/.bashrc  (or ~/.zshrc)"
echo "         fish:     source ~/.config/fish/config.fish"
echo "    2. Set your API key:        export ANTHROPIC_API_KEY=your_key"
echo "    3. Launch:                  oh"
echo "    4. Launch ohmo:             ohmo"
echo "    5. Docs:                    https://github.com/HKUDS/OpenHarness"
echo ""
