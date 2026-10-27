# Automated-Reputation-Management-System

# 9/21 - ag2478
# dev, test, and prod environements (lubuntu) created
# RabbitMQ running on ag2478 laptop and connection to three environments tested

# 9/24 - ag2478
# entire enviroment rebuilt, in quadrulplicate
# vms are ubuntu, rabbitmq for messaging, nginx for hosting, mariadb for db (tbd)
# trigger_update.py locally to pull to VMs
# Update-VM.bat locally to manage the pull request
# git_worker.py on vm to listen for pull request
# git_worker.service on vm for systemctl to keep it running ON BOOT
# mailapp on vm for nginx to host the site (point to 7182)

# 10/1 - Josue10-18
# database VM is ubuntu, mariadb for db, rabbitmq for messaging (python scripts coming)
# created database: reputation_app
# created app user: arms_app (SELECT/INSERT/UPDATE/DELETE only), password NOT in repo
# bind-address = 0.0.0.0 in 50-server.cnf so other VMs can connect on 3306
# schema.sql in /database to build tables: users, customers, email_events, logs
# customers table drives the 3 nudges / 2 week timer (status, nudges_sent, next_send_at)
# TODO: rabbitmq read/write script, log to db, hook into start script

# 10/26 - Josue10-18
# database VM: jxo-dev, MariaDB, database reputation_app, user arms_app (password NOT in repo)
# reachable over ZeroTier VPN at 10.211.59.206 port 3306 (ufw allows 10.211.59.0/24)
# data lives on the VM's disk (/var/lib/mariadb), survives reboots
# users table: username, email, password_hash (bcrypt, never plain text), business_name
# database/arms_db.py: register_user(), login_user(), log_event() helper (not used by auth_worker.py)
# registered users verified in the table after front-end registration
# rmq_agent.py runs on this VM as rmq-agent.service so compose.py can start/check mariadb
# python3 compose/compose.py start|status starts and checks all four services
