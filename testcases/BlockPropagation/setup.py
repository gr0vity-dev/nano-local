#!./venv_nano_local/bin/python
from os import popen
from math import ceil
from time import time
import unittest
from pre_gen import PreGenLedger
from src.nano_block_ops import BlockGenerator, BlockAsserts
from src.nano_rpc import NanoRpc, NanoTools
from src.parse_nano_local_config import ConfigReadWrite, ConfigParser, Helpers
import copy
from interruptingcow import timeout
import logging
import time
import json
import inspect
from multiprocessing import Process, Queue, Value

class Init :

    def __init__(self, testcase) :
        self.conf = ConfigParser()
        self.ba = BlockAsserts()
        self.nano_rpc =  self.set_rpcs()

        if testcase == 1 :
            pass
        elif testcase == 2 :
            pass
        elif testcase == 3 :
            pass
        elif testcase == 4 :
            pass
        elif testcase == 5 :
            pass
        elif testcase == 6 :
            pass
        elif testcase == 7 :
            pass
        elif testcase == 8 :
            pass
        elif testcase == 9 :
            self.t9_variables()
        elif testcase == 10 :
            pass
    

    def t9_variables(self):
        self.debug = True
        self.pre_gen = PreGenLedger("3_nodes_equal_weight__genesis_0_weight")       
        self.pre_gen_files = {"json_file" : self.pre_gen.pre_gen_file_names["bucket_rounds"]["json_file"] ,
                              "ledger_file" : self.pre_gen.pre_gen_file_names["bucket_funding"]["ledger_file"]}  
        
        

    def set_rpcs(self):
        return [NanoRpc(x) for x in self.conf.get_rpc_endpoints()]

    def online_bucket_main(self, queue, spam_running):
        #create online change blocks for 1 bucket and measure confirmation_times
        timeout_per_conf = 120
        main_bucket_seed = self.pre_gen.get_bucket_seed(self.pre_gen.pre_gen_bucket_saturation_main_index)
        bg = BlockGenerator(default_rpc_index=2, broadcast_blocks=True)
        bg.set_single_change_rep()
        #random_rep = self.nano_rpc[2].get_account_data(self.nano_rpc[2].generate_seed(), 0)["account"] #generate a random account and set is as new rep

        for i in range(0,self.pre_gen.pre_gen_accounts) :
            if spam_running.value == False : return #will wait for the last confirmation before quitting function even when spam has already finished.       
            change_response = bg.blockgen_single_change(main_bucket_seed,i)
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


    def setup_ledger(self, ledger_source, use_nanoticker = False) :
        #copy ledger to all nodes and restart nodes
        commands = ["./run_nano_local.py restart"] #last command
        for node_name in self.conf.get_nodes_name():
            ledger_destination = f"./nano_nodes/{node_name}/NanoTest/data.ldb"
            commands.insert(0, f"cp -p {ledger_source} {ledger_destination}") 
           
        
        for command in commands :
            shell_output = popen(command).read()
            if shell_output.strip() != "" : raise Exception(shell_output)
                  
        self.ba.assert_all_blocks_cemented()

        if use_nanoticker : #wait 3 minutes for Nanoticker to properly get new data.ldb     
            time.sleep(60*3) 

        
    def mp_start_join(self, mp_procs):       
        for proc in mp_procs:
            proc.start()
        
        for proc in mp_procs:
            proc.join()
