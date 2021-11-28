docker ps -a | grep nano_local_ | awk '{system("docker stop "$(NF)" && docker rm "$(NF))}' 
rm -rf nano_local
rm -rf reps
rm -rf output
rm -rf __pycache__
rm docker-compose.yml