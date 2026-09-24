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


