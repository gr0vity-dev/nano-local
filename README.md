# nano-local
Spin up your own local nano network with a genesis account and multiple reps

prerequisites : 
* python3
* docker
* docker-compose

To run your own network simply run this command :

<code>python3 run_nano_local.py --pr_quorum={#reps_for_quorum} --pr_non_quorum={#additional_reps}</code>

Here is an example for a network with 1 genesis acocunt, 3 main reps and 2 small reps.

<code>python3 run_nano_local.py --pr_quorum=3 --pr_non_quorum=2</code>

When the script fails, try running <code>docker-compose up -d</code> manually and rerun the script again again.

Te remove all docker containers and files created by the script, run

<code>./remove_nano_local.sh</code>
