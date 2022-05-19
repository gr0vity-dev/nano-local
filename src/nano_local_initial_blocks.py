from src.nano_rpc import Api
from src.parse_nano_local_config import ConfigParser
import logging
import time



class InitialBlocks :

    def __init__(self, rpc_url="http://localhost:45000"):   
        self.api = Api(rpc_url)
        self.config = ConfigParser().config_dict
        self.__append_config()

    def __append_config(self):           
            
        self.config["burn_account_data"] = {"account" : "nano_1111111111111111111111111111111111111111111111111111hifc8npp"}

        self.config["genesis_account_data"] = self.api.key_expand(self.config["genesis_key"])
        self.config["canary_account_data"] = self.api.key_expand(self.config["canary_key"])

        self.config["node_account_data"] = []
        for node in self.config["representatives"]["nodes"]:
            if "seed" not in node :
                node["seed"] = self.api.generate_new_seed()["seed"]
            
            if "key" in node :
                account_data = self.api.key_expand(node["key"])
            else:
                account_data = self.api.get_account_data(node["seed"], 0)
            if "balance" in node :
                account_data["balance"] = node["balance"]
            if "vote_weight_percent" in node :
                account_data["vote_weight_percent"] = node["vote_weight_percent"]
            
            node["account"] = account_data["account"]
            self.config["node_account_data"].append(account_data)  
            # "seed": seed,
            # "index": index,
            # "private": account_data["private"],
            # "public": account_data["public"],
            # "account": account_data["account"],    
    

    def __epoch_link(self, epoch: int):
        message = f"epoch v{epoch} block"
        as_hex = bytearray(message, "ascii").hex()
        link = as_hex.upper().ljust(64, '0')
        return link
 

    def __publish_epochs(self):
        e = 1        
        self.__log_active_difficulty()
        while e <= self.config["epoch_count"]:
            link = self.__epoch_link(e)
            epoch_block = self.api.create_epoch_block(
                link,
                self.config["genesis_account_data"]["private"],
                self.config["genesis_account_data"]["account"]
                )
            logging.info("EPOCH {} sent by genesis : HASH {}".format(e, epoch_block["hash"]))
            self.__log_active_difficulty()
            e += 1
        pass

    def __log_active_difficulty(self):
        diff = self.api.get_active_difficulty()
        logging.info(f'current_diff : [{diff["network_current"]}]  current_receive_diff: [{diff["network_receive_current"]}]' )

    def __publish_canary(self):
        fv_canary_send_block = self.api.create_send_block_pkey( self.config["genesis_account_data"]["private"],
                                                                self.config["genesis_account_data"]["account"],
                                                                self.config["canary_account_data"]["account"],
                                                                1)
        logging.info("SEND FINAL VOTES CANARY BLOCK FROM {} To {} : HASH {}".format(self.config["genesis_account_data"]["account"],
                                                                                    self.config["canary_account_data"]["account"],
                                                                                    fv_canary_send_block["hash"] ))
        
        fv_canary_open_block = self.api.create_open_block(self.config["canary_account_data"]["account"],
                                                          self.config["canary_account_data"]["private"],
                                                          1,
                                                          self.config["genesis_account_data"]["account"],
                                                          fv_canary_send_block["hash"]
                                                          )
        logging.info("OPENED CANARY ACCOUNT {} : HASH {}".format(self.config["canary_account_data"]["account"],fv_canary_open_block["hash"] ))
        

    def __send_to_burn(self):
        if "burn_amount" not in self.config :
            logging.debug("[burn_amount] is not set. exit send_to_burn()")
            return False

        genesis_balance = int(self.api.check_balance(self.config["genesis_account_data"]["account"])["balance_raw"]) 
        if int(self.config["burn_amount"]) > genesis_balance:
            logging.warning("[burn_amount] exceeds genesis balance. exit send_to_burn()")
            return False               
       
        send_block = self.api.create_send_block_pkey(self.config["genesis_account_data"]["private"],
                                                     self.config["genesis_account_data"]["account"],
                                                     self.config["burn_account_data"]["account"],
                                                     self.config["burn_amount"])
        
        logging.info("SENT {:>40} FROM {} To {} : HASH {}".format( send_block["amount_raw"],
                                                            self.config["genesis_account_data"]["account"],
                                                            self.config["burn_account_data"]["account"],
                                                            send_block["hash"] ))
         

    def __send_vote_weigh(self):

        #Convert from vote_weigh_% into balance
        genesis_balance = int(self.api.check_balance(self.config["genesis_account_data"]["account"], include_only_confirmed = False)["balance_raw"])
        for node_account_data in self.config["node_account_data"]:
            if "vote_weight_percent" in node_account_data :
                node_account_data["balance"] = int(genesis_balance * node_account_data["vote_weight_percent"] * 0.01)

        for node_account_data in self.config["node_account_data"]: 
                if "balance" not in node_account_data : continue #skip genesis that was added as node              
                
                send_block = self.api.create_send_block_pkey(self.config["genesis_account_data"]["private"],
                                                             self.config["genesis_account_data"]["account"],
                                                             node_account_data["account"],
                                                             node_account_data["balance"])

                logging.info("SENT {:>40} FROM {} To {} : HASH {}".format(send_block["amount_raw"],
                                                                      self.config["genesis_account_data"]["account"],
                                                                      node_account_data["account"],
                                                                      send_block["hash"] ))
                
                open_block = self.api.create_open_block(node_account_data["account"],
                                    node_account_data["private"],
                                    node_account_data["balance"],
                                    node_account_data["account"],
                                    send_block["hash"]
                                    )
                logging.info("OPENED PR ACCOUNT {} : HASH {}".format(node_account_data["account"],open_block["hash"] ))    
        
   
    def create_node_wallet(self, rpc_url, node_name, private_key = None, seed = None): 
        api = Api(rpc_url)        
        
        if private_key != None:
            wallet = api.wallet_create(None)["wallet"]  
            account = api.wallet_add(wallet, private_key)["account"]            
        if seed != None : 
            wallet = api.wallet_create(seed)["wallet"] 
            account = api.get_account_data(seed,0)["account"]    
        logging.info(f"WALLET {wallet} CREATED FOR {node_name} WITH ACCOUNT {account}")
        
    
    def publish_initial_blocks(self):
        self.__publish_epochs()
        self.__publish_canary()
        self.__send_to_burn()
        self.__send_vote_weigh()
