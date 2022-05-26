# nano-local

prerequisites : 
* python3
* docker
* docker-compose (if you use docker-compose v1.xx make add <code>--compose_version=1</code> flag)

## Quickstart :

#### Create a virtual python environment with all dependencies :

<code>$ ./venv_nano_local.sh</code>

#### Spin up a network :

| Action       | Code       | Description  |
| :----------  |:-----------| -----|
| Create | <code>$ ./run_nano_local.py create</code> | Create folders and node config |
| Start | <code>$ ./run_nano_local.py start</code> | Start all nodes (optional flag <code>--build = true</code> rebuilds docker containers)|
| Init |<code>$ ./run_nano_local.py init</code>  | Create Epochs Canary Burn and Vote weight distribution |
| Test |<code>$ ./run_nano_local.py test</code>  | runs all tests (optional flag <code>--case = {module.class.test_method}</code>) |
| CSI | <code>$ ./run_nano_local.py csi</code> | Do all of the above : c(reate) s(tart) i(nit) |
| Stop | <code>$ ./run_nano_local.py stop</code>|  Stop all nodes and services |
| Reset | <code>$ ./run_nano_local.py reset</code> |  Delete all blocks except genesis block by removing data.ldb from all nodes |
| Destroy | <code>$ ./run_nano_local.py destroy</code> |  Remove all nodes and delte virtaul environment |


#### Optional : Configure the network :

<code>nano_local_config.toml</code> define all aspects of the network : genesis account, burn_amount, number of nodes, versions,...

You can enable various services :

| Service       | Code      | Description  |
| :-----------  |:----------| -----|
| remote_address | <code>remote_address='127.0.0.1'</code> | server address inside your LAN (localhost by default) |
| [nanolooker](https://github.com/running-coder/nanolooker) | <code>nanolooker_enable = true</code> | Available at http://{remote_address}:42000 |
| [nano-vote-visualizer](https://github.com/numsu/nano-vote-visualizer) | <code>nanovotevisu_enable = true</code> | Available at http://{remote_address}:42001 |
| [nanoticker](https://github.com/Joohansson/nanoticker) | <code>nanoticker_enable = true</code> | Available at http://{remote_address}:42002 |
| [nano-node-monitor](https://github.com/nanotools/nanoNodeMonitor)| <code>nanomonitor_enable = true</code> | Available at http://{remote_address}:46000, 46001, 46002, ... |


#### Optional : Delete virtual python environment
To remove your virtual python environment 
<code>$ ./venv_nano_local.sh delete</code>


