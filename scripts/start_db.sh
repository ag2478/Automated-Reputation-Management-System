#!/bin/bash
# start_db.sh - run this my partner's VM.

DB_HOST="${DB_HOST:?Set DB_HOST to the database VM IP, e.g. DB_HOST=192.168.1.50 ./start_db.sh}"
DB_SSH_USER="${DB_SSH_USER:-dev}"
DB_USER="arms_app"
DB_NAME="reputation_app"

echo "[1/3] Starting MariaDB on $DB_HOST ..."
# BatchMode=yes means SSH will never ask for a password; it uses the key only.
if ! ssh -o BatchMode=yes -o ConnectTimeout=5 "$DB_SSH_USER@$DB_HOST" \
     "sudo systemctl start mariadb"; then
  echo "ERROR: could not start MariaDB over SSH. Is the SSH key set up? (see setup notes)"
  exit 1
fi

echo "[2/3] Waiting for port 3306 ..."
for i in $(seq 1 15); do
  if nc -z -w 2 "$DB_HOST" 3306; then
    echo "Port 3306 is open."
    break
  fi
  if [ "$i" -eq 15 ]; then
    echo "ERROR: port 3306 never opened. Check bind-address and the firewall on the DB VM."
    exit 1
  fi
  sleep 2
done

echo "[3/3] Testing database login as $DB_USER ..."
if [ -z "$DB_PASSWORD" ]; then
  read -s -p "Password for $DB_USER: " DB_PASSWORD
  echo
fi

if MYSQL_PWD="$DB_PASSWORD" mariadb -h "$DB_HOST" -u "$DB_USER" "$DB_NAME" \
     -e "SHOW TABLES;"; then
  echo "SUCCESS: database is up and reachable from this VM."
else
  echo "ERROR: login failed. Check the password and that the user host is '%'."
  exit 1
fi
