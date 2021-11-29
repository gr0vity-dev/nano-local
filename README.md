# nano-local
Spin up your own local nano network with a genesis account and multiple reps

prerequisites : 
* python3
* docker
* docker-compose

To run your own network simply run this command :

<code>python3 run_local.py --pr_quorum={number_of_large_reps} --pr_non_quorum={number_of_small_reps}</code>

Here is an example for a network with 1 genesis acocunt, 3 main reps and 2 small reps.

<code>python3 run_local.py --pr_quorum=3 --pr_non_quorum=2</code>

Te remove all docker containers and files created by the script, run

<code>./remove_nano_local.sh</code>
