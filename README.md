# nano-local
This projects enables you to spin up your own local nano network with your own genesis block.
RPC access to the genesis account is enabled by default at port http://localhost:45000 
All configuration is done inside <code>nano_local_config.toml</code>
Many additional services can be enabled : [nanolooker, nanoNodeMonitor, nano-vote-visualizer, nanoticker]
A test-suite is included to do some basic checks. Currently some tests may fail.


prerequisites : 
* python3
* docker
* docker-compose (if you use docker-compose v1.xx try adding <code>--compose_version=1</code> flag)

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

#### Optional : Run Tests :

<code>$ ./run_nano_local.py test</code> runs all tests.

| Test       | Code      | Description  |
| :-----------  |:----------| -----|
|all | <code>$ ./run_nano_local.py test</code> | run all tests|
||<code>$ ./run_nano_local.py test -c basic.NetworkChecks</code>||
|rpc_online|<code>test_rpc_online</code> | all nodes online|
|peer_count|<code>test_peer_count</code> | all nodes interconnected|
|equal_block_count|<code>test_equal_block_count</code> | all nodes have same blocks|
|equal_online_stake_total|<code>test_equal_online_stake_total</code> | all nodes see same online weight|
|equal_confirmation_quorum|<code>test_equal_confirmation_quorum</code> |all nodes have equal network view |
|equal_peers_stake_total|<code>test_equal_peers_stake_total</code> | all nodes have equal peer weight|
|equal_representatives_online|<code>test_equal_representatives_online</code> | all nodes have same online representatives|
||<code>$ ./run_nano_local.py test -c basic.BlockPropagation</code>||
|account_splitting_1022_step1|<code>test_account_splitting_1022_step1</code> | Create 1022 accounts by splitting each account into 2|
|account_splitting_1022_step2|<code>test_account_splitting_1022_step2</code> | Publish all blocks (2044)|
|account_splitting_1022_step3|<code>test_account_splitting_1022_step3</code> | Check if all blocks are confirmed|



#### Optional : Delete virtual python environment
To remove your virtual python environment 
<code>$ ./venv_nano_local.sh delete</code>


