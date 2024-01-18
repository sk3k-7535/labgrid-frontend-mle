# LABBY

## Goal
Labby ought to be a labgrid web frontend to get an overview over the places acquired right now, even maybe providing some functionalities.

## usage
The frontend can be started by entering the labgrid-web-client directory and `npm run start` (development)

The labby controller is started by entering the python-labby-client directory and `python -m labby`. 
It also needs to be configured. The configuration takes the frontend- and backend-URL and -REALM. Frontend refers to the web client mentioned above, while the main labgrid installation with its coordinator is called the backend.

## infrastructure
As labgrid does, labby operates on a WAMP system.

### WAMP: web application messaging protocol.
The components that shall communicate with each other are connected to a mutual router and in a mutual realm.
There are two ways of communication:
1. A component broadcasts information in a channel, while other components may listen to it. This is done by publishing or subscribing to a topic and providing a function to run every time, a message is received.
2. A components registers an interface string other components may call to trigger a certain function call in the providing component.

### labgrid-labby communication
Labgrid provides a wamp router (the labgrid-coordinator) to which a component created by labby is able to connect.
The labby backend component subscribes to `place_changed` and `resource_changed` to receive updates.
Also a couple of wrappers for labgrid interfaces are written to be called when necessary.

### web-labby communication
labby also opens another wamp router on its own, for the communication with the frontend. A labby frontend component connects to it and registers multiple interfaces.
The functions called through these are in turn connected to the labby backend client wrapper functions, to call the labgrid interface as necessary.

## overview  
### labgrid-web-client
contains angular web view.
The url for the backend router from labby is implemented on `app/_services/place.service.ts`, `app/_services/resource.service.ts` and `app/console/console.component.ts` with `app/auth/login.service.ts`.

### python-wamp-client
contains main labby functionality (in MVC this would be the Controler)
in `labby/router/.crossbar/config.json` the configuration for the labby router (connection to frontend) is found.

## INSTALLATION
### prerequirements
A labgrid coordinator needs to be running with a known host url (and port).
Also it needs to be known, which authentication method is used.
Default is none, at mle this does not suffice, so in `labby\labby.py` the parameter `DEFAULT_COORDINATOR` needs to be set to `false`.

### labby
Create a virtual environment and install the `requirements.txt` into it.
Within the virtual environment enter the directory `python-wamp-client` and run `python -m labby`.
The configuration can be modified by three options. The easiest though are 
a. create and edit a `.labby_config.json` in the same folder or
b. run the above command with parameters.
For mle usage: change the global parameter `DEFAULT_COORDINATOR` in `labby\labby.py` to `False`.

The configuration json file may look like:
```
{
	"backend_url": "ws://<coordinator-url>:20408/ws",
	"backend_realm": "realm1",
	"frontend_url": "ws://localhost:8083/ws",
	"frontend_realm": "frontend"
}
```
### angular-frontend
For *development* purposes, 
install npm, in the `labgrid-web-client` run `npm install` and then `npm run start`.
For *deployment* purposes, the angular frontend can be build by `npm run build`.
The created/updated folder `labgrid-web-client/dist` may be copied e.g. to /var/www/dist, before a web server as apache deploys the site.
The apache config (`\etc\apache2\sites-available\lgwebend.conf`) may look like this (not for fire)
```
<VirtualHost *:80>
	ServerName lgwebend.localhost
	DocumentRoot /var/www/dist/labgrid-web-client
	<Directory "/var/www/dist/labgrid-web-client">
		AllowOverride All
		Require all granted
	</Directory>
</VirtualHost>
```
Apache needs to enable (`sudo a2ensite lgwebend.conf`) the site and restart (`sudo systemctl reload apache2`).
Afterwards, the website is reacheable under `lgwebend.localhost`.

*Rewriting*
- `sudo a2enmod rewrite`
- `sudo systemctl restart apache2`
- `vim .htaccess` in project root
