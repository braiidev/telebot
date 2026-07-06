#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/braiidev/telebot.git"
INSTALL_DIR="$HOME/.config/telebot"
SERVICE_DIR="$HOME/.config/systemd/user"
BIN_TBOT="/usr/local/bin/tbot"
BIN_TELEBOT="/usr/local/bin/telebot"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}INFO${NC}  $1"; }
ok()    { echo -e "${GREEN}OK${NC}    $1"; }
warn()  { echo -e "${YELLOW}WARN${NC}  $1"; }
err()   { echo -e "${RED}ERR${NC}   $1"; }

cleanup() { rm -rf "$TMPDIR"; }
trap cleanup EXIT

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║        telebot — Install Script          ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
echo ""

# ── 1. Get the source code ──────────────────────────────────────
if [[ -d "$INSTALL_DIR" && -f "$INSTALL_DIR/app.py" ]]; then
    info "Ya existe una instalación en $INSTALL_DIR"
    read -r -p "¿Actualizar? (git pull) [s/N] " CONFIRM
    if [[ "$CONFIRM" =~ ^[sS]$ ]]; then
        cd "$INSTALL_DIR"
        git pull || warn "git pull falló, continuando con los archivos existentes"
        ok "Actualizado"
    else
        info "Usando instalación existente"
    fi
else
    info "Clonando repositorio $REPO_URL ..."
    TMPDIR=$(mktemp -d)
    if git clone --depth=1 "$REPO_URL" "$TMPDIR" 2>/dev/null; then
        mkdir -p "$INSTALL_DIR"
        cp -a "$TMPDIR"/. "$INSTALL_DIR/"
        rm -rf "$TMPDIR"
        ok "Repositorio clonado en $INSTALL_DIR"
    else
        warn "No se pudo clonar el repositorio ($REPO_URL)"
        warn "Asegurate de que el repo exista o clonalo manualmente."
        echo ""
        echo "  Modo manual:"
        echo "    git clone $REPO_URL $INSTALL_DIR"
        echo "    $0   (y volvé a ejecutar este script)"
        echo ""
        read -r -p "¿Copiar desde el directorio actual ($PWD)? [s/N] " COPY
        if [[ "$COPY" =~ ^[sS]$ ]]; then
            mkdir -p "$INSTALL_DIR"
            cp -a "$PWD"/. "$INSTALL_DIR/"
            ok "Copiado desde $PWD"
        else
            err "No hay código fuente. Saliendo."
            exit 1
        fi
    fi
fi

cd "$INSTALL_DIR"

# ── 2. Create data directories ─────────────────────────────────
mkdir -p data/{audio,video,image,document,avatars}
ok "Directorios de datos creados en $INSTALL_DIR/data/"

# ── 3. .env ─────────────────────────────────────────────────────
if [[ -f .env ]]; then
    info ".env ya existe: $(grep -c '^TOKEN=' .env || true) variables configuradas"
    read -r -p "¿Sobrescribir .env? [s/N] " OVERWRITE
    if [[ ! "$OVERWRITE" =~ ^[sS]$ ]]; then
        ok ".env conservado"
    fi
fi

if [[ ! -f .env || "$OVERWRITE" =~ ^[sS]$ ]]; then
    echo ""
    echo -e "${YELLOW}➜  Configurar token de Telegram${NC}"
    echo "   Creá un bot en @BotFather y obtené el token."
    echo "   Ejemplo: 1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
    echo ""
    read -r -p "   Token: " TOKEN
    while [[ -z "$TOKEN" ]]; do
        warn "El token no puede estar vacío"
        read -r -p "   Token: " TOKEN
    done

    cat > .env <<ENV
TOKEN=$TOKEN
HOST=127.0.0.1
PORT=8080
ENV
    ok ".env creado con TOKEN y configuración por defecto (HOST=127.0.0.1 PORT=8080)"
    echo "   Podés editarlo después en: $INSTALL_DIR/.env"
fi

# ── 4. Dependencies ──────────────────────────────────────────────
info "Instalando dependencias de Python..."
pip install -r "$INSTALL_DIR/requirements.txt" 2>&1 | tail -1
ok "Dependencias instaladas"

# ── 5. Systemd service files ───────────────────────────────────
mkdir -p "$SERVICE_DIR"

cat > "$SERVICE_DIR/telebot.service" <<UNIT
[Unit]
Description=HomeBot Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$BIN_TBOT
Restart=always
RestartSec=10
WorkingDirectory=$INSTALL_DIR

[Install]
WantedBy=default.target
UNIT

cat > "$SERVICE_DIR/telebot-notifier.service" <<UNIT
[Unit]
Description=HomeBot Desktop Notifier
After=network-online.target telebot.service
Wants=telebot.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 $INSTALL_DIR/notifier.py
Restart=always
RestartSec=5
WorkingDirectory=$INSTALL_DIR

[Install]
WantedBy=default.target
UNIT

systemctl --user daemon-reload
ok "Servicios systemd instalados en $SERVICE_DIR"

