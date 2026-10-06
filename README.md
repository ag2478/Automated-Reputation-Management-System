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

