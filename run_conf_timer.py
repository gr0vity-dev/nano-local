#!./venv_nano_local/bin/python
from src.nano_rpc import NanoRpc
from src.nano_block_ops import BlockGenerator, BlockAsserts
from src.parse_nano_local_config import Helpers
import pandas as pd
from tabulate import tabulate
from datetime import datetime
from colorama import Fore, Style
from time import strftime,gmtime,time, sleep


bg = BlockGenerator(default_rpc_index=2, broadcast_blocks=False)
ba = BlockAsserts(default_rpc_index=2)
h = Helpers()
bg.set_single_change_rep()
timeout_s = 20
#random_rep = self.nano_rpc[2].get_account_data(self.nano_rpc[2].generate_seed(), 0)["account"] #generate a random account and set is as new rep




def get_table(table, print_header = True):
    col_width = [max(len(str(x)) for x in col) for col in zip(*table)]     
     
    for line in table:
        if print_header == False :
            print_header = True ; continue
        return ("| " + " | ".join("{:{}}".format(x , col_width[i]) for i, x in enumerate(line)) + " |")

def compute_stats(data, iter_count):    
    block_count_start = data["block_count"]
    block_count_end = BlockGenerator().get_nano_rpc_default().block_count()
    new_blocks =    int(block_count_end.get("count",0))    - int(data["block_count"].get("count",0))
    new_cemented =  int(block_count_end.get("cemented",0)) - int(data["block_count"].get("cemented",0))
    confirmations = [x["conf_duration"] for x in data["conf_lst"] if x["timeout"] == False]
    timeouts = [x for x in data["conf_lst"] if x["timeout"]]
    conf_duration = time() - data["start_time"]

    gather_int = { "confs":len(confirmations),
                    "timeouts": len(timeouts) ,
                    "bps" : new_blocks / conf_duration,
                    "cps" : new_cemented / conf_duration,
                    "min_conf_s" : min(confirmations) if len(confirmations) > 0 else -1,
                    "max_conf_s" : max(confirmations) if len(confirmations) > 0 else -1,
                    "perc_50_s":h.percentile(confirmations,50) if len(confirmations) > 0 else -1,
                    "perc_75_s":h.percentile(confirmations,75) if len(confirmations) > 0 else -1,
                    "perc_90_s":h.percentile(confirmations,90) if len(confirmations) > 0 else -1,
                    "perc_99_s":h.percentile(confirmations,99) if len(confirmations) > 0 else -1,
                    "timeout_s" : timeout_s,
                    "total_s": conf_duration,
                    "new_blocks" : new_blocks,
                    "new_cemented" : new_cemented, }    
    data["conf_lst"] = []
    data["block_count"] = block_count_end
    data["start_time"] = time()
   

    table_pr1 = (gather_int.keys(), [str(round(gather_int[x],2)).ljust(8) for x in gather_int])
    print_header = True if iter_count == 0 else False
    line1 = f'{strftime("%H:%M:%S", gmtime())} {get_table(table_pr1, print_header=print_header)}'
    
    day_of_year = datetime.now().strftime('%j')
    exec_time = datetime.now().strftime("%H%M%S")
    file_path = f"./{day_of_year}_run_conf_timer.out"
    f = open(file_path, "a")
    f.write(line1 + "\n")
    f.close()
    print(f"append to {file_path}")



def main():    
        data = {"block_count" : BlockGenerator().get_nano_rpc_default().block_count(), 
                "start_time" : time(),
                "conf_lst" : [], }        
        for i in range(0,5000) :
            while True: 
                try:
                    q_res = {"timeout_uduration" : timeout_s}
                    blocks = []
                    change_response = bg.blockgen_single_change(source_seed="FACE000000000000000000000000000000000000000000000000000000000025", source_index=i)        
                    blocks.append(change_response["block"])
                    ba.assert_blocks_published(blocks,sync=True)        
                    t1 = time()
                    try:
                        ba.assert_single_block_confirmed(change_response["hash"], exit_after_s=timeout_s, sleep_on_stall_s=0.1)
                        q_res["conf_duration"] = time() -t1
                        q_res["timeout"] = False
                    except :
                        q_res["timeout"] = True
                        pass
                    data["conf_lst"].append(q_res)    
                    if (i % 10) == 0 :
                        compute_stats(data,i)
                    break
                except Exception as e :
                    print(str(e))
                    sleep(5)
               

if __name__=="__main__":
    main()
        
    
# change_block = bg.blockgen_single_change(source_seed="FACE000000000000000000000000000000000000000000000000000000000025", source_index=1)
# print(change_block)

# print(bg.conf.get_rpc_endpoints())
# nano_rpc = NanoRpc(bg.conf.get_rpc_endpoints()[0])
# print(nano_rpc.RPC_URL)
# #nano_rpc = bg.get_nano_rpc_default()
# #print(nano_rpc.RPC_URL)
# nano_rpc = NanoRpc("http://0.0.0.0:45001")
# nano_rpc.publish_block(change_block["block"], change_block["subtype"])