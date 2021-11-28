 
#!/usr/bin/env python
"""
Command-line tool using argparse
"""
import argparse
import requests
import json
import time
from nano_rpc import Api

# GLOBAL variables
url = "http://localhost:45000"
headers = {"Content-type": "application/json", "Accept": "text/plain"}
api = Api(url)
rep = "nano_3e3j5tkog48pnny9dmfzj1r16pg8t1e76dz5tmac6iq689wyjfpiij4txtdo" #genesis account (not voting)
setup_stats = None #{"destination_seed" : {"bucket" : 1, "counter" : 0}}

def set_setup_stats(bucket_i, seed, current_index):
    # {
    #     "buckets": {
    #         "bucket1": {
    #             "seed": "103114481181051161210000...1",
    #             "opened_accounts": 9999
    #         },
    #         "bucket2": {
    #             "seed": "103114481181051161210000...2",
    #             "opened_accounts": 9999
    #         }
    #     }
    # }
    setup_stats["buckets"]["bucket{}".format(bucket_i)] = {"seed" : seed, "opened_accounts" : current_index }



def get_bucket_seed(bucket):
    prefix = "10311448118105116121"    
    filler = "0"
    return "{}{}{}".format(prefix, filler * (64 - len(str(bucket))- len(prefix)), bucket)     

def create_send_and_receive_blocks(source_private_key, dest_amount_raw, dest_seed, dest_index):
    source_account_data = api.key_expand(source_private_key)
    # print("private key {} for account {}".format(source_account_data["private"],
    #                                              source_account_data["account"]))

    # {
    #     "private": "34F0A37AAD20F4A260F0A5B3CB3D7FB50673212263E58A380BC10474BB039CE4",
    #     "public": "B0311EA55708D6A53C75CDBF88300259C6D018522FE3D4D0A242E431F9E8B6D0",
    #     "account": "nano_3e3j5tkog48pnny9dmfzj1r16pg8t1e76dz5tmac6iq689wyjfpiij4txtdo"
    # }   

    req_dest_account = {
        "action": "deterministic_key",
        "seed": dest_seed,
        "index": dest_index,
    }
    r = requests.post(url, json=req_dest_account, headers=headers)
    dest_account_data = json.loads(r.text)
    dest_account_data = {
        "seed": dest_seed,
        "index": dest_index,
        "private": dest_account_data["private"],
        "public": dest_account_data["public"],
        "account": dest_account_data["account"],
    }    
    req_source_balance = {
        "action": "account_balance",
        "account": source_account_data["account"],
    }
    r = requests.post(url, json=req_source_balance, headers=headers)
    source_balance = int(json.loads(r.text)["balance"])

    # END CREATE SEED AND WRITE TO FILE AND QR CODE
    # -------------- 1) END -------------------------

    # -------------- 2) START -------------------------
    if source_balance > 0 and source_balance >= dest_amount_raw:
        send_block = api.create_send_block_pkey(
            source_account_data["private"],
            source_account_data["account"],            
            dest_account_data["account"],
            dest_amount_raw
        )

        receive_block = api.create_open_block(
            dest_account_data["account"],
            dest_account_data["private"],
            dest_amount_raw,
            rep,
            send_block["hash"]
        )
    else:
        print(
            "insuffient funds{} bucket:{} account:{}".format(
                source_balance, i, source_account_data["account"]
            )
        )



if __name__ == "__main__":

    # Create the parser object, with its documentation message.
    parser = argparse.ArgumentParser(description="Echo your input")

    # Add a position-based command with its help message.
    parser.add_argument("--genesis_pkey", default= "34F0A37AAD20F4A260F0A5B3CB3D7FB50673212263E58A380BC10474BB039CE4", help="Seed to derive destination addresses") 
    parser.add_argument("--accounts_per_bucket", default=10000, help="Seed to derive destination addresses") 

    # Use the parser to parse the arguments.
    args = parser.parse_args()
  

    # -------------- 0) START -------------------------
    # This script will create 10000 accounts in the buckets 0-28 and 93-103. 
    # 400k send blocks and 400k receive blocks in total
    small_buckets = range(0, 28+1)
    large_buckets = range(93, 103+1)
    accounts_per_bucket = 9900

    dest_seed = "0" * 64 #api.generate_seed()

    try :
        #Send from multiple accounts. Init with 1 per bucket
        for i in small_buckets: 
            dest_amount_raw = int(int(2 ** i) * accounts_per_bucket)
            dest_index = i  
            create_send_and_receive_blocks(args.genesis_pkey, dest_amount_raw, dest_seed, dest_index)            

        for i in large_buckets: 
            dest_amount_raw = int(int(2 ** i +1) * accounts_per_bucket)
            dest_index = i  
            create_send_and_receive_blocks(args.genesis_pkey, dest_amount_raw, dest_seed, dest_index)


        for i in small_buckets:
            for dest_index in range(0,accounts_per_bucket) :       
                dest_amount_raw = int(2 ** i)
                l_dest_seed = get_bucket_seed(i)
                create_send_and_receive_blocks(api.get_account_data(dest_seed,i)["private"], dest_amount_raw, l_dest_seed, dest_index)
                set_setup_stats(i, l_dest_seed, dest_index)


        for i in large_buckets:
            for dest_index in range(0,accounts_per_bucket) :        
                dest_amount_raw = int(2 ** i +1) 
                l_dest_seed = get_bucket_seed(i)
                create_send_and_receive_blocks(api.get_account_data(dest_seed,i)["private"], dest_amount_raw, l_dest_seed, dest_index)
                set_setup_stats(i, l_dest_seed, dest_index)
        
        file1 = open("output/setup_stats.json", "w", newline=",")
        file1.write(str(setup_stats).replace("'", "\""))
        file1.close()

    except Exception:
        file1 = open("output/setup_stats.json", "w", newline=",")
        file1.write(str(setup_stats).replace("'", "\""))
        file1.close()