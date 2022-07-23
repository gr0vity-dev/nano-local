#!./venv_nano_local/bin/python
from subprocess import call
from time import time
from src.nano_block_ops import BlockGenerator, BlockAsserts
from pre_gen import PreGenLedger
from src.nano_rpc import NanoRpc
from src.parse_nano_local_config import ConfigParser
import time
from multiprocessing import Value

class Init :

    def __init__(self, testcase) :
        self.conf = ConfigParser()
        self.ba = BlockAsserts()
        self.bg = BlockGenerator()
        self.nano_rpc_all =  self.bg.get_rpc_all()

        if testcase == 1 :
            self.n1_variables()
            self.n1_t1_variables()
        elif testcase == 2 :
            self.n1_variables()
            self.n1_t2_variables()
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
            pass
        elif testcase == 10 :
            pass

    def n1_variables(self):
        self.path = "./pregen_ledgers"
        self.network_dir = "_private_3nodes_equal_weight_1"
        self.path_json1_ldb = f'{self.path}/{self.network_dir}/1_accounts_split.json'
        self.path_data1_ldb = f'{self.path}/{self.network_dir}/1_data.ldb'
        self.path_json2_ldb = f'{self.path}/{self.network_dir}/2_bucket_funding.json'
        self.path_data2_ldb = f'{self.path}/{self.network_dir}/2_data.ldb'
        self.path_json3_ldb = f'{self.path}/{self.network_dir}/3_change_blocks_rounds.json'
        self.path_data3_ldb = f'{self.path}/{self.network_dir}/3_data.ldb'



    def n1_t1_variables(self):
        self.debug = True
        self.pre_gen_files = {"ledger_file" : self.path_data2_ldb,
                              "json_file" : self.path_json3_ldb }


    def n1_t2_variables(self):
        self.debug = True
        self.single_tx_timeout = 19.99
        self.pre_gen_files = {"ledger_file" : self.path_data2_ldb,
                              "json_file" : self.path_json3_ldb }



    def set_rpcs(self):
        return [NanoRpc(x) for x in self.conf.get_rpc_endpoints()]

    def online_bucket_main(self, queue, timeout_s ,spam_running=Value("i", True), ):
        pre_gen = PreGenLedger(self.network_dir, pregen = False)
        #create online change blocks for 1 bucket and measure confirmation_times
        timeout_per_conf = 120
        main_bucket_seed = pre_gen.get_bucket_seed(pre_gen.pre_gen_bucket_saturation_main_index)
        bg = BlockGenerator(default_rpc_index=2, broadcast_blocks=True)
        bg.set_single_change_rep()
        #random_rep = self.nano_rpc[2].get_account_data(self.nano_rpc[2].generate_seed(), 0)["account"] #generate a random account and set is as new rep

        for i in range(0,pre_gen.pre_gen_accounts) :
            q_res = {"timeout_uduration" : timeout_s}
            if spam_running.value == False : return #will wait for the last confirmation before quitting function even when spam has already finished.
            change_response = bg.blockgen_single_change(main_bucket_seed,i)
            t1 = time.time()
            try:
                self.ba.assert_single_block_confirmed(change_response["hash"], exit_after_s=timeout_s, sleep_on_stall_s=0.1)
                q_res["conf_duration"] = time.time() -t1
                q_res["timeout"] = False
            except :
                q_res["timeout"] = True
                pass

            queue.put(q_res)
    
    def exec_commands(self,commands):
        for command in commands :
            status = call(command, shell=True)
            if status != 0 : raise Exception(f"{command} failed with status:{status}")

    def stop_nodes(self, sleep=0) :
        commands = ["./run_nano_local.py stop_nodes"] #last command        
        self.exec_commands(commands)
        time.sleep(sleep)
        
    

    def setup_ledger(self, ledger_source, use_nanoticker = False) :
        #copy ledger to all nodes and restart nodes
        commands = ["./run_nano_local.py stop_nodes"] #last command
        for node_name in self.conf.get_nodes_name():
            ledger_destination = f"./nano_nodes/{node_name}/NanoTest/data.ldb"
            commands.append(f"cp -p {ledger_source} {ledger_destination}")
        commands.append("./run_nano_local.py start") #last command

        self.exec_commands(commands)

        self.ba.assert_all_blocks_cemented()

        #if use_nanoticker : #wait 3 minutes for Nanoticker to properly get new data.ldb
        #    time.sleep(60*3)


    def mp_start_join(self, mp_procs):
        for proc in mp_procs:
            proc.start()

        for proc in mp_procs:
            proc.join()
