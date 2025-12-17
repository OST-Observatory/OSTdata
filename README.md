# Data archive for the OST observatory

In this Django project we are building a website for the data archive of the 
[OST Observatory](polaris.astro.physik.uni-potsdam.de) of the 
[University of Potsdam](www.uni-potsdam.de).
This project is based on the [Astronomical Observation Tracking System
(AOTS)](https://github.com/vosjo/AOTS), primarily developed by Joris (vosjo).

## Installing Django and dependencies

In the following, we will install OSTdata, Django, and all dependencies using a Python virtual environment to avoid conflicts with other packages and projects. The frontend is built with Vue 3 + Vite, which we will install as well.

### 1. Prerequisites

Create a directory where all files and the required Python modules can be placed:

```
mkdir ostdata
cd ostdata
```

For the rest of this guide, we will assume that this directory is located in the user's home directory.

You need the python-dev package (we assume here a Debian system or one of its derivatives, such as Ubuntu). Moreover you should update pip:

```
sudo apt update
sudo apt install python-dev-is-python3
pip install -U pip
```

### 2. Create the virtual environment

Create a new virtual python environment for OSTdata and activate it (Bash syntax):

```
python -m venv ostdata_env
source ostdata_env/bin/activate
```

On Windows computers, run

```
python -m venv ostdata_env
ostdata_env\Scripts\Activate
```

### 3. Clone OSTdata from GitHub

```
git clone https://github.com/OST-Observatory/OSTdata.git
```

### 4. Install the requirements

```
cd OSTdata
pip install -r requirements.txt
```

### 5. Install Node.js (Debian/Ubuntu)

```
sudo apt install -y nodejs npm
```

### 6. Install frontend dependencies

```
cd OSTdata/frontend
npm ci || npm install
```

## Running OSTdata locally

To run OSTdata locally, using the simple sqlite database and the included server:

### 1. Setup the database

```
python manage.py makemigrations
python manage.py migrate
```

In case you want a fresh start, run:

```
find . -path "*/migrations/*.py" -not -name "__init__.py" -delete
find . -path "*/migrations/*.pyc"  -delete
```

and drop the database or remove the db.sqlite3 file.

### 2. Create a admin user

```
python manage.py createsuperuser
>>> Username: admin_user_name
>>> Email address: admin@example.com
>>> Password: **********
>>> Password (again): *********
>>> Superuser created successfully.
```

### 3. Start the backend (Django) server

```
python manage.py runserver
```

### 4. Start the frontend (Vue) server

In a different terminal:

```
cd OSTdata/frontend
npm run dev
```

## Set up PostgreSQL for production

This is only necessary if you want to run in production.

Install PostgreSQL:

```
sudo apt install postgresql
```

Start the psql shell:

```
sudo -u postgres psql
```

Create the database, user and connect them:

```
CREATE DATABASE ostdatadb;
CREATE USER ostdatauser WITH PASSWORD 'password';
ALTER ROLE ostdatauser SET client_encoding TO 'utf8';
ALTER ROLE ostdatauser SET default_transaction_isolation TO 'read committed';
ALTER ROLE ostdatauser SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE ostdatadb TO ostdatauser;
```

List all databases:

```
\l
```

Connect to our database and list all tables:

```
\c ostdatadb
\dt
```

To drop the database and recreate it when you want to completely reset everything (the user does not get deleted in this process):

```
DROP DATABASE ostdatadb;
CREATE DATABASE ostdatadb;
GRANT ALL PRIVILEGES ON DATABASE ostdatadb TO ostdatauser;
```

Exit psql:

```
\q
```

## Running OSTdata in production using a PostgreSQL database

Instructions modified from: https://www.digitalocean.com/community/tutorials/how-to-set-up-django-with-postgres-nginx-and-gunicorn-on-ubuntu-18-04

### 1. Create an .env file

To protect secrets like the postgres database password or the Django security
key they are embedded in OSTdata via environment variables. The environment
variables are defined in the .env file in the OSTdata directory. As an example we
provide .env.example.

```
cp ostdata/.env.example  ostdata/.env
```

### 2. Adjust the .env file

In `.env` specify the secret Django security key, the PostgreSQL database password, the
server IP and URL, as well as the hostname of the production machine.
If a custom log directory is required or a different database user was defined during setup,
specify that here as well.

```
SECRET_KEY=generate_and_add_your_secret_security_key_here
DATABASE_NAME=ostdatadb
DATABASE_USER=ostdatauser
DATABASE_PASSWORD=your_database_password
DATABASE_HOST=localhost
DATABASE_PORT=
DEVICE=the_name_of_your_device_used_in_production
ALLOWED_HOSTS=server_url,server_ip,localhost
LOG_DIR=logs/
DEFAULT_FROM_EMAIL=example@email.com
# When running under a URL prefix (e.g. /data_archive), ensure STATIC_URL matches:
# If FORCE_SCRIPT_NAME=/data_archive → STATIC_URL=/data_archive/static/
STATIC_URL=/data_archive/static/
```

Instructions on how to generate a secret key can be found here: https://tech.serhatteker.com/post/2020-01/django-create-secret-key/

### 3. Setup the database

```
python manage.py makemigrations
python manage.py migrate
```

In case you want a fresh start, run:

```
find . -path "*/migrations/*.py" -not -name "__init__.py" -delete
find . -path "*/migrations/*.pyc"  -delete
```

and drop the database or remove the db.sqlite3 file.

### 4. Create a admin user

```
python manage.py createsuperuser
>>> Username: admin_user_name
>>> Email address: admin@example.com
>>> Password: **********
>>> Password (again): *********
>>> Superuser created successfully.
```

You should use a different username instead of admin to increase security.

### 5. Configure frontend base paths

This is needed in production so that the frontend calls the correct backend and resolves assets under the mounted path.
If the site runs under `/data_archive`, set both variables:

```
cd OSTdata/frontend
cat > .env << 'EOF'
VITE_API_BASE=/data_archive/api
VITE_BASE=/data_archive/
EOF
```

If your site runs at the domain root, you can keep the defaults:

```
VITE_API_BASE=/api
VITE_BASE=/
```

### 6. Build the Vue frontend

```
cd OSTdata/frontend
npm run build
```

This produces a `dist/` folder with static assets.

### 7. Collect static files

```
python manage.py collectstatic
```

## Set up Gunicorn

### 1. Create socket unit

```
sudo nano /etc/systemd/system/gunicorn_ostdata.socket
```

Add the following content to this file (adjust the path as needed):

```
[Unit]
Description=gunicorn socket

[Socket]
ListenStream=/path_to_home_dir/ostdata/run/gunicorn.sock

[Install]
WantedBy=sockets.target
```

Replace 'path_to_app_directory' with the actual application directory.

### 2. Define the service file

```
sudo nano /etc/systemd/system/gunicorn_ostdata.service
```

Add the following content to this file:

```
[Unit]
Description=OSTdata gunicorn daemon
Requires=gunicorn_ostdata.socket
After=network.target


[Service]
User=ostdata
Group=www-data
WorkingDirectory=/path_to_home_dir/ostdata/OSTdata
ExecStart=/path_to_home_dir/ostdata/ostdata_env/bin/gunicorn \
          --access-logfile - \
          --workers 3 \
          --timeout 600 \
          --error-logfile /path_to_home_dir/ostdata/OSTdata/logs/gunicorn_error.log \
          --capture-output \
          --log-level info \
          --bind unix:/path_to_home_dir/ostdata/run/gunicorn.sock \
          ostdata.wsgi:application

[Install]
WantedBy=multi-user.target
```

Adjust the directories and the user name as needed.

### 3. Start gunicorn and set it up to start at boot

```
sudo systemctl start gunicorn_ostdata.socket
sudo systemctl enable gunicorn_ostdata.socket
```

Check the Gunicorn status and logs:

```
sudo systemctl status gunicorn_ostdata.socket
sudo journalctl -u gunicorn_ostdata.socket
```

Check that a gunicorn.sock file is created:

```
ls /path_to_home_dir/ostdata/OSTdata/OSTdata/run/
>>> gunicorn.sock
```

When changes are made to the gunicorn.service file run:

```
sudo systemctl daemon-reload
sudo systemctl restart gunicorn_ostdata
```

Check status:

```
sudo systemctl status gunicorn_ostdata
```

## Set up logrotate

To enable log rotation the following file should be added to /etc/logrotate.d:

```
/home/ostdata/www/ostdata/OSTdata/logs/*.log {
  rotate 14
  daily
  compress
  delaycompress
  nocreate
  notifempty
  missingok
  su ostdata www-data
}
```

Change user name, group, and the log directory as needed.

Alternatively, `logging.handlers.RotatingFileHandler` can be configured as the logging handler in `settings_production.py`.

## Configure Apache web server

We will deploy the website using the Gunicorn Unix socket defined above on an Apache web server. The Apache reverse proxy functionality will be used for this purpose.

The website should be available on a specific subpage. In our case this is "data_archive". For this to work the variable 'FORCE_SCRIPT_NAME' in 'settings_production.py' is set to '/data_archive'.

### 1. Activate proxy modules

In the first step we will activate the necessary proxy modules.

```
sudo a2enmod proxy
sudo a2enmod proxy_http
```

### 2. Configure the virtual host

The second step is to configure the virtual host. Add the following to your virtual host definition in `/etc/apache2/sites-enabled` (the SSL vHost for your domain).

```
SSLProxyEngine on
SSLProxyVerify none
SSLProxyCheckPeerCN off
SSLProxyCheckPeerName off
ProxyPreserveHost On

ProxyPass /data_archive/static/ !

Alias "/data_archive/static/" "/path_to_app_directory/ostdata/OSTdata/static/"
# Serve Vite-built assets at /data_archive/assets/ (files live in static/assets/)
Alias "/data_archive/assets/" "/path_to_app_directory/ostdata/OSTdata/static/assets/"
Alias /data_archive/robots.txt "/path_to_app_directory/ostdata/OSTdata/static/robots.txt"


# Serve the SPA shell for all non-API routes under /data_archive
<IfModule mod_rewrite.c>
  RewriteEngine On
  # Do not rewrite API or static
  RewriteCond %{REQUEST_URI} !^/data_archive/(api|static|assets)/ [NC]
  RewriteCond %{REQUEST_URI} !^/data_archive/robots\.txt$ [NC]
  # Rewrite all other /data_archive routes to the built SPA index.html
  RewriteRule ^/data_archive(?:/.*)?$ /data_archive/static/index.html [PT,L]
</IfModule>

Define SOCKET_NAME /path_to_app_directory/ostdata/run/gunicorn.sock
ProxyPass        /data_archive/api unix://${SOCKET_NAME}|http://%{HTTP_HOST}/data_archive/api
ProxyPassReverse /data_archive/api unix://${SOCKET_NAME}|http://%{HTTP_HOST}/data_archive/api
```

The first block ensures that our Django app trusts the proxy, while the `ProxyPass /data_archive/static/ !` line makes sure requests for static files are not proxied (they are served directly by Apache). The next aliases map static files and `robots.txt`. The final block proxies API requests to Gunicorn via the Unix socket. Replace 'path_to_app_directory' with the actual application directory.

### 3. Serve static files

Since Django itself does not serve files, the static files must be served directly from the Apache server. For this purpose, we create a configuration file in "/etc/apache2/conf-available", which we name "data_archive.conf".

Add the following lines to this file:

```
<Directory "/path_to_app_directory/ostdata/OSTdata/static/">
    Require all granted
    Options -Indexes
    AllowOverride None
    # Long-lived caching for fingerprinted assets; adjust if needed
    ExpiresActive On
    ExpiresDefault "access plus 1 year"
    Header set Cache-Control "public, max-age=31536000, immutable"
    # Prevent MIME sniffing issues
    Header always set X-Content-Type-Options "nosniff"
</Directory>
```

As always, replace 'path_to_app_directory' with the correct path.

Activate this configuration file with:

```
sudo a2enconf data_archive
```

### 4. Restart the Apache server

Restart the Apache web server so that the changes take into effect:

```
sudo systemctl restart apache2
```

The data archive website should now be up and running.

Notes:

- We deploy the Vue SPA through Django’s static pipeline (`collectstatic`). No separate Apache alias for `frontend/dist` is needed.
- Make sure `robots.txt` is available in `static/robots.txt` so it’s served at `/data_archive/robots.txt`.

## Directory watcher (automatic ingest)

This project includes a filesystem watcher that monitors your data root and automatically:

- creates new Observation Runs for new top-level directories
- ingests new files below a run
- updates DB paths and run name when a top-level run directory is renamed
- reacts to file modifications (re-extracts header info and updates stats)

Configure environment in `ostdata/.env`:

```
# Absolute directory to watch
DATA_DIRECTORY=/absolute/path/to/data

# Optional: enable periodic FS/DB reconciliation (Celery Beat)
ENABLE_FS_RECONCILE=false

# Optional: watcher tuning
# Debounce window for modified events (seconds)
WATCH_DEBOUNCE_SECONDS=2.0
# Comma-separated list of ignored file suffixes
WATCH_IGNORED_SUFFIXES=.filepart,.bck,.swp
# Delay before processing newly created files (seconds)
WATCH_CREATED_DELAY_SECONDS=20
# Optional stability window (seconds): file size must remain unchanged
WATCH_STABILITY_SECONDS=0
# Use polling instead of inotify (set to 1 for some network mounts, e.g. NFS/CIFS)
WATCH_USE_POLLING=0
# Polling interval in seconds (only used when WATCH_USE_POLLING=1)
WATCH_POLLING_INTERVAL=1.0
```

Run the watcher (manual):

```
python manage.py watch_data
```

Run the watcher as systemd service (recommended):

```
sudo nano /etc/systemd/system/ostdata-watcher.service
```

```
[Unit]
Description=OSTdata directory watcher
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/path/to/OSTdata
Environment=PYTHONUNBUFFERED=1
# Optionally load environment from a file (paths, settings overrides)
# EnvironmentFile=/etc/ostdata/ostdata.env
ExecStart=/path/to/venv/bin/python manage.py watch_data
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Then:

```
sudo systemctl daemon-reload
sudo systemctl enable ostdata-watcher
sudo systemctl start ostdata-watcher
sudo journalctl -u ostdata-watcher -f
```

Notes:

- Only top-level directories are treated as runs. Subfolders are ignored for run create/delete.
- File modifications are debounced (short delay) to avoid re-processing half-written files.
- File moves update the stored path; top-level run renames also update the run name and all paths under it.

Hash-based recovery of renamed files:

- Each DataFile stores file_size and a SHA-256 content_hash computed at ingest and on modification.
- If a rename/move is missed while the watcher is down, the periodic reconcile task scans the expected run directory for files matching the same size and hash and rewrites DB paths accordingly.
- The watcher’s move handler also attempts a hash-based match when it cannot find the original record.

### One-off rename helper

If a run folder was renamed outside the watcher, fix DB names/paths with:

```
python manage.py rename_run OLD_RUN_NAME NEW_RUN_NAME [--data-root /absolute/data]
```

### Optional periodic reconcile (Celery Beat)

To enable an automated reconciliation (verify/correct stored paths to match the current run name and existing files), set in `ostdata/.env`:

```
ENABLE_FS_RECONCILE=true
```

Ensure Celery Beat is running (see Celery section). The task runs daily at 03:00 by default and logs a summary.

## Async Download Jobs (Celery)

This project supports asynchronous preparation of ZIP archives for data files using Celery. You can run tasks synchronously (eager mode, no Redis needed) or with Redis for real async behavior. Production notes included below.

Frontend behavior (Data Files tables):

- Observation Run Detail → Data Files:
  - "Download all" and "Download filtered" automatically use the asynchronous download job when more than 5 files are involved. Otherwise, a direct download is used.
  - Progress is polled in the background; once ready, the ZIP download starts automatically (with authentication).
- Object Detail → Data Files:
  - Same behavior as above; this view uses the bulk job (across runs).
- Note: In eager mode (without Redis) jobs run synchronously and the download is usually available immediately.

### 1) Minimal setup (no Redis, eager mode)

- Install dependencies (in your venv):
  - `pip install -r requirements.txt`
- Configure environment:
  - Set `CELERY_TASK_ALWAYS_EAGER=true` (or in `.env`: `CELERY_TASK_ALWAYS_EAGER=1`).
  - No broker or worker is needed; tasks run synchronously in the Django process.
- Use the API:
  - Create job: `POST /api/runs/runs/{run_id}/download-jobs/` with JSON `{ "ids": [..]?, "filters": {..}? }`
  - Poll status: `GET /api/runs/jobs/{job_id}/status`
  - Download when ready: `GET /api/runs/jobs/{job_id}/download`

### 2) Local async setup (Redis via Docker)

- Start Redis (step-by-step):
  
  1. Install Docker if you don’t have it:
     
     - Windows/macOS: install "Docker Desktop" from the official site and start it (ensure it’s running).
     - Linux (Debian/Ubuntu):
       - `sudo apt update`
       - `sudo apt install -y docker.io`
       - Add your user to the docker group so you can run docker without sudo: `sudo usermod -aG docker $USER` and then log out/in (or reboot) once.
  
  2. Verify Docker works: `docker --version` (should print a version) and `docker run hello-world` (should print a hello message).
  
  3. Start a Redis container locally:
     
     - Command:
       
       ```bash
       docker run --name ost-redis -p 6379:6379 -d --restart unless-stopped redis:7-alpine
       ```
       
       - `--name ost-redis`: names the container so you can manage it easily
       - `-p 6379:6379`: maps Redis’ default port to your machine
       - `-d`: runs in background (detached)
       - `--restart unless-stopped`: auto-start on reboot
  
  4. Check it’s running:
     
     - `docker ps` should show a container named `ost-redis` with `0.0.0.0:6379->6379/tcp`
  
  5. Stop/Start later:
     
     - Stop: `docker stop ost-redis`
     - Start again: `docker start ost-redis`

- Configure environment (e.g. in `.env`):
  
  - `CELERY_TASK_ALWAYS_EAGER=0`
  - `CELERY_BROKER_URL=redis://localhost:6379/0`
  - `CELERY_RESULT_BACKEND=redis://localhost:6379/1`

- Run Celery worker (from `OSTdata/`):
  
  - `celery -A ostdata worker -l info`
  - On macOS/Windows, you may add `-P solo`.

- Use the same API endpoints as above. Jobs will run in the background; poll status and download when done.

### 3) Production configuration

- Redis/Broker (local installation on the same server):
  
  1. Install Redis (Debian/Ubuntu):
     
     - `sudo apt update`
     - `sudo apt install -y redis-server`
  
  2. Enable/Start the service:
     
     - `sudo systemctl enable redis-server`
     - `sudo systemctl start redis-server`
     - Check status: `systemctl status redis-server` (should be active/running)
  
  3. Verify Redis is working:
     
     - `redis-cli ping` → should return `PONG`
  
  4. Recommended config (bind to localhost only):
     
     - Edit `/etc/redis/redis.conf` and ensure:
       - `bind 127.0.0.1 ::1` (or at least `127.0.0.1`)
       - `protected-mode yes`
     - Restart Redis: `sudo systemctl restart redis-server`
  
  5. Django/Celery environment (production):
     
     - Prefer defining environment in the systemd units (Environment or EnvironmentFile). Services do not read `/etc/environment` by default.
     
     - Minimal variables (either in an EnvironmentFile or inline in the unit):
       
       - `CELERY_TASK_ALWAYS_EAGER=0`
       - `CELERY_BROKER_URL=redis://127.0.0.1:6379/0`
       - `CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1`
     
     - Example EnvironmentFile:
       
       ```ini
       # /etc/ostdata/celery.env
       CELERY_TASK_ALWAYS_EAGER=0
       CELERY_BROKER_URL=redis://127.0.0.1:6379/0
       CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1
       # Optional app vars also used by gunicorn
       DJANGO_SETTINGS_MODULE=ostdata.settings
       SECRET_KEY=...  
       ```
       
       And in the unit:
       
       ```ini
       EnvironmentFile=/etc/ostdata/celery.env
       ```
     
     - About `.env` vs systemd variables: `settings.py` loads `.env`, but values provided by the process environment (systemd Environment/EnvironmentFile) take precedence. You can keep `.env` for defaults and override in systemd as needed.
  
  6. Apply migrations (only needed once per DB after enabling the results backend):
     
     - From your project directory: `python manage.py migrate`
     - If you already ran migrations after adding `django_celery_results`, you can skip this step.

- Workers (systemd services):
  
  - Run Celery under systemd so it starts on boot and is supervised.
  
  - Example unit file `/etc/systemd/system/celery.service`:
    
    ```ini
    [Unit]
    Description=Celery Worker for OSTdata
    After=network.target redis-server.service
    
    [Service]
    Type=simple
    User=www-data
    Group=www-data
    WorkingDirectory=/path/to/OSTdata
    Environment=PYTHONUNBUFFERED=1
    Environment=CELERY_TASK_ALWAYS_EAGER=0
    Environment=CELERY_BROKER_URL=redis://127.0.0.1:6379/0
    Environment=CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1
    ExecStart=/path/to/venv/bin/celery -A ostdata worker -l info -O fair
    Restart=always
    RestartSec=5
    
    [Install]
    WantedBy=multi-user.target
    ```
  
  - Reload and start:
    
    - `sudo systemctl daemon-reload`
    - `sudo systemctl enable celery`
    - `sudo systemctl start celery`
    - Check logs: `journalctl -u celery -f`
  
  - Optional: Celery Beat for periodic tasks (e.g., cleanup). Create `/etc/systemd/system/celery-beat.service`:
    
    ```ini
    [Unit]
    Description=Celery Beat for OSTdata
    After=network.target redis-server.service
    
    [Service]
    Type=simple
    User=www-data
    Group=www-data
    WorkingDirectory=/path/to/OSTdata
    Environment=PYTHONUNBUFFERED=1
    Environment=CELERY_TASK_ALWAYS_EAGER=0
    Environment=CELERY_BROKER_URL=redis://127.0.0.1:6379/0
    Environment=CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1
    ExecStart=/path/to/venv/bin/celery -A ostdata beat -l info
    Restart=always
    RestartSec=5
    
    [Install]
    WantedBy=multi-user.target
    ```

- Storage and cleanup:
  
  - Ensure the worker user has read access to data files and write access to a temp directory for ZIPs.
  
  - Cleanup of old ZIPs:
    
    - Built-in option (recommended): enable the Celery Beat task that deletes ZIPs for jobs past `expires_at` and marks them `expired`.
      
      - In `ostdata/.env`:
        
        ```
        ENABLE_DOWNLOAD_CLEANUP=true
        DOWNLOAD_JOB_TTL_HOURS=72
        ```
      
      - Ensure Celery Beat is running (see service example above). Jobs completed by the worker are given an expiry based on `DOWNLOAD_JOB_TTL_HOURS`.
    
    - Alternative: a cron job that deletes ZIPs older than N days in your temp directory.

- Security:
  
  - Keep Redis bound to `127.0.0.1` unless you explicitly need remote access; otherwise firewall the port.
  - The API enforces ownership/visibility: ZIPs can only be downloaded by the user who created the job (or for public runs when anonymous).

### API summary

- `POST /api/runs/runs/{run_id}/download-jobs/` → `{ job_id }`
- `GET /api/runs/jobs/{job_id}/status` → `{ status, progress, bytes_total, bytes_done, url? }`
- `POST /api/runs/jobs/{job_id}/cancel` → `{ status }`
- `GET /api/runs/jobs/{job_id}/download` → ZIP file when ready

Payload example for job creation:

```json
{
  "ids": [1, 2, 3],
  "filters": {
    "file_type": "FITS",
    "main_target": "M67",
    "exposure_type": ["LI"],
    "spectroscopy": false,
    "exptime_min": 10,
    "exptime_max": 600,
    "file_name": "light",
    "instrument": "QHY"
  }
}
```

Notes:

- In eager mode, job creation returns immediately and the resulting ZIP can usually be downloaded right away.
- The ZIP is generated on the server’s filesystem; ensure adequate disk space and permissions.

# Access Control (ACL) for Admin Features

The project uses a lightweight ACL on top of Django auth to control access to admin features. Superusers bypass all checks. Roles (staff, supervisor, student) are represented by Django Groups, and a set of custom Permissions (codenames) is attached to the `User` content type.

- Permissions (subset):
  
  - Users: `users.acl_users_view`, `users.acl_users_edit_roles`, `users.acl_users_delete`
  - Objects: `users.acl_objects_view_private`, `users.acl_objects_edit`, `users.acl_objects_merge`, `users.acl_objects_delete`
  - Runs: `users.acl_runs_edit`, `users.acl_runs_publish`, `users.acl_runs_delete`
  - Tags: `users.acl_tags_manage`
  - Jobs: `users.acl_jobs_view_all`, `users.acl_jobs_cancel_any`, `users.acl_jobs_ttl_modify`
  - Maintenance: `users.acl_maintenance_cleanup`, `users.acl_maintenance_reconcile`, `users.acl_maintenance_orphans`
  - Banner: `users.acl_banner_manage`
  - System: `users.acl_system_health_view`, `users.acl_system_settings_view`

- Defaults:
  
  - Groups `staff`, `supervisor`, `student` are created automatically together with sensible default permission sets on first access to the ACL endpoint.
  - On login, the system syncs flags (`is_staff`, `is_supervisor`, `is_student`) to membership in the respective Django Groups to keep ACLs consistent.

- Admin API to manage ACL:
  
  - GET `/api/users/admin/acl/` → returns `{ groups, permissions, matrix }`
  - POST `/api/users/admin/acl/set` with `{ matrix: { groupName: [permissionCodenames...] } }`

- UI:
  
  - Admin → Users: includes an “ACL” matrix to set permissions per role.
  - Admin routes are additionally guarded on the frontend:
    - Health requires `acl_system_health_view`
    - Maintenance requires at least one of `acl_maintenance_*` or `acl_banner_manage`
    - Users requires `acl_users_view`
  - Buttons and actions in Jobs, Objects, Runs and Tags are shown/disabled according to the user’s permissions; missing rights show a tooltip “No permission”.

Notes:

- Backend endpoints enforce permissions regardless of UI state.
- Superuser bypasses all ACL checks.
- If you change Group memberships manually (e.g. via Django admin), the changes take effect immediately; on next login the role flags are synced.

# Acknowledgements

This projects uses code from the following projects:

* The .ser parser from the [PlanetarySystemStacker (PSS)](https://github.com/Rolf-Hempel/PlanetarySystemStacker)
