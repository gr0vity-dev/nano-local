#!/bin/sh

#Script to create and delete a virtualenv to keep dependencies separate from other projects 
# ./venv_nano_local.sh create 
 # ./venv_nano_local.sh delete

action=$1

if [ "$action" = "create" ]; 
then
    pip3 install virtualenv --quiet
    python3 -m venv venv_nano_local
    . venv_nano_local/bin/activate

    pip3 install -r ./config/requirements.txt --quiet

    echo "A new virstaul environment was created. "
    echo "To enter the virtal environment run"
    echo "   $ source venv_nano_local/bin/activate"
    echo ""
    echo "To exit the virtual environemnt run"
    echo "   $ deactivate"

    return 0

elif [ "$action" = "delete" ];
then 
    . venv_nano_local/bin/activate
    deactivate    
    rm -rf venv_nano_local

else
     echo "run ./venv_nano_local.sh create "
     echo "or"
     echo "run ./venv_nano_local.sh delete "
fi


