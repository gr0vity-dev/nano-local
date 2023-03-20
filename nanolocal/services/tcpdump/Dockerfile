FROM ubuntu 
RUN apt-get update && apt-get install -y tcpdump 
CMD tcpdump -U -i any -s 0 -w nano-local.pcap port 17075