# nano-local

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

<code>config/nano_local_config.toml</code>

#### Spin up a network :


Create folders and node config : <code>$ python3 run_nano_local.py create</code>

Start all nodes <code>$ python3 run_nano_local.py start</code>

Create Epochs Canary Burn and Vote weight distribution <code>$ python3 run_nano_local.py init</code>  

Do all above : <code>$ python3 run_nano_local.py csi</code> c(reate) s(tart) i(nit)


#### Stop / Delete network nodes
To stop all nodes
<code>$ python3 run_nano_local.py stop</code>

To remove all nodes
<code>$ python3 run_nano_local.py delete</code>

#### Delete virtual python environment
To remove your virtual python environment 
<code>$ ./venv_nano_local.sh delete</code>
<code>$ deactivate</code>