# ── 6. Global commands ─────────────────────────────────────────
sudo tee "$BIN_TBOT" > /dev/null <<SCRIPT
#!/bin/bash
exec python3 "$INSTALL_DIR/app.py" "\$@"
SCRIPT
sudo chmod +x "$BIN_TBOT"

# telebot CLI — same script but with INSTALL_DIR
sudo tee "$BIN_TELEBOT" > /dev/null <<'SCRIPT'
#!/bin/bash
# telebot — manage the telebot service

DIR="__INSTALL_DIR__"
CMD="${1:-status}"
SVC="telebot"
NOTIFIER_SVC="telebot-notifier"

case "$CMD" in
  start|stop|restart|status|enable|disable)
    systemctl --user "$CMD" "$SVC"
    ;;
  notifier)
    ACTION="${2:-status}"
    case "$ACTION" in
      start|stop|restart|status|enable|disable)
        systemctl --user "$ACTION" "$NOTIFIER_SVC"
        ;;
      *)
        echo "Uso: telebot notifier {start|stop|restart|status|enable|disable}"
        exit 1
        ;;
    esac
    ;;
  log|logs)
    journalctl --user -u "$SVC" -n 50 -f
    ;;
  help|--help|-h)
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║                    telebot - Help                    ║"
    echo "╚══════════════════════════════════════════════════════╝"
    echo ""
    echo "DESCRIPCIÓN"
    echo "  Chatbot de Telegram con interfaz web, notificaciones"
    echo "  en tiempo real y popups de escritorio vía tkinter."
    echo ""
    echo "USO"
    echo "  telebot <comando>"
    echo ""
    echo "COMANDOS"
    echo "  start       Inicia el bot + servidor web"
    echo "  stop        Detiene el bot"
    echo "  restart     Reinicia el bot"
    echo "  status      Muestra el estado del servicio"
    echo "  enable      Habilita el inicio automático al boot"
    echo "  disable     Deshabilita el inicio automático"
    echo "  logs        Sigue los logs del bot en tiempo real"
    echo "  notifier    Gestiona el servicio de notificador"
    echo "    start|stop|restart|status|enable|disable"
    echo "  help        Muestra esta ayuda"
    echo ""
    echo "INSTALACIÓN EN OTRO DISPOSITIVO"
    echo ""
    echo "  1. Clonar el repositorio:"
    echo "     git clone https://github.com/braiidev/telebot ~/.config/telebot"
    echo ""
    echo "  2. Ejecutar install.sh:"
    echo "     bash ~/.config/telebot/install.sh"
    echo ""
    echo "  3. Seguir las instrucciones en pantalla."
    echo ""
    echo "REQUISITOS"
    echo "  - Python 3.13+"
    echo "  - ffmpeg (para conversión OGG→MP3)"
    echo "  - tkinter (para popups de escritorio)"
    echo "  - systemd (para gestión de servicios)"
    echo "  - sudo (para instalar comandos globales)"
    ;;
  *)
    echo "Uso: telebot {start|stop|restart|status|enable|disable|logs|notifier|help}"
    exit 1
    ;;
esac
SCRIPT
sudo sed -i "s|__INSTALL_DIR__|$INSTALL_DIR|g" "$BIN_TELEBOT"
sudo chmod +x "$BIN_TELEBOT"

ok "Comandos globales instalados:"
echo "   $BIN_TBOT     (entry point del bot)"
echo "   $BIN_TELEBOT  (CLI de gestión)"

# ── 7. enable-linger ────────────────────────────────────────────
if ! loginctl show-user "$USER" | grep -q "Linger=yes"; then
    info "Habilitando linger para servicios de usuario..."
    sudo loginctl enable-linger "$USER"
    ok "Linger habilitado — el bot arrancará solo al encender el PC"
else
    ok "Linger ya está habilitado"
fi

# ── 8. Summary ──────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║      Instalación completada               ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""
echo "  Directorio    : $INSTALL_DIR"
echo "  Config        : $INSTALL_DIR/.env"
echo "  Datos         : $INSTALL_DIR/data/"
echo "  Servicios     : $SERVICE_DIR/telebot.service"
echo "                  $SERVICE_DIR/telebot-notifier.service"
echo "  Comandos      : telebot, tbot"
echo ""

# ── 9. Ask to start ─────────────────────────────────────────────
read -r -p "¿Iniciar el bot ahora? [S/n] " START
if [[ ! "$START" =~ ^[nN]$ ]]; then
    info "Habilitando e iniciando servicios..."
    systemctl --user enable telebot
    systemctl --user start telebot
    sleep 2
    if systemctl --user is-active --quiet telebot; then
        ok "telebot está corriendo"
    else
        warn "telebot no arrancó — revisá los logs con: telebot logs"
    fi

    systemctl --user enable telebot-notifier
    systemctl --user start telebot-notifier
    ok "telebot-notifier está listo"
    echo ""
    echo "  ➜  Abrí http://localhost:8080 en tu navegador"
    echo "  ➜  Gestioná el bot con: telebot <comando>"
    echo "  ➜  Logs en vivo: telebot logs"
else
    info "Podés arrancar después con:"
    echo "  systemctl --user start telebot"
    echo "  systemctl --user start telebot-notifier"
fi

echo ""
