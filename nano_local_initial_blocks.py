
from nano_rpc import Api
from config.parse_nano_local_config import get_config_variables
import logging



class InitialBlocks :

    def __init__(self, rpc_url="http://localhost:45000"):   
        self.api = Api(rpc_url)
        self.config = get_config_variables()
        self.append_config()


    def append_config(self):    
        self.config["burn_account_data"] = {"account" : "nano_1111111111111111111111111111111111111111111111111111hifc8npp"}

        self.config["genesis_account_data"] = self.api.key_expand(self.config["genesis_key"])
        self.config["canary_account_data"] = self.api.key_expand(self.config["canary_key"])

        self.config["node_account_data"] = []
        for node in self.config["representatives"]["nodes"]:
            if "seed" not in node :
                node["seed"] = self.api.generate_new_seed()["seed"]
            
            account_data = self.api.get_account_data(node["seed"], 0)
            if "balance" in node :
                account_data["balance"] = node["balance"]
            if "vote_weight_percent" in node :
                account_data["vote_weight_percent"] = node["vote_weight_percent"]

            self.config["node_account_data"].append(account_data)  
            # "seed": seed,
            # "index": index,
            # "private": account_data["private"],
            # "public": account_data["public"],
            # "account": account_data["account"],
    



    def epoch_link(self, epoch: int):
        message = f"epoch v{epoch} block"
        as_hex = bytearray(message, "ascii").hex()
        link = as_hex.upper().ljust(64, '0')
        return link
 

    def publish_epochs(self):
        e = 1
        while e <= self.config["epoch_count"]:
            link = self.epoch_link(e)
            epoch_block = self.api.create_epoch_block(
                link,
                self.config["genesis_account_data"]["private"],
                self.config["genesis_account_data"]["account"]
                )
            logging.info("EPOCH {} sent by genesis : HASH {}".format(e, epoch_block["hash"]))
            e += 1
        pass

    def publish_canary(self):
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
        

    def send_to_burn(self):
        if "burn_amount" not in self.config :
            logging.debug("[burn_amount] is not set. exit send_to_burn()")
            return False

        genesis_balance = int(self.api.check_balance(self.config["genesis_account_data"]["account"])["balance_raw"]) 
        if int(self.config["burn_amount"]) > genesis_balance:
            logging.warn("[burn_amount] exceeds genesis balance. exit send_to_burn()")
            return False               
       
        send_block = self.api.create_send_block_pkey(self.config["genesis_account_data"]["private"],
                                                     self.config["genesis_account_data"]["account"],
                                                     self.config["burn_account_data"]["account"],
                                                     self.config["burn_amount"])
        
        logging.info("SEND FROM {} To {} : HASH {}".format( self.config["genesis_account_data"]["account"],
                                                            self.config["burn_account_data"]["account"],
                                                            send_block["hash"] ))
         

    def send_vote_weigh(self):

        #Convert from vote_weigh_% into balance
        genesis_balance = int(self.api.check_balance(self.config["genesis_account_data"]["account"])["balance_raw"])
        for node_account_data in self.config["node_account_data"]:
            if "vote_weight_percent" in node_account_data :
                node_account_data["balance"] = int(genesis_balance * node_account_data["vote_weight_percent"] * 0.01)

        for node_account_data in self.config["node_account_data"]:               
                
                send_block = self.api.create_send_block_pkey(self.config["genesis_account_data"]["private"],
                                                             self.config["genesis_account_data"]["account"],
                                                             node_account_data["account"],
                                                             node_account_data["balance"])
                logging.info("SEND FROM {} To {} : HASH {}".format(self.config["genesis_account_data"]["account"],
                                                                                node_account_data["account"],
                                                                                send_block["hash"] ))
                
                open_block = self.api.create_open_block(node_account_data["account"],
                                    node_account_data["private"],
                                    node_account_data["balance"],
                                    node_account_data["account"],
                                    send_block["hash"]
                                    )
                logging.info("OPENED PR ACCOUNT {} : HASH {}".format(node_account_data["account"],open_block["hash"] ))    
        

    def publish_initial_blocks(self):
        self.publish_epochs()
        self.publish_canary()
        self.send_to_burn()
        self.send_vote_weigh()