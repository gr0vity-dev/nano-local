# nano-local
Spin up your own local nano network with a genesis account and multiple reps

prerequisites : 
* python3
* docker
* docker-compose

Quickstart :

<code>python3 run_nano_local.py --node_log=True</code>

Spins up a network with 1 genesis acocunt, 2 main reps and 1 small rep.
It uses nanocurrency/nano-test:latest docker image


To remove all docker containers and files created by the script, run :
<code>./remove_nano_local.sh</code>
