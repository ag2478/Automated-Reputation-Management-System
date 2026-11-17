RBMQ_DIR="$HOME/Automated-Reputation-Management-System/RBMQ"
CONTROLLER="$RBMQ_DIR/rmq_controller.py"
HOSTS=("ag2478-dev" "ag2478-test" "ag2478-prod" "aks55-dev-1" "ojo-dev" "jxo-dev")
PORTS=(4369 5672 15672 25672)

GREEN="\033[1;32m"
RED="\033[1;31m"
YELLOW="\033[1;33m"
CYAN="\033[1;36m"
BOLD="\033[1m"
NC="\033[0m"

declare -a IP_ADDR TS_STATE RMQ_STATE AGT_STATE TS_BADGE RMQ_BADGE AGT_BADGE

collect_metrics() {
    ONLINE_RMQ_COUNT=0
    QUEUE_DATA=""

    # Query active agent consumers from whichever cluster node is online
    if sudo -n rabbitmqctl status >/dev/null 2>&1; then
        QUEUE_DATA=$(sudo rabbitmqctl list_queues name consumers 2>/dev/null)
    fi

    for i in "${!HOSTS[@]}"; do
        host="${HOSTS[$i]}"

        # 1. Resolve IP
        resolved=$(getent hosts "$host" | awk '{print $1}' | head -n 1)
        if [ -z "$resolved" ]; then
            IP_ADDR[$i]=$(printf "%-15s" "UNRESOLVED")
        else
            IP_ADDR[$i]=$(printf "%-15s" "$resolved")
        fi

        # 2. Tailscale / ICMP Reachability
        if ping -c 1 -W 1 "$host" >/dev/null 2>&1; then
            TS_STATE[$i]="UP"
            TS_BADGE[$i]="${GREEN}ONLINE ${NC}"
        else
            TS_STATE[$i]="DOWN"
            TS_BADGE[$i]="${RED}OFFLINE${NC}"
        fi

        # 3. RabbitMQ Broker Port 5672 Status
        if [ "${TS_STATE[$i]}" == "UP" ] && nc -z -w 1 "$host" 5672 >/dev/null 2>&1; then
            RMQ_STATE[$i]="UP"
            RMQ_BADGE[$i]="${GREEN}ONLINE ${NC}"
            ((ONLINE_RMQ_COUNT++))
        else
            RMQ_STATE[$i]="DOWN"
            RMQ_BADGE[$i]="${RED}OFFLINE${NC}"
        fi

        # 4. RPC Agent Queue Consumer Status
        if [ -n "$QUEUE_DATA" ]; then
            consumers=$(echo "$QUEUE_DATA" | awk -v q="agent_${host}" '$1 == q {print $2}')
            if [ -n "$consumers" ] && [ "$consumers" -ge 1 ] 2>/dev/null; then
                AGT_STATE[$i]="UP"
                AGT_BADGE[$i]="${GREEN}ONLINE ${NC}"
            else
                AGT_STATE[$i]="DOWN"
                AGT_BADGE[$i]="${RED}OFFLINE${NC}"
            fi
        else
            AGT_STATE[$i]="UNKNOWN"
            AGT_BADGE[$i]="${YELLOW}WAIT   ${NC}"
        fi
    done
}

