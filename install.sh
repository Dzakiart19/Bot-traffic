#!/bin/bash
set -e

GREEN='\033[1;32m'
YELLOW='\033[1;33m'
RED='\033[1;31m'
BLUE='\033[1;34m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[✓]${NC} $1"; }
info() { echo -e "${BLUE}[i]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
fail() { echo -e "${RED}[✗]${NC} $1"; exit 1; }

echo ""
echo -e "${GREEN}╔══════════════════════════════════════╗"
echo -e "║         BOT MONITOR  INSTALLER       ║"
echo -e "╚══════════════════════════════════════╝${NC}"
echo ""

# ── 1. Detect OS ────────────────────────────────────────────
info "Mendeteksi sistem operasi..."

if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    OS=$(uname -s | tr '[:upper:]' '[:lower:]')
fi

info "OS terdeteksi: $OS"

# ── 2. Python 3 ─────────────────────────────────────────────
info "Memeriksa Python 3..."
if command -v python3 &>/dev/null; then
    PY_VER=$(python3 --version 2>&1)
    ok "Python sudah ada: $PY_VER"
else
    info "Menginstall Python 3..."
    case "$OS" in
        ubuntu|debian|linuxmint|pop)
            sudo apt-get update -qq
            sudo apt-get install -y python3 python3-pip python3-venv
            ;;
        fedora|rhel|centos)
            sudo dnf install -y python3 python3-pip
            ;;
        arch|manjaro)
            sudo pacman -Sy --noconfirm python python-pip
            ;;
        *)
            fail "OS tidak dikenali. Install Python 3 secara manual lalu jalankan ulang script ini."
            ;;
    esac
    ok "Python 3 berhasil diinstall"
fi

# ── 3. pip ──────────────────────────────────────────────────
info "Memeriksa pip..."
if ! command -v pip3 &>/dev/null && ! python3 -m pip --version &>/dev/null 2>&1; then
    info "Menginstall pip..."
    case "$OS" in
        ubuntu|debian|linuxmint|pop)
            sudo apt-get install -y python3-pip
            ;;
        *)
            curl -sS https://bootstrap.pypa.io/get-pip.py | python3
            ;;
    esac
fi
ok "pip siap"

# ── 4. Firefox ──────────────────────────────────────────────
info "Memeriksa Firefox..."
if command -v firefox &>/dev/null; then
    FF_VER=$(firefox --version 2>/dev/null | head -1)
    ok "Firefox sudah ada: $FF_VER"
else
    info "Menginstall Firefox..."
    case "$OS" in
        ubuntu|debian|linuxmint|pop)
            sudo apt-get update -qq
            sudo apt-get install -y firefox
            ;;
        fedora|rhel|centos)
            sudo dnf install -y firefox
            ;;
        arch|manjaro)
            sudo pacman -Sy --noconfirm firefox
            ;;
        darwin)
            if command -v brew &>/dev/null; then
                brew install --cask firefox
            else
                fail "Homebrew tidak ditemukan. Install Firefox manual dari https://www.mozilla.org"
            fi
            ;;
        *)
            warn "Tidak bisa install Firefox otomatis. Download manual dari https://www.mozilla.org"
            ;;
    esac
    ok "Firefox berhasil diinstall"
fi

# ── 5. Geckodriver ──────────────────────────────────────────
info "Memeriksa Geckodriver..."
if command -v geckodriver &>/dev/null; then
    GK_VER=$(geckodriver --version 2>&1 | head -1)
    ok "Geckodriver sudah ada: $GK_VER"
else
    info "Menginstall Geckodriver..."

    GECKO_VERSION="0.36.0"
    ARCH=$(uname -m)

    case "$OS" in
        ubuntu|debian|linuxmint|pop)
            sudo apt-get install -y wget tar
            ;;
    esac

    case "$ARCH" in
        x86_64|amd64) GECKO_ARCH="linux64" ;;
        aarch64|arm64) GECKO_ARCH="linux-aarch64" ;;
        i686|i386) GECKO_ARCH="linux32" ;;
        *)
            if [[ "$OS" == "darwin" ]]; then
                ARCH_MAC=$(uname -m)
                if [[ "$ARCH_MAC" == "arm64" ]]; then GECKO_ARCH="macos-aarch64"
                else GECKO_ARCH="macos"; fi
            else
                fail "Arsitektur $ARCH tidak didukung"
            fi
            ;;
    esac

    GECKO_URL="https://github.com/mozilla/geckodriver/releases/download/v${GECKO_VERSION}/geckodriver-v${GECKO_VERSION}-${GECKO_ARCH}.tar.gz"
    info "Download dari: $GECKO_URL"
    wget -q "$GECKO_URL" -O /tmp/geckodriver.tar.gz
    tar -xzf /tmp/geckodriver.tar.gz -C /tmp
    sudo mv /tmp/geckodriver /usr/local/bin/geckodriver
    sudo chmod +x /usr/local/bin/geckodriver
    rm -f /tmp/geckodriver.tar.gz
    ok "Geckodriver v${GECKO_VERSION} berhasil diinstall"
fi

# ── 6. Python packages ──────────────────────────────────────
info "Menginstall Python packages..."
python3 -m pip install --upgrade pip -q
python3 -m pip install \
    requests \
    beautifulsoup4 \
    selenium \
    flask \
    flask-socketio \
    -q
ok "Semua Python packages berhasil diinstall"

# ── 7. Verifikasi ───────────────────────────────────────────
echo ""
info "Verifikasi instalasi..."
python3 -c "import requests, bs4, selenium, flask, flask_socketio; print('OK')" \
    && ok "Semua modul Python bisa diimport" \
    || fail "Ada modul yang gagal diimport!"

command -v firefox    &>/dev/null && ok "Firefox   : $(firefox --version 2>/dev/null | head -1)"
command -v geckodriver &>/dev/null && ok "Geckodriver: $(geckodriver --version 2>&1 | head -1)"

# ── Done ─────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════╗"
echo -e "║     INSTALASI SELESAI! 🎉             ║"
echo -e "╚══════════════════════════════════════╝${NC}"
echo ""
echo -e "  Jalankan bot dengan:"
echo -e "  ${YELLOW}python3 app.py${NC}"
echo ""
