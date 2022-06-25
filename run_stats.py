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

    def get_block_count_prs(self):
        bc = []
        
        for rpc in self.rpcs:
            res = rpc.block_count()
            if res is not None :
                bc.append(res)       
        if len(bc) > 0 : bc.pop(0) #remove genesis (non PR)      
        return bc
    
    def get_election_stats(self):
        stats = []
        for rpc in self.rpcs:
            rpc_res = rpc.get_stats()
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
    
    def get_active_confirmations(self):
        aecs = []
        try:
            for rpc in self.rpcs: #this should be async to get even better results.               
                aecs.append(rpc.confirmation_active())
        except Exception as e:
            print("rpc not reachable", str(e))
            #return []
        if len(aecs) > 0 : aecs.pop(0) #remove genesis (non PR)
        return aecs
    
    def get_overlap_percent(self, union_length, avg_aec_size):        
        return round((union_length / max(1,avg_aec_size)) * 100,2)

    def print_to_console(self, data,format, print_header_inc, repeat_header):

            
            if format == "line" :
                print( Fore.LIGHTBLUE_EX + f'aec_overlap_all|count_all|max' , end='')
                print( Style.RESET_ALL, end='')
                print( f'{data["overlap_all"]:>6}|{data["overlap_all_count"]:>4}|{data["overlap_max"]:>6}' , end='')
                print( Fore.LIGHTBLUE_EX + f'   .count|cemented' , end='')
                print( Style.RESET_ALL, end='')
                print( Fore.GREEN + f' pr1:' , end='')
                print( Style.RESET_ALL, end='')
                print( f'{data["pr1_bc_inc"]:>4}|{data["pr1_cemented_inc"]:>4}' , end='')
                print( Fore.GREEN + f' |pr2:' , end='')
                print( Style.RESET_ALL, end='')
                print( f'{data["pr2_bc_inc"]:>4}|{data["pr2_cemented_inc"]:>4}' , end='')
                print( Fore.GREEN + f' |pr3:'  , end='')
                print( Style.RESET_ALL, end='')
                print( f'{data["pr3_bc_inc"]:>4}|{data["pr3_cemented_inc"]:>4}' , end='')
                print( Fore.LIGHTBLUE_EX + f'   .confirmed|dropped|churn|elections_started|hinted:' , end='')
                print( Style.RESET_ALL, end='')
                print( Fore.GREEN + f' pr1:' , end='')
                print( Style.RESET_ALL, end='')
                print( f' {data["pr1_e_conf"]:>4}|{data["pr1_e_drop"]:>4}|{data["pr1_churn"]:>4}|{data["pr1_e_start"]:>4}|{data["pr1_e_hint"]:>2}' , end='')
                print( Fore.GREEN + f' |pr2:' , end='')
                print( Style.RESET_ALL, end='')
                print( f' {data["pr2_e_conf"]:>4}|{data["pr2_e_drop"]:>4}|{data["pr2_churn"]:>4}|{data["pr2_e_start"]:>4}|{data["pr2_e_hint"]:>2}' , end='')
                print( Fore.GREEN + f' |pr3:'  , end='')
                print( Style.RESET_ALL, end='')
                print( f' {data["pr3_e_conf"]:>4}|{data["pr3_e_drop"]:>4}|{data["pr3_churn"]:>4}|{data["pr3_e_start"]:>4}|{data["pr3_e_hint"]:>2}', end='')
                        
                print( Fore.LIGHTBLUE_EX + f'   example_hash', end='')           
                print( Style.RESET_ALL, end='')
                print( data["example_hash"] )
                   
            if format == "table" :
                data.pop("pr1") ; data.pop("pr2") ; data.pop("pr3") #remove keys used for "table_per_pr" formatting option
                #print(data.values())          
                table = (data.keys(), data.values())                       
                if (print_header_inc % repeat_header) == 0 : print_header = True
                print(get_table(table, print_header=print_header))
                print_header = False          



            if format == "table_per_pr" :
                file_path = f"./{datetime.now().strftime('%j')}_run_stats.out"
                header = 'time     | PRs | AEC overlap | AEC overlap count | AEC unconf. | AEC churn | elect_start | elect_conf | elect_drop | block_inc  | cemented_inc     | elect_hint | AEC overlap PR_% | count      | cemented %   | sync count | miss cement. |'
                if print_header_inc == 0 :
                    print(header) 
                    self.conf_p.append_line(file_path, header + "\n") 

                values = [["pr1","overlap_all","overlap_all_count","aec_uncon_1","pr1_churn","pr1_e_start","pr1_e_conf","pr1_e_drop","pr1_bc_inc","pr1_cemented_inc","pr1_e_hint","overlap_1_2_perc", "bc_pr1","cem_perc_pr1","sync_pr1_c","sync_cem_pr1"], 
                          ["pr2","overlap_all","overlap_all_count","aec_uncon_1","pr2_churn","pr2_e_start","pr2_e_conf","pr2_e_drop","pr2_bc_inc","pr2_cemented_inc","pr2_e_hint","overlap_2_3_perc", "bc_pr2","cem_perc_pr2","sync_pr2_c","sync_cem_pr2"],
                          ["pr3","overlap_all","overlap_all_count","aec_uncon_1","pr3_churn","pr3_e_start","pr3_e_conf","pr3_e_drop","pr3_bc_inc","pr3_cemented_inc","pr3_e_hint","overlap_1_3_perc", "bc_pr3","cem_perc_pr3","sync_pr3_c","sync_cem_pr3"],
                          ]        
                table_pr1 = (values[0], [str(data[x]) for x in values[0]])
                table_pr2 = (values[1], [str(data[x]).replace("1_2", "2_1") for x in values[1]])
                table_pr3 = (values[2], [str(data[x]).replace("1_3", "3_1").replace("2_3", "3_2") for x in values[2]])
                
                line1 = f'{strftime("%H:%M:%S", gmtime())} {get_table(table_pr1, print_header=False)}'
                line2=  f'{"         " + get_table(table_pr2, False, color=Fore.LIGHTGREEN_EX)} '
                line3=  f'{"         " + get_table(table_pr3, False, color=Fore.LIGHTBLUE_EX)} '
                line4=  f'{"-"*len(header)}'
                print(line1)
                #print(Fore.LIGHTYELLOW_EX + line2)
                #print(Fore.LIGHTBLUE_EX + line3)
                print( line2)
                print(line3)
                print( Style.RESET_ALL, end="")
                print(line4)
                print(header, end = "\r" )
                
                #without format
                line2=  f'{"         " + get_table(table_pr2, False)} '
                line3=  f'{"         " + get_table(table_pr3, False)} '                
                self.conf_p.append_line(file_path, line1 + "\n"+ line2 + "\n"+ line3 + "\n"+ line4 + "\n")
  
    def compare_active_elections(self, every_s = 5, repeat_header = 10, format = "table"):        
        print_header_inc = -1
        previous_aecs = []
        previous_bcs = []
        previous_stats = []        
        
        while True :     
            print_header_inc = print_header_inc + 1
            stats = self.get_election_stats()
            aecs_detail = self.get_active_confirmations()            
            aecs = [set(x["confirmations"]) for x in aecs_detail] if len(aecs_detail) > 0 else set()
            bcs = self.get_block_count_prs() 
           
            if len(aecs) == 0 : #if rpc non reachable.
                time.sleep(5)
                continue                 
            
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
            if len(previous_aecs) == len(aecs) :                                                   
                for i in range(0, len(aecs)):                    
                    churn.append( str(len(previous_aecs[i]) - len(aecs[i].intersection(previous_aecs[i]))).ljust(4) )
            
            election_delta = []
            for i in range(0, len(stats)):
                pr_election_stats = []
                for key,value in stats[i].items():
                    if len(previous_stats) <= i : break
                    delta = value - previous_stats[i].get(key, 0)                   
                    pr_election_stats.append(delta)
                election_delta.append(pr_election_stats)

                
                
            
            count_cemented_delta = []
            if len(previous_bcs) == len(bcs) :                                                   
                for i in range(0, len(bcs)):
                    count_delta = int(bcs[i]["count"]) - int(previous_bcs[i]["count"])
                    cemented_delta = int(bcs[i]["cemented"]) - int(previous_bcs[i]["cemented"])
                    #count_cemented_delta.append(f'{count_delta};{cemented_delta}'.ljust(10))          
                    count_cemented_delta.append([count_delta, cemented_delta])                                  


            example_hash =  list(union)[0] if len(union) > 0 else ""          
            
            data = {
                     "overlap_all_count"    : union_length , 
                     "overlap_all"          : str(overlap) + "%",
                     "overlap_max"          : str(max_overlap) + "%",                   
                     "pr1_churn"            : churn[0] if len(churn) > 0 else "" , 
                     "pr1_e_start"          : election_delta[0][0] if len(election_delta) > 0 and len(election_delta[0]) > 0 else "", 
                     "pr1_e_conf"           : election_delta[0][1] if len(election_delta) > 0 and len(election_delta[0]) > 1 else "", 
                     "pr1_e_drop"           : election_delta[0][2] if len(election_delta) > 0 and len(election_delta[0]) > 2 else "",
                     "pr1_bc_inc"           : count_cemented_delta[0][0] if len(count_cemented_delta) > 0 and len(count_cemented_delta[0]) > 0 else "",  
                     "pr1_cemented_inc"     : count_cemented_delta[0][1] if len(count_cemented_delta) > 0 and len(count_cemented_delta[0]) > 1 else "", 
                     "pr1_e_hint"           : election_delta[0][3] if len(election_delta) > 0 and len(election_delta[0]) > 3 else "",          
                     "pr2_churn"            : churn[1] if len(churn) > 1 else "",
                     "pr2_e_start"          : election_delta[1][0] if len(election_delta) > 1 and len(election_delta[1]) > 0 else "",
                     "pr2_e_conf"           : election_delta[1][1] if len(election_delta) > 1 and len(election_delta[1]) > 1 else "",
                     "pr2_e_drop"           : election_delta[1][2] if len(election_delta) > 1 and len(election_delta[1]) > 2 else "",
                     "pr2_bc_inc"           : count_cemented_delta[1][0] if len(count_cemented_delta) > 1 and len(count_cemented_delta[1]) > 0 else "",
                     "pr2_cemented_inc"     : count_cemented_delta[1][1] if len(count_cemented_delta) > 1 and len(count_cemented_delta[1]) > 1 else "",
                     "pr2_e_hint"           : election_delta[1][3] if len(election_delta) > 1 and len(election_delta[1]) > 3 else "",
                     "pr3_churn"            : churn[2] if len(churn) > 2 else "",
                     "pr3_e_start"          : election_delta[2][0] if len(election_delta) > 2 and len(election_delta[2]) > 0 else "",
                     "pr3_e_conf"           : election_delta[2][1] if len(election_delta) > 2 and len(election_delta[2]) > 1 else "",
                     "pr3_e_drop"           : election_delta[2][2] if len(election_delta) > 2 and len(election_delta[2]) > 2 else "",
                     "pr3_bc_inc"           : count_cemented_delta[2][0] if len(count_cemented_delta) > 2 and len(count_cemented_delta[2]) > 0 else "",
                     "pr3_cemented_inc"     : count_cemented_delta[2][1] if len(count_cemented_delta) > 2 and len(count_cemented_delta[2]) > 1 else "",
                     "pr3_e_hint"           : election_delta[2][3] if len(election_delta) > 2 and len(election_delta[2]) > 3 else "", 
                     "overlap_1_2_abs"      : oberlap_pr["0_1"]["abs"]  if "0_1" in oberlap_pr and "abs" in oberlap_pr["0_1"] else "",
                     "overlap_1_3_abs"      : oberlap_pr["0_2"]["abs"] if "0_2" in oberlap_pr and "abs" in oberlap_pr["0_2"] else "",
                     "overlap_2_3_abs"      : oberlap_pr["1_2"]["abs"] if "1_2" in oberlap_pr and "abs" in oberlap_pr["1_2"] else "",
                     "overlap_1_2_perc"     : "1_2  " +str(oberlap_pr["0_1"]["perc"]) + "%" if "0_1" in oberlap_pr and "perc" in oberlap_pr["0_1"] else "",
                     "overlap_1_3_perc"     : "1_3  " +str(oberlap_pr["0_2"]["perc"]) + "%" if "0_2" in oberlap_pr and "perc" in oberlap_pr["0_2"] else "",
                     "overlap_2_3_perc"     : "2_3  " +str(oberlap_pr["1_2"]["perc"]) + "%" if "1_2" in oberlap_pr and "perc" in oberlap_pr["1_2"] else "",
                     "pr1"                  : "PR1",
                     "pr2"                  : "PR2",
                     "pr3"                  : "PR3",
                     "aec_uncon_1"          : aecs_detail[0]["unconfirmed"] if len(aecs_detail) > 0 else "",
                     "aec_uncon_2"          : aecs_detail[1]["unconfirmed"] if len(aecs_detail) > 1 else "",
                     "aec_uncon_3"          : aecs_detail[2]["unconfirmed"] if len(aecs_detail) > 2 else "",
                     "bc_pr1"               : bcs[0]["count"].ljust(10) if len(bcs) > 0 and "count" in bcs[0] else " "*10,
                     "bc_pr2"               : bcs[1]["count"].ljust(10) if len(bcs) > 1 and "count" in bcs[1] else " "*10,
                     "bc_pr3"               : bcs[2]["count"].ljust(10) if len(bcs) > 2 and "count" in bcs[2] else " "*10,
                     "cem_perc_pr1"         : round(int(bcs[0]["cemented"]) / int(bcs[0]["count"]) *100,2) if len(bcs) > 0 and "count" in bcs[0] and "cemented" in bcs[0] else "",
                     "cem_perc_pr2"         : round(int(bcs[1]["cemented"]) / int(bcs[1]["count"]) *100,2) if len(bcs) > 1 and "count" in bcs[1] and "cemented" in bcs[1] else "",
                     "cem_perc_pr3"         : round(int(bcs[2]["cemented"]) / int(bcs[2]["count"]) *100,2) if len(bcs) > 2 and "count" in bcs[2] and "cemented" in bcs[2] else "",
                     "sync_pr1_c"           : round(int(bcs[0]["count"])/max([int(x["count"]) for x in bcs]) *100,2) if len(bcs) > 0 and "count" in bcs[0] else "",
                     "sync_pr2_c"           : round(int(bcs[1]["count"])/max([int(x["count"]) for x in bcs]) *100,2) if len(bcs) > 1 and "count" in bcs[1] else "",
                     "sync_pr3_c"           : round(int(bcs[2]["count"])/max([int(x["count"]) for x in bcs]) *100,2) if len(bcs) > 2 and "count" in bcs[2] else "",
                     "sync_cem_pr1"         : round(max([int(x["cemented"]) for x in bcs]) -int(bcs[0]["cemented"]),2) if len(bcs) > 0 and "cemented" in bcs[0] else "",
                     "sync_cem_pr2"         : round(max([int(x["cemented"]) for x in bcs]) -int(bcs[1]["cemented"]),2) if len(bcs) > 1 and "cemented" in bcs[1] else "",
                     "sync_cem_pr3"         : round(max([int(x["cemented"]) for x in bcs]) -int(bcs[2]["cemented"]),2) if len(bcs) > 2 and "cemented" in bcs[2] else "",
                     "example_hash"         : example_hash 
                     }
            
            
            self.print_to_console(data, format, print_header_inc, repeat_header)
            
            
            previous_aecs = aecs
            previous_bcs = bcs
            previous_stats = stats
            time.sleep(every_s)                      
        
         
  
def main():
    s = NanoStats()
    s.compare_active_elections(every_s = 5, repeat_header = 10, format = "table_per_pr")


if __name__ == "__main__":       
    main()
