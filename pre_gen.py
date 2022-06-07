#!./venv_nano_local/bin/python
from os import system, popen
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
import pandas as pd
from tabulate import tabulate
import traceback

tc = unittest.TestCase()   


     

class PreGenLedger():

    def __init__(self, pre_gen_folder_name):
        self.nano_rpc = Api("undefined") #used to hint at availabe functions whiel coding
        self.nano_rpc = self.set_rpcs() #access all avilable rpcs at nano_rpc.node_name                
        self.nano_tools = NanoTools()
        self.conf = ConfigParser()
        self.open_counter = 0
        self.set_class_params(pre_gen_folder_name)

    def set_class_params(self, pre_gen_folder_name):
        self.pre_gen_path = f"./testcases/pre_gen/{pre_gen_folder_name}/"
        self.pre_gen_file_names = DotDict({"account_split" : {"json_file" : f"{self.pre_gen_path}/1_accounts_split.json" , "ledger_file" : f"{self.pre_gen_path}/1_data.ldb"}, 
                                           "bucket_funding" : {"json_file" : f"{self.pre_gen_path}/2_bucket_funding.json" , "ledger_file" : f"{self.pre_gen_path}/2_data.ldb"},
                                           "bucket_rounds" : {"json_file" : f"{self.pre_gen_path}/3_change_blocks_rounds.json" , "ledger_file" : f"{self.pre_gen_path}/3_data.ldb"} , })
        
        self.pre_gen_bucket_seed_prefix = "FACE" # {prefix}000.000{bucket_id} (example bucket_17_seed : FACE000000000000000000000000000000000000000000000000000000000017)
        self.pre_gen_account_min_end_balance = 100 * 10**30
        self.pre_gen_max_bucket = 105 #used to prefill buckets from 0 to 105 (at 105 you'll need at least pre_gen_account_min_end_balance=2**106 (~81.113) )
        self.pre_gen_start_index = 0 #skip # seeds and pre_generation at index # (should be 0 except for testing purposes)
        self.pre_gen_accounts = 5000 #(must be smaller than (2**(pre_gen_splitting_depth+1) -2))
        self.pre_gen_bucket_saturation_main_index = 100
        self.pre_gen_bucket_saturation_indexes = [1,2,3,4,5]
        self.pre_gen_bucket_saturation_rounds = 10 # (pre_gen_bucket_saturation_rounds * pre_gen_accounts will be crated per index.  Example: 10*5000 * 4 = 200'000 )
        self.validate()
    
    def validate(self):        
        system(f"mkdir -p {self.pre_gen_path}")       
        tc.assertGreater(self.pre_gen_account_min_end_balance, 2 ** (self.pre_gen_max_bucket+1))
        tc.assertGreater(self.pre_gen_max_bucket+1, self.pre_gen_bucket_saturation_main_index)
        for bucket_index in self.pre_gen_bucket_saturation_indexes :
            tc.assertGreater(self.pre_gen_max_bucket,bucket_index)
        
    def set_rpcs(self):
        api = [] 
        conf = ConfigParser()
        for node_name in conf.get_nodes_name() :
            node_conf = conf.get_node_config(node_name)
            api.append(Api(node_conf["rpc_url"]))
        return api
    
    def get_node_name(self, index = 0) :
        node_names = self.conf.get_nodes_name()
        if len(node_names) > index :
            return node_names[index]
        else :
            logging.warning(f"requested node_name {index} but only {len(node_names)} nodes defined. Retruning first node_name")
            return node_names[0]

    def open_account(self, representative, source_key, destination_seed, send_amount, final_account_balance_raw, number_of_accounts, destination_index = 0):        
        if number_of_accounts is not None and self.open_counter >= number_of_accounts : return []
        self.open_counter = self.open_counter + 1
        destination = self.nano_rpc[1].generate_account(destination_seed, destination_index)
        send_block = self.nano_rpc[1].create_send_block_pkey(source_key,
                                                                     destination["account"],
                                                                     send_amount * final_account_balance_raw ,
                                                                     broadcast=False)
               
        open_block = self.nano_rpc[1].create_open_block(destination["account"],
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
        source = self.nano_rpc[1].generate_account(source_seed, 0)
        destination = self.nano_rpc[1].generate_account(destination_seed, destination_index)
        return self.open_account(destination["account"], source["private"],destination_seed, 1 , 2**bucket, None, destination_index=destination_index )

    def recursive_split(self,seed_prefix, representative, source_account, number_of_accounts, splitting_depth, current_depth, final_account_balance_raw):
        seed = f'{seed_prefix}{str(0)*(64 - len(seed_prefix))}' 
        blocks = self.open_account(representative , source_account["private"], seed, (2**(splitting_depth - current_depth +1) -1) , final_account_balance_raw, number_of_accounts)
        blocks_ab = self.account_splitting(seed_prefix, number_of_accounts, current_depth=current_depth+1, representative=representative, source_seed=seed, final_account_balance_raw=final_account_balance_raw )
        return blocks + blocks_ab

    def assert_list_of_blocks_published(self, list_of_blocks, sync = True, is_running = Value('i', False)) :        
        for blocks in list_of_blocks :            
            self.assert_blocks_published(blocks,sync=sync)
        is_running.value = False

    def assert_blocks_published(self, blocks, sync = True):
        blocks_to_publish_count = len(blocks)
        rpc_block_count_start = int(self.nano_rpc[1].block_count()["count"])
        #print("start block_count" , rpc_block_count_start)        
        self.nano_rpc[1].publish_blocks(blocks, json_data=True, sync=sync) #we don't care about the result
        rpc_block_count_end = int(self.nano_rpc[1].block_count()["count"])
        #print("end block_count", rpc_block_count_end)
        tc.assertGreaterEqual(rpc_block_count_end - rpc_block_count_start, blocks_to_publish_count ) #if other blocks arrive in the meantime

    def assert_blocks_confirmed(self, block_hashes, max_stall_duration_s = 6*60, exit_on_first_stall = False):       

        #block_hashes = list(map(lambda x: x["hash"], blocks))
        block_count = len(block_hashes)
        sleep_on_stall_s = 5
        timeout_inc = 0
        timeout_max = 5 * max_stall_duration_s #stalled for 30 minutes

        try:           
            confirmed_count = 0
            while confirmed_count < block_count:
                last_confirmed_count = confirmed_count
                confirmed_hashes = self.nano_rpc[3].block_confirmed_aio(block_hashes, ignore_errors = ["Block not found"],)
                block_hashes = list(set(block_hashes) - confirmed_hashes)
                confirmed_count = confirmed_count + len(confirmed_hashes)
                if confirmed_count != block_count  :
                    time.sleep(sleep_on_stall_s)
                    print(f"{confirmed_count}/{block_count} blocks confirmed....", end="\r")
                if confirmed_count == last_confirmed_count : # stalling block_count                    
                    if exit_on_first_stall : return {"total_block_count" : block_count, 
                                                     "confirmed_count" : confirmed_count, 
                                                     "unconfirmed_count" : block_count - confirmed_count }
                    
                    timeout_max = timeout_max - sleep_on_stall_s                
                    timeout_inc = timeout_inc + sleep_on_stall_s                   
                    if timeout_inc >= max_stall_duration_s :
                        raise ValueError(f"No new confirmations for {max_stall_duration_s}s... Fail blocks_confirmed") #break if no new confirmatiosn for 6 minutes (default)                    
                else : #reset stall timer
                    timeout_inc = 0
                if timeout_max <= 0 : 
                    tc.fail(f"Max timeout of {timeout_max} seconds reached")
            print(f"{confirmed_count}/{block_count} blocks confirmed")
        except Exception as ex: #when timeout hits            
            tc.fail(str(ex))
        tc.assertEqual(confirmed_count, block_count)

    def account_splitting(self, seed_prefix, number_of_accounts, current_depth = 1, representative = None, source_seed = None, source_index = 0, write_to_disk = False, folder = "storage", final_account_balance_raw = 10 **30 ):
        #split each account into 2 by sending half of the account funds to 2 other accounts.
        # at the end of teh split, each account will have 1 nano               
        splitting_depth = ceil(log10(number_of_accounts + 2) / log10(2)) -1        
        if current_depth > splitting_depth : return [] #end of recursion is reached         
             
        if current_depth == 1 : 
            if source_seed is None:  #find a seed with enough funding             
                for node_conf in self.conf.get_nodes_config():
                    #find one representative that holds enough funds to cover all sends
                    if int(self.nano_rpc[1].check_balance(node_conf.account)["balance_raw"]) > (number_of_accounts * final_account_balance_raw) : #raw
                        source_account_data = node_conf.account_data                    
                        break 
            else:
                source_account_data = self.nano_rpc[1].generate_account(source_seed, source_index) 
            #source balance must be greater than            
            tc.assertGreater(int(self.nano_rpc[1].check_balance(source_account_data["account"])["balance_raw"]), int(self.nano_tools.raw_mul(number_of_accounts, final_account_balance_raw)))
            representative = self.nano_rpc[self.conf.get_nodes_name()[0]].account_info(source_account_data["account"]) #keep the same representative for all opened accounts   
        else :
            source_account_data = self.nano_rpc[1].generate_account(source_seed, 0)       

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

    # def assert_all_blocks_cemented(self):
    #     try:
    #         with timeout(30) :
    #             for nano_rpc in self.nano_rpc :
    #                 block_count = nano_rpc.block_count()
    #                 if block_count["count"] != block_count["cemented"] :
    #                     time.sleep(1)
    #                 # else :
    #                 #     tc.assertEqual(block_count["count"], block_count["cemented"])
    #     except RuntimeError as e :            
    #         tc.fail(e)
    
    def assert_all_blocks_cemented(self):                
        for nano_rpc in self.nano_rpc :
            block_count = nano_rpc.block_count()                    
            tc.assertEqual(block_count["count"], block_count["cemented"])
       
    
    def write_blocks_to_disk(self, rpc_block_list, path):  
        hash_list = []
        seed_list = []
        block_list = []

        if any(isinstance(i, list) for i in rpc_block_list[:2]) : #nested list :
            for block_list_i in rpc_block_list :
                tc.assertEqual(len(list(filter(lambda x: x["success"] , block_list_i))), len(block_list_i))
                block_list.append(list(map(lambda x: x["block"] , block_list_i)))
                seed_list.append(list(set([x["account_data"]["source_seed"] for x in block_list_i if x["account_data"]["source_seed"] is not None])))
                hash_list.append(list(map(lambda x: x["hash"] , block_list_i)))            

        else :
            tc.assertEqual(len(list(filter(lambda x: x["success"] , rpc_block_list))), len(rpc_block_list))
            hash_list = list(map(lambda x: x["hash"], rpc_block_list))
            seed_list = list(set([x["account_data"]["source_seed"] for x in rpc_block_list if x["account_data"]["source_seed"] is not None])) #remove duplicate seeds with set
            block_list = list(map(lambda x: x["block"], rpc_block_list))
        
        res = {"h" : hash_list, "s" : seed_list, "b" : block_list}

        ConfigReadWrite().write_json(path, res)

    def write_ledger_to_disk(self, ledger_destinations):
        self.assert_all_blocks_cemented()
        ledger_source = self.conf.get_nodes_name[0]
        command = f"cp -p {ledger_source} {ledger_destinations}"
        system(command)

    def read_blocks_from_disk(self, path , seeds = False, hashes = False, blocks = False ) :
        res = ConfigReadWrite().read_json(path)        
        if seeds : return res["s"]
        if hashes : return res["h"]
        if blocks : return res["b"]
        return res

#PRE_GENERATE_BLOCKS
    def pre_gen_account_split(self, source_seed = None, source_private_key = None):       
        #tc.assertFalse(source_seed == source_private_key == None) #if seed and key is none, account_splitting will use an account from config with enough available balance
        self.assert_all_blocks_cemented()
        #starts with 1 account and doubles the number of accounts with each increasing splitting_depth. first account needs enough funding                
        res = self.account_splitting("C0C0", self. pre_gen_accounts, source_seed= source_seed, final_account_balance_raw=self.pre_gen_account_min_end_balance)
        self.write_blocks_to_disk(res, self.pre_gen_file_names.account_split.json_file)
    
    def pre_gen_bucket_funding(self):
        #create 1 send block from each account of test_pregenerate_depth_12 to FADE0000000000....1 , ...2 , ...3

        self.assert_all_blocks_cemented()        
        seeds = self.read_blocks_from_disk(self.pre_gen_file_names.account_split.json_file, seeds=True)

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
        self.write_blocks_to_disk(block_list_of_list, self.pre_gen_file_names.bucket_funding.json_file)
        
    def pre_gen_bucket_rounds(self):  
        self.assert_all_blocks_cemented()          
        block_list_of_list = []
        block_list = []

        for round in range(0,self.pre_gen_bucket_saturation_rounds):
            random_rep = self.nano_rpc[1].get_account_data(self.nano_rpc[1].generate_seed(), 0)["account"] #generate a random account and set is as new rep
            if block_list != [] : block_list_of_list.append(block_list)
            block_list = []
            for bucket_index in self.pre_gen_bucket_saturation_indexes :
                bucket_seed = self.get_bucket_seed(bucket_index)
                for account_index in range(self.pre_gen_start_index, self.pre_gen_accounts):
                    block_list.append(self.nano_rpc[1].create_change_block(bucket_seed, account_index, random_rep, broadcast=False))
        if block_list != [] : block_list_of_list.append(block_list)
       
        self.write_blocks_to_disk(block_list_of_list,self.pre_gen_file_names.bucket_rounds.json_file )

#PUBLISH PRE_GENERATED_BLOCKS
    def publish_account_split(self) :
        blocks = self.read_blocks_from_disk(self.pre_gen_file_names.account_split.json_file, blocks = True)
        self.assert_blocks_published(blocks, sync=True)
    
    def publish_bucket_funding(self) :
        block_list_of_list = self.read_blocks_from_disk(self.pre_gen_file_names.bucket_funding.json_file, blocks = True)
        for blocks in block_list_of_list :
            self.assert_blocks_published(blocks, sync=False)       

    def publish_bucket_rounds(self) :
        block_list_of_list = self.read_blocks_from_disk(self.pre_gen_file_names.bucket_rounds.json_file, blocks = True)
        for blocks in block_list_of_list :
            self.assert_blocks_published(blocks, sync=False)    

#ASSERT PRE_GENERATED_BLOCKS CONFIRMED
    def blocks_confirmed_account_split(self):
        block_hashes = self.read_blocks_from_disk(self.pre_gen_file_names.account_split.json_file, hashes = True)
        self.assert_blocks_confirmed(block_hashes)

    def blocks_confirmed_bucket_funding(self):
        block_hashes = self.read_blocks_from_disk(self.pre_gen_file_names.bucket_funding.json_file, hashes = True)
        self.assert_blocks_confirmed(block_hashes)
    
    def blocks_confirmed_bucket_rounds(self):
        block_hashes = self.read_blocks_from_disk(self.pre_gen_file_names.bucket_rounds.json_file, hashes = True)
        self.assert_blocks_confirmed(block_hashes)
    
    


#TESTCASE    

    def online_bucket_main(self, queue, spam_running):
        #create online change blocks for 1 bucket and measure confirmation_times
        timeout_per_conf = 120
        main_bucket_seed = self.get_bucket_seed(self.pre_gen_bucket_saturation_main_index)
        random_rep = self.nano_rpc[3].get_account_data(self.nano_rpc[3].generate_seed(), 0)["account"] #generate a random account and set is as new rep

        for i in range(0,self.pre_gen_accounts) :
            if spam_running.value == False : return #will wait for the last confirmation before quitting function even when spam has already finished.       
            change_response = self.nano_rpc[3].create_change_block(main_bucket_seed, i,random_rep,broadcast=True)            
            t1 = time.time()
            try:
                with timeout(timeout_per_conf, exception=RuntimeError):
                    while True : 
                        #if spam_running.value == False : return #will quit                          
                        is_confirmed = False
                        for nano_rpc in self.nano_rpc :
                            #if any of our nodes has seen this block as confirmed. 
                            # Sometimes not all nodes see the blocks confirmed at the same time.
                            is_confirmed = nano_rpc.block_confirmed(block_hash = change_response["hash"])
                            if is_confirmed : break
                        if is_confirmed : break 
                        print("unconfirmed" , change_response["hash"], end="\r" )                               
                        time.sleep(0.1)                        
            except RuntimeError:
                print (f"no confirmation after {timeout_per_conf} seconds")
            conf_time = time.time() -t1
            queue.put(conf_time)
            #print(f"online_bucket_main : conf_time:{conf_time}" , end="\r")


    def setup_ledger(self, ledger_source, use_nanoticker = False) :
        #copy ledger to all nodes and restart nodes
        commands = ["./run_nano_local.py restart"] #last command
        for node_name in self.conf.get_nodes_name():
            ledger_destination = f"./nano_nodes/{node_name}/NanoTest/data.ldb"
            commands.insert(0, f"cp -p {ledger_source} {ledger_destination}") 
           
        
        for command in commands :
            shell_output = popen(command).read()
            if shell_output.strip() != "" : raise Exception(shell_output)
                  
        self.assert_all_blocks_cemented()

        if use_nanoticker : #wait 3 minutes for Nanoticker to properly get new data.ldb     
            time.sleep(60*3) 

        
    def mp_start_join(self, mp_procs):       
        for proc in mp_procs:
            proc.start()
        
        for proc in mp_procs:
            proc.join()

    def test_9_publish_bucket_saturation(self, debug = False):   
        
        self.setup_ledger(self.pre_gen_file_names.bucket_funding.ledger_file, use_nanoticker = not debug)        
        blocks = self.read_blocks_from_disk(self.pre_gen_file_names.bucket_rounds.json_file)
        mp_procs = []
        mp_q = Queue()
        h = Helpers()     
        
        if debug :
            first_round_blocks = blocks["b"][0][:10]
            first_round_block_hashes = blocks["h"][0][:10]   
            spam_round_blocks = [x[:10] for x in blocks["b"][1:len(blocks["b"])]]  
        else:
            first_round_blocks = blocks["b"][0]
            first_round_block_hashes = blocks["h"][0]  
            spam_round_blocks = [x for x in blocks["b"][1:len(blocks["b"])]]  
        
        spam_block_count = sum( [ len(b) for b in spam_round_blocks])        

        t1 = time.time()
        #Every spam account broadcasts a recent change block, so priority should be reduced over older blocks      
        #   aio_http gets stuck if mp_ process follows non-mp_ process. Run everything in multiprocessing mode.
        mp_procs.append(Process(target=self.assert_blocks_published, args=(first_round_blocks,), kwargs={"sync" : True}))
        mp_procs.append(Process(target=self.assert_blocks_confirmed, args=(first_round_block_hashes,))) #not important for this test
        self.mp_start_join(mp_procs)
        first_round_duration = time.time() - t1
              
      
        #Start multiple processes in parallel.
        #1)Start spam with pre_generated blocks. All spam accounts have a recent transaction from blocks published in previous setp
        #2)Broadcast 1 genuine block from different accounts. Monitor confirmation duration for each block and move to next account.
        t2 = time.time()
        mp_spam_running = Value('i', True)
        spam_proc = Process(target=self.assert_list_of_blocks_published, args=(spam_round_blocks,), kwargs={"sync" : False, "is_running" : mp_spam_running})
        legit_proc = Process(target=self.online_bucket_main, args=(mp_q,mp_spam_running,))
        
        spam_proc.start()
        legit_proc.start()
        
        spam_proc.join()
        spam_duration = time.time() - t2 #measure time when spam has ended
        legit_proc.join() #wait for last confirmation after spam has ended

       
        #Convert result of online_bucket_main() from mp_q to list.
        mp_q.put(None)
        conf_duration = list(iter(mp_q.get, None))       
        test_duration = time.time() - t1

        res = { "confs":len(conf_duration),                
                "spam_s": spam_duration,
                "bps" : spam_block_count / spam_duration,
                "main_cps" : len(conf_duration) / test_duration,
                "min" :min(conf_duration),
                "max" : max(conf_duration),
                "timeouts": len(list(filter(lambda x: x >= 120, conf_duration))) ,  
                "perc_50":h.percentile(conf_duration,50),
                "perc_75":h.percentile(conf_duration,75),
                "perc_90":h.percentile(conf_duration,90),
                "perc_99":h.percentile(conf_duration,99),                  
                "spam_block_count" : spam_block_count,
                "round1_s" : first_round_duration,
                "test_s" : test_duration }    
       
        return res
       

def main():
    pre_gen = PreGenLedger()

    pre_gen.pre_gen_account_split() #,source_seed=pre_gen.get_prefixed_suffixed_seed("ACDC", "27"))
    pre_gen.publish_account_split()    
    pre_gen.blocks_confirmed_account_split()
    pre_gen.write_ledger_to_disk(pre_gen.pre_gen_file_names.account_split.ledger_file)

    pre_gen.pre_gen_bucket_funding()
    pre_gen.publish_bucket_funding()
    pre_gen.blocks_confirmed_bucket_funding()
    pre_gen.write_ledger_to_disk(pre_gen.pre_gen_file_names.bucket_funding.ledger_file)

    pre_gen.pre_gen_bucket_rounds()
    pre_gen.publish_bucket_rounds()
    pre_gen.blocks_confirmed_bucket_rounds()
    pre_gen.write_ledger_to_disk(pre_gen.pre_gen_file_names.bucket_rounds.ledger_file)


def to_fwf(path, df):
    content = tabulate(df.values.tolist(), list(df.columns), tablefmt="plain", floatfmt=".2f")
    open(path, "w").write(content)

if __name__ == "__main__":    
    res = []
    pre_gen = PreGenLedger("3_nodes_equal_weight__genesis_0_weight")  
    for i in range (0,11) :
        try:            
            res.append(pre_gen.test_9_publish_bucket_saturation(debug=False))             
            print(pd.DataFrame(res))  
        except Exception as e:
            traceback.print_exc()
            pass  

    ConfigReadWrite().write_list("./test0.txt", res)
    df = pd.DataFrame(res)
    print(df)   
    to_fwf("./test1.txt", df)


    #BOOTSTRAPPING TEST BY DELETING DATA.lDB FOR 1 NODE and monitor that node.
    #REPEAT FOR PR and for NON PR node.

    # pre_gen.setup_ledger(pre_gen.pre_gen_file_names.bucket_funding.ledger_file) 
    # pre_gen.publish_bucket_rounds()
    # pre_gen.blocks_confirmed_bucket_rounds()
    #main()