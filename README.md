# nano-local
Spin up your own local nano network with a genesis account and multiple reps

prerequisites : 
* python3
* docker
* docker-compose

## Quickstart :

#### Create a virtual python environment with all dependencies :

<code>$ ./venv_nano_local.sh create</code>

Enter into the virtual environment

<code>$ source venv_nano_local/bin/activate</code>

#### Optional configure the network :

<code>$config/nano_local_config.toml</code>

#### Spin up a network :

Create foldes and config : <code>$ python3 nano_local_net.py create</code>

Run docker-compose <code>$ python3 nano_local_net.py start</code>

TODO: Generate blocks with vote weights specified in the nano_local_config.toml

<code>$ python3 nano_local_net.py init</code>  

#### Stop / Delete network nodes
To stop all nodes
<code>$ python3 nano_local_net.py stop</code>

To remove all nodes
<code>$ python3 nano_local_net.py delete</code>

#### Delete virtual python environment
To remove your virtual python environment 
<code>$ ./venv_nano_local.sh delete</code>
<code>$ deactivate</code>
