#!/usr/bin/env bash

set -e
set -u
set -o pipefail

# --- Configuration for Iconize Pro ---
APP_NAME="IconizePro"
SCRIPT_NAME="iconize_pro.py" # Make sure this matches your script filename
COMMENT_DESC="Create app icons (PNGs, ICOs) from images, including SVG"
# Python dependencies for Iconize Pro
PYTHON_DEPS="PyQt6 Pillow cairosvg qdarkstyle"
LAUNCHER_SCRIPT_NAME="iconize-pro"
# --- End Configuration ---

PREFERRED_ICON_NAME="icon.png" # Prefer PNG for theming
FALLBACK_ICON_NAME="icon.ico"
INSTALL_BASE_DIR="${HOME}/.local/share"
INSTALL_DIR="${INSTALL_BASE_DIR}/${APP_NAME}"
VENV_DIR="${INSTALL_DIR}/venv"
BIN_DIR="${HOME}/.local/bin"
LAUNCHER_SCRIPT_PATH="${BIN_DIR}/${LAUNCHER_SCRIPT_NAME}"
DESKTOP_ENTRY_DIR="${HOME}/.local/share/applications"
DESKTOP_ENTRY_NAME="${APP_NAME}.desktop"
DESKTOP_ENTRY_PATH="${DESKTOP_ENTRY_DIR}/${DESKTOP_ENTRY_NAME}"
# Icon location for system themes (Freedesktop standard)
ICON_INSTALL_DIR_BASE="${HOME}/.local/share/icons/hicolor"
ICON_INSTALL_DIR_PNG="${ICON_INSTALL_DIR_BASE}/scalable/apps" # PNGs are often treated as scalable

# --- Helper Functions ---
err() {
  echo "[!] Error: $*" >&2
  exit 1
}

msg() {
  echo "[*] $*"
}

warn() {
  echo "[!] Warning: $*" >&2
}

# --- Uninstall Function ---
uninstall() {
    msg "Starting uninstallation of ${APP_NAME}..."

    if [ -f "${DESKTOP_ENTRY_PATH}" ]; then
        msg "Removing desktop entry: ${DESKTOP_ENTRY_PATH}"
        rm -f "${DESKTOP_ENTRY_PATH}"
    fi

    # Also remove the potentially installed themed icon
    local THEMED_ICON_PATH="${ICON_INSTALL_DIR_PNG}/${APP_NAME}.png"
    if [ -f "${THEMED_ICON_PATH}" ]; then
         msg "Removing themed icon: ${THEMED_ICON_PATH}"
         rm -f "${THEMED_ICON_PATH}"
    fi

    # Try updating caches after removal
    if command -v update-desktop-database &> /dev/null; then
        msg "Updating desktop database..."
        update-desktop-database "${DESKTOP_ENTRY_DIR}" &> /dev/null || msg "  (Optional) Failed to update desktop database."
    fi
    if command -v gtk-update-icon-cache &> /dev/null; then
        msg "Updating icon cache..."
        gtk-update-icon-cache -f -t "${ICON_INSTALL_DIR_BASE}" &> /dev/null || msg "  (Optional) Failed to update icon cache."
    fi


    if [ -f "${LAUNCHER_SCRIPT_PATH}" ]; then
        msg "Removing launcher script: ${LAUNCHER_SCRIPT_PATH}"
        rm -f "${LAUNCHER_SCRIPT_PATH}"
    fi

    if [ -d "${INSTALL_DIR}" ]; then
        msg "Removing installation directory: ${INSTALL_DIR}"
        rm -rf "${INSTALL_DIR}"
    fi

    msg "${APP_NAME} uninstalled successfully."
    exit 0
}

