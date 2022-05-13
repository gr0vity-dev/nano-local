# nano-local

prerequisites : 
* python3
* docker
* docker-compose (if you use docker-compose v1.xx make add <code>--compose_version=1</code> flag)

## Quickstart :

#### Create a virtual python environment with all dependencies :

<code>$ ./venv_nano_local.sh</code>

#### Spin up a network :

<code>$ ./run_nano_local.py create</code> : Create folders and node config

<code>$ ./run_nano_local.py start</code> : Start all nodes

<code>$ ./run_nano_local.py init</code> : Create Epochs Canary Burn and Vote weight distribution   

Do all above with a single command: 

<code>$ ./run_nano_local.py csi</code> c(reate) s(tart) i(nit)

#### Reset network nodes 

<code>$ ./run_nano_local.py csi</code> : Delete all blocks except genesis block

#### Stop / Delete network nodes
<code>$ ./run_nano_local.py stop</code> : Stop all nodes

<code>$ ./run_nano_local.py destroy</code> : Remove all nodes and delte virtaul environment


#### Optional : Configure the network :

<code>nano_local_config.toml</code> define all aspects of the network : genesis account, burn_amount, number of nodes, versions,...

#### Optional : Delete virtual python environment
To remove your virtual python environment 
<code>$ ./venv_nano_local.sh delete</code>


