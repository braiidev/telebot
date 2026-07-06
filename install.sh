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

TMPDIR=""
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
    read -r -p "¿Actualizar? (git pull) [s/N] " CONFIRM < /dev/tty
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
    info ".env ya existe"
    read -r -p "¿Sobrescribir? [s/N] " OVERWRITE < /dev/tty
    if [[ ! "$OVERWRITE" =~ ^[sS]$ ]]; then
        ok ".env conservado"
    fi
fi

if [[ ! -f .env || "$OVERWRITE" =~ ^[sS]$ ]]; then
    echo ""
    echo -e "${YELLOW}➜  Token de Telegram${NC}"
    echo "   Creá un bot en @BotFather y pegá el token."
    echo "   Dejalo vacío para configurar después con: telebot set token"
    echo "   Ejemplo: 1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
    echo ""
    read -r -p "   Token (enter para omitir): " TOKEN < /dev/tty

    cat > .env <<ENV
HOST=127.0.0.1
PORT=8080
ENV

    if [[ -n "$TOKEN" ]]; then
        echo "TOKEN=$TOKEN" >> .env
        ok ".env creado con TOKEN + configuración por defecto"
    else
        ok ".env creado con valores por defecto (sin token)"
        echo "  ➜  Configurá el token después con: telebot set token"
    fi
    echo "   Podés editar: $INSTALL_DIR/.env"
fi

