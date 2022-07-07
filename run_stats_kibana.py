#!./venv_nano_local/bin/python

from os import system, listdir
from os.path import exists
from math import ceil, log10
from time import time
from src.parse_nano_local_config import ConfigParser, ConfigReadWrite
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
import threading
import queue

#nodes_stat returns a list with 1 stat for all nodes
#node_stats retruns a dict with all stats for 1 node
#nodes_stats retruns a list with all stats for all nodes

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
        self.conf_rw = ConfigReadWrite()
        self.conf_p = ConfigParser()

    def get_req_object(self, url, request) :
        return {"url" : url, "request" : request}
    
   
    
    def extract_raw_merge_stats(self, node_stats, rpc_res) : 
        self.add_key_if_not_exists(node_stats, "delta", {}) 
        if rpc_res is not None :            
            if rpc_res is not None and "entries" in rpc_res :
                for stat in rpc_res["entries"]:
                    node_stats["delta"][f'stats_{stat["type"]}_{stat["dir"]}_{stat["detail"]}'] = int(stat["value"])
      
    def get_node_name_from_rpc_url(self, url):
        for node in self.conf_p.get_nodes_config() :                     
            if node["rpc_url"] == url : return node["name"] 

    def values_to_integer(self, flat_json, skip_keys = []) :
        pop_keys = []
        for key,value in flat_json.items() :
            if key in skip_keys : continue
            try:
                flat_json[key] = float(value)
            except:
                pop_keys.append(key)
    
        for key in pop_keys :
            flat_json.pop(key)
        return flat_json
         
    def get_nodes_stat_by_key(self, node_stats, key) :
        nodes_stat = []
        for node_stats in node_stats.values() :
            if key in node_stats : nodes_stat.append( node_stats[key])
        return nodes_stat
    

    def get_node_count(self, nodes_stats):
        return len(nodes_stats) - 1 #exclude shared stats
    

       
    def add_key_if_not_exists(self, dict_l, key, default) :
        if key not in dict_l : dict_l[key] = default

    def extend_node_stats_with_delta(node_stats, previous_stats) :

        for action, stats in node_stats.items() :
            if action == "block_count" : 
                stats[action]["uncemented"] = stats[action]["count"] - stats[action]["cemented"]            
        
     
    
    def get_single_request(self, request_responses,action, rpc_url):        
        return request_responses[action][rpc_url]
    
    def get_all_requests(self, request_responses, action):
        sorted_requests = []
        for rpc in self.rpcs :
            sorted_requests.append(request_responses[action][rpc.RPC_URL])
        return sorted_requests    
    
    def get_overlap_percent(self, union_length, avg_aec_size):        
        return round((union_length / max(1,avg_aec_size)) * 100,2)

            
    def get_path(self, filename) :
        return f"./log/{datetime.now().strftime('%j')}_{filename}"           
 
    def get_keys_as_list(self, nodes_stats):
        return [x for x in nodes_stats.keys()]
    
    def log_file_kibana(self, nodes_stats):
        day_of_year = datetime.now().strftime('%j')
        filename = f"run_stats_kibana.log"  #prepended by day_of_year
        nodes_stats_copy = copy.deepcopy(nodes_stats)
        node_names = self.get_keys_as_list(nodes_stats)  
        for i in range(0,self.get_node_count(nodes_stats)) :
            if  "delta" in nodes_stats[node_names[i]]  : nodes_stats_copy[node_names[i]].pop("delta")  

       #add 1 line per node + 1 line for shared stats
        for node_stats in nodes_stats_copy.values() :
            self.conf_rw.append_json(self.get_path(filename),node_stats )  
    
    def extend_node_stats_shared_stats(self, node_stats, nano_nodes_version,timestamp):  #prepare_node_stats step3 (last)
        self.add_key_if_not_exists(node_stats, "shared_stats", {})   

        node_stats["shared_stats"]["calc_timestamp"] = timestamp
        ##### version #####
        node_stats["shared_stats"]["user_nano_nodes_version"] = nano_nodes_version
        #####AEC overlap#######
        
        delta_stats =  self.get_nodes_stat_by_key(node_stats, "delta")
        aecs = [stats["aecs"]for stats in delta_stats]
        union = aecs[0]
        aec_avg_size = sum(len(x) for x in aecs) / len(aecs) 

        aecs_pr = aecs[1:]        
        union_pr = aecs_pr[0]
        aec_pr_avg_size = sum(len(x) for x in aecs_pr) / len(aecs_pr)       

        max_overlap = 0
        
        #AEC overlap for all PRs
        for aec in aecs_pr :
            union_pr = union_pr.intersection(aec)
            union_length = len(union_pr)            
        node_stats["shared_stats"]["calc_overlap_prs"] = self.get_overlap_percent(union_length, aec_pr_avg_size)

        for aec in aecs : 
            union = union.intersection(aec)
            union_length = len(union)
        node_stats["shared_stats"]["calc_overlap_all_nodes"] = self.get_overlap_percent(union_length, aec_avg_size)

        #max AEC overlap of 2 PRs
        for i in range(0, len(aecs)):
            for j in range(i, len(aecs)):
                if i == j : continue #no need to compare to itself
                overlap_pr_i_j = len(aecs[i].intersection(aecs[j]))
                aec_avg_size_i_j = (len(aecs[i]) + len(aecs[j])) / 2               
                node_stats["shared_stats"][f'calc_{i}_{j}_abs'] = overlap_pr_i_j
                node_stats["shared_stats"][f'calc_{i}_{j}_perc'] = self.get_overlap_percent(overlap_pr_i_j, aec_avg_size_i_j)
                max_overlap = max(max_overlap, self.get_overlap_percent(overlap_pr_i_j, aec_avg_size_i_j))   
        node_stats["shared_stats"]["calc_overlap_max"] = max_overlap

    def extend_node_stats_by_pr(self, nodes_stats, timestamp) :     #prepare_node_stats step2 
        #for key in node_stats.keys():
        node_stats = [ x for x in nodes_stats.values() ] #returns list of node_stats

        block_count_cemented = self.get_nodes_stat_by_key(nodes_stats, "block_count_cemented")           
        block_count_count = self.get_nodes_stat_by_key(nodes_stats, "block_count_count")
        
        for i in range(0, len(nodes_stats)) : 
            #for i in range(0, len(block_count_cemented)) :
            node_stats[i][f"calc_uncemented"] = round(max(block_count_count) - block_count_cemented[i],2)
            node_stats[i][f"calc_uncemented_node_view"] = round(block_count_count[i] - block_count_cemented[i],2) 
            node_stats[i][f"calc_sync_block_count"] = round(block_count_count[i]/max(block_count_count) *100,2 )
            node_stats[i][f"calc_sync_cemented"] = round(block_count_cemented[i]/max(block_count_cemented) *100,2 )
            node_stats[i][f"calc_percent_cemented"] = round(block_count_cemented[i]/max(block_count_count) *100,2 )
            node_stats[i][f"calc_missing_cemented"] = round(max(block_count_cemented) - block_count_cemented[i],2)
            node_stats[i][f"calc_timestamp"] = timestamp
            

    def set_node_stats(self, request_responses) : #prepare_node_stats step1
        node_stats={}
        for action, urls in request_responses.items():            
            for url, response in urls.items():
                node_name = self.get_node_name_from_rpc_url(url)
                if node_name not in node_stats : node_stats[node_name] = {"_node_name" : node_name }
                self.add_key_if_not_exists(node_stats[node_name], "delta", {}) 

                if action == "stats" : 
                    self.extract_raw_merge_stats(node_stats[node_name], response)                   
                elif action == "confirmation_active" : 
                    confirmations_key = "confirmation_active_confirmations"   
                    #convert to integer except "confirmations"
                    for key,value in self.values_to_integer(response, skip_keys=["confirmations"]).items(): 
                        node_stats[node_name][f'{action}_{key}'] = value 
                    #convert "confirmations" to set()   
                    if node_stats[node_name][confirmations_key] == '' :node_stats[node_name][confirmations_key] = set() #convert '' to set
                    else :node_stats[node_name][confirmations_key] = set(node_stats[node_name][confirmations_key])                    
                    #move "confirmations" to delta["aecs"]
                    node_stats[node_name]["delta"]["aecs"] = (node_stats[node_name].pop(confirmations_key))
                    
                else: #generic extract data as_is as json 
                    for key,value in self.values_to_integer(response).items(): node_stats[node_name][f'{action}_{key}'] = value   
                                    
        return node_stats   
    
    def calc_delta_stats(self, current, previous, interval) :  #compare_active_elections step4 (last)
        if previous is None : return   

        #get list of 1 stat for all nodes
        block_count_cemented_current = self.get_nodes_stat_by_key(current, "block_count_cemented") 
        block_count_cemented_previous = self.get_nodes_stat_by_key(previous, "block_count_cemented") 
        block_count_count_current = self.get_nodes_stat_by_key(current, "block_count_count")          
        block_count_count_previous = self.get_nodes_stat_by_key(previous, "block_count_count")
                            
        keys = [ x for x in current.keys() ] #returns list of node_stats

        for i in range(0, self.get_node_count(current)) :  

            current[keys[i]]["calc_delta_bps_last_5s"] = (block_count_count_current[i] - block_count_count_previous[i]) / interval  #calc bps   
            current[keys[i]]["calc_delta_cps_last_5s"] = (block_count_cemented_current[i] - block_count_cemented_previous[i]) / interval #calc cps

            if "delta" in current[keys[i]] :
                #calc churn
                aec_union = current[keys[i]]["delta"]["aecs"].union(previous[keys[i]]["delta"]["aecs"])
                aec_inter = current[keys[i]]["delta"]["aecs"].intersection(previous[keys[i]]["delta"]["aecs"])
                current[keys[i]]["calc_delta_churn"] = len(aec_union) - len(aec_inter)
                
                #compute delta stats
                for key, node_stat in current[keys[i]]["delta"].items():
                    if str(key).startswith("stats") :
                        current[keys[i]][f"delta_{key}"] = node_stat - previous[keys[i]]["delta"].get(key , 0)     

    def prepare_node_stats(self, request_responses, nano_node_version) :  #compare_active_elections step3
        timestamp = datetime.now().strftime("%Y-%d-%m, %H:%M:%S")
        node_stats = self.set_node_stats(request_responses)
        self.extend_node_stats_by_pr(node_stats,timestamp)         
        self.extend_node_stats_shared_stats(node_stats, nano_node_version, timestamp)        
        return node_stats
    
    def exec_requests(self, collected_requests):   #compare_active_elections step2 
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
   

    def collect_requests(self): #compare_active_elections step1
        requests = []
        for rpc in self.rpcs:
            requests.append(self.get_req_object(rpc.RPC_URL, rpc.get_stats(request_only=True)))
            requests.append(self.get_req_object(rpc.RPC_URL, rpc.block_count(request_only=True)))
            requests.append(self.get_req_object(rpc.RPC_URL, rpc.confirmation_active(request_only=True)))
            requests.append(self.get_req_object(rpc.RPC_URL, rpc.confirmation_quorum(request_only=True)))
        return requests
   
    def compare_active_elections(self, previous_nodes_stats = None, nano_node_version = None, interval = None):    

        requests = self.collect_requests()
        request_responses = self.exec_requests(requests)        
        current_nodes_stats = self.prepare_node_stats(request_responses, nano_node_version)
        self.calc_delta_stats(current_nodes_stats, previous_nodes_stats, interval)        
        
        self.log_file_kibana(current_nodes_stats)
        return current_nodes_stats
        


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
    
    previous_nodes_stats = None
    while True :
        
        interval = 5
        t1 = run_threaded( s.compare_active_elections,  kwargs={"previous_nodes_stats" : previous_nodes_stats, "nano_node_version":  args.version,  "interval": interval})       
        time.sleep(interval)      
        previous_nodes_stats = t1.join()
    
    


if __name__ == "__main__":       
    main()
