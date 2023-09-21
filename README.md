#User Guide
##step 1 : open a terminal as sudo and enter following commands
•	open a terminal
•	enter ‘sudo su’
##step 1 : install pip3(python3-pip
•	sudo su
•	apt-get install python3-pip
##step 2 : install python libraries
•	pip install beautifulsoup4
•	pip install docopt
•	pip install jinja2
•	pip install Keras
•	pip install matplotlib
•	pip install msgpack-python
•	pip install numpy
•	pip install pandas
•	pip install Scrapy
•	pip install tensorflow
•	pip install urllib3
•	pip install protobuf
##step 3 : insert the host details in to config.ini
•	server_host : 192.168.12
•	server_port : 55553
•	msgrpc_user : admin
•	msgrpc_pass : admin
##step 4 : start Metasploit framework database
•	msfdb init
##step 5 : run msfconsole
•	msfconsole
##step 6 : configure RPC server according to config.ini
•	load msgrpc ServerHost=192.168.220.144 ServerPort=55553 User=admin Pass=admin
##step 7 : run the python file using following command
•	python3 ./javelin.py <source_ip> -m <mode>
•	ex: python3 ./javelin.py 192.168.1.3 -m test