# ── 4. Dependencies ──────────────────────────────────────────────
info "Instalando dependencias de Python..."
python3 -m pip install --break-system-packages -r "$INSTALL_DIR/requirements.txt" 2>&1 | tail -1
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
  start|enable)
    systemctl --user "$CMD" "$SVC"
    ;;
  stop)
    systemctl --user stop "$NOTIFIER_SVC" 2>/dev/null
    systemctl --user stop "$SVC"
    ;;
  disable)
    systemctl --user disable "$NOTIFIER_SVC" 2>/dev/null
    systemctl --user disable "$SVC"
    ;;
  restart)
    systemctl --user stop "$NOTIFIER_SVC" 2>/dev/null
    systemctl --user restart "$SVC"
    ;;
  status)
    systemctl --user status "$SVC"
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
  uninstall)
    echo ""
    echo "╔══════════════════════════════════════════════╗"
    echo "║           telebot — Uninstall                ║"
    echo "╚══════════════════════════════════════════════╝"
    echo ""
    echo "Se va a eliminar lo siguiente:"
    echo ""
    echo "  📦 Servicios systemd:"
    echo "     - $SVC"
    echo "     - $NOTIFIER_SVC"
    echo ""
    echo "  📁 Código y datos: $DIR"
    echo ""
    echo "  🔧 Comandos globales:"
    echo "     - /usr/local/bin/tbot"
    echo "     - /usr/local/bin/telebot"
    echo ""
    echo -n "¿Realmente deseas eliminar telebot? (y/N) "
    read -r CONFIRM
    if [[ ! "$CONFIRM" =~ ^[yY]$ ]]; then
      echo "Cancelado."
      exit 0
    fi
    echo ""
    echo "Deteniendo servicios..."
    systemctl --user stop "$NOTIFIER_SVC" 2>/dev/null
    systemctl --user stop "$SVC" 2>/dev/null
    systemctl --user disable "$NOTIFIER_SVC" 2>/dev/null
    systemctl --user disable "$SVC" 2>/dev/null
    echo "Eliminando servicios systemd..."
    rm -f "$HOME/.config/systemd/user/$SVC.service"
    rm -f "$HOME/.config/systemd/user/$NOTIFIER_SVC.service"
    systemctl --user daemon-reload
    echo "Eliminando $DIR..."
    rm -rf "$DIR"
    echo "Eliminando comandos globales..."
    sudo rm -f /usr/local/bin/tbot /usr/local/bin/telebot
    echo ""
    echo "✅ telebot desinstalado."
    echo ""
    echo "Para remover el inicio automático (opcional):"
    echo "  sudo loginctl disable-linger \$USER"
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
    echo "  telebot <comando> [args]"
    echo ""
    echo "COMANDOS"
    echo "  start           Inicia el bot + servidor web"
    echo "  stop            Detiene el bot y notificador"
    echo "  restart         Reinicia el bot (notificador se reajusta solo)"
    echo "  status          Muestra el estado del servicio"
    echo "  enable          Habilita el inicio automático al boot"
    echo "  disable         Deshabilita el inicio automático"
    echo "  logs            Sigue los logs en tiempo real"
    echo "  notifier        Gestiona el servicio de notificador"
    echo "    start|stop|restart|status|enable|disable"
    echo "  set token TKN   Configura el token de Telegram"
    echo "  set host HOST   Cambia HOST (defecto: 127.0.0.1)"
    echo "  set port NUM    Cambia PORT (defecto: 8080)"
    echo "  set debug on|off  Activa/desactiva modo debug"
    echo "  set show        Muestra la configuración actual"
    echo "  uninstall       Elimina telebot por completo"
    echo "  help            Muestra esta ayuda"
    echo ""
    echo "EJEMPLOS"
    echo "  telebot set token 123456:ABCdef"
    echo "  telebot set port 9090"
    echo "  telebot set debug on"
    echo "  telebot set show"
    echo "  telebot restart   (para aplicar cambios)"
    echo ""
    echo "INSTALACIÓN EN OTRO DISPOSITIVO"
    echo ""
    echo "  curl -fsSL https://raw.githubusercontent.com/braiidev/telebot/main/install.sh | bash"
    echo ""
    echo "REQUISITOS"
    echo "  - Python 3.13+"
    echo "  - ffmpeg (para conversión OGG→MP3)"
    echo "  - tkinter (para popups de escritorio)"
    echo "  - systemd (para gestión de servicios)"
    echo "  - sudo (para instalar comandos globales)"
    ;;
  set)
    KEY="$2"
    VAL="$3"
    ENV_FILE="$DIR/.env"
    if [[ ! -f "$ENV_FILE" ]]; then
      echo "Error: no se encuentra $ENV_FILE"
      echo "Ejecutá install.sh primero o creá el archivo manualmente."
      exit 1
    fi
    case "$KEY" in
      token)
        if [[ -z "$VAL" ]]; then
          echo "Uso: telebot set token <token>"
          exit 1
        fi
        if grep -q '^TOKEN=' "$ENV_FILE"; then
          sed -i "s|^TOKEN=.*|TOKEN=$VAL|" "$ENV_FILE"
        else
          echo "TOKEN=$VAL" >> "$ENV_FILE"
        fi
        echo "Token actualizado. Reiniciá el bot: telebot restart"
        ;;
      host)
        if [[ -z "$VAL" ]]; then
          echo "Uso: telebot set host <host>"
          exit 1
        fi
        if grep -q '^HOST=' "$ENV_FILE"; then
          sed -i "s|^HOST=.*|HOST=$VAL|" "$ENV_FILE"
        else
          echo "HOST=$VAL" >> "$ENV_FILE"
        fi
        echo "Host actualizado a $VAL. Reiniciá el bot: telebot restart"
        ;;
      port)
        if [[ -z "$VAL" ]]; then
          echo "Uso: telebot set port <número>"
          exit 1
        fi
        if grep -q '^PORT=' "$ENV_FILE"; then
          sed -i "s|^PORT=.*|PORT=$VAL|" "$ENV_FILE"
        else
          echo "PORT=$VAL" >> "$ENV_FILE"
        fi
        echo "Puerto actualizado a $VAL. Reiniciá el bot: telebot restart"
        ;;
      debug)
        case "$VAL" in
          on|true|1)
            if grep -q '^DEBUG=' "$ENV_FILE"; then
              sed -i 's|^DEBUG=.*|DEBUG=true|' "$ENV_FILE"
            else
              echo "DEBUG=true" >> "$ENV_FILE"
            fi
            echo "Modo debug activado. Reiniciá el bot: telebot restart"
            ;;
          off|false|0)
            if grep -q '^DEBUG=' "$ENV_FILE"; then
              sed -i 's|^DEBUG=.*|DEBUG=false|' "$ENV_FILE"
            else
              echo "DEBUG=false" >> "$ENV_FILE"
            fi
            echo "Modo debug desactivado. Reiniciá el bot: telebot restart"
            ;;
          *)
            echo "Uso: telebot set debug on|off"
            exit 1
            ;;
        esac
        ;;
      show)
        echo "=== Configuración actual ($ENV_FILE) ==="
        while IFS='=' read -r k v; do
          if [[ "$k" == "TOKEN" && -n "$v" ]]; then
            echo "TOKEN=${v:0:8}...${v: -4}"
          else
            echo "$k=$v"
          fi
        done < "$ENV_FILE"
        ;;
      *)
        echo "Uso: telebot set {token|host|port|debug|show}"
        exit 1
        ;;
    esac
    ;;
  *)
    echo "Uso: telebot {start|stop|restart|status|enable|disable|logs|notifier|set|uninstall|help}"
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
read -r -p "¿Iniciar el bot ahora? [S/n] " START < /dev/tty
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
