# nano-local

prerequisites : 
* python3
* docker
* docker-compose V2 (if you use docker-compose v1.xx rename config/default_dc_env_V1 to config/default_dc_env)

## Quickstart :

#### Create a virtual python environment with all dependencies :

<code>$ ./venv_nano_local.sh create</code>

Enter into the virtual environment

<code>$ source venv_nano_local/bin/activate</code>

#### Optional configure the network :

<code>config/nano_local_config.toml</code>

#### Spin up a network :


<code>$ python3 run_nano_local.py create</code> : Create folders and node config

<code>$ python3 run_nano_local.py start</code> : Start all nodes

<code>$ python3 run_nano_local.py init</code> : Create Epochs Canary Burn and Vote weight distribution   

Do all above with a single command: 

<code>$ python3 run_nano_local.py csi</code> c(reate) s(tart) i(nit)


#### Stop / Delete network nodes
<code>$ python3 run_nano_local.py stop</code> : Stop all nodes

<code>$ python3 run_nano_local.py delete</code> : Remove all nodes

#### Delete virtual python environment
To remove your virtual python environment 
<code>$ ./venv_nano_local.sh delete</code>
<code>$ deactivate</code>
