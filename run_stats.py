#!./venv_nano_local/bin/python

from os import system, listdir
from os.path import exists
from math import ceil, log10
from time import time
from src.parse_nano_local_config import ConfigReadWrite
from src.nano_rpc import NanoRpc
from src.nano_block_ops import BlockAsserts, BlockGenerator, BlockReadWrite
import copy
import logging
import time
from time import strftime,gmtime
from datetime import datetime
import json
import inspect
from colorama import Fore, Style
import argparse
import re
import schedule
import threading
import queue


def get_table(table, print_header = True, color=""):
    col_width = [max(len(str(x)) for x in col) for col in zip(*table)]     
     
    for line in table:
        if print_header == False :
            print_header = True ; continue
        return ("| " + " | ".join("{}{:{}}{}".format(color, x , col_width[i], Style.RESET_ALL) for i, x in enumerate(line)) + " |")


class NanoStats():
   
    def __init__(self):        
        self.bg = BlockGenerator(default_rpc_index = 1, broadcast_blocks=False)       
        self.rpcs = self.bg.get_rpc_all() 
        self.conf_p = ConfigReadWrite()

    def get_block_count_prs(self, request_responses):
        bc = []
        action = self.rpcs[0].block_count(request_only=True)["action"]
        
        for rpc in self.rpcs:
            res = self.get_single_request(request_responses, action, rpc.RPC_URL)
            if res is not None :
                bc.append(res)       
        if len(bc) > 0 : bc.pop(0) #remove genesis (non PR)      
        return bc
    
    def get_election_stats(self, request_responses):
        stats = []
        action = self.rpcs[0].get_stats(request_only=True)["action"]

        for rpc in self.rpcs:
            rpc_res = self.get_single_request(request_responses, action, rpc.RPC_URL)
            res = {}
            if rpc_res is not None :                
                for stat in rpc_res["entries"] :
                    if stat["detail"] in [ "election_start" , "election_confirmed_all", "election_drop_all", "election_hinted_started" ] :
                        if stat["detail"] == "election_start" : stat["detail"] = "e_start"
                        if stat["detail"] == "election_confirmed_all" : stat["detail"] = "e_conf"
                        if stat["detail"] == "election_drop_all" : stat["detail"] = "e_drop"
                        if stat["detail"] == "election_hinted_started" : stat["detail"] = "e_hint"
                        res[f'{stat["detail"]}_{stat["dir"]}'] = int(stat["value"])
                stats.append(res)       
        if len(stats) > 0 : stats.pop(0) #remove genesis (non PR)
        return stats
    
    def get_stats(self,request_responses):
        stats = []
        action = self.rpcs[0].get_stats(request_only=True)["action"]

        for rpc in self.rpcs :
            merged_stat = {}
            rpc_res = self.get_single_request(request_responses, action, rpc.RPC_URL)
            if rpc_res is not None and "entries" in rpc_res :
                for stat in rpc_res["entries"]:
                    merged_stat[f'{stat["type"]}_{stat["dir"]}_{stat["detail"]}'] = int(stat["value"])
                stats.append(merged_stat)
            else :
                print("entries not in stats rpc response")
        return stats
    
    def get_active_confirmations(self, request_responses):
        aecs = []
        action = self.rpcs[0].confirmation_active(request_only=True)["action"]
        try:
            for rpc in self.rpcs: #this should be async to get even better results.               
                aecs.append(self.get_single_request(request_responses,action, rpc.RPC_URL))
        except Exception as e:
            print("rpc not reachable", str(e))
            #return []
        if len(aecs) > 0 : aecs.pop(0) #remove genesis (non PR)
        return aecs

    def get_req_object(self, url, request) :
        return {"url" : url, "request" : request}
    
    def collect_requests(self):
        requests = []
        for rpc in self.rpcs:
            requests.append(self.get_req_object(rpc.RPC_URL, rpc.get_stats(request_only=True)))
            requests.append(self.get_req_object(rpc.RPC_URL, rpc.block_count(request_only=True)))
            requests.append(self.get_req_object(rpc.RPC_URL, rpc.confirmation_active(request_only=True)))
        return requests
    
    def exec_requests(self, collected_requests):   
        result = {}     
        res = self.bg.get_nano_rpc_default().exec_parallel_post(collected_requests)
        
        #{"action" : {"url1" : {}, "url2" : {}, ...}}
        for request in res :
            action = request["request"]["action"]
            url = request["url"]
            response = request["response"]
            if action not in result : result[action] = {}
            if url not in result[action] : result[action][url] = {}
            result[action][url] = response
        
        return result
    
    def get_single_request(self, request_responses,action, rpc_url):        
        return request_responses[action][rpc_url]
    
    def get_all_requests(self, request_responses, action):
        sorted_requests = []
        for rpc in self.rpcs :
            sorted_requests.append(request_responses[action][rpc.RPC_URL])
        return sorted_requests    
    
    def get_overlap_percent(self, union_length, avg_aec_size):        
        return round((union_length / max(1,avg_aec_size)) * 100,2)

    def log_to_console_aec(self, data, values,nano_node_version=None):    

            file_path = f"./{datetime.now().strftime('%j')}_run_stats.out"
            header = 'time     | PRs  | AEC overlap | AEC overlap count | AEC unconf.   | AEC churn | elect_start | elect_conf | elect_drop | block_inc  | cemented_inc     | elect_hint | AEC overlap PR_% | count      | cemented %   | sync count | miss cement. | uncemented       |'
            # if print_header_inc == 0 :
            #     print(header) 
            #     self.conf_p.append_line(file_path, header + "\n") 
                  
            table_pr1 = ([x.replace("__pr1", "pr__") for x in values[0]], [str(data[x]) for x in values[0]])
            table_pr2 = ([x.replace("__pr2", "pr__") for x in values[1]], [str(data[x]).replace("1_2", "2_1") for x in values[1]])
            table_pr3 = ([x.replace("__pr3", "pr__") for x in values[2]], [str(data[x]).replace("1_3", "3_1").replace("2_3", "3_2") for x in values[2]])
            
            line1 = f'{strftime("%H:%M:%S", gmtime())} {get_table(table_pr1, print_header=False)}'
            line2=  f'{"         " + get_table(table_pr2, False, color=Fore.LIGHTGREEN_EX)} '
            line3=  f'{"         " + get_table(table_pr3, False, color=Fore.LIGHTBLUE_EX)} '
            line4=  f'{"-"*len(header)}'
            print(line1); print( line2) ; print(line3) ; print( Style.RESET_ALL, end="") ; print(line4) ;print(header, end = "\r" )
            
            #without format
            #line2=  f'{"         " + get_table(table_pr2, False)} '
            #line3=  f'{"         " + get_table(table_pr3, False)} '                
            #self.conf_p.append_line(file_path, line1 + "\n"+ line2 + "\n"+ line3 + "\n"+ line4 + "\n")
            
    def get_path(self, filename) :
        return f"./log/{datetime.now().strftime('%j')}_{filename}.log"

    def log_write_file_aec(self, data, values, filename = "aec_stats", nano_node_version = None):  
              
        ts = [{},{},{}]
        for i in range(0,3):
            ts[i]["version"] = nano_node_version

            for key in values[i] :                        
                #string values
                if key == f'__pr{i+1}' : 
                    ts[i]["_pr"] = str(data[key])
                # elif isinstance(data[key], str) :
                #     ts[i][key] = data[key]  
                elif key in ["elapsed"]:
                        ts[i][key] = data[key]                
                #integer values
                else : 
                    try:
                        newValue = str(data[key]).replace("1_2  ","").replace("2_3  ","").replace("1_3  ","")
                        newKey = key.replace("bc_", "block_count_").replace(f"_pr{i+1}", "").replace(f"pr{i+1}_", "").replace("e_", "election_").replace("cem_", "cemented_").replace("overlap_", "aec_overlap_")                               
                        
                        ts[i][newKey] = float(newValue)
                    except Exception as e:
                        print(str(e),newKey,newValue )
            self.conf_p.append_json(self.get_path(filename), ts[i])         
        

         
    def log_write_file_stats_delta(self, request_responses, previous = None, nano_node_version = None, filename = "counter_stats"):
        
        if previous is None : previous = {}        
        rpc_stats = self.get_stats(request_responses)        
        if previous == {}:
            previous = rpc_stats                  
        for i in range(0, len(rpc_stats)):
            stats_delta = {}
            stats_delta["_pr"] = f'PR{i+1}'
            stats_delta["version"] = nano_node_version    
            for key,value in rpc_stats[i].items() :   
                if len(previous) > i : # prevent "IndexError: list index out of range" error
                    stats_delta[key] = value - previous[i].get(key, 0)           

            self.conf_p.append_json(self.get_path(filename), stats_delta)
        
    
    def aec_stats(self, current, previous = None, nano_node_version = None):       
        
        stats = current["election_stats"]
        aecs_detail = current["aecs"]
        aecs = [set(x["confirmations"]) for x in aecs_detail] if len(aecs_detail) > 0 else set()
        bcs = current["bcs"]
        p_aecs_detail = previous["aecs"]
        p_aecs = [set(x["confirmations"]) for x in p_aecs_detail] if len(p_aecs_detail) > 0 else set()
              
        if len(aecs) == 0 : #if rpc non reachable.
            return      
        
        aec_avg_size = sum(len(x) for x in aecs) / len(aecs)
        union = set()
        max_overlap = 0
        oberlap_pr = {}
        
        #AEC overlap for all PRs
        for aec in aecs :            
            if union == set() : union = aec
            else : union = union.intersection(aec)
            union_length = len(union)
        overlap = self.get_overlap_percent(union_length, aec_avg_size)
        

        #max AEC overlap of 2 PRs
        for i in range(0, len(aecs)):
            for j in range(i, len(aecs)):
                if i == j : continue #no need to compare to itself
                overlap_pr_i_j = len(aecs[i].intersection(aecs[j]))
                aec_avg_size_i_j = (len(aecs[i]) + len(aecs[j])) / 2
                oberlap_pr[f'{i}_{j}'] = {}
                oberlap_pr[f'{i}_{j}']["abs"] = overlap_pr_i_j
                oberlap_pr[f'{i}_{j}']["perc"] = self.get_overlap_percent(overlap_pr_i_j, aec_avg_size_i_j)
                max_overlap = max(max_overlap, self.get_overlap_percent(overlap_pr_i_j, aec_avg_size_i_j))             


        #churn in blocks every {every_s =5} seconds for each PR
        churn = []
        if len(p_aecs) == len(aecs) :                                                   
            for i in range(0, len(aecs)):                    
                churn.append( str(len(p_aecs[i]) - len(aecs[i].intersection(p_aecs[i]))).ljust(4) )
        
        election_delta = []
        for i in range(0, len(stats)):
            pr_election_stats = []
            for key,value in stats[i].items():
                if len(previous["election_stats"]) <= i : break
                delta = value - previous["election_stats"][i].get(key, 0)                   
                pr_election_stats.append(delta)
            election_delta.append(pr_election_stats)

        count_cemented_delta = []
        if len(previous["bcs"]) == len(bcs) :                                                   
            for i in range(0, len(bcs)):
                count_delta = int(bcs[i]["count"]) - int(previous["bcs"][i]["count"])
                cemented_delta = int(bcs[i]["cemented"]) - int(previous["bcs"][i]["cemented"])
                #count_cemented_delta.append(f'{count_delta};{cemented_delta}'.ljust(10))          
                count_cemented_delta.append([count_delta, cemented_delta])                                  


        example_hash =  list(union)[0] if len(union) > 0 else ""       
        
        data = {
                    "overlap_all_count"    : union_length , 
                    "overlap_all"          : str(overlap) ,
                    "overlap_max"          : str(max_overlap),                   
                    "pr1_churn"            : churn[0] if len(churn) > 0 else 0 , 
                    "pr1_e_start"          : election_delta[0][0] if len(election_delta) > 0 and len(election_delta[0]) > 0 else 0, 
                    "pr1_e_conf"           : election_delta[0][1] if len(election_delta) > 0 and len(election_delta[0]) > 1 else 0, 
                    "pr1_e_drop"           : election_delta[0][2] if len(election_delta) > 0 and len(election_delta[0]) > 2 else 0,
                    "pr1_bc_inc"           : count_cemented_delta[0][0] if len(count_cemented_delta) > 0 and len(count_cemented_delta[0]) > 0 else 0,  
                    "pr1_cemented_inc"     : count_cemented_delta[0][1] if len(count_cemented_delta) > 0 and len(count_cemented_delta[0]) > 1 else 0, 
                    "pr1_e_hint"           : election_delta[0][3] if len(election_delta) > 0 and len(election_delta[0]) > 3 else 0,          
                    "pr2_churn"            : churn[1] if len(churn) > 1 else 0,
                    "pr2_e_start"          : election_delta[1][0] if len(election_delta) > 1 and len(election_delta[1]) > 0 else 0,
                    "pr2_e_conf"           : election_delta[1][1] if len(election_delta) > 1 and len(election_delta[1]) > 1 else 0,
                    "pr2_e_drop"           : election_delta[1][2] if len(election_delta) > 1 and len(election_delta[1]) > 2 else 0,
                    "pr2_bc_inc"           : count_cemented_delta[1][0] if len(count_cemented_delta) > 1 and len(count_cemented_delta[1]) > 0 else 0,
                    "pr2_cemented_inc"     : count_cemented_delta[1][1] if len(count_cemented_delta) > 1 and len(count_cemented_delta[1]) > 1 else 0,
                    "pr2_e_hint"           : election_delta[1][3] if len(election_delta) > 1 and len(election_delta[1]) > 3 else 0,
                    "pr3_churn"            : churn[2] if len(churn) > 2 else 0,
                    "pr3_e_start"          : election_delta[2][0] if len(election_delta) > 2 and len(election_delta[2]) > 0 else 0,
                    "pr3_e_conf"           : election_delta[2][1] if len(election_delta) > 2 and len(election_delta[2]) > 1 else 0,
                    "pr3_e_drop"           : election_delta[2][2] if len(election_delta) > 2 and len(election_delta[2]) > 2 else 0,
                    "pr3_bc_inc"           : count_cemented_delta[2][0] if len(count_cemented_delta) > 2 and len(count_cemented_delta[2]) > 0 else 0,
                    "pr3_cemented_inc"     : count_cemented_delta[2][1] if len(count_cemented_delta) > 2 and len(count_cemented_delta[2]) > 1 else 0,
                    "pr3_e_hint"           : election_delta[2][3] if len(election_delta) > 2 and len(election_delta[2]) > 3 else 0, 
                    "overlap_1_2_abs"      : oberlap_pr["0_1"]["abs"]  if "0_1" in oberlap_pr and "abs" in oberlap_pr["0_1"] else 0,
                    "overlap_1_3_abs"      : oberlap_pr["0_2"]["abs"] if "0_2" in oberlap_pr and "abs" in oberlap_pr["0_2"] else 0,
                    "overlap_2_3_abs"      : oberlap_pr["1_2"]["abs"] if "1_2" in oberlap_pr and "abs" in oberlap_pr["1_2"] else 0,
                    "overlap_1_2_perc"     : "1_2  " +str(oberlap_pr["0_1"]["perc"]) if "0_1" in oberlap_pr and "perc" in oberlap_pr["0_1"] else 0,
                    "overlap_1_3_perc"     : "1_3  " +str(oberlap_pr["0_2"]["perc"]) if "0_2" in oberlap_pr and "perc" in oberlap_pr["0_2"] else 0,
                    "overlap_2_3_perc"     : "2_3  " +str(oberlap_pr["1_2"]["perc"]) if "1_2" in oberlap_pr and "perc" in oberlap_pr["1_2"] else 0,
                    "__pr1"                : "PR1",
                    "__pr2"                : "PR2",
                    "__pr3"                : "PR3",
                    "aec_uncon_pr1"          : aecs_detail[0]["unconfirmed"] if len(aecs_detail) > 0 else 0,
                    "aec_uncon_pr2"          : aecs_detail[1]["unconfirmed"] if len(aecs_detail) > 1 else 0,
                    "aec_uncon_pr3"          : aecs_detail[2]["unconfirmed"] if len(aecs_detail) > 2 else 0,
                    "bc_pr1"               : bcs[0]["count"].ljust(10) if len(bcs) > 0 and "count" in bcs[0] else " "*10,
                    "bc_pr2"               : bcs[1]["count"].ljust(10) if len(bcs) > 1 and "count" in bcs[1] else " "*10,
                    "bc_pr3"               : bcs[2]["count"].ljust(10) if len(bcs) > 2 and "count" in bcs[2] else " "*10,
                    "cem_perc_pr1"         : round(int(bcs[0]["cemented"]) / int(bcs[0]["count"]) *100,2) if len(bcs) > 0 and "count" in bcs[0] and "cemented" in bcs[0] else 0,
                    "cem_perc_pr2"         : round(int(bcs[1]["cemented"]) / int(bcs[1]["count"]) *100,2) if len(bcs) > 1 and "count" in bcs[1] and "cemented" in bcs[1] else 0,
                    "cem_perc_pr3"         : round(int(bcs[2]["cemented"]) / int(bcs[2]["count"]) *100,2) if len(bcs) > 2 and "count" in bcs[2] and "cemented" in bcs[2] else 0,
                    "sync_pr1_c"           : round(int(bcs[0]["count"])/max([int(x["count"]) for x in bcs]) *100,2) if len(bcs) > 0 and "count" in bcs[0] else 0,
                    "sync_pr2_c"           : round(int(bcs[1]["count"])/max([int(x["count"]) for x in bcs]) *100,2) if len(bcs) > 1 and "count" in bcs[1] else 0,
                    "sync_pr3_c"           : round(int(bcs[2]["count"])/max([int(x["count"]) for x in bcs]) *100,2) if len(bcs) > 2 and "count" in bcs[2] else 0,
                    "sync_cem_pr1"         : round(max([int(x["cemented"]) for x in bcs]) -int(bcs[0]["cemented"]),2) if len(bcs) > 0 and "cemented" in bcs[0] else 0,
                    "sync_cem_pr2"         : round(max([int(x["cemented"]) for x in bcs]) -int(bcs[1]["cemented"]),2) if len(bcs) > 1 and "cemented" in bcs[1] else 0,
                    "sync_cem_pr3"         : round(max([int(x["cemented"]) for x in bcs]) -int(bcs[2]["cemented"]),2) if len(bcs) > 2 and "cemented" in bcs[2] else 0,
                    "example_hash"         : example_hash,
                    "version"              : nano_node_version,                   
                    "pr1_uncemented"       : int(bcs[0]["count"]) - int(bcs[0]["cemented"]) if len(bcs) > 0 and "count" in bcs[0] and "cemented" in bcs[0] else 0,
                    "pr2_uncemented"       : int(bcs[1]["count"]) - int(bcs[1]["cemented"]) if len(bcs) > 1 and "count" in bcs[1] and "cemented" in bcs[1] else 0,
                    "pr3_uncemented"       : int(bcs[2]["count"]) - int(bcs[2]["cemented"]) if len(bcs) > 2 and "count" in bcs[2] and "cemented" in bcs[2] else 0,
                    }
            
        values = [  ["__pr1","overlap_all","overlap_all_count","aec_uncon_pr1","pr1_churn","pr1_e_start","pr1_e_conf","pr1_e_drop","pr1_bc_inc","pr1_cemented_inc","pr1_e_hint","overlap_1_2_perc", "bc_pr1","cem_perc_pr1","sync_pr1_c","sync_cem_pr1", "pr1_uncemented"], 
                    ["__pr2","overlap_all","overlap_all_count","aec_uncon_pr2","pr2_churn","pr2_e_start","pr2_e_conf","pr2_e_drop","pr2_bc_inc","pr2_cemented_inc","pr2_e_hint","overlap_2_3_perc", "bc_pr2","cem_perc_pr2","sync_pr2_c","sync_cem_pr2", "pr2_uncemented"],
                    ["__pr3","overlap_all","overlap_all_count","aec_uncon_pr3","pr3_churn","pr3_e_start","pr3_e_conf","pr3_e_drop","pr3_bc_inc","pr3_cemented_inc","pr3_e_hint","overlap_1_3_perc", "bc_pr3","cem_perc_pr3","sync_pr3_c","sync_cem_pr3", "pr3_uncemented"],
                ]
        
        return (data, values)

    def compare_active_elections(self, previous = None, nano_node_version = None):    

        requests = self.collect_requests()
        request_responses = self.exec_requests(requests) 
        #print(request_responses)

        if previous is None : previous = {"aecs" : [], "bcs" : [], "stats" : [], "election_stats" : []}
        current = { "aecs" : self.get_active_confirmations(request_responses), 
                    "bcs" : self.get_block_count_prs(request_responses), 
                    "election_stats" : self.get_election_stats(request_responses),
                    "stats" : self.get_stats(request_responses)}       
       
        #print("DEBUG_PRINT",current)
        data , values = self.aec_stats(current,previous, )
        self.log_to_console_aec(data,values,nano_node_version=nano_node_version)
        self.log_write_file_aec(data,values, nano_node_version=nano_node_version)
        self.log_write_file_stats_delta(request_responses, previous["stats"], nano_node_version=nano_node_version)   

        #print(previous)
        
        previous = current
        return previous
        #time.sleep(every_s)     


