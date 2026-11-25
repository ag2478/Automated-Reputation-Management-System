#!/bin/bash
# galera_start.sh - start this VM's MariaDB node in the ARMS Galera cluster.
#
# Usage (on any of the three database VMs):
#   sudo ./galera_start.sh
#
# The rule:
#   - MariaDB already running                  -> nothing to do
#   - another node answers on the Galera port  -> normal start (join that cluster)
#   - nobody answers                           -> bootstrap a NEW cluster from this node
#
# Safety: if nobody answers and grastate.dat says this node is NOT safe to
# bootstrap (it was not the last node to stop), the script refuses, because
# bootstrapping from an out-of-date node can lose recent writes.
# Override only if you know this node has the newest data:
#   sudo FORCE=1 ./galera_start.sh
#
# Exit code: 0 = MariaDB running, 1 = failed or refused

NODES="jxo-dev aks55-dev ag2478-test"
GALERA_PORT=4567
ME="$(hostname)"

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run with sudo."
  exit 1
fi

if systemctl is-active --quiet mariadb; then
  SIZE=$(mariadb -N -e "SHOW STATUS LIKE 'wsrep_cluster_size'" 2>/dev/null | awk '{print $2}')
  echo "[$ME] MariaDB is already running. wsrep_cluster_size=${SIZE:-unknown}"
  exit 0
fi

# Is any OTHER node's Galera port open?
PEER_UP=""
for node in $NODES; do
  [ "$node" = "$ME" ] && continue
  if nc -z -w 2 "$node" "$GALERA_PORT" 2>/dev/null; then
    echo "[$ME] peer $node is up."
    PEER_UP="$node"
  fi
done

if [ -n "$PEER_UP" ]; then
  echo "[$ME] joining the existing cluster..."
  if ! systemctl start mariadb; then
    echo "[$ME] start failed. See: sudo journalctl -u mariadb -n 30 --no-pager"
    exit 1
  fi
else
  GRASTATE=""
  for dir in /var/lib/mariadb /var/lib/mysql; do
    [ -f "$dir/grastate.dat" ] && GRASTATE="$dir/grastate.dat" && break
  done

  if [ -n "$GRASTATE" ] && grep -q 'safe_to_bootstrap: 0' "$GRASTATE" && [ "$FORCE" != "1" ]; then
    echo "[$ME] no peers are up, and this node is NOT marked safe to bootstrap."
    echo "      Start the node that stopped last first, or rerun with:"
    echo "      sudo FORCE=1 $0"
    exit 1
  fi

  if [ "$FORCE" = "1" ] && [ -n "$GRASTATE" ]; then
    sed -i 's/safe_to_bootstrap: 0/safe_to_bootstrap: 1/' "$GRASTATE"
  fi

  echo "[$ME] no peers are up. Bootstrapping a new cluster from this node..."
  if ! galera_new_cluster; then
    echo "[$ME] bootstrap failed. See: sudo journalctl -u mariadb -n 30 --no-pager"
    exit 1
  fi
fi

sleep 5
if systemctl is-active --quiet mariadb; then
  SIZE=$(mariadb -N -e "SHOW STATUS LIKE 'wsrep_cluster_size'" 2>/dev/null | awk '{print $2}')
  echo "[$ME] MariaDB is running. wsrep_cluster_size=${SIZE:-unknown}"
  exit 0
else
  echo "[$ME] MariaDB did not come up. See: sudo journalctl -u mariadb -n 30 --no-pager"
  exit 1
fi