# --- Installation Function ---
install() {
    msg "Starting installation of ${APP_NAME}..."

    msg "Checking prerequisites..."
    if ! command -v python3 &> /dev/null; then err "python3 not found"; fi
    msg "  [+] Python 3 found: $(command -v python3)"
    if ! python3 -c "import venv" &> /dev/null; then err "python3-venv module not found (often in python3-venv package)"; fi
    msg "  [+] Python 3 venv module found."

    # --- Crucial Warning about Cairosvg System Dependencies ---
    msg "---------------------------------------------------------------------"
    warn "IMPORTANT: This application uses 'cairosvg' for SVG support."
    warn "'cairosvg' requires system libraries (like Cairo, Pango, GDK-Pixbuf)"
    warn "that this script CANNOT install automatically."
    warn "Please ensure they are installed using your system's package manager"
    warn "BEFORE proceeding if you need SVG support. Examples:"
    warn "  Debian/Ubuntu: sudo apt update && sudo apt install libcairo2-dev libpango1.0-dev libgdk-pixbuf2.0-dev"
    warn "  Fedora:        sudo dnf install cairo-devel pango-devel gdk-pixbuf2-devel"
    warn "  Arch:          sudo pacman -S cairo pango gdk-pixbuf2"
    warn "Installation of Python dependencies might fail if these are missing."
    read -p "Press Enter to continue, or Ctrl+C to cancel and install system deps..." </dev/tty
    msg "---------------------------------------------------------------------"
    # --- End Warning ---

    SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
    msg "  [*] Looking for source files in: ${SCRIPT_DIR}"

    if [ ! -f "${SCRIPT_DIR}/${SCRIPT_NAME}" ]; then err "Application script not found: ${SCRIPT_DIR}/${SCRIPT_NAME}"; fi
    msg "  [+] Application script found."

    local SOURCE_ICON_PATH=""
    local FINAL_ICON_NAME=""
    local ICON_TYPE="none" # Track if we found png, ico, or none
    if [ -f "${SCRIPT_DIR}/${PREFERRED_ICON_NAME}" ]; then
        msg "  [+] Using preferred icon (PNG): ${PREFERRED_ICON_NAME}"
        SOURCE_ICON_PATH="${SCRIPT_DIR}/${PREFERRED_ICON_NAME}"
        FINAL_ICON_NAME="${PREFERRED_ICON_NAME}" # Keep .png extension
        ICON_TYPE="png"
    elif [ -f "${SCRIPT_DIR}/${FALLBACK_ICON_NAME}" ]; then
        msg "  [*] Using fallback icon (ICO): ${FALLBACK_ICON_NAME}"
        warn "    (A PNG icon is recommended for better desktop integration)"
        SOURCE_ICON_PATH="${SCRIPT_DIR}/${FALLBACK_ICON_NAME}"
        FINAL_ICON_NAME="${FALLBACK_ICON_NAME}" # Keep .ico extension
        ICON_TYPE="ico"
    else
        warn "  No icon file found ('${PREFERRED_ICON_NAME}' or '${FALLBACK_ICON_NAME}'). Installing without icon."
    fi

    msg "Creating directories..."
    mkdir -p "${INSTALL_DIR}"
    mkdir -p "${BIN_DIR}"
    mkdir -p "${DESKTOP_ENTRY_DIR}"
    # Only create png icon dir if we actually have a png
    if [ "${ICON_TYPE}" == "png" ]; then
        mkdir -p "${ICON_INSTALL_DIR_PNG}"
    fi
    msg "  [+] Directories created."

    msg "Creating Python virtual environment..."
    python3 -m venv "${VENV_DIR}" || err "Failed to create venv."
    msg "  [+] Virtual environment created."

    msg "Installing Python dependencies (${PYTHON_DEPS})..."
    msg "  (This may take a moment, especially for cairosvg compilation...)"
    # Activate venv for pip install
    # shellcheck source=/dev/null
    # source "${VENV_DIR}/bin/activate"
    "${VENV_DIR}/bin/pip" install --upgrade pip &> /dev/null
    # Use --no-cache-dir to potentially avoid issues with older caches
    if ! "${VENV_DIR}/bin/pip" install ${PYTHON_DEPS} --no-cache-dir; then
        warn "------------------------------------------------------------"
        warn "Failed to install Python dependencies."
        warn "This often happens if the system libraries for 'cairosvg'"
        warn "(Cairo, Pango, GDK-Pixbuf) are missing or incompatible."
        warn "Please review the warnings above and ensure the required"
        warn "system packages are installed correctly."
        warn "------------------------------------------------------------"
        err "Dependency installation failed."
    fi
    # deactivate
    msg "  [+] Dependencies installed."

    msg "Copying application files..."
    cp "${SCRIPT_DIR}/${SCRIPT_NAME}" "${INSTALL_DIR}/" || err "Failed to copy script."
    # Copy the chosen icon (if one was found) to the main app dir
    if [ -n "${SOURCE_ICON_PATH}" ]; then
        cp "${SOURCE_ICON_PATH}" "${INSTALL_DIR}/${FINAL_ICON_NAME}" || err "Failed to copy icon to app dir."
        # Also copy the preferred PNG icon to the themed location if it exists
        if [ "${ICON_TYPE}" == "png" ]; then
             cp "${SOURCE_ICON_PATH}" "${ICON_INSTALL_DIR_PNG}/${APP_NAME}.png" || err "Failed to copy icon to theme dir."
             msg "  [*] Copied icon to theme dir: ${ICON_INSTALL_DIR_PNG}/${APP_NAME}.png"
        fi
    fi
    msg "  [+] Files copied."

    msg "Creating launcher script..."
    tee "${LAUNCHER_SCRIPT_PATH}" > /dev/null << EOF
#!/usr/bin/env bash
# Launcher for ${APP_NAME}
# Change to the installation directory first to ensure relative paths work
cd "${INSTALL_DIR}" || exit 1
# Execute the python script within its virtual environment
exec "${VENV_DIR}/bin/python" "${INSTALL_DIR}/${SCRIPT_NAME}" "\$@"
EOF
    chmod +x "${LAUNCHER_SCRIPT_PATH}" || err "Failed to make launcher executable."
    msg "  [+] Launcher script created: ${LAUNCHER_SCRIPT_PATH}"

    msg "Creating desktop entry..."

    # Icon name for the desktop entry (prefer just name if themed PNG exists)
    local DESKTOP_ENTRY_ICON_VALUE="${APP_NAME}" # Use simple name if themed PNG icon was copied
    if [ "${ICON_TYPE}" != "png" ]; then
        # If only .ico exists or no icon, use absolute path from install dir
        if [ "${ICON_TYPE}" == "ico" ]; then
            DESKTOP_ENTRY_ICON_VALUE="${INSTALL_DIR}/${FINAL_ICON_NAME}"
            msg "  [*] Using absolute ICO icon path in desktop entry: ${DESKTOP_ENTRY_ICON_VALUE}"
        else
            DESKTOP_ENTRY_ICON_VALUE="" # Empty if no icon at all
            msg "  [*] No icon specified for desktop entry."
        fi
    else
         msg "  [*] Using themed icon name in desktop entry: ${APP_NAME}"
    fi


    # Use direct python execution in desktop file, ensure PATH includes venv bin
    # Setting QT_QPA_PLATFORM=xcb can help on Wayland systems if issues arise
    local EXEC_COMMAND="env QT_QPA_PLATFORM=xcb ${VENV_DIR}/bin/python ${INSTALL_DIR}/${SCRIPT_NAME}"

    tee "${DESKTOP_ENTRY_PATH}" > /dev/null << EOF
[Desktop Entry]
Version=1.0
Name=${APP_NAME}
Comment=${COMMENT_DESC}
Exec=${EXEC_COMMAND}
Path=${INSTALL_DIR}
Icon=${DESKTOP_ENTRY_ICON_VALUE}
Terminal=false
Type=Application
Categories=Utility;Graphics;Development;
EOF
    chmod 644 "${DESKTOP_ENTRY_PATH}" || warn "  Could not set permissions on desktop entry."
    msg "  [+] Desktop entry created: ${DESKTOP_ENTRY_PATH}"

    # --- Force Update Caches ---
    msg "Updating caches (may take a moment)..."
    if command -v update-desktop-database &> /dev/null; then
        update-desktop-database "${DESKTOP_ENTRY_DIR}" &> /dev/null || msg "  (Optional) Failed to update desktop database."
    else
        msg "  [*] 'update-desktop-database' not found. Skipping."
    fi
    if command -v gtk-update-icon-cache &> /dev/null; then
        # Ensure the target directory exists before updating cache for it
        mkdir -p "${ICON_INSTALL_DIR_BASE}"
        gtk-update-icon-cache -f -t "${ICON_INSTALL_DIR_BASE}" &> /dev/null || msg "  (Optional) Failed to update icon cache."
    else
        msg "  [*] 'gtk-update-icon-cache' not found. Skipping."
    fi
    msg "  [+] Caches updated (attempted)."


    msg "--------------------------------------------------"
    msg "${APP_NAME} installation completed successfully!"
    msg "You can now run the application by:"
    msg "  1. Typing '${LAUNCHER_SCRIPT_NAME}' in your terminal."
    msg "  2. Finding '${APP_NAME}' in your desktop application menu (may require logout/login or restart)."
    msg "To uninstall, run this script again with: ./install.sh --uninstall"
    msg "--------------------------------------------------"
}

# --- Main Execution Logic ---
# Check if --uninstall flag is passed
if [ "$#" -gt 0 ] && [ "$1" == "--uninstall" ]; then
    uninstall
else
    # If not uninstalling, run the installation process
    # Optionally check for existing installation and prompt for reinstall/update
    if [ -d "${INSTALL_DIR}" ]; then
        msg "Existing installation found at ${INSTALL_DIR}."
        read -p "Reinstall/Update ${APP_NAME}? (y/N): " confirm </dev/tty
        if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
             msg "Aborting installation."
             exit 0
        fi
         msg "Proceeding with reinstallation..."
    fi
    install
fi

exit 0