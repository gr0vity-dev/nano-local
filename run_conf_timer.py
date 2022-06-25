#!./venv_nano_local/bin/python
from src.nano_rpc import NanoRpc
from src.nano_block_ops import BlockGenerator, BlockAsserts
from src.parse_nano_local_config import Helpers
import pandas as pd
from tabulate import tabulate
from datetime import datetime

import time


bg = BlockGenerator(default_rpc_index=2, broadcast_blocks=False)
ba = BlockAsserts(default_rpc_index=2)
h = Helpers()
bg.set_single_change_rep()
timeout_s = 20
#random_rep = self.nano_rpc[2].get_account_data(self.nano_rpc[2].generate_seed(), 0)["account"] #generate a random account and set is as new rep

def compute_stats(data):    
    block_count_start = data["block_count"]
    block_count_end = BlockGenerator().get_nano_rpc_default().block_count()
    new_blocks =    int(block_count_end.get("count",0))    - int(data["block_count"].get("count",0))
    new_cemented =  int(block_count_end.get("cemented",0)) - int(data["block_count"].get("cemented",0))
    confirmations = [x["conf_duration"] for x in data["conf_lst"] if x["timeout"] == False]
    timeouts = [x for x in data["conf_lst"] if x["timeout"]]
    conf_duration = time.time() - data["start_time"]

    res = { "confs":len(confirmations),
                "timeouts": len(timeouts) ,
                "bps" : new_blocks / conf_duration,
                "cps" : new_cemented / conf_duration,
                "min_conf_s" : min(confirmations) if len(confirmations) > 0 else "timeout",
                "max_conf_s" : max(confirmations) if len(confirmations) > 0 else "timeout",
                "perc_50_s":h.percentile(confirmations,50) if len(confirmations) > 0 else "timeout",
                "perc_75_s":h.percentile(confirmations,75) if len(confirmations) > 0 else "timeout",
                "perc_90_s":h.percentile(confirmations,90) if len(confirmations) > 0 else "timeout",
                "perc_99_s":h.percentile(confirmations,99) if len(confirmations) > 0 else "timeout",
                "timeout_s" : timeout_s,
                "total_s": conf_duration,
                "new_blocks" : new_blocks,
                "new_cemented" : new_cemented, }    
    data["conf_lst"] = []
    data["block_count"] = block_count_end
    data["start_time"] = time.time()
   
    lst = []
    lst.append(res)

    df = pd.DataFrame(lst)
    content = tabulate(df.values.tolist(), list(df.columns), tablefmt="plain", floatfmt=".3f")
    print(content)
    day_of_year = datetime.now().strftime('%j')
    exec_time = datetime.now().strftime("%H%M%S")
    file_path = f"./conf_timer_{day_of_year}.txt"
    f = open(file_path, "a")
    f.write("\n" + content.split("\n")[1])
    f.close()



def main():    
        data = {"block_count" : BlockGenerator().get_nano_rpc_default().block_count(), 
                "start_time" : time.time(),
                "conf_lst" : [], }
        for i in range(3005,5000) :        
            q_res = {"timeout_uduration" : timeout_s}
            blocks = []
            change_response = bg.blockgen_single_change(source_seed="FACE000000000000000000000000000000000000000000000000000000000025", source_index=i)        
            blocks.append(change_response["block"])
            ba.assert_blocks_published(blocks,sync=True)        
            t1 = time.time()
            try:
                ba.assert_single_block_confirmed(change_response["hash"], exit_after_s=timeout_s, sleep_on_stall_s=0.1)
                q_res["conf_duration"] = time.time() -t1
                q_res["timeout"] = False
            except :
                q_res["timeout"] = True
                pass
            data["conf_lst"].append(q_res)    
            if (i % 10) == 0 :
                compute_stats(data)
               

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