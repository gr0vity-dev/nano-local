# nano-local

This project aims to easily spin up custom [nano-currency](https://nano.org) network on your local computer.
The default config spins up a network 4 node : 1 genesis and 3 voting nodes of which each holds 33.3% of the total vote weight.
Each node comes with their rpc and websocket endpoint enabled.

All configuration is done inside the config file :  `nanolocal/nl_config.toml`
Many additional services can be enabled : 
- nanolooker
- nanoNodeMonitor
- nano-vote-visualizer
- nanoticker
A test-suite with some basic network- and block propagation checks can be run after having initialised the network.


## prerequisites 

* python3.7
* docker
* docker-compose (if you use docker-compose v1.xx try adding <code>--compose_version=1</code> flag)

## Quickstart :

#### Create a virtual python environment with all dependencies :

<code>$ ./setup_python_venv.sh</code>

#### Spin up a network :

| Action            | Code                                          | Description  |
| :----------       |:--------------------------------------------- | -----|
| create            |<code>$ ./nl_run.py create</code>      | Create folders and node config |
| start             |<code>$ ./nl_run.py start</code>       | Start all nodes and services (optional flag <code>--build = true</code> rebuilds docker containers)|
| init              |<code>$ ./nl_run.py init</code>        | Create Epochs Canary Burn and Vote weight distribution |
| test              |<code>$ ./nl_run.py test</code>        | runs tests from <code>[testcase]</code> section of <code>nl_config.toml</code>  |
| pytest            |<code>$ ./nl_run.py pytest</code>      | runs tests from <code>[testcase]</code> section of <code>nl_config.toml</code> |
| stop              |<code>$ ./nl_run.py stop</code>        | Stop all nodes and services |
| stop_nodes        |<code>$ ./nl_run.py stop_nodes</code>  | Stop nodes only |
| restart           |<code>$ ./nl_run.py restart</code>     | Restart nodes only  |
| restart_wait_sync |<code>$ ./nl_run.py restart_wait_sync</code>    | Restart nodes until 100% of blocks are confirmed  |
| reset             |<code>$ ./nl_run.py reset</code>       | Delete all blocks except genesis block by removing data.ldb from all nodes |
| destroy           |<code>$ ./nl_run.py destroy</code>     | Remove all nodes and delte virtaul environment |

####  Query nodes :

Each node can be queried via RPC (see the [official documentation](https://docs.nano.org/commands/rpc-protocol/) )

| Node          | RPC                        | Websocket  |
| :----------   |:-------------------------- | -----------------------|
| nl_genesis    |http://127.0.0.1:45000      | ws://127.0.0.1:47000 |
| nl_pr1        |http://127.0.0.1:45001      | ws://127.0.0.1:47001 |
| nl_pr2        |http://127.0.0.1:45002      | ws://127.0.0.1:47002 |
| nl_pr3        |http://127.0.0.1:45003      | ws://127.0.0.1:47003 |


#### Optional : Configure the network :

<code>nl_config.toml</code> define all aspects of the network : genesis account, burn_amount, number of nodes, versions,...

You can enable various services :

| Service       | Code      | Description  |
| :-----------  |:----------| -----|
| remote_address | <code>remote_address='127.0.0.1'</code> | server address inside your LAN (localhost by default) |
| [nanolooker](https://github.com/running-coder/nanolooker) | <code>nanolooker_enable = true</code> | Available at http://{remote_address}:42000 |
| [nano-vote-visualizer](https://github.com/numsu/nano-vote-visualizer) | <code>nanovotevisu_enable = true</code> | Available at http://{remote_address}:42001 |
| [nanoticker](https://github.com/Joohansson/nanoticker) | <code>nanoticker_enable = true</code> | Available at http://{remote_address}:42002 |
| [nano-node-monitor](https://github.com/nanotools/nanoNodeMonitor)| <code>nanomonitor_enable = true</code> | Available at http://{remote_address}:46000, 46001, 46002, ... |

#### Optional : Run Tests :

All tests are configured in the <code>[testcase]</code> section of <code>nl_config.toml</code>
<code>$ ./nl_run.py test</code> runs the configured tests



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