draw_ascii_map() {
    clear
    NOW=$(date "+%Y-%m-%d %H:%M:%S")
    PCT=$(( ONLINE_RMQ_COUNT * 100 / 6 ))

    if [ "$ONLINE_RMQ_COUNT" -ge 4 ]; then
        HEALTH_BANNER="${GREEN}HEALTHY QUORUM ($ONLINE_RMQ_COUNT/6 Nodes Online - ${PCT}%)${NC}"
    elif [ "$ONLINE_RMQ_COUNT" -ge 1 ]; then
        HEALTH_BANNER="${YELLOW}MAJORITY OUTAGE SURVIVAL MODE ($ONLINE_RMQ_COUNT/6 Nodes Online - ${PCT}% | autoheal active)${NC}"
    else
        HEALTH_BANNER="${RED}TOTAL CLUSTER OUTAGE (0/6 Nodes Online - force_boot required)${NC}"
    fi

    echo -e "${BOLD}=====================================================================================${NC}"
    echo -e "   ${CYAN}TAILSCALE & RABBITMQ LIVE CLUSTER TOPOLOGY MAP${NC}        Updated: $NOW"
    echo -e "   Status: $HEALTH_BANNER"
    echo -e "${BOLD}=====================================================================================${NC}\n"

    # Top Row: Nodes 1, 2, 3
    H0=$(printf "[1] %-17s" "${HOSTS[0]}")
    H1=$(printf "[2] %-17s" "${HOSTS[1]}")
    H2=$(printf "[3] %-17s" "${HOSTS[2]}")

    echo -e "  +-----------------------+     +-----------------------+     +-----------------------+"
    echo -e "  | ${BOLD}${H0}${NC} |     | ${BOLD}${H1}${NC} |     | ${BOLD}${H2}${NC} |"
    echo -e "  | IP : ${IP_ADDR[0]}  |     | IP : ${IP_ADDR[1]}  |     | IP : ${IP_ADDR[2]}  |"
    echo -e "  | VPN: ${TS_BADGE[0]}          |     | VPN: ${TS_BADGE[1]}          |     | VPN: ${TS_BADGE[2]}          |"
    echo -e "  | RMQ: ${RMQ_BADGE[0]} (:5672)  |     | RMQ: ${RMQ_BADGE[1]} (:5672)  |     | RMQ: ${RMQ_BADGE[2]} (:5672)  |"
    echo -e "  | AGT: ${AGT_BADGE[0]}          |     | AGT: ${AGT_BADGE[1]}          |     | AGT: ${AGT_BADGE[2]}          |"
    echo -e "  +-----------+-----------+     +-----------+-----------+     +-----------+-----------+"
    echo -e "              |                             |                             |"
    echo -e "              +-----------------------------+-----------------------------+"
    echo -e "                                            |"
    echo -e "                    ${CYAN}[====== TAILSCALE MESH VPN (tailscale0) ======]${NC}"
    echo -e "                                            |"
    echo -e "              +-----------------------------+-----------------------------+"
    echo -e "              |                             |                             |"

    # Bottom Row: Nodes 4, 5, 6
    H3=$(printf "[4] %-17s" "${HOSTS[3]}")
    H4=$(printf "[5] %-17s" "${HOSTS[4]}")
    H5=$(printf "[6] %-17s" "${HOSTS[5]}")

    echo -e "  +-----------+-----------+     +-----------+-----------+     +-----------+-----------+"
    echo -e "  | ${BOLD}${H3}${NC} |     | ${BOLD}${H4}${NC} |     | ${BOLD}${H5}${NC} |"
    echo -e "  | IP : ${IP_ADDR[3]}  |     | IP : ${IP_ADDR[4]}  |     | IP : ${IP_ADDR[5]}  |"
    echo -e "  | VPN: ${TS_BADGE[3]}          |     | VPN: ${TS_BADGE[4]}          |     | VPN: ${TS_BADGE[5]}          |"
    echo -e "  | RMQ: ${RMQ_BADGE[3]} (:5672)  |     | RMQ: ${RMQ_BADGE[4]} (:5672)  |     | RMQ: ${RMQ_BADGE[5]} (:5672)  |"
    echo -e "  | AGT: ${AGT_BADGE[3]}          |     | AGT: ${AGT_BADGE[4]}          |     | AGT: ${AGT_BADGE[5]}          |"
    echo -e "  +-----------------------+     +-----------------------+     +-----------------------+\n"

    echo -e "${BOLD}LIVE CONTROLS (Auto-refreshes every 3s):${NC}"
    echo -e "  ${YELLOW}[s]${NC} Shut Down N Nodes (Resilience Test)    ${YELLOW}[r]${NC} Recover / Force-Boot All Offline Nodes"
    echo -e "  ${YELLOW}[t]${NC} Toggle Single Node (1-6)               ${YELLOW}[p]${NC} Detailed Port & Cluster Dump"
    echo -e "  ${YELLOW}[q]${NC} Quit Live Monitor"
}

