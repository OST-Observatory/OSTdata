# OSTdata

This project is based on the Astronomical Observation Tracking System (AOTS, https://github.com/vosjo/AOTS), primarily developed by Joris (vosjo).

## Installing Django and dependencies

In the following we will install OSTdata, Django and all dependencies using a python virtualenv to avoid conflicts with other packages and projects.

### 1. Prerequisites

Create a directory where all files and the required Python modules can be placed:
```
mkdir ostdata
cd ostdata
```

For the rest of this guide, we will assume that this directory is located in the user's home directory.

You need the python-dev package and virtualenv  (we assume here a Debian system or one of its derivatives, such as Ubuntu). Moreover you should update pip:
```
sudo apt-get install python-dev-is-python3
pip install -U pip
pip install virtualenv
```

### 2. Create the virtual environment

Create a new virtual python environment for OSTdata and activate it (Bash syntax):
```
virtualenv ostdata_env
source ostdata_env/bin/activate
```

On Windows Computers do

```
virtualenv ostdata_env
ostdata_env\Scripts\Activate
```

If this fails with an error similar to: Error: unsupported locale setting
do:
```
export LC_ALL=C
```

### 3. Clone OSTdata from github
```
git clone https://github.com/OST-Observatory/OSTdata.git
```

### 4. Install the requirements
```
cd OSTdata
pip install -r requirements.txt
```



## Running OSTdata locally

To run OSTdata locally, using the simple sqlite database and the included server:

### 1. Setup the database
```
python manage.py makemigrations obs_run
python manage.py makemigrations objects
python manage.py makemigrations users
python manage.py makemigrations tags
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

### 3. Start the development server
```
python manage.py runserver
```



## Setup postgres database for production

This is only necessary if you want to run in production.

Install the postgres database:

```
sudo apt install postgresql
```

Start postgres command line:
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

Exit the psql:
```
\q
```

## Running OSTdata in production using a postgres database

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
In .env the secret Django security key, the postgres database password, the
server IP and URL, as well as the name of the computer used in production needs
to be specified. If a special log directory is required or a different database
user was defined during setup, this has to be specified here as well.
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
```

Instructions on how to generate a secret key can be found here: https://tech.serhatteker.com/post/2020-01/django-create-secret-key/

### 3. Setup the database
```
python manage.py makemigrations obs_run
python manage.py makemigrations objects
python manage.py makemigrations users
python manage.py makemigrations tags
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

### 5. Collect static files
```
python manage.py collectstatic
```


## Setup gunicorn

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

Replace 'path_to_home_dir' with the actual home directory.


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
Adjusts the directories and the user name as needed.


### 3. Start gunicorn and set it up to start at boot
```
sudo systemctl start gunicorn_ostdata.socket
sudo systemctl enable gunicorn_ostdata.socket
```

Check status of gunicorn with and the log files with:

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


## Setup logroate
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

Alternatively, 'logging.handlers.RotatingFileHandler' can be selected as class
for the logging handlers in settings_production.py.


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

The second step is to configure the virtual host. Add the following to your virtual host definition in '/etc/apache2/sites-enabled'.

```
SSLProxyEngine on
SSLProxyVerify none
SSLProxyCheckPeerCN off
SSLProxyCheckPeerName off
ProxyPreserveHost On

ProxyPass /data_archive/static/ !

Define SOCKET_NAME /path_to_home_directory/ostdata/run/gunicorn.sock
ProxyPass /data_archive unix://${SOCKET_NAME}|http://%{HTTP_HOST}
ProxyPassReverse /data_archive unix://${SOCKET_NAME}|http://%{HTTP_HOST}
```

The first block of lines ensures that our Django weather station app trusts our web server, while the second block ensures that requests for static files are not directed to the Unix socket, as these files are supplied directly by the Apache server (see next step). The third block of commands directs requests to the 'data_archive' page to the Unix socket, and thus to our Django weather app. Replace 'path_to_home_directory' with the actual path to your home directory.


### 3. Serve static files

Since Django itself does not serve files, the static files must be served directly from the Apache server. For this purpose, we create a configuration file in "/etc/apache2/conf-available", which we name "data_archive.conf".

Add the following lines to this file:

```
Alias /data_archive/robots.txt /path_to_home_directory/ostdata/OSTdata/templates/robots.txt
Alias "/data_archive/static" "/path_to_home_directory/ostdata/OSTdata/static"

<Directory /path_to_home_directory/ostdata/OSTdata/static>
        Require all granted
</Directory>
```

As always, replace 'path_to_home_directory' with the correct path.

Activate this configuration file with:

```
sudo a2enconf data_archive
```

### 4. Restart the Apache server

Restart the Apache web server so that the changes take into effect:

```
sudo systemctl restart apache2
```

The weather station website should now be up and running.


# Acknowledgements

This projects uses code from the following projects:

* The .ser parser from the [PlanetarySystemStacker (PSS)](https://github.com/Rolf-Hempel/PlanetarySystemStacker)

