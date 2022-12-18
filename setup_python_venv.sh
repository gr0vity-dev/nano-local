#!/bin/sh

#Script to create and delete a virtualenv to keep dependencies separate from other projects 
# ./venv_nanolocal.sh create 
 # ./venv_nanolocal.sh delete

action=$1

if [ "$action" = "" ]; 
then
    rm -rf venv_nanolocal
    python3 -m venv venv_nanolocal
    . venv_nanolocal/bin/activate

    ./venv_nanolocal/bin/pip3 install wheel
    ./venv_nanolocal/bin/pip3 install -r ./requirements.txt --quiet

    echo "A new virstaul environment was created. "


elif [ "$action" = "delete" ];
then 
    . venv_nanolocal/bin/activate
    deactivate    
    rm -rf venv_nanolocal

else
     echo "run ./setup_python_venv.sh  to create a virtual python environment"
     echo "or"
     echo "run ./setup_python_venv.sh delete  to delete the virstual python environment"
fi


