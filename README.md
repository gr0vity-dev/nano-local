# nano-local
nano-local is a feature complete local nanocurrency network that enables prototyping on a local version of the nano network.
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

<code>$ ./setup_venv.sh</code>

#### Spin up a network :

| Action            | Code                                          | Description  |
| :----------       |:--------------------------------------------- | -----|
| create            |<code>$ ./run_nano_local.py create</code>      | Create folders and node config |
| start             |<code>$ ./run_nano_local.py start</code>       | Start all nodes and services (optional flag <code>--build = true</code> rebuilds docker containers)|
| init              |<code>$ ./run_nano_local.py init</code>        | Create Epochs Canary Burn and Vote weight distribution |
| csi               |<code>$ ./run_nano_local.py csi</code>         | Do all of the above : c(reate) s(tart) i(nit) |
| test              |<code>$ ./run_nano_local.py test</code>        | runs tests from <code>[testcase]</code> section of <code>nano_local_config.toml</code>  |
| pytest            |<code>$ ./run_nano_local.py pytest</code>      | runs tests from <code>[testcase]</code> section of <code>nano_local_config.toml</code> |
| stop              |<code>$ ./run_nano_local.py stop</code>        | Stop all nodes and services |
| stop_nodes        |<code>$ ./run_nano_local.py stop_nodes</code>  | Stop nodes only |
| restart           |<code>$ ./run_nano_local.py restart</code>     | Restart nodes only  |
| restart_wait_sync |<code>$ ./run_nano_local.py restart_wait_sync</code>    | Restart nodes until 100% of blocks are confirmed  |
| reset             |<code>$ ./run_nano_local.py reset</code>       | Delete all blocks except genesis block by removing data.ldb from all nodes |
| destroy           |<code>$ ./run_nano_local.py destroy</code>     | Remove all nodes and delte virtaul environment |


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

All tests are configured in the <code>[testcase]</code> section of <code>nano_local_config.toml</code>
<code>$ ./run_nano_local.py test</code> runs the configured tests



| Module | Test                        | Code                                           | Description  |
| :---   | :-------------------------  |:-----------------------------------------------| -------------|
|basic   |>NetworkChecks               |
|basic   |rpc_online                   |<code>test_rpc_online</code>                    | all nodes online| 
|basic   |peer_count                   |<code>test_peer_count</code>                    | all nodes interconnected|
|basic   |equal_block_count            |<code>test_equal_block_count</code>             | all nodes have same blocks|
|basic   |equal_online_stake_total     |<code>test_equal_online_stake_total</code>      | all nodes see same online weight|
|basic   |equal_confirmation_quorum    |<code>test_equal_confirmation_quorum</code>     |all nodes have equal network view |
|basic   |equal_peers_stake_total      |<code>test_equal_peers_stake_total</code>       | all nodes have equal peer weight|
|basic   |equal_representatives_online |<code>test_equal_representatives_online</code>  | all nodes have same online representatives|
|basic   |>BlockPropagation            |
|basic   |account_split_10             |<code>test_1_account_split_10</code>            | Create 10 accounts by splitting each account into 2 new accounts|
|basic   |account_split_1000           |<code>test_1_account_split_1000</code>          | Create 1000 accounts by splitting each account into 2 new accounts|

#### Optional : Delete virtual python environment
To remove your virtual python environment 
<code>$ ./setup_venv.sh delete</code>


