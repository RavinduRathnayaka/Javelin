# Javelin: Automated penetration testing tool

In the ever-changing landscape of cyberspace, securing digital assets has become a 
top priority for both businesses and individuals. Cybersecurity experts must stay one 
step ahead of cyber criminals as they employ increasingly sophisticated techniques to 
exploit vulnerabilities.     
Enter the world of automated penetration testing, a novel approach that combines the 
capabilities of cutting-edge artificial intelligence with the knowledge of cybersecurity 
experts. In this new era of cyber defence, these digital fortresses not only fortify 
themselves but also dynamically adapt to the onslaught of threats, ensuring robust 
testing and vulnerability assessment generating. Here it is discussed how manual 
penetration testing can be improved using automation to save time and effort while 
maximizing the quality of the vulnerability assessment. The output of the automation 
will take time, and to improve the accuracy of the result without human errors, 
automation will take a lot of time because of the large variety of vulnerability 
assessment techniques. To improve the efficiency of automation, this is where artificial 
intelligence comes in and makes automation more effective.    
     
**KEYWORDS**: _cybersecurity, exploit, vulnerabilities, automated penetration testing, 
automation, artificial intelligence_

# User Guide
## step 0 : 
### open a terminal as sudo and enter following commands
open a terminal
```
sudo su
```
## step 1 : 
### install pip3(python3-pip
```apt-get install python3-pip```
## step 2 : 
### install python libraries
```
pip install beautifulsoup4
```
```
pip install docopt
```
```
pip install jinja2
```
```
pip install Keras
```
```
pip install matplotlib
```
```
pip install msgpack-python
```
```
pip install numpy
```
```
pip install pandas
```
```
pip install Scrapy
```
```
pip install tensorflow
```
```
pip install urllib3
```
```
pip install protobuf
```
## step 3 : 
### insert the host details in to config.ini
```
server_host : 192.168.12
server_port : 55553
msgrpc_user : admin
msgrpc_pass : admin
```
## step 4 : 
### start Metasploit framework database
```
msfdb init
```
## step 5 : 
### run msfconsole
```
msfconsole
```
## step 6 : 
### configure RPC server according to config.ini
```
load msgrpc ServerHost=192.168.220.144 ServerPort=55553 User=admin Pass=admin
```
## step 7 : 
### run the python file using following command
```
python3 ./javelin.py <source_ip> -m <mode>
```
>	ex: python3 ./javelin.py 192.168.1.3 -m test



# Acknowledgement
I wish to express my deepest gratitude to my project supervisor, Mr. Chamindra 
Attanayake, for their invaluable guidance, patience, and unwavering support 
throughout this project. Their depth of knowledge and practical insights were 
instrumental in the successful completion of this work.   
    
I am also thankful to all the faculty members in the faculty of computing at NSBM 
green university and the University of Plymouth for their help and support. Their 
teachings and encouragement provided the foundation for this project.
I would like to thank the Open Worldwide Application Security Project (OWASP), the 
services of which were pivotal in gathering data and conducting experiments that 
were crucial to this project.   
    
I would also like to acknowledge my peers for their camaraderie, constructive 
criticism, and intellectual discussions which helped shape this project.
Lastly, my heartfelt appreciation goes to my family and friends, whose constant 
encouragement and moral support were invaluable. Their belief in my capabilities 
inspired me to push my boundaries and strive for excellence.
