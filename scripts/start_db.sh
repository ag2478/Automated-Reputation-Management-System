#!/bin/bash
# start_db.sh - run from any VM to confirm the ARMS database is up.


DB_HOST="${DB_HOST:?Set DB_HOST, e.g. DB_HOST=192.168.1.50 ./check_db.sh}"
DB_USER="arms_app"
DB_NAME="reputation_app"

echo "[1/2] Checking port 3306 on $DB_HOST ..."
for i in $(seq 1 15); do
  if nc -z -w 2 "$DB_HOST" 3306; then
    echo "Port 3306 is open."
    break
  fi
  if [ "$i" -eq 15 ]; then
    echo "ERROR: database not reachable on port 3306."
    exit 1
  fi
  sleep 2
done

echo "[2/2] Testing login as $DB_USER ..."
if [ -z "$DB_PASSWORD" ]; then
  read -s -p "Password for $DB_USER: " DB_PASSWORD
  echo
fi

if MYSQL_PWD="$DB_PASSWORD" mariadb -h "$DB_HOST" -u "$DB_USER" "$DB_NAME" -e "SHOW TABLES;"; then
  echo "SUCCESS: database is up and reachable."
  exit 0
else
  echo "ERROR: login failed."
  exit 1
fi
