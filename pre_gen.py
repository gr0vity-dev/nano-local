#!./venv_nano_local/bin/python
from os import system
from math import ceil, log10
from time import time
from src.nano_rpc import Api, NanoTools
from src.nano_local_initial_blocks import InitialBlocks
from src.parse_nano_local_config import ConfigReadWrite, ConfigParser, Helpers, DotDict
import copy
from interruptingcow import timeout
import logging
import time
import json
import inspect
from multiprocessing import Process, Queue, Value
import unittest

tc = unittest.TestCase()        

class PreGenLedger():

    def __init__(self):
        self.nano_rpc = Api("undefined") #used to hint at availabe functions whiel coding
        self.nano_rpc = self.set_rpcs() #access all avilable rpcs at nano_rpc.node_name                
        self.nano_tools = NanoTools()
        self.conf = ConfigParser()
        self.open_counter = 0
        self.set_class_params()

    def set_class_params(self):
        self.pre_gen_path = "./testcases/pre_gen/3_nodes_equal_weight__genesis_0_weight/"
        self.pre_gen_file_names = DotDict({"account_split" : f"{self.pre_gen_path}/1_accounts_split.json" , 
                                           "bucket_funding" : f"{self.pre_gen_path}/2_bucket_funding.json",
                                           "bucket_rounds" : f"{self.pre_gen_path}/3_change_blocks_rounds.json", })
        self.online_splitting_depth = 9
        self.pre_gen_bucket_seed_prefix = "FACE" # {prefix}000.000{bucket_id} (example bucket_17_seed : FACE000000000000000000000000000000000000000000000000000000000017)
        
        self.pre_gen_account_end_balance = 100 * 10**30
        self.pre_gen_max_bucket = 105 #used to prefill buckets from 0 to 105 (at 105 you'll need at least pre_gen_account_end_balance=2**106 (~81.113) )
        self.pre_gen_start_index = 0 #skip # seeds and pre_generation at index # (should be 0 except for testing purposes)
        self.pre_gen_accounts = 5000 #(must be smaller than (2**(pre_gen_splitting_depth+1) -2))
        self.pre_gen_bucket_saturation_main_index = 100
        self.pre_gen_bucket_saturation_indexes = [1,2,3,4,5]
        self.pre_gen_bucket_saturation_rounds = 2 # (pre_gen_bucket_saturation_rounds * pre_gen_accounts will be crated per index.  Example: 10*5000 * 4 = 200'000 )
        self.validate()
    
    def validate(self):        
        system(f"mkdir -p {self.pre_gen_path}")
       
        tc.assertGreater(self.pre_gen_account_end_balance, 2 ** (self.pre_gen_max_bucket+1))
        tc.assertGreater(self.pre_gen_max_bucket+1, self.pre_gen_bucket_saturation_main_index)
        for bucket_index in self.pre_gen_bucket_saturation_indexes :
            tc.assertGreater(self.pre_gen_max_bucket,bucket_index)
    
    
    def set_rpcs(self) -> dict[str, object]:
        api = {}
        conf = ConfigParser()
        for node_name in conf.get_nodes_name() :
            node_conf = conf.get_node_config(node_name)
            api[node_conf["name"]] = Api(node_conf["rpc_url"])
        return DotDict(api)

    def open_account(self, representative, send_key, destination_seed, send_amount, final_account_balance_raw, number_of_accounts, destination_index = 0):        
        if number_of_accounts is not None and self.open_counter >= number_of_accounts : return []
        self.open_counter = self.open_counter + 1
        destination = self.nano_rpc.nl_genesis.generate_account(destination_seed, destination_index)
        send_block = self.nano_rpc.nl_genesis.create_send_block_pkey(send_key,
                                                                     destination["account"],
                                                                     send_amount * final_account_balance_raw ,
                                                                     broadcast=False)
               
        open_block = self.nano_rpc.nl_genesis.create_open_block(destination["account"],
                                                                destination["private"],
                                                                send_amount * final_account_balance_raw,
                                                                representative,
                                                                send_block["hash"],
                                                                broadcast=False)
       
        open_block["account_data"]["source_seed"] = destination_seed

        res = [ send_block, open_block ]
        print("accounts opened:  {:>6}".format(self.open_counter), end='\r')
        return res

    def get_prefixed_suffixed_seed(self, prefix, suffix) :        
        return f'{prefix}{str(0)*(64 - len(str(suffix)) - len(str(prefix)))}{str(suffix)}'

    def get_bucket_seed(self, bucket_id) :
        bucket_prefix = "FACE"
        if bucket_id >= 0 and bucket_id <= 128 :
            return self.get_prefixed_suffixed_seed(bucket_prefix, bucket_id)

    def fund_bucket(self, bucket, source_seed, destination_index):

        destination_seed = self.get_bucket_seed(bucket)
        source = self.nano_rpc.nl_genesis.generate_account(source_seed, 0)
        destination = self.nano_rpc.nl_genesis.generate_account(destination_seed, destination_index)
        return self.open_account(destination["account"], source["private"],destination_seed, 1 , 2**bucket, None, destination_index=destination_index )
        

    


    def recursive_split(self,seed_prefix, representative, source_account, number_of_accounts, splitting_depth, current_depth, final_account_balance_raw):
        seed = f'{seed_prefix}{str(0)*(64 - len(seed_prefix))}' 
        blocks = self.open_account(representative , source_account["private"], seed, (2**(splitting_depth - current_depth +1) -1) , final_account_balance_raw, number_of_accounts)
        blocks_ab = self.account_splitting(seed_prefix, number_of_accounts, current_depth=current_depth+1, representative=representative, source_seed=seed, final_account_balance_raw=final_account_balance_raw )
        return blocks + blocks_ab

    def assert_blocks_published(self, blocks, sync = True, is_running = Value('i', False)):
        blocks_to_publish_count = len(blocks)
        rpc_block_count_start = int(self.nano_rpc.nl_genesis.block_count()["count"])
        print(rpc_block_count_start)
        is_running.value = True
        self.nano_rpc.nl_genesis.publish_blocks(blocks, json_data=True) #we don't care about the result
        rpc_block_count_end = int(self.nano_rpc.nl_genesis.block_count()["count"])
        print(rpc_block_count_end)
        is_running.value = False
        tc.assertGreaterEqual(rpc_block_count_end - rpc_block_count_start, blocks_to_publish_count ) #if other blocks arrive in the meantime


    def assert_blocks_confirmed(self, block_hashes, max_stall_duration_s = 3*60):       

        #block_hashes = list(map(lambda x: x["hash"], blocks))
        block_count = len(block_hashes)
        sleep_on_stall_s = 5
        timeout_inc = 0
        timeout_max = 10 * max_stall_duration_s #stalled for 30 minutes

        try:           
            confirmed_count = 0
            while confirmed_count < block_count:
                last_confirmed_count = confirmed_count
                confirmed_hashes = self.nano_rpc.nl_pr1.block_confirmed_aio(block_hashes)
                block_hashes = list(set(block_hashes) - confirmed_hashes)
                confirmed_count = confirmed_count + len(confirmed_hashes)
                if confirmed_count != block_count  :
                    print(f"{confirmed_count}/{block_count} blocks confirmed....", end="\r")
                if confirmed_count == last_confirmed_count :
                    timeout_max = timeout_max - sleep_on_stall_s                
                    timeout_inc = timeout_inc + sleep_on_stall_s
                    time.sleep(sleep_on_stall_s)
                    if timeout_inc >= max_stall_duration_s :
                        raise ValueError(f"No new confirmations for {max_stall_duration_s}s... Fail blocks_confirmed") #break if no new confirmatiosn for 3 minutes (default)                    
                else : #reset stall timer
                    timeout_inc = 0
                if timeout_max <= 0 : 
                    tc.fail(f"Max timeout of {timeout_max} seconds reached")
            print(f"{confirmed_count}/{block_count} blocks confirmed")
        except Exception as ex: #when timeout hits           
            tc.fail(str(ex))
        print("")       
        tc.assertEqual(confirmed_count, block_count)
        
  
    def publish_bucket_saturation(self, data):
        #Fetch and publish pre-generated blocks for bucket saturation. (10rounds of 5000blocks for bucket 1,2,3 and 4)
        for bucket_id, rounds in data["buckets"].items() :
            for round, publish_commands in rounds.items() :
                self.publish_blocks(publish_commands, json_data=True, sync=False)
        return True

    def get_publish_commands_from_bucket_saturation(self,data, json_data = False, take_rounds = []) :
        #returns a string object (like reading from flatfile)
        response = []
        for bucket_id, rounds in data["buckets"].items() :
            for round, publish_commands in rounds.items() :
                if len(take_rounds) > 0 :
                    if round not in take_rounds : continue
                for command in publish_commands :
                    if json_data :
                        response.append(command)
                    else:
                        response.append((str(command).replace("'", '"')))
        return response

    def online_bucket_main(self, queue, spam_running):
        #create online change blocks for 1 bucket and measure confirmation_times
        timeout_per_conf = 120
        main_bucket_seed = self.get_bucket_seed(self.pre_gen_bucket_saturation_main_index)
        random_rep = self.nano_rpc.nl_pr1.get_account_data(self.nano_rpc.nl_pr1.generate_seed(), 0)["account"] #generate a random account and set is as new rep

        for i in range(0,self.pre_gen_accounts) :
            if spam_running.value == False : return #publish while spam blocks are being published
            change_response = self.nano_rpc.nl_pr1.create_change_block(main_bucket_seed, i,random_rep,broadcast=True)
            print(change_response["hash"])
            t1 = time.time()

            try:
                with timeout(timeout_per_conf, exception=RuntimeError):
                    while (not self.nano_rpc.nl_pr1.block_confirmed(block_hash = change_response["hash"])):
                        time.sleep(0.2)
            except RuntimeError:
                print (f"no confirmation after {timeout_per_conf} seconds")

            queue.put(time.time() -t1)

    def test_9_publish_bucket_saturation(self):
        path = "./testcases/pregenerated_blocks/bucket_saturation_0_200000_blocks.json"
        data = ConfigReadWrite().read_json(path)
        q = Queue()

        #Every account broadcasts a recent change block.
        first_round_commands = self.get_publish_commands_from_bucket_saturation(data, json_data = True, take_rounds=["0"])
        self.publish_blocks(first_round_commands, sync=False, json_data = True)
        self.blocks_confirmed(publish_commands = first_round_commands, percentage = 90) #move on if 90% of blocks are confirmed

        #When Every spam account has a recent confirmation, broadcast the remaning spam.
        #At the same tiem broadcast 1 transaction per account with no recent activity. LRU priorisation_test
        spam_publish_commands = self.get_publish_commands_from_bucket_saturation(data, json_data = True, take_rounds=[str(x) for x in range(1, self.pre_gen_bucket_saturation_rounds) ])


        spam_running = Value('i', True)
        t1 = time.time()
        p1 = Process(target=self.publish_blocks, args=(spam_publish_commands,), kwargs={"sync" : False, "json_data" : True, "is_running" : spam_running})
        p2 = Process(target=self.online_bucket_main, args=(q,spam_running,))
        #p3 = Process(target=self.blocks_confirmed, kwargs= {"publish_commands"  : publish_commands}) # no need to wait for spam confirmation

        p1.start()
        p2.start()
        #p3.start()

        p1.join()
        p2.join()
        #p3.join()

        q.put(None)
        conf_duration = list(iter(q.get, None))


        h = Helpers()
        duration = time.time() - t1
        print({ "saturation_duration_s" : duration,
                "saturation_blocks_per_second" : len(spam_publish_commands) / duration,
                "main_bucket_confirmation_count" : len(conf_duration),
                "main_bucket_confirmations_per_second" : len(conf_duration) / duration,
                "main_bucket_min_duration" : min(conf_duration),
                "main_bucket_max_duration" : max(conf_duration),
                "main_bucket_percentiles" : {"50" : h.percentile(conf_duration,50),
                                             "75" : h.percentile(conf_duration,75),
                                             "90" : h.percentile(conf_duration,90),
                                             "99" : h.percentile(conf_duration,99)}
               })


    def account_splitting(self, seed_prefix, number_of_accounts, current_depth = 1, representative = None, source_seed = None, source_index = 0, write_to_disk = False, folder = "storage", final_account_balance_raw = 10 **30 ):
        #split each account into 2 by sending half of the account funds to 2 other accounts.
        # at the end of teh split, each account will have 1 nano               
        splitting_depth = ceil(log10(number_of_accounts + 2) / log10(2)) -1        
        if current_depth > splitting_depth : return [] #end of recursion is reached         
             
        if current_depth == 1 : 
            if source_seed is None:  #find a seed with enough funding             
                for node_conf in self.conf.get_nodes_config():
                    #find one representative that holds enough funds to cover all sends
                    if int(self.nano_rpc.nl_genesis.check_balance(node_conf.account)["balance_raw"]) > (number_of_accounts * final_account_balance_raw) : #raw
                        source_account_data = node_conf.account_data                    
                        break 
            else:
                source_account_data = self.nano_rpc.nl_genesis.generate_account(source_seed, source_index) 
            #source balance must be greater than            
            tc.assertGreater(int(self.nano_rpc.nl_genesis.check_balance(source_account_data["account"])["balance_raw"]), int(self.nano_tools.raw_mul(number_of_accounts, final_account_balance_raw)))
            representative = self.nano_rpc[self.conf.get_nodes_name()[0]].account_info(source_account_data["account"]) #keep the same representative for all opened accounts   
        else :
            source_account_data = self.nano_rpc.nl_genesis.generate_account(source_seed, 0)       

        seed_prefix_A = f'{seed_prefix}A'  #Seed _A ... _AA / _BA...
        seed_prefix_B = f'{seed_prefix}B'  #Seed _B ... _AB / _BB...       
        publish_commands_branch_A = self.recursive_split(seed_prefix_A, representative, source_account_data, number_of_accounts, splitting_depth, current_depth, final_account_balance_raw)        
        publish_commands_branch_B = self.recursive_split(seed_prefix_B, representative, source_account_data, number_of_accounts, splitting_depth, current_depth, final_account_balance_raw)
        all_publish_commands =  publish_commands_branch_A + publish_commands_branch_B

        if current_depth == 1 :
            print("")
            tc.assertEqual(len(all_publish_commands), 2* number_of_accounts )
            if write_to_disk :
                ConfigReadWrite().write_list(f"./testcases/{folder}/test_account_splitting_depth_{splitting_depth}.txt", [str(line).replace("'", '"') for line in all_publish_commands])
        return all_publish_commands[:2 * (number_of_accounts)]

    def assert_all_blocks_cemented(self):
        try:
            with timeout(30) :
                for node_name in self.conf.get_nodes_name() :
                    block_count = self.nano_rpc[node_name].block_count()
                    if block_count["count"] != block_count["cemented"] :
                        time.sleep(1)
                    # else :
                    #     tc.assertEqual(block_count["count"], block_count["cemented"])
        except RuntimeError as e :
            tc.fail(e)
    
    def write_blocks_to_disk(self, rpc_block_list, path):
       

        hash_list = []
        seed_list = []
        block_list = []

        if any(isinstance(i, list) for i in rpc_block_list[:2]) : #nested list :
            for block_list_i in rpc_block_list :
                tc.assertEqual(len(list(filter(lambda x: x["success"] , block_list_i))), len(block_list_i))
                block_list.append(list(map(lambda x: x["block"] , block_list_i)))
                seed_list.extend(list(set([x["account_data"]["source_seed"] for x in block_list_i if x["account_data"]["source_seed"] is not None])))
                hash_list.extend(list(map(lambda x: x["hash"] , block_list_i)))            

        else :
            tc.assertEqual(len(list(filter(lambda x: x["success"] , rpc_block_list))), len(rpc_block_list))
            hash_list = list(map(lambda x: x["hash"], rpc_block_list))
            seed_list = list(set([x["account_data"]["source_seed"] for x in rpc_block_list if x["account_data"]["source_seed"] is not None])) #remove duplicate seeds with set
            block_list = list(map(lambda x: x["block"], rpc_block_list))
        
        res = {"h" : hash_list, "s" : seed_list, "b" : block_list}

        ConfigReadWrite().write_json(path, res)
       
    
    def read_blocks_from_disk(self, path , seeds = False, hashes = False, blocks = False ) :
        res = ConfigReadWrite().read_json(path)        
        if seeds : return res["s"]
        if hashes : return res["h"]
        if blocks : return res["b"]
        return res


    def pre_gen_account_split(self, source_seed = None, source_private_key = None):       
        #tc.assertFalse(source_seed == source_private_key == None) #if seed and key is none, account_splitting will use an account from config with enough available balance
        self.assert_all_blocks_cemented()
        #starts with 1 account and doubles the number of accounts with each increasing splitting_depth. first account needs enough funding                
        res = self.account_splitting("C0C0", self. pre_gen_accounts, source_seed= source_seed, final_account_balance_raw=self.pre_gen_account_end_balance)
        self.write_blocks_to_disk(res, self.pre_gen_file_names.account_split)

    def publish_account_split(self) :
        blocks = self.read_blocks_from_disk(self.pre_gen_file_names.account_split, blocks = True)
        self.assert_blocks_published(blocks)
    
    def publish_bucket_funding(self) :
        block_list_of_list = self.read_blocks_from_disk(self.pre_gen_file_names.bucket_funding, blocks = True)
        for blocks in block_list_of_list :
            self.assert_blocks_published(blocks)
    
    def publish_bucket_funding(self) :
        block_list_of_list = self.read_blocks_from_disk(self.pre_gen_file_names.bucket_funding, blocks = True)
        for blocks in block_list_of_list :
            self.assert_blocks_published(blocks)
    
    def publish_bucket_rounds(self) :
        block_list_of_list = self.read_blocks_from_disk(self.pre_gen_file_names.bucket_rounds, blocks = True)
        for blocks in block_list_of_list :
            self.assert_blocks_published(blocks)
    
    def blocks_confirmed_account_split(self):
        block_hashes = self.read_blocks_from_disk(self.pre_gen_file_names.account_split, hashes = True)
        self.assert_blocks_confirmed(block_hashes)
    
    def blocks_confirmed_bucket_rounds(self):
        block_hashes = self.read_blocks_from_disk(self.pre_gen_file_names.bucket_rounds, hashes = True)
        self.assert_blocks_confirmed(block_hashes)
    
    def blocks_confirmed_bucket_funding(self):
        block_hashes = self.read_blocks_from_disk(self.pre_gen_file_names.bucket_funding, hashes = True)
        self.assert_blocks_confirmed(block_hashes)
    
    def pre_gen_bucket_funding(self):
        #create 1 send block from each account of test_pregenerate_depth_12 to FADE0000000000....1 , ...2 , ...3

        self.assert_all_blocks_cemented()        
        seeds = self.read_blocks_from_disk(self.pre_gen_file_names.account_split, seeds=True)

        block_list_of_list = []
        for bucket_index in range(0,self.pre_gen_max_bucket+1) : # bucket 0 ==1 raw bucket 105 =~ 40.565 Nano
            start_index = self.pre_gen_start_index
            break_count = self.pre_gen_accounts

            destination_index = 0
            bucket_blocks = []
            for source_seed in seeds : #publish send and open blocks separately
                #create 5000 send blocks to each bucket FACE00000...1 ; FACE00000...2 ; ... ; FACE0000...125 from index 0 to 5000
                if destination_index < start_index :
                    #chose start_account to send from (for testing purposes, start_index default = 0)
                    destination_index = destination_index + 1
                    continue
                if destination_index > break_count : break
                res = self.fund_bucket(bucket_index, source_seed, destination_index )
                bucket_blocks.extend(res)
                destination_index = destination_index + 1
            block_list_of_list.append(bucket_blocks)
        self.write_blocks_to_disk(block_list_of_list, self.pre_gen_file_names.bucket_funding)
        
    def pre_gen_bucket_rounds(self):  
        self.assert_all_blocks_cemented()          
        block_list_of_list = []
        block_list = []

        for round in range(0,self.pre_gen_bucket_saturation_rounds):
            random_rep = self.nano_rpc.nl_genesis.get_account_data(self.nano_rpc.nl_genesis.generate_seed(), 0)["account"] #generate a random account and set is as new rep
            if block_list != [] : block_list_of_list.append(block_list)
            block_list = []
            for bucket_index in self.pre_gen_bucket_saturation_indexes :
                bucket_seed = self.get_bucket_seed(bucket_index)
                for account_index in range(self.pre_gen_start_index, self.pre_gen_accounts):
                    block_list.append(self.nano_rpc.nl_genesis.create_change_block(bucket_seed, account_index, random_rep, broadcast=False))
        if block_list != [] : block_list_of_list.append(block_list)
       
        self.write_blocks_to_disk(block_list_of_list,self.pre_gen_file_names.bucket_rounds )



if __name__ == "__main__":
    pre_gen = PreGenLedger()
    pre_gen.pre_gen_account_split() #,source_seed=pre_gen.get_prefixed_suffixed_seed("ACDC", "27"))
    pre_gen.publish_account_split()
    pre_gen.blocks_confirmed_account_split()
    pre_gen.pre_gen_bucket_funding()
    pre_gen.publish_bucket_funding()
    pre_gen.pre_gen_bucket_rounds()
    pre_gen.publish_bucket_rounds()