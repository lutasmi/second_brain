# Despliegue en la nube

Objetivo: que el sistema sea autosuficiente — el bot corre 24/7 en un
servidor y la biblioteca se replica en Google Drive, sin depender de ningún
ordenador personal encendido.

```
Telegram ──▶ bot (servidor Linux, 24/7) ──▶ library/ (Markdown, fuente de verdad)
                                                 │  rclone copy (cada 5 min)
                                                 ▼
                                   Google Drive: second_brain/library
                                   (copia de seguridad + lectura desde móvil/web)
```

Principios que se conservan:

- La fuente de verdad son los Markdown del disco del servidor.
- Google Drive es un **espejo de solo salida** (`rclone copy`, nunca borra):
  copia de seguridad + acceso de lectura desde cualquier dispositivo.
- Nada depende del proveedor: el mismo contenedor corre en cualquier VPS,
  y `library/` puede copiarse/moverse cuando quieras.

## 1. Elegir servidor

Cualquier Linux pequeño sirve (1 vCPU / 1 GB RAM basta de sobra):

| Opción                        | Coste          | Nota                                    |
|-------------------------------|----------------|------------------------------------------|
| Oracle Cloud "Always Free"    | 0 €            | ARM 4 vCPU/24 GB gratis; registro engorroso |
| Google Cloud `e2-micro`       | 0 €            | Capa gratuita permanente (us-*)          |
| Hetzner CX22                  | ~4 €/mes       | Sencillo y fiable (UE)                   |
| Cualquier VPS (DigitalOcean…) | 4–6 €/mes      |                                          |

Crea una VM con **Ubuntu 24.04 LTS** y acceso SSH.

## 2. Instalar Docker y clonar el repositorio

```bash
ssh usuario@tu-servidor
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && exit   # reconecta para aplicar el grupo

ssh usuario@tu-servidor
git clone <url-de-este-repo> second_brain && cd second_brain
```

## 3. Configurar `.env`

```bash
cp .env.example .env
nano .env    # TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_IDS
             # y opcionalmente ANTHROPIC_API_KEY para describir imágenes
```

## 4. Autorizar Google Drive (una sola vez)

El servidor no tiene navegador, así que la autorización se hace en dos pasos
con la cuenta **Secondo_Cerebro@gmail.com**:

**En tu ordenador** (una vez, con navegador):

```bash
brew install rclone            # o: sudo apt install rclone
rclone authorize "drive"       # abre el navegador → inicia sesión con
                               # Secondo_Cerebro@gmail.com → copia el token JSON
```

**En el servidor**:

```bash
mkdir -p rclone
cat > rclone/rclone.conf <<'EOF'
[gdrive]
type = drive
scope = drive
token = PEGA_AQUI_EL_TOKEN_JSON
EOF
```

Verifica: `docker run --rm -v ./rclone:/config/rclone rclone/rclone lsd gdrive:`

## 5. Arrancar

```bash
docker compose up -d
docker compose logs -f bot     # debe decir "Application started"
```

Envía un mensaje al bot: la nota aparece en `library/` del servidor y, en
menos de 5 minutos, en Google Drive → `second_brain/library/`.

> ⚠️ **Solo una instancia del bot a la vez.** Telegram no permite dos
> procesos haciendo polling con el mismo token: apaga el bot local antes de
> arrancar el del servidor (o verás errores 409 Conflict).

## 6. Operación

```bash
docker compose logs -f bot                         # actividad
docker compose exec bot second-brain reprocess     # reintentar pendientes
docker compose exec bot second-brain index         # reconstruir índice
docker compose exec bot second-brain search "..."  # buscar
docker compose pull && docker compose up -d --build  # actualizar
```

## Opción B: sin Docker

En `deploy/systemd/` hay unidades listas: un servicio para el bot y un
timer que espeja la biblioteca cada 5 minutos.

```bash
sudo apt install python3.11-venv tesseract-ocr tesseract-ocr-spa rclone git
sudo useradd -r -m -d /opt/second_brain secondbrain
sudo -u secondbrain git clone <url-de-este-repo> /opt/second_brain
cd /opt/second_brain
sudo -u secondbrain python3 -m venv .venv
sudo -u secondbrain .venv/bin/pip install .
sudo -u secondbrain cp .env.example .env && sudo -u secondbrain nano .env
# rclone: mismo paso 4, con el config en /opt/second_brain/.config/rclone/

sudo cp deploy/systemd/second-brain*.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now second-brain.service second-brain-sync.timer
```

## Recuperación ante desastres

La biblioteca completa está en Google Drive. Si el servidor desaparece:

1. Crea otro servidor y repite los pasos 2–4.
2. Restaura la biblioteca: `rclone copy gdrive:second_brain/library library/`
3. `docker compose up -d`

Nada más que restaurar: no hay base de datos que migrar (el índice se
regenera con `second-brain index`).