class ReturnValueThread(threading.Thread):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.result = None

    def run(self):
        if self._target is None:
            return  # could alternatively raise an exception, depends on the use case
        try:
            self.result = self._target(*self._args, **self._kwargs)
        except Exception as exc:
            print(f'{type(exc).__name__}: {exc}')  # properly handle the exception

    def join(self, *args, **kwargs):
        super().join(*args, **kwargs)
        return self.result

def run_threaded(job_func, *args, **kwargs):
    job_thread = ReturnValueThread(target=job_func, *args, **kwargs)   
    job_thread.start()
    return job_thread
         
        
def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--version',
                        help='mandatory, specify the nano_node version you are running (for logging purpose)')   
    return parser.parse_args()         
  
def main():
    s = NanoStats()   
    args = parse_args() 
    if args.version is None :
        raise Exception("Please specify a nano_node version for logging purpose")   
    
    previous = None
    while True :   
        t1 = run_threaded( s.compare_active_elections,  kwargs={"previous" : previous, "nano_node_version":  args.version,})       
        time.sleep(5)
        previous = t1.join()
        
        
        #t2.join()
        print(time.time())

    # if args.command == 'aec' : #c(reate) s(tart) i(nit)
    #     s.compare_active_elections(nano_node_version = args.version, every_s = 5, repeat_header = 10, format = "table_per_pr")

    # elif args.command == 'stats':
    #     s.log_stats_delta(nano_node_version = args.version, every_s = 5,)
    
    


if __name__ == "__main__":       
    main()
