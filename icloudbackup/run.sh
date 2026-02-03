#!/usr/bin/with-contenv bashio
set -e

bashio::log.info "Starting iCloud Backup App..."

# Ensure data directory exists
mkdir -p /data/pyicloud

# Get configuration
USERNAME=$(bashio::config "username")
PASSWORD=$(bashio::config "password")
DIRECTORY=$(bashio::config "icloud_directory_name")
DELETE_LOCAL=$(bashio::config "delete_local_backups_after_upload")

bashio::log.info "iCloud Directory: ${DIRECTORY}"
bashio::log.info "Delete after upload: ${DELETE_LOCAL}"

# Start application
cd /app
exec python3 uploader.py "${USERNAME}" "${PASSWORD}" "${DIRECTORY}" "${DELETE_LOCAL}"
