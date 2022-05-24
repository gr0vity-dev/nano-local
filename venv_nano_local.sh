#!/bin/sh

#Script to create and delete a virtualenv to keep dependencies separate from other projects 
# ./venv_nano_local.sh create 
 # ./venv_nano_local.sh delete

action=$1

if [ "$action" = "" ]; 
then
    pip3 install virtualenv --quiet
    python3 -m venv venv_nano_local
    . venv_nano_local/bin/activate

    pip3 install wheel
    pip3 install -r ./config/requirements.txt --quiet

    echo "A new virstaul environment was created. "
    echo "Quickstart to your nano-local network:"
    echo "   $ ./run_nano_local.py csi"
    
elif [ "$action" = "delete" ];
then 
    . venv_nano_local/bin/activate
    deactivate    
    rm -rf venv_nano_local

else
     echo "run ./venv_nano_local.sh  to create a virtual python environment"
     echo "or"
     echo "run ./venv_nano_local.sh delete  to delete the virstual python environment"
fi


