 
#!/usr/bin/env python
"""
Command-line tool using argparse
"""
import requests
import json
import logging
import os
import sys
from nano_rpc import Api
import argparse
import math
import time


# GLOBAL variables
url_1 = "http://localhost:45001"
headers = {"Content-type": "application/json", "Accept": "text/plain"}
path = "/root/testing/nanoBeta"


def add_preconfigured_peers(preconfigured_peers, new_peer):
    if preconfigured_peers == None :
            preconfigured_peers = '"{}"'.format(new_peer)
    else :
        preconfigured_peers = '{},"{}"'.format(preconfigured_peers, new_peer)
    return preconfigured_peers
    

def get_config_node_toml(preconfigured_peers, voting):
    content= '''[node.websocket]
# WebSocket server bind address.
# type:string,ip
address = "::ffff:0.0.0.0"
# Enable or disable WebSocket server.
# type:bool
enable = true
port = 47000

[rpc]
# Enable or disable RPC.
# type:bool
enable = true
enable_sign_hash = true

[node]
work_threads = 1
enable_voting = {voting}
peering_port = 44000
preconfigured_peers = {preconfigured_peers}'''.format(preconfigured_peers= preconfigured_peers, voting = voting)
    return content
     


def get_config_rpc_toml():
    content = '''
# Bind address for the RPC server
# type:string,ip
address = "::ffff:0.0.0.0"

# Enable or disable control-level requests
# type:bool
enable_control = true
enable_sign_hash = true
port = 45000

[logging]
log_rpc = false'''
    return content


def get_docker_compose_node_settings(i, pr_name):
    content ='''  {pr_name}:\r
    build: ./nano_local/nano-workspace/docker/.\r
    user: "0"\r
    command: ./nano-workspace/build/nano_node --daemon --config rpc.enable=true --network dev\r
    container_name : {pr_name}\r
    restart: unless-stopped\r
    ports:\r
    - 4400{i}:44000/udp\r
    - 4400{i}:44000\r
    - 4500{i}:45000\r
    - 4700{i}:47000\r
    volumes:\r
    - ./reps/{pr_name}:/root\r
    networks:\r
    - nano-local\r\r'''.format(i=i, pr_name=pr_name)
    return content
    


def make_pr(docker_conatiner, genesis_key = None):
    # docker_conatiner="nano_local_pr1"
    os.system("docker exec -it {} nano-workspace/build/nano_node --network dev --wallet_create".format(docker_conatiner))
    wallet_pr=os.popen("docker exec -it {} nano-workspace/build/nano_node --network dev --wallet_list | awk 'FNR == 1 {{print $3}}' | tr -d '\r'".format(docker_conatiner)).read()
    if genesis_key == None :
       os.system("docker exec -it {} nano-workspace/build/nano_node --network dev --account_create --wallet={}".format(docker_conatiner,wallet_pr)) 
    else:
        os.system("docker exec -it {} nano-workspace/build/nano_node --network dev --wallet_add_adhoc --wallet={} --key=34F0A37AAD20F4A260F0A5B3CB3D7FB50673212263E58A380BC10474BB039CE4".format(docker_conatiner, wallet_pr)).read()
    pr_address=os.popen("docker exec -it {} nano-workspace/build/nano_node --network dev --wallet_list | awk 'FNR == 2 {print $1}' | tr -d '\r')".format(docker_conatiner)).read()
    return {"wallet" : wallet_pr, "nano_address" : pr_address}

def make_pr_api(rpc_url, docker_conatiner, pr_type, genesis_key = None):
    print(rpc_url , docker_conatiner, pr_type, genesis_key )
    api = Api(rpc_url)
    seed = api.generate_seed()
    
    account_data = {}
    if genesis_key == None:
        wallet_data = api.wallet_create(seed)
        account_data = api.get_account_data(seed,0)
        is_genesis = False
    else :
        wallet_data = api.wallet_create(None)
        seed = None
        account_data["account"] = api.wallet_add(wallet_data["wallet"], genesis_key)["account"]
        account_data["private"] = genesis_key
        is_genesis = True
    
    response = {"rpc_url" : rpc_url,
                "docker_conatiner" : docker_conatiner,
                "wallet" : wallet_data["wallet"] ,
                "seed" : seed,               
                "private_key" : account_data["private"],
                "nano_address" : account_data["account"],
                "is_genesis" : is_genesis ,
                "pr_type": pr_type }   
    return response
    