shutdown_n_nodes() {
    echo ""
    read -r -p "Enter how many RabbitMQ nodes to shut down (1-5): " count
    if ! [[ "$count" =~ ^[1-5]$ ]]; then
        echo -e "${RED}Invalid number. Choose between 1 and 5.${NC}"
        sleep 2
        return
    fi

    stopped=0
    # Stop remote/secondary nodes first (indices 5 down to 1) so ag2478-dev stays online as RPC router
    for idx in 5 4 3 2 1 0; do
        if [ "$stopped" -ge "$count" ]; then
            break
        fi
        if [ "${RMQ_STATE[$idx]}" == "UP" ]; then
            target="${HOSTS[$idx]}"
            echo -e "${YELLOW} -> Sending RPC stop for rabbitmq-server to ${target}...${NC}"
            python3 "$CONTROLLER" "$target" rabbitmq stop
            ((stopped++))
        fi
    done

    echo -e "${GREEN}Dispatched shutdown to $stopped node(s). Returning to live feed...${NC}"
    sleep 2
}

recover_all_nodes() {
    echo -e "\n${CYAN}Recovering all offline RabbitMQ nodes (with force_boot)...${NC}"
    # Ensure local node is up first if it was stopped
    if [ "${RMQ_STATE[0]}" == "DOWN" ]; then
        echo -e "${YELLOW} -> Force-booting local node (${HOSTS[0]})...${NC}"
        sudo rabbitmqctl force_boot >/dev/null 2>&1 || true
        sudo systemctl start rabbitmq-server
    fi

    for idx in 1 2 3 4 5; do
        if [ "${RMQ_STATE[$idx]}" == "DOWN" ] && [ "${TS_STATE[$idx]}" == "UP" ]; then
            target="${HOSTS[$idx]}"
            echo -e "${YELLOW} -> Sending RPC start (force_boot) for rabbitmq-server to ${target}...${NC}"
            python3 "$CONTROLLER" "$target" rabbitmq start
        fi
    done
    echo -e "${GREEN}Recovery commands complete. Returning to live feed...${NC}"
    sleep 2
}

toggle_single_node() {
    echo ""
    read -r -p "Select node number [1-6] to toggle RabbitMQ: " num
    if ! [[ "$num" =~ ^[1-6]$ ]]; then
        echo -e "${RED}Invalid node selection.${NC}"
        sleep 1
        return
    fi
    idx=$((num - 1))
    target="${HOSTS[$idx]}"

    if [ "${RMQ_STATE[$idx]}" == "UP" ]; then
        echo -e "${YELLOW}Stopping rabbitmq-server on $target...${NC}"
        python3 "$CONTROLLER" "$target" rabbitmq stop
    else
        echo -e "${CYAN}Starting rabbitmq-server (with force_boot) on $target...${NC}"
        if [ "$idx" -eq 0 ]; then
            sudo rabbitmqctl force_boot >/dev/null 2>&1 || true
            sudo systemctl start rabbitmq-server
        else
            python3 "$CONTROLLER" "$target" rabbitmq start
        fi
    fi
    sleep 2
}

detailed_port_dump() {
    clear
    echo -e "${BOLD}=== DETAILED TCP PORT & CLUSTER DIAGNOSTIC ===${NC}"
    for host in "${HOSTS[@]}"; do
        echo -e "\n${YELLOW}Host: $host${NC}"
        for port in "${PORTS[@]}"; do
            if nc -z -w 1 "$host" "$port" >/dev/null 2>&1; then
                echo -e "  Port $port: ${GREEN}OPEN${NC}"
            else
                echo -e "  Port $port: ${RED}CLOSED${NC}"
            fi
        done
    done
    echo -e "\n${BOLD}=== RABBITMQ CLUSTER STATUS ===${NC}"
    sudo rabbitmqctl cluster_status 2>/dev/null | sed -n '/Disk Nodes/,/Versions/p'
    echo ""
    read -r -p "Press Enter to return to the live ASCII map..."
}

# Main Live Loop
while true; do
    collect_metrics
    draw_ascii_map

    if read -r -s -t 3 -n 1 key; then
        case "$key" in
            s|S) shutdown_n_nodes ;;
            r|R) recover_all_nodes ;;
            t|T) toggle_single_node ;;
            p|P) detailed_port_dump ;;
            q|Q) echo -e "\nExiting monitor."; exit 0 ;;
        esac
    fi
done