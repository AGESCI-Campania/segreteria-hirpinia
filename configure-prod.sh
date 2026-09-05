#!/usr/bin/env bash
# Prepara la configurazione di produzione di Catello: genera la configurazione del
# reverse proxy scelto, senza mai eseguire comandi di sistema con privilegi elevati
# (niente sudo/systemctl/apt). Idempotente: una volta scelta un'opzione, le esecuzioni
# successive la richiamano senza richiedere di nuovo l'input, salvo --force.
#
# NOTA: questo script è una bozza ragionevole, non un porting verificato del pattern
# "Plancia" citato nel documento di progettazione (§ D-18): prima di un go-live reale
# vanno rivisti domini, TLS/certbot ed eventuali header di sicurezza aggiuntivi.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

DEPLOY_CONFIG=".deploy-config"
FORCE=0
PROXY_ARG=""

for arg in "$@"; do
  case "$arg" in
    --proxy=*) PROXY_ARG="${arg#--proxy=}" ;;
    --force) FORCE=1 ;;
    -h|--help)
      echo "Uso: $0 [--proxy=nginx-docker|nginx-host|apache-host] [--force]"
      exit 0
      ;;
    *)
      echo "Argomento sconosciuto: $arg" >&2
      exit 1
      ;;
  esac
done

if [[ ! -f .env ]]; then
  echo "Manca .env. Esegui prima:" >&2
  echo "  cp .env.example .env   # e personalizza i valori" >&2
  exit 1
fi

if [[ -f "$DEPLOY_CONFIG" && "$FORCE" -ne 1 ]]; then
  CURRENT="$(cat "$DEPLOY_CONFIG")"
  echo "Configurazione già presente: proxy=${CURRENT} (vedi ${DEPLOY_CONFIG})."
  echo "Usa --force per rigenerarla."
  exit 0
fi

PROXY="$PROXY_ARG"
if [[ -z "$PROXY" ]]; then
  echo "Scegli il reverse proxy per la produzione:"
  select opt in "nginx-docker" "nginx-host" "apache-host"; do
    if [[ -n "${opt:-}" ]]; then
      PROXY="$opt"
      break
    fi
  done
fi

case "$PROXY" in
  nginx-docker|nginx-host|apache-host) ;;
  *)
    echo "Valore non valido per --proxy: '$PROXY' (attesi: nginx-docker, nginx-host, apache-host)" >&2
    exit 1
    ;;
esac

case "$PROXY" in
  nginx-docker)
    mkdir -p docker/nginx
    cat > docker/nginx/catello.conf <<'EOF'
# TODO: sostituire i domini con quelli reali prima del go-live e aggiungere TLS
# (es. certbot). Il servizio "web" è quello definito in compose.prod.yaml.
server {
    listen 80;
    server_name segreteria.agescihirpinia.it catello.agescihirpinia.it;

    client_max_body_size 20M;

    location /static/ {
        alias /srv/segreteriahirpinia/static/;
    }

    # Niente location /media/: quei file richiedono l'autenticazione applicata
    # da Django (PDF, CSV, allegati con dati personali), un alias diretto la
    # bypasserebbe. Le richieste a /media/... vanno proxate come tutto il resto.

    location / {
        proxy_pass http://web:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

    cat > compose.prod.nginx.yaml <<'EOF'
# Override che aggiunge nginx come reverse proxy in Docker.
# Uso: docker compose -f compose.prod.yaml -f compose.prod.nginx.yaml up -d
services:
  nginx:
    image: nginx:1.27-alpine
    container_name: catello_nginx
    restart: unless-stopped
    depends_on:
      - web
    ports:
      - "80:80"
    volumes:
      - ./docker/nginx/catello.conf:/etc/nginx/conf.d/default.conf:ro
      - /srv/segreteriahirpinia/static:/srv/segreteriahirpinia/static:ro
EOF

    echo
    echo "Generati docker/nginx/catello.conf e compose.prod.nginx.yaml."
    echo "Avvio: docker compose -f compose.prod.yaml -f compose.prod.nginx.yaml up -d"
    echo "TODO: aggiungere TLS (porta 443, certificati) prima del go-live."
    ;;

  nginx-host|apache-host)
    mkdir -p deploy
    if [[ "$PROXY" == "nginx-host" ]]; then
      FILE="deploy/nginx.conf.example"
      cat > "$FILE" <<'EOF'
# Esempio di vhost nginx per un host che NON usa Docker per il reverse proxy.
# TODO: sostituire i domini, copiare in /etc/nginx/sites-available/, abilitare
# con un symlink in sites-enabled/, verificare con `nginx -t` e ricaricare.
# Aggiungere TLS (es. certbot) prima del go-live.
server {
    listen 80;
    server_name segreteria.agescihirpinia.it catello.agescihirpinia.it;

    client_max_body_size 20M;

    location /static/ {
        alias /srv/segreteriahirpinia/static/;
    }

    # Niente location /media/: quei file richiedono l'autenticazione applicata
    # da Django (PDF, CSV, allegati con dati personali), un alias diretto la
    # bypasserebbe. Le richieste a /media/... vanno proxate come tutto il resto.

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
    else
      FILE="deploy/apache.conf.example"
      cat > "$FILE" <<'EOF'
# Esempio di vhost Apache per un host che NON usa Docker per il reverse proxy.
# TODO: sostituire i domini, copiare in /etc/apache2/sites-available/, abilitare
# con a2ensite, verificare con `apachectl configtest` e ricaricare.
# Richiede mod_proxy e mod_proxy_http abilitati (a2enmod proxy proxy_http).
# Aggiungere TLS (es. certbot) prima del go-live.
<VirtualHost *:80>
    ServerName segreteria.agescihirpinia.it
    ServerAlias catello.agescihirpinia.it

    Alias /static/ /srv/segreteriahirpinia/static/

    # Niente Alias /media/: quei file richiedono l'autenticazione applicata da
    # Django (PDF, CSV, allegati con dati personali), un alias diretto la
    # bypasserebbe. Le richieste a /media/... vanno proxate come tutto il resto.

    ProxyPreserveHost On
    ProxyPass /static/ !
    ProxyPass / http://127.0.0.1:8000/
    ProxyPassReverse / http://127.0.0.1:8000/
</VirtualHost>
EOF
    fi

    echo
    echo "Generato $FILE — passi manuali (nessun comando eseguito da questo script):"
    echo "  1. Copiare il file nella posizione corretta per $PROXY."
    echo "  2. Sostituire i domini con quelli reali."
    echo "  3. Verificare la sintassi e ricaricare il servizio."
    echo "  4. Configurare TLS (es. certbot) prima del go-live."
    echo "compose.prod.yaml espone già l'app su 127.0.0.1:8000, indipendentemente da questa scelta."
    ;;
esac

echo "$PROXY" > "$DEPLOY_CONFIG"
echo
echo "Configurazione salvata in $DEPLOY_CONFIG (proxy=$PROXY)."