if __name__ == "__main__":

    # Create the parser object, with its documentation message.
    parser = argparse.ArgumentParser(description="Echo your input")

    # Add a position-based command with its help message.    
    parser.add_argument(
        "--pr_quorum",
        type=int,
        help="#of prs to reach quorum",
    )
    parser.add_argument(
        "--pr_non_quorum", type=int, help="#of prs who are not needed for quorum"
    )

    parser.add_argument(
        "--build", type=bool, default=True, help="#of prs who are not needed for quorum"
    )

    parser.add_argument(
        "--compose", type=bool, default=True, help="#of prs who are not needed for quorum"
    )

    # Use the parser to parse the arguments.
    args = parser.parse_args()

    print('''Default settings for the local nano network :
    Your network will have {} major reps that hold 70 percent of the voting weight.
    Your network will have {} minor reps that hold 0.015 percent of the voting weight each.
    The remaining weight sits idle at the genesis account. This account will not vote.
    When all your PRs are running, the network has {} percent online voting weight. 
    '''.format(args.pr_quorum, args.pr_non_quorum, (70 + args.pr_non_quorum * 0.015)))
    time.sleep(5)

    #TODO : Min quroumPR = 1, max quroumPR = 900 , max totalPR = 990
    os.system("mkdir -p nano_local")  
    os.system("mkdir -p reps")  
    os.system("mkdir -p output")  
    if(os.path.isdir("nano_local/nano-workspace")) == False :
        os.system("cd nano_local && git clone https://github.com/dsiganos/nano-workspace.git")  
    if args.build :
        os.system("cd nano_local/nano-workspace/docker && docker build -t gr0vity/local_beta:1.0 .")    
    #TODO set flag when built succeeded. Dont run again!

    total_pr = args.pr_quorum + args.pr_non_quorum + 1 #special case for genesis. make it as non voting
    
    #erase content of existing file
    file1 = open(
            "docker-compose.yml", "w", newline="\n"
        )
    file1.write("version: '3'\rservices:\r\r")
    file1.close()
    #append new content
    file1 = open(
            "docker-compose.yml", "a", newline="\n"
        )

    pr_names = {}
    preconfigured_peers = None

    for i in range(0, total_pr ): 
        if i == 0 : 
            pr_name  = "nano_local_genesis" 
        else  :
            pr_name = "nano_local_pr{}".format(i)
        preconfigured_peers = add_preconfigured_peers(preconfigured_peers,pr_name)
        os.system("cd reps && mkdir -p {}".format(pr_name))
        if i <= args.pr_quorum : 
            if i == 0 : #genesis
                pr_names[pr_name] = {"pr_type" : "genesis", 
                                     "genesis_key" : "34F0A37AAD20F4A260F0A5B3CB3D7FB50673212263E58A380BC10474BB039CE4", 
                                     "peering_port": "4400{}".format(i), 
                                     "rpc_port" : "4500{}".format(i)}
            else:
                pr_names[pr_name] = {"pr_type" : "pr_quorum", 
                                     "genesis_key" : None, 
                                     "peering_port": "4400{}".format(i),
                                     "rpc_port" : "4500{}".format(i)}            
        else :
            pr_names[pr_name] = {"pr_type" : "pr_non_quorum", "genesis_key" : None, "peering_port": "4400{}".format(i), "rpc_port" : "4500{}".format(i)}
  
        
        file1.write(get_docker_compose_node_settings(i, pr_name))
    file1.write("\rnetworks:\r")
    file1.write("  nano-local:\r")
    file1.write("    driver: bridge\r")
    file1.close()

    preconfigured_peers = "[{}]".format(preconfigured_peers)
    print(preconfigured_peers)

      
    for key, value in pr_names.items(): 
        os.system("cd reps/{} && mkdir -p NanoDev".format(key))  
        voting = "false" if key == "genesis" else "true" 
        f_config_node = open(
            "reps/{}/NanoDev/config-node.toml".format(key), "w", newline="\n"
        )
        f_config_node.write(get_config_node_toml(preconfigured_peers,voting))
        f_config_node.close()

        f_config_rpc = open(
            "reps/{}/NanoDev/config-rpc.toml".format(key), "w", newline="\n"
        )
        f_config_rpc.write(get_config_rpc_toml())
        f_config_rpc.close()

    exit

    if args.compose :
    #docker compose bugs. works eventually when trying once for each PR
        # for i in range(1, total_pr + 1):
        #     time.sleep(2)  
        #     os.system("docker-compose up -d") 
        os.system("docker-compose up -d")    

    #API calls to create wallets. account and seed data for PRs
    pr_data = {}
    f = open(
        "output/pr_data.txt", "w", newline="\n"
    )
    f.write("PR seeds wallets and more\r")
    f.close()
    for key, value in pr_names.items():        
        result = make_pr_api("http://127.0.0.1:{}".format(value["rpc_port"]),
                                    key, 
                                    value["pr_type"],
                                    value["genesis_key"] )
                         
        f = open(
            "output/pr_data.txt", "a", newline="\n"
        )
        f.write("{}\r".format(str(result)))
        f.close()
        pr_data[key] = result

   

    for key, genesis in pr_data.items():        
        if genesis["pr_type"] == "genesis" : 
            api = Api(genesis["rpc_url"])  
            genesis_balance = int(api.check_balance(genesis["nano_address"])["balance_raw"])
            
            for key, pr in pr_data.items():
                if pr["pr_type"] == "pr_quorum" :
                    pr_balance_raw = round((genesis_balance * 0.7) /  args.pr_quorum)
                elif pr["pr_type"] == "pr_non_quorum" :
                    pr_balance_raw = round(genesis_balance * 0.015)
                else:
                    print(str(pr))
                    continue
                
                send_block = api.create_send_block_pkey(genesis["private_key"],
                                        genesis["nano_address"],
                                        pr["nano_address"],
                                        pr_balance_raw)
                print("SEND FROM {} To {} : HASH {}".format(genesis["nano_address"],pr["nano_address"],send_block["hash"] ))
                open_block = api.create_open_block(pr["nano_address"],
                                    pr["private_key"],
                                    pr_balance_raw,
                                    pr["nano_address"],
                                    send_block["hash"]
                                    )
                print("OPENED for {} with PR {}".format(pr["nano_address"],pr["nano_address"] ))                
                    

        
    

